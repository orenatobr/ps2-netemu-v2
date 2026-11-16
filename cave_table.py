"""Code cave: memory card 1 chosen from a fixed table (ISO file name -> card path). No store outside the stack frame.

The run-time builds of the card path all crashed the console, while a hook that reads /tmp/cfg.bin and points `r5` at a fixed
string worked. This one only compares: it takes the last path component of the ISO path in /tmp/cfg.bin (the path starts at
byte 1, after a type byte; byte 0 is accepted too) and walks a table of `name\\0card\\0` records ended by an empty name. A match
points `r5` at the card string of the record (all discs of a game list the same card). No match leaves `r5` alone.
"""
from __future__ import annotations

from cave_cardfile import card_path
from ppcasm import assemble

HOOK_VA, HOOK_STOCK = 0x12A528, 0x7D800026  # mfcr r12
RESUME = 0x12A52C
OPEN, READ, CLOSE = 0x1ECC5C, 0x1ED5CC, 0x1ECB10
PREFIX = b"/savedata/vmc/"
CFG_PATH = b"/tmp/cfg.bin"
FRAME, S_FD, S_N, S_BUF, BUF_SIZE = 0x1D0, 0xB0, 0xB8, 0xC0, 0x100


def table(isos: list[str]) -> bytes:
    """The table bytes for the ISO paths: one record per distinct file name, ended by an empty name."""
    out, seen = b"", set()
    for iso in isos:
        base, card = iso.rsplit("/", 1)[-1], card_path(iso)
        if card and base not in seen:
            seen.add(base)
            out += base.encode() + b"\0" + card.encode() + b"\0"
    return out + b"\0"


def build(cave_va: int, isos: list[str]) -> tuple[list[tuple[int, int, int, str]], int]:
    """Return the (va, old, new, what) patches and the bytes used from `cave_va`."""
    data = CFG_PATH.ljust(16, b"\0") + table(isos)
    data += b"\0" * (-len(data) % 4)
    cfg_va, table_va, code_va = cave_va, cave_va + 16, cave_va + len(data)
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
        ("label", "scanned"), ("lis", "r9", table_va >> 16), ("ori", "r9", "r9", table_va & 0xFFFF),
        ("label", "next"), ("lbz", "r0", 0, "r9"), ("cmpwi", "r0", 0), ("beq", "restore"), ("mr", "r4", "r5"), ("mr", "r6", "r9"),
        ("label", "cmp"),
        ("lbz", "r7", 0, "r6"), ("lbz", "r8", 0, "r4"), ("cmpw", "r7", "r8"), ("bne", "skip"), ("cmpwi", "r7", 0), ("beq", "found"),
        ("addi", "r6", "r6", 1), ("addi", "r4", "r4", 1), ("b", "cmp"),
        ("label", "found"), ("addi", "r5", "r6", 1), ("std", "r5", 0x80, "r1"), ("b", "restore"),
        ("label", "skip"),  # past the name and the card of this record
        ("lbz", "r0", 0, "r9"), ("addi", "r9", "r9", 1), ("cmpwi", "r0", 0), ("bne", "skip"),
        ("label", "skipc"), ("lbz", "r0", 0, "r9"), ("addi", "r9", "r9", 1), ("cmpwi", "r0", 0), ("bne", "skipc"), ("b", "next"),
        ("label", "restore"), *load, ("ld", "r0", FRAME + 0x10, "r1"), ("addi", "r1", "r1", FRAME), ("mtlr", "r0"),
        ("mfcr", "r12"), ("b", RESUME),
    ]
    words = assemble(code_va, lines)
    patches = [(cave_va + i, 0, int.from_bytes(data[i:i + 4], "big"), "card table") for i in range(0, len(data), 4)]
    patches += [(code_va + 4 * i, 0, w, "card table code") for i, w in enumerate(words)]
    patches.append((HOOK_VA, HOOK_STOCK, assemble(HOOK_VA, [("b", code_va)])[0], "jump to the card table cave"))
    return patches, len(data) + 4 * len(words)
