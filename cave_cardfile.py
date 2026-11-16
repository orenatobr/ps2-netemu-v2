"""Code cave: memory card 1 gets a card named after the game, shared by all the discs of the game.

Built only from what the console has already shown to be safe: the redirect of `r5` (a fixed card path worked), and the
emulator's own file calls on /tmp/cfg.bin (a probe that opens, reads 256 bytes and closes it worked). Nothing else reaches
outside the cave: no ISO read, no hook in the disc code.

0x12a528(slot, 0, path, ...) receives the card path as `r5`. When the slot is 0, `r4` is 0 and `r5` starts with
`/savedata/vmc/` (the shared card of ISO games; PS2 Classics use another layout and are left alone) the cave reads
`/tmp/cfg.bin`, which Cobra fills with the path of the mounted ISO (one byte, then the path):

    0x1ecc5c(0, path) -> fd (negative on failure)    0x1ed5cc(fd, offset, buffer, size) -> bytes read
    0x1ecb10(fd)      -> close

and builds `/savedata/vmc/PS2_<name>.VM2` from the file name of the ISO: no folder, no extension, every `(Disc N)` or
`[Disc N]` tag removed with the space before it (so all discs of a game get the same card), and every character that is not a
letter, a digit, `_` or `-` turned into `_` (Grandia III (USA) (Disc 2).iso becomes PS2_Grandia_III__USA_.VM2). The same rule
is `card_name()` (used by the tests and by the installer, which creates the cards). Whatever is not understood leaves `r5`.
"""
from __future__ import annotations

from ppcasm import assemble

HOOK_VA, HOOK_STOCK = 0x12A528, 0x7D800026  # mfcr r12
RESUME = 0x12A52C
OPEN, READ, CLOSE = 0x1ECC5C, 0x1ED5CC, 0x1ECB10
PREFIX = b"/savedata/vmc/"
NAME_PREFIX = b"PS2_"
CFG_PATH = b"/tmp/cfg.bin"
SUFFIX = b".VM2"
FRAME, S_FD, S_N, S_BUF, BUF_SIZE = 0x1D0, 0xB0, 0xB8, 0xC0, 0x100
MAX_NAME = 60
PATH_SIZE = 96
DATA_SIZE = 16 + PATH_SIZE


def sanitize(c: str) -> str:
    """A letter, a digit, '_' or '-' stays; anything else becomes '_'."""
    return c if (c.isascii() and c.isalnum()) or c in "_-" else "_"


def card_name(iso_path: str) -> str:
    """The card name (without the PS2_ prefix and the extension) for an ISO path, or '' (reference for the cave)."""
    base = iso_path.rsplit("/", 1)[-1]
    dot = base.rfind(".")
    if dot > 0 and len(base) - dot <= 5:
        base = base[:dot]
    out: list[str] = []
    i = 0
    while i < len(base):
        c = base[i]
        if c in "([" and base[i + 1:i + 5] in ("Disc", "disc"):
            while i < len(base):
                i += 1
                if base[i - 1] in ")]":
                    break
            if out and out[-1] == " ":
                out.pop()
            continue
        if len(out) >= MAX_NAME:
            break
        out.append(c)
        i += 1
    name = "".join(out).rstrip(" ")
    return "".join(sanitize(c) for c in name)


def card_path(iso_path: str) -> str:
    """The card path for an ISO path ('' when the ISO gives no name)."""
    name = card_name(iso_path)
    return f"/savedata/vmc/PS2_{name}.VM2" if name else ""


