"""Code cave: give slot 1 a memory card named after the serial of the game, shared by all discs of the game.

The same logic as the PS1 emulator patch. 0x12a528(slot, 0, path, ...) receives the card path as `r5` and copies it into
the emulator's card object. The hook at its first instruction runs this cave. When the slot is 0 (memory card 1), `r4` is
0 and `r5` starts with `/savedata/vmc/` (the shared card of ISO games; PS2 Classics use another layout and are left
alone), the cave

  1. reads `/tmp/cfg.bin`, which Cobra fills with the path of the ISO it mounted (one byte, then the path), using the
     emulator's own file calls (the ones it makes for /tmp/game/ps2bootparam.dat):
         0x1ecc5c(0, path) -> fd (negative on failure)   0x1ed5cc(fd, offset, buffer, size) -> bytes read
         0x1ecb10(fd)      -> close
  2. for a disc named `(Disc N)` or `[Disc N]` with N from 2 to 9, tries the image with the same name and `1`: every disc
     of a game then uses the card of disc 1. Without that file (or for any other name) the image itself is used;
  3. reads the ISO9660 volume descriptor (sector 16, 2048 byte sectors), the root directory and `SYSTEM.CNF`, takes the
     executable after `BOOT2 = cdrom0:\\` (`SLUS_213.45`) and turns it into the serial `SLUS-21345` (upper case, `_` to
     `-`, `.` dropped);
  4. points `r5` at `/savedata/vmc/SLUS-21345.VM2`.

Whatever is not understood (no file, other layout, no BOOT2 line, other slot) leaves `r5` as it was. The cave keeps
r3..r10 and LR, redoes the displaced stock instruction (`mfcr r12`) and ends at 0x12a52c. It uses a 2.8 KB stack frame
for the sector and the two image paths.
"""
from __future__ import annotations

from ppcasm import assemble

HOOK_VA, HOOK_STOCK = 0x12A528, 0x7D800026  # mfcr r12
RESUME = 0x12A52C
OPEN, READ, CLOSE = 0x1ECC5C, 0x1ED5CC, 0x1ECB10
PREFIX = b"/savedata/vmc/"
SUFFIX = b".VM2"
CFG_PATH = b"/tmp/cfg.bin"
SECTOR = 2048
FRAME = 0x500  # small: a first version with a 2.8 KB frame and 2 KB reads took the console down
S_FD, S_N, S_OFF, S_POS, S_LEN, S_REC = 0xB0, 0xB8, 0xC0, 0xC8, 0xD0, 0xD8
S_BUF, BUF_SIZE = 0xE0, 0x400  # one buffer for every read
ALIGN = 0x200  # every read of the image starts at a multiple of this and has a size that is a multiple of it
CFG_READ = 0x100  # the read of /tmp/cfg.bin that is known to work
PATH_SIZE = 128
CONSTS = b"CD001".ljust(6, b"\0") + b"BOOT2".ljust(6, b"\0") + b"SYSTEM.CNF".ljust(12, b"\0") + b"Disc ".ljust(8, b"\0")  # +0, +6, +12, +24
C_CD001, C_BOOT2, C_CNF, C_DISC = 0, 6, 12, 24
DATA_SIZE = 16 + PATH_SIZE + len(CONSTS)
MAX_SERIAL, MIN_SERIAL = 16, 4


def serial_from_cnf(text: bytes) -> str:
    """The serial of a SYSTEM.CNF text, or '' (reference for the cave)."""
    i = text.find(b"BOOT2")
    if i < 0:
        return ""
    j = text.find(b":", i + 5)
    if j < 0:
        return ""
    k = j + 1
    while k < len(text) and text[k] in b"\\/":
        k += 1
    out = []
    while k < len(text) and text[k] not in b";" and text[k] > 0x20 and len(out) < MAX_SERIAL:
        c = chr(text[k])
        k += 1
        if c == ".":
            continue
        out.append("-" if c == "_" else c.upper())
    return "".join(out) if len(out) >= MIN_SERIAL else ""


def disc_one(iso_path: str) -> str | None:
    """The path of disc 1 for a disc 2..9 image, or None (reference for the cave)."""
    for open_, close in (("(", ")"), ("[", "]")):
        i = iso_path.find(f"{open_}Disc ")
        if i >= 0 and i + 6 < len(iso_path) and iso_path[i + 6] in "23456789":
            return iso_path[:i + 6] + "1" + iso_path[i + 7:]
    return None


