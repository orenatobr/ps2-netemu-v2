"""Code cave: give slot 1 a memory card file of its own instead of the shared one.

0x12a528(slot, 0, path, ...) receives the card path as `r5` and copies it into the emulator's card object. The hook at its
first instruction runs this cave: when the slot is 0 (memory card 1), `r4` is 0 and `r5` is a path that starts with
`/savedata/vmc/`, and the serial cave has left a path at `path_va`, `r5` is replaced by that address; anything else goes
through untouched. The displaced stock instruction (`mfcr r12`) is redone first and the cave ends at 0x12a52c.

Only r0, r11 and r12 are used. r12 holds the condition register, saved by the stock code the same way.
"""
from __future__ import annotations

from ppcasm import assemble

HOOK_VA, HOOK_STOCK = 0x12A528, 0x7D800026  # mfcr r12
RESUME = 0x12A52C
PREFIX = b"/savedata/vmc/"


def build(cave_va: int, path_va: int) -> tuple[list[tuple[int, int, int, str]], int]:
    """Return the (va, old, new, what) patches and the bytes used from `cave_va`."""
    lines: list[tuple] = [
        ("mfcr", "r12"),  # the displaced stock instruction
        ("cmpwi", "r3", 0), ("bne", "done"), ("cmpdi", "r4", 0), ("bne", "done"), ("cmpdi", "r5", 0), ("beq", "done"),
    ]
    for i, c in enumerate(PREFIX):
        lines += [("lbz", "r0", i, "r5"), ("cmpwi", "r0", c), ("bne", "done")]
    lines += [
        ("lis", "r11", path_va >> 16), ("ori", "r11", "r11", path_va & 0xFFFF),
        ("lbz", "r0", 0, "r11"), ("cmpwi", "r0", 0), ("beq", "done"),  # no serial: the shared card stays
        ("mr", "r5", "r11"),
        ("label", "done"), ("b", RESUME),
    ]
    words = assemble(cave_va, lines)
    patches = [(cave_va + 4 * i, 0, w, "card cave code") for i, w in enumerate(words)]
    patches.append((HOOK_VA, HOOK_STOCK, assemble(HOOK_VA, [("b", cave_va)])[0], "jump to the card cave"))
    return patches, 4 * len(words)