def build(cave_va: int) -> tuple[list[tuple[int, int, int, str]], int]:
    """Return the (va, old, new, what) patches and the bytes used from `cave_va`."""
    cfg_va, path_va = cave_va, cave_va + 16
    code_va = cave_va + DATA_SIZE
    save = [("std", f"r{n}", 0x70 + 8 * (n - 3), "r1") for n in range(3, 11)]
    load = [("ld", f"r{n}", 0x70 + 8 * (n - 3), "r1") for n in range(3, 11)]
    lines: list[tuple] = [
        ("stdu", "r1", -FRAME, "r1"), ("mflr", "r0"), ("std", "r0", FRAME + 0x10, "r1"), *save,
        ("cmpwi", "r3", 0), ("bne", "restore"), ("cmpdi", "r4", 0), ("bne", "restore"), ("cmpdi", "r5", 0), ("beq", "restore"),
    ]
    for i, c in enumerate(PREFIX):
        lines += [("lbz", "r0", i, "r5"), ("cmpwi", "r0", c), ("bne", "restore")]
    lines += [
        ("li", "r3", 0), ("lis", "r4", cfg_va >> 16), ("ori", "r4", "r4", cfg_va & 0xFFFF), ("bl", OPEN),
        ("cmpwi", "r3", 0), ("blt", "restore"), ("std", "r3", S_FD, "r1"),
        ("li", "r4", 0), ("addi", "r5", "r1", S_BUF), ("li", "r6", BUF_SIZE), ("bl", READ), ("std", "r3", S_N, "r1"),
        ("ld", "r3", S_FD, "r1"), ("bl", CLOSE),
        ("ld", "r3", S_N, "r1"), ("cmpwi", "r3", 1), ("blt", "restore"),
        ("addi", "r11", "r1", S_BUF), ("li", "r0", 0), ("stb", "r0", BUF_SIZE - 1, "r11"), ("mr", "r4", "r11"), ("li", "r6", 0),
        ("label", "first"),  # the first '/' within the first four bytes
        ("lbz", "r0", 0, "r4"), ("cmpwi", "r0", 0x2F), ("beq", "have"), ("cmpwi", "r0", 0), ("beq", "restore"),
        ("addi", "r4", "r4", 1), ("addi", "r6", "r6", 1), ("cmpwi", "r6", 4), ("blt", "first"), ("b", "restore"),
        ("label", "have"), ("mr", "r5", "r4"),
        ("label", "scan"),  # r5 = start of the last path component, r4 = end of the string
        ("lbz", "r0", 0, "r4"), ("cmpwi", "r0", 0), ("beq", "scanned"), ("addi", "r4", "r4", 1), ("cmpwi", "r0", 0x2F),
        ("bne", "scan"), ("mr", "r5", "r4"), ("b", "scan"),
        ("label", "scanned"), ("addi", "r6", "r4", -1),
        ("label", "ext"),  # cut a short extension at the last '.'
        ("cmpw", "r6", "r5"), ("ble", "noext"), ("subf", "r7", "r6", "r4"), ("cmpwi", "r7", 5), ("bgt", "noext"),
        ("lbz", "r0", 0, "r6"), ("cmpwi", "r0", 0x2E), ("beq", "cut"), ("addi", "r6", "r6", -1), ("b", "ext"),
        ("label", "cut"), ("mr", "r4", "r6"),
        ("label", "noext"),
        ("lis", "r9", (path_va + len(PREFIX) + len(NAME_PREFIX)) >> 16),
        ("ori", "r9", "r9", (path_va + len(PREFIX) + len(NAME_PREFIX)) & 0xFFFF), ("li", "r10", 0),
        ("label", "cp"),
        ("cmpw", "r5", "r4"), ("bge", "endcopy"), ("lbz", "r0", 0, "r5"),
        ("cmpwi", "r0", 0x28), ("beq", "tag"), ("cmpwi", "r0", 0x5B), ("bne", "plain"),
        ("label", "tag"),  # '(' or '[' followed by Disc / disc
        ("lbz", "r6", 1, "r5"), ("cmpwi", "r6", 0x44), ("beq", "d1"), ("cmpwi", "r6", 0x64), ("bne", "plain"),
        ("label", "d1"),
        ("lbz", "r6", 2, "r5"), ("cmpwi", "r6", 0x69), ("bne", "plain"), ("lbz", "r6", 3, "r5"), ("cmpwi", "r6", 0x73),
        ("bne", "plain"), ("lbz", "r6", 4, "r5"), ("cmpwi", "r6", 0x63), ("bne", "plain"),
        ("label", "skipt"),
        ("cmpw", "r5", "r4"), ("bge", "tagdone"), ("lbz", "r0", 0, "r5"), ("addi", "r5", "r5", 1),
        ("cmpwi", "r0", 0x29), ("beq", "tagdone"), ("cmpwi", "r0", 0x5D), ("bne", "skipt"),
        ("label", "tagdone"),  # drop the space that came before the tag (it is stored as '_' only after the loop)
        ("cmpwi", "r10", 0), ("ble", "cp"), ("lbz", "r0", -1, "r9"), ("cmpwi", "r0", 0x20), ("bne", "cp"),
        ("addi", "r9", "r9", -1), ("addi", "r10", "r10", -1), ("b", "cp"),
        ("label", "plain"),
        ("cmpwi", "r10", MAX_NAME), ("bge", "endcopy"), ("stb", "r0", 0, "r9"), ("addi", "r9", "r9", 1),
        ("addi", "r10", "r10", 1), ("addi", "r5", "r5", 1), ("b", "cp"),
        ("label", "endcopy"),  # no trailing spaces, at least one character
        ("cmpwi", "r10", 0), ("ble", "restore"), ("lbz", "r0", -1, "r9"), ("cmpwi", "r0", 0x20), ("bne", "trimmed"),
        ("addi", "r9", "r9", -1), ("addi", "r10", "r10", -1), ("b", "endcopy"),
        ("label", "trimmed"),
        # every character that is not a letter, a digit, '_' or '-' becomes '_'
        ("lis", "r8", (path_va + len(PREFIX) + len(NAME_PREFIX)) >> 16),
        ("ori", "r8", "r8", (path_va + len(PREFIX) + len(NAME_PREFIX)) & 0xFFFF), ("mr", "r7", "r10"),
        ("label", "san"),
        ("cmpwi", "r7", 0), ("ble", "sandone"), ("lbz", "r0", 0, "r8"),
        ("cmpwi", "r0", 0x2D), ("beq", "sanok"), ("cmpwi", "r0", 0x5F), ("beq", "sanok"),
        ("cmpwi", "r0", 0x30), ("blt", "sanbad"), ("cmpwi", "r0", 0x39), ("ble", "sanok"),
        ("cmpwi", "r0", 0x41), ("blt", "sanbad"), ("cmpwi", "r0", 0x5A), ("ble", "sanok"),
        ("cmpwi", "r0", 0x61), ("blt", "sanbad"), ("cmpwi", "r0", 0x7A), ("ble", "sanok"),
        ("label", "sanbad"), ("li", "r0", 0x5F), ("stb", "r0", 0, "r8"),
        ("label", "sanok"), ("addi", "r8", "r8", 1), ("addi", "r7", "r7", -1), ("b", "san"),
        ("label", "sandone"),
    ]
    for i, c in enumerate(SUFFIX + b"\0"):
        lines += [("li", "r0", c), ("stb", "r0", i, "r9")]
    lines += [
        ("lis", "r5", path_va >> 16), ("ori", "r5", "r5", path_va & 0xFFFF), ("std", "r5", 0x80, "r1"),
        ("label", "restore"), *load, ("ld", "r0", FRAME + 0x10, "r1"), ("addi", "r1", "r1", FRAME), ("mtlr", "r0"),
        ("mfcr", "r12"), ("b", RESUME),
    ]
    words = assemble(code_va, lines)
    data = CFG_PATH.ljust(16, b"\0") + (PREFIX + NAME_PREFIX).ljust(PATH_SIZE, b"\0")
    patches = [(cave_va + i, 0, int.from_bytes(data[i:i + 4], "big"), "card cave data") for i in range(0, len(data), 4)]
    patches += [(code_va + 4 * i, 0, w, "card cave code") for i, w in enumerate(words)]
    patches.append((HOOK_VA, HOOK_STOCK, assemble(HOOK_VA, [("b", code_va)])[0], "jump to the card cave"))
    return patches, DATA_SIZE + 4 * len(words)