def build(cave_va: int, debug: bool = False, stop_after: str | None = None) -> tuple[list[tuple[int, int, int, str]], int]:
    """Return the (va, old, new, what) patches and the bytes used from `cave_va`.

    With `debug`, every place where the cave gives up sends slot 1 to the card `DBG_<stage letter>` instead of leaving the
    shared card, so the stage that failed can be read from the card file the game wrote to. (Both debug builds took the console
    down, so it is not used on the console.)

    With `stop_after` ("pvd", "dir" or "cnf") the cave stops once that stage worked and sends slot 1 to
    `/savedata/vmc/PS2_TEST.VM2`; a stage that fails leaves the shared card. Which file the game writes to tells how far the
    cave got, with no marker card.
    """
    cfg_va, path_va, const_va = cave_va, cave_va + 16, cave_va + 16 + PATH_SIZE
    code_va = cave_va + DATA_SIZE

    def const(off: int) -> list[tuple]:
        return [("lis", "r4", (const_va + off) >> 16), ("ori", "r4", "r4", (const_va + off) & 0xFFFF)]

    save = [("std", f"r{n}", 0x70 + 8 * (n - 3), "r1") for n in range(3, 11)]
    load = [("ld", f"r{n}", 0x70 + 8 * (n - 3), "r1") for n in range(3, 11)]
    lines: list[tuple] = [
        ("stdu", "r1", -FRAME, "r1"), ("mflr", "r0"), ("std", "r0", FRAME + 0x10, "r1"), *save,
        ("cmpwi", "r3", 0), ("bne", "restore"), ("cmpdi", "r4", 0), ("bne", "restore"), ("cmpdi", "r5", 0), ("beq", "restore"),
        ("mr", "r3", "r5"), ("lis", "r4", path_va >> 16), ("ori", "r4", "r4", path_va & 0xFFFF), ("li", "r5", len(PREFIX)),
        ("bl", "memeq"), ("cmpwi", "r3", 0), ("beq", "f_Y"),  # the path starts with /savedata/vmc/
        # 1. /tmp/cfg.bin holds the ISO path
        ("li", "r3", 0), ("lis", "r4", cfg_va >> 16), ("ori", "r4", "r4", cfg_va & 0xFFFF), ("bl", OPEN),
        ("cmpwi", "r3", 0), ("blt", "f_A"), ("std", "r3", S_FD, "r1"),
        ("li", "r4", 0), ("addi", "r5", "r1", S_BUF), ("li", "r6", CFG_READ), ("bl", READ), ("std", "r3", S_N, "r1"),
        ("ld", "r3", S_FD, "r1"), ("bl", CLOSE), ("ld", "r3", S_N, "r1"), ("cmpwi", "r3", 1), ("blt", "f_B"),
        ("addi", "r11", "r1", S_BUF), ("li", "r0", 0), ("stb", "r0", CFG_READ - 1, "r11"), ("mr", "r4", "r11"), ("li", "r6", 0),
        ("label", "first"),  # the first '/' within the first four bytes
        ("lbz", "r0", 0, "r4"), ("cmpwi", "r0", 0x2F), ("beq", "have"), ("cmpwi", "r0", 0), ("beq", "f_C"),
        ("addi", "r4", "r4", 1), ("addi", "r6", "r6", 1), ("cmpwi", "r6", 4), ("blt", "first"), ("b", "f_C"),
        ("label", "have"),  # 2. open the image (its path is still in the buffer)
        ("li", "r3", 0), ("bl", OPEN), ("cmpwi", "r3", 0), ("blt", "f_D"), ("std", "r3", S_FD, "r1"),
        # 3. volume descriptor: 512 bytes at 0x8000
        ("ld", "r3", S_FD, "r1"), ("li", "r4", 0), ("ori", "r4", "r4", 0x8000), ("addi", "r5", "r1", S_BUF), ("li", "r6", ALIGN),
        ("bl", READ), ("cmpwi", "r3", ALIGN), ("bne", "f_E"),
        ("addi", "r3", "r1", S_BUF + 1), *const(C_CD001), ("li", "r5", 5), ("bl", "memeq"), ("cmpwi", "r3", 0), ("beq", "f_E"),
        *([("b", "probe_close")] if stop_after == "pvd" else []),
        ("addi", "r11", "r1", S_BUF), ("li", "r12", 158), ("lwbrx", "r6", "r11", "r12"), ("mulli", "r6", "r6", SECTOR),
        ("std", "r6", S_OFF, "r1"), ("li", "r12", 166), ("lwbrx", "r7", "r11", "r12"), ("cmpwi", "r7", SECTOR), ("ble", "lenok"),
        ("li", "r7", SECTOR),
        ("label", "lenok"), ("std", "r7", S_LEN, "r1"), ("li", "r0", 0), ("std", "r0", S_POS, "r1"),
        ("label", "dir"),  # 4. the root directory: one aligned 1 KB window per record
        ("ld", "r9", S_POS, "r1"), ("ld", "r7", S_LEN, "r1"), ("cmpw", "r9", "r7"), ("bge", "f_G"),
        ("rlwinm", "r10", "r9", 0, 0, 22), ("ld", "r6", S_OFF, "r1"), ("add", "r4", "r6", "r10"),
        ("ld", "r3", S_FD, "r1"), ("addi", "r5", "r1", S_BUF), ("li", "r6", BUF_SIZE), ("bl", READ), ("cmpwi", "r3", ALIGN),
        ("blt", "f_F"),
        ("ld", "r9", S_POS, "r1"), ("rlwinm", "r10", "r9", 0, 23, 31), ("addi", "r8", "r1", S_BUF), ("add", "r8", "r8", "r10"),
        ("std", "r8", S_REC, "r1"), ("lbz", "r0", 0, "r8"), ("cmpwi", "r0", 0), ("beq", "nextsector"),
        ("lbz", "r11", 32, "r8"), ("cmpwi", "r11", 10), ("blt", "nextrec"),
        ("addi", "r3", "r8", 33), *const(C_CNF), ("li", "r5", 10), ("bl", "memeq"), ("cmpwi", "r3", 0), ("bne", "found"),
        ("label", "nextrec"), ("ld", "r8", S_REC, "r1"), ("lbz", "r0", 0, "r8"), ("ld", "r9", S_POS, "r1"),
        ("add", "r9", "r9", "r0"), ("std", "r9", S_POS, "r1"), ("b", "dir"),
        ("label", "nextsector"),  # the rest of this sector is padding
        ("ld", "r9", S_POS, "r1"), ("ori", "r9", "r9", 0x7FF), ("addi", "r9", "r9", 1), ("std", "r9", S_POS, "r1"), ("b", "dir"),
        ("label", "found"),  # 5. SYSTEM.CNF: 512 bytes at its sector
        *([("b", "probe_close")] if stop_after == "dir" else []),
        ("ld", "r8", S_REC, "r1"), ("li", "r12", 2), ("lwbrx", "r6", "r8", "r12"), ("mulli", "r4", "r6", SECTOR),
        ("ld", "r3", S_FD, "r1"), ("addi", "r5", "r1", S_BUF), ("li", "r6", ALIGN), ("bl", READ),
        ("std", "r3", S_N, "r1"), ("ld", "r3", S_FD, "r1"), ("bl", CLOSE),
        ("ld", "r10", S_N, "r1"), ("cmpwi", "r10", 1), ("blt", "f_H"),
        *([("b", "probe_ok")] if stop_after == "cnf" else []),
        # 6. BOOT2 = cdrom0:\SLUS_213.45;1  ->  SLUS-21345
        ("addi", "r8", "r1", S_BUF), ("li", "r6", 0),
        ("label", "boot"),
        ("addi", "r7", "r6", 5), ("cmpw", "r7", "r10"), ("bgt", "f_I"), ("add", "r3", "r8", "r6"), *const(C_BOOT2),
        ("li", "r5", 5), ("bl", "memeq"), ("cmpwi", "r3", 0), ("bne", "colon0"), ("addi", "r6", "r6", 1), ("b", "boot"),
        ("label", "colon0"), ("addi", "r6", "r6", 5),
        ("label", "colon"),
        ("cmpw", "r6", "r10"), ("bge", "f_I"), ("add", "r7", "r8", "r6"), ("lbz", "r0", 0, "r7"), ("addi", "r6", "r6", 1),
        ("cmpwi", "r0", 0x3A), ("bne", "colon"),
        ("label", "skip"),
        ("cmpw", "r6", "r10"), ("bge", "f_I"), ("add", "r7", "r8", "r6"), ("lbz", "r0", 0, "r7"),
        ("cmpwi", "r0", 0x5C), ("beq", "skipnext"), ("cmpwi", "r0", 0x2F), ("bne", "name"),
        ("label", "skipnext"), ("addi", "r6", "r6", 1), ("b", "skip"),
        ("label", "name"),
        ("lis", "r9", (path_va + len(PREFIX)) >> 16), ("ori", "r9", "r9", (path_va + len(PREFIX)) & 0xFFFF), ("li", "r11", 0),
        ("label", "cp"),
        ("cmpw", "r6", "r10"), ("bge", "fin"), ("add", "r7", "r8", "r6"), ("lbz", "r0", 0, "r7"),
        ("cmpwi", "r0", 0x3B), ("beq", "fin"), ("cmpwi", "r0", 0x21), ("blt", "fin"),
        ("cmpwi", "r0", 0x2E), ("beq", "skipchar"),
        ("cmpwi", "r0", 0x5F), ("bne", "notus"), ("li", "r0", 0x2D),
        ("label", "notus"),
        ("cmpwi", "r0", 0x61), ("blt", "keep"), ("cmpwi", "r0", 0x7A), ("bgt", "keep"),
        ("mr", "r7", "r0"), ("addi", "r0", "r7", -0x20),
        ("label", "keep"),
        ("stb", "r0", 0, "r9"), ("addi", "r9", "r9", 1), ("addi", "r11", "r11", 1), ("cmpwi", "r11", MAX_SERIAL), ("bge", "fin"),
        ("label", "skipchar"), ("addi", "r6", "r6", 1), ("b", "cp"),
        ("label", "fin"), ("cmpwi", "r11", MIN_SERIAL), ("blt", "f_I"),
    ]
    for i, c in enumerate(SUFFIX + b"\0"):
        lines += [("li", "r0", c), ("stb", "r0", i, "r9")]
    lines += [("lis", "r5", path_va >> 16), ("ori", "r5", "r5", path_va & 0xFFFF), ("std", "r5", 0x80, "r1"), ("b", "restore")]
    for code in "ABCDHIY":  # where the cave gives up with nothing open: leave the shared card, or mark the stage
        lines += [("label", f"f_{code}")] + ([("li", "r0", ord(code)), ("b", "dbg")] if debug else [("b", "restore")])
    for code in "EFG":  # the image is open: close it first
        lines += [("label", f"f_{code}")] + ([("li", "r0", ord(code)), ("b", "cdbg")] if debug else [("b", "closefail")])
    lines += [("label", "closefail"), ("ld", "r3", S_FD, "r1"), ("bl", CLOSE), ("b", "restore")]
    if debug:
        lines += [("label", "cdbg"), ("std", "r0", S_N, "r1"), ("ld", "r3", S_FD, "r1"), ("bl", CLOSE), ("ld", "r0", S_N, "r1"),
                  ("label", "dbg"), ("lis", "r9", (path_va + len(PREFIX)) >> 16), ("ori", "r9", "r9", (path_va + len(PREFIX)) & 0xFFFF)]
        for i, c in enumerate(b"DBG_"):
            lines += [("li", "r11", c), ("stb", "r11", i, "r9")]
        lines += [("stb", "r0", 4, "r9")]
        for i, c in enumerate(SUFFIX + b"\0"):
            lines += [("li", "r11", c), ("stb", "r11", 5 + i, "r9")]
        lines += [("lis", "r5", path_va >> 16), ("ori", "r5", "r5", path_va & 0xFFFF), ("std", "r5", 0x80, "r1"), ("b", "restore")]
    if stop_after:
        lines += [("label", "probe_close"), ("ld", "r3", S_FD, "r1"), ("bl", CLOSE),
                  ("label", "probe_ok"), ("lis", "r9", (path_va + len(PREFIX)) >> 16),
                  ("ori", "r9", "r9", (path_va + len(PREFIX)) & 0xFFFF)]
        for i, c in enumerate(b"PS2_TEST.VM2\0"):
            lines += [("li", "r0", c), ("stb", "r0", i, "r9")]
        lines += [("lis", "r5", path_va >> 16), ("ori", "r5", "r5", path_va & 0xFFFF), ("std", "r5", 0x80, "r1"), ("b", "restore")]
    lines += [
        ("label", "restore"), *load, ("ld", "r0", FRAME + 0x10, "r1"), ("addi", "r1", "r1", FRAME), ("mtlr", "r0"),
        ("mfcr", "r12"), ("b", RESUME),
        ("label", "memeq"),  # r3 = 1 when the r5 bytes at r3 and r4 are equal, else 0 (clobbers r0, r4, r5, r12)
        ("cmpwi", "r5", 0), ("ble", "eq"), ("lbz", "r0", 0, "r3"), ("lbz", "r12", 0, "r4"), ("cmpw", "r0", "r12"),
        ("bne", "ne"), ("addi", "r3", "r3", 1), ("addi", "r4", "r4", 1), ("addi", "r5", "r5", -1), ("b", "memeq"),
        ("label", "eq"), ("li", "r3", 1), ("blr",), ("label", "ne"), ("li", "r3", 0), ("blr",),
    ]
    words = assemble(code_va, lines)
    data = CFG_PATH.ljust(16, b"\0") + PREFIX.ljust(PATH_SIZE, b"\0") + CONSTS
    assert len(data) == DATA_SIZE
    patches = [(cave_va + i, 0, int.from_bytes(data[i:i + 4], "big"), "card cave data") for i in range(0, len(data), 4)]
    patches += [(code_va + 4 * i, 0, w, "card cave code") for i, w in enumerate(words)]
    patches.append((HOOK_VA, HOOK_STOCK, assemble(HOOK_VA, [("b", code_va)])[0], "jump to the card cave"))
    return patches, DATA_SIZE + 4 * len(words)
