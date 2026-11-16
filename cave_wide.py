"""EXPERIMENT: widen the destination rectangle of the game picture by 4/3 (for a 16:9 game shown in a 4:3 frame).

0x115ee4(&width, &height) hands the video output size to the routine that draws the game frame (0x282978); the quad runs from
(0,0) to that size. This hook returns width * 4 / 3 instead. If the pillar bars come from a 4:3 sized destination, the picture
then fills the screen. Not a per game switch yet: it affects every game. The height and the returned mode byte are untouched.
"""
from __future__ import annotations

from ppcasm import assemble

HOOK_VA, HOOK_STOCK = 0x115EE8, 0x80090010  # lwz r0,0x10(r9)
RESUME = 0x115EEC


def build(cave_va: int) -> tuple[list[tuple[int, int, int, str]], int]:
    """Return the (va, old, new, what) patches and the bytes used from `cave_va`."""
    words = assemble(cave_va, [
        ("lwz", "r0", 0x10, "r9"), ("mulli", "r0", "r0", 4), ("li", "r11", 3), ("divw", "r0", "r0", "r11"), ("b", RESUME),
    ])
    patches = [(cave_va + 4 * i, 0, w, "wide cave") for i, w in enumerate(words)]
    patches.append((HOOK_VA, HOOK_STOCK, assemble(HOOK_VA, [("b", cave_va)])[0], "jump to the wide cave"))
    return patches, 4 * len(words)
