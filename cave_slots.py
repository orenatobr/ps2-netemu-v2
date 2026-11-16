"""Code cave: memory card 1 chosen through a table file, with fixed card paths and no store outside the stack frame.

The card path must stay valid for the whole of the emulator function that receives it (it is kept in `r28`), and every build
that built a path at run time took the console down. So the image carries NSLOTS fixed paths, `/savedata/vmc/PS2_CNN.VM2`,
and the hook only computes `slots + NN * STRIDE`.

Which slot belongs to which game is a file the installer writes, `/savedata/vmc/PS2_CARDS.TBL`, of 128 byte records:

    byte 0       the slot number (0 to NSLOTS - 1)
    bytes 1..    the ISO file name (up to 126 bytes, NUL terminated), the empty name ends the table

The hook reads `/tmp/cfg.bin` (Cobra's file with the mounted ISO path: a type byte, then the path), takes the last path
component, reads the table record by record (`0x1ed5cc(fd, offset, buffer, size)`) and compares each name. A match
points `r5` at the slot path; anything else leaves the shared card. All the discs of a game list the same slot.
"""
from __future__ import annotations

from ppcasm import assemble

HOOK_VA, HOOK_STOCK = 0x12A528, 0x7D800026  # mfcr r12
RESUME = 0x12A52C
OPEN, READ, CLOSE = 0x1ECC5C, 0x1ED5CC, 0x1ECB10
PREFIX = b"/savedata/vmc/"
CFG_PATH = b"/tmp/cfg.bin"
TABLE_PATH = b"/savedata/vmc/PS2_CARDS.TBL"
RECORD = 128
NSLOTS, STRIDE = 32, 26  # '/savedata/vmc/PS2_C00.VM2' and its NUL
FRAME = 0x270
S_FD, S_N, S_TFD, S_IDX, S_BASE, S_RES, S_BUF, BUF_SIZE, S_REC = 0xB0, 0xB8, 0xC0, 0xC8, 0xD0, 0xD8, 0xE0, 0x100, 0x1E0


def slot_path(n: int) -> str:
    """The fixed card path of a slot."""
    return f"/savedata/vmc/PS2_C{n:02d}.VM2"


def record(slot: int, iso_name: str) -> bytes:
    """One table record, or b'' when the name does not fit."""
    raw = iso_name.encode()
    if not 0 <= slot < NSLOTS or not raw or len(raw) > RECORD - 2:
        return b""
    return (bytes([slot]) + raw).ljust(RECORD, b"\0")


def build(cave_va: int) -> tuple[list[tuple[int, int, int, str]], int]:
    """Return the (va, old, new, what) patches and the bytes used from `cave_va`."""
    cfg_va, tbl_va, slots_va = cave_va, cave_va + 16, cave_va + 48
    data = CFG_PATH.ljust(16, b"\0") + TABLE_PATH.ljust(32, b"\0")
    data += b"".join(slot_path(n).encode().ljust(STRIDE, b"\0") for n in range(NSLOTS))
    code_va = cave_va + len(data)
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
        ("addi", "r10", "r1", S_BUF), ("lbz", "r0", 1, "r10"), ("cmpwi", "r0", 0x2F), ("bne", "try0"),
        ("addi", "r4", "r10", 1), ("b", "scan0"),
        ("label", "try0"), ("lbz", "r0", 0, "r10"), ("cmpwi", "r0", 0x2F), ("bne", "restore"), ("mr", "r4", "r10"),
        ("label", "scan0"), ("mr", "r5", "r4"),
        ("label", "scan"),  # r5 = start of the last path component
        ("lbz", "r0", 0, "r4"), ("cmpwi", "r0", 0), ("beq", "scanned"), ("addi", "r4", "r4", 1), ("cmpwi", "r0", 0x2F),
        ("bne", "scan"), ("mr", "r5", "r4"), ("b", "scan"),
        ("label", "scanned"), ("std", "r5", S_BASE, "r1"), ("li", "r0", -1), ("std", "r0", S_RES, "r1"),
        ("li", "r0", 0), ("std", "r0", S_IDX, "r1"),
        ("li", "r3", 0), ("lis", "r4", tbl_va >> 16), ("ori", "r4", "r4", tbl_va & 0xFFFF), ("bl", OPEN),
        ("cmpwi", "r3", 0), ("blt", "restore"), ("std", "r3", S_TFD, "r1"),
        ("label", "rec"),
        ("ld", "r3", S_TFD, "r1"), ("ld", "r4", S_IDX, "r1"), ("mulli", "r4", "r4", RECORD), ("addi", "r5", "r1", S_REC),
        ("li", "r6", RECORD), ("bl", READ), ("cmpwi", "r3", 2), ("blt", "closet"),
        ("lbz", "r0", S_REC + 1, "r1"), ("cmpwi", "r0", 0), ("beq", "closet"),
        ("ld", "r4", S_BASE, "r1"), ("addi", "r6", "r1", S_REC + 1),
        ("label", "cmp"),
        ("lbz", "r7", 0, "r6"), ("lbz", "r8", 0, "r4"), ("cmpw", "r7", "r8"), ("bne", "nomatch"), ("cmpwi", "r7", 0),
        ("beq", "match"), ("addi", "r6", "r6", 1), ("addi", "r4", "r4", 1), ("b", "cmp"),
        ("label", "match"), ("lbz", "r0", S_REC, "r1"), ("std", "r0", S_RES, "r1"), ("b", "closet"),
        ("label", "nomatch"), ("ld", "r3", S_IDX, "r1"), ("addi", "r3", "r3", 1), ("std", "r3", S_IDX, "r1"), ("b", "rec"),
        ("label", "closet"), ("ld", "r3", S_TFD, "r1"), ("bl", CLOSE),
        ("ld", "r0", S_RES, "r1"), ("cmpwi", "r0", 0), ("blt", "restore"), ("cmpwi", "r0", NSLOTS), ("bge", "restore"),
        ("mulli", "r0", "r0", STRIDE), ("lis", "r5", slots_va >> 16), ("ori", "r5", "r5", slots_va & 0xFFFF),
        ("add", "r5", "r5", "r0"), ("std", "r5", 0x80, "r1"),
        ("label", "restore"), *load, ("ld", "r0", FRAME + 0x10, "r1"), ("addi", "r1", "r1", FRAME), ("mtlr", "r0"),
        ("mfcr", "r12"), ("b", RESUME),
    ]
    words = assemble(code_va, lines)
    patches = [(cave_va + i, 0, int.from_bytes(data[i:i + 4], "big"), "card slots data") for i in range(0, len(data), 4)]
    patches += [(code_va + 4 * i, 0, w, "card slots code") for i, w in enumerate(words)]
    patches.append((HOOK_VA, HOOK_STOCK, assemble(HOOK_VA, [("b", code_va)])[0], "jump to the card slots cave"))
    return patches, len(data) + 4 * len(words)
