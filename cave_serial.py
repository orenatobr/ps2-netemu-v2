"""Code cave: remember the serial of the disc and the card path it maps to.

0x1339dc reads SYSTEM.CNF of a PS2 disc into a buffer and then calls 0x133280(ctx, buffer, size) to parse it. The call at
0x133c00 is redirected here. This routine reads `BOOT2 = cdrom0:\\SLUS_213.45;1` from the buffer, turns the executable
name into the serial `SLUS-21345` (letters upper case, `_` to `-`, `.` dropped) and writes the card path
`/savedata/vmc/SLUS-21345.VM2` at `path_va`; a disc without a usable BOOT2 line leaves `path_va` empty. It then calls
the original 0x133280 with the registers it received, and returns its result.
"""
from __future__ import annotations

from ppcasm import assemble

CALL_VA, CALL_STOCK = 0x133C00, 0x4BFFF681  # bl 0x133280
PARSE_VA = 0x133280
PREFIX = b"/savedata/vmc/"
SUFFIX = b".VM2"
MAX_SCAN, MAX_SERIAL, MIN_SERIAL = 0x400, 16, 4


def program(path_va: int) -> list[tuple]:
    """The routine as assembler lines. r3 r4 r5 = context, buffer, size (as the parser receives them)."""
    hi, lo = path_va >> 16, path_va & 0xFFFF
    lines: list[tuple] = [
        ("stdu", "r1", -0x70, "r1"), ("mflr", "r0"), ("std", "r0", 0x80, "r1"),
        ("std", "r3", 0x60, "r1"), ("std", "r4", 0x58, "r1"), ("std", "r5", 0x50, "r1"),
        ("lis", "r11", hi), ("ori", "r11", "r11", lo), ("li", "r0", 0), ("stb", "r0", 0, "r11"),  # no path yet
        ("cmplwi", "r5", MAX_SCAN), ("ble", "sized"), ("li", "r5", MAX_SCAN),
        ("label", "sized"), ("li", "r6", 0),
        ("label", "scan"),  # look for BOOT2
        ("addi", "r7", "r6", 5), ("cmpw", "r7", "r5"), ("bgt", "done"), ("add", "r8", "r4", "r6"),
    ]
    for i, c in enumerate(b"BOOT2"):
        lines += [("lbz", "r0", i, "r8"), ("cmpwi", "r0", c), ("bne", "next") if i < 4 else ("beq", "found")]
    lines += [
        ("label", "next"), ("addi", "r6", "r6", 1), ("b", "scan"),
        ("label", "found"), ("addi", "r6", "r6", 5),
        ("label", "colon"),  # the ':' of cdrom0:
        ("cmpw", "r6", "r5"), ("bge", "done"), ("add", "r8", "r4", "r6"), ("lbz", "r0", 0, "r8"), ("addi", "r6", "r6", 1),
        ("cmpwi", "r0", 0x3A), ("bne", "colon"),
        ("label", "skip"),  # backslashes and slashes
        ("cmpw", "r6", "r5"), ("bge", "done"), ("add", "r8", "r4", "r6"), ("lbz", "r0", 0, "r8"),
        ("cmpwi", "r0", 0x5C), ("beq", "skipnext"), ("cmpwi", "r0", 0x2F), ("bne", "copy"),
        ("label", "skipnext"), ("addi", "r6", "r6", 1), ("b", "skip"),
        ("label", "copy"),
    ]
    for i, c in enumerate(PREFIX):
        lines += [("li", "r0", c), ("stb", "r0", i, "r11")]
    lines += [
        ("addi", "r9", "r11", len(PREFIX)), ("li", "r10", 0),
        ("label", "cp"),
        ("cmpw", "r6", "r5"), ("bge", "fin"), ("add", "r8", "r4", "r6"), ("lbz", "r0", 0, "r8"),
        ("cmpwi", "r0", 0x3B), ("beq", "fin"), ("cmpwi", "r0", 0x21), ("blt", "fin"),  # ';' or a control/space ends it
        ("cmpwi", "r0", 0x2E), ("beq", "skipchar"),  # '.' is dropped
        ("cmpwi", "r0", 0x5F), ("bne", "notus"), ("li", "r0", 0x2D),  # '_' becomes '-'
        ("label", "notus"),
        ("cmpwi", "r0", 0x61), ("blt", "keep"), ("cmpwi", "r0", 0x7A), ("bgt", "keep"),
        ("mr", "r7", "r0"), ("addi", "r0", "r7", -0x20),  # lower case to upper case
        ("label", "keep"),
        ("stb", "r0", 0, "r9"), ("addi", "r9", "r9", 1), ("addi", "r10", "r10", 1),
        ("cmpwi", "r10", MAX_SERIAL), ("bge", "fin"),
        ("label", "skipchar"), ("addi", "r6", "r6", 1), ("b", "cp"),
        ("label", "fin"),
        ("cmpwi", "r10", MIN_SERIAL), ("blt", "bad"),
    ]
    for i, c in enumerate(SUFFIX + b"\0"):
        lines += [("li", "r0", c), ("stb", "r0", i, "r9")]
    lines += [
        ("b", "done"),
        ("label", "bad"), ("li", "r0", 0), ("stb", "r0", 0, "r11"),
        ("label", "done"),
        ("ld", "r3", 0x60, "r1"), ("ld", "r4", 0x58, "r1"), ("ld", "r5", 0x50, "r1"),
        ("bl", PARSE_VA),
        ("ld", "r0", 0x80, "r1"), ("addi", "r1", "r1", 0x70), ("mtlr", "r0"), ("blr",),
    ]
    return lines


def build(cave_va: int, path_va: int) -> tuple[list[tuple[int, int, int, str]], int]:
    """Return the (va, old, new, what) patches and the number of bytes used from `cave_va`."""
    words = assemble(cave_va, program(path_va))
    patches = [(cave_va + 4 * i, 0, w, "serial cave code") for i, w in enumerate(words)]
    patches.append((CALL_VA, CALL_STOCK, assemble(CALL_VA, [("bl", cave_va)])[0], "call the serial cave"))
    return patches, 4 * len(words)
