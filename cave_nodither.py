"""Code cave: switch the RSX dither off (method 0x0300) in the state reset of the draw code.

The routine at 0x280530 emits the default RSX state into the command buffer one command at a time (header word, value word, then
the pointer kept at `r31 + 24` is advanced; the end of the buffer is `r31 + 16`). The command at 0x2805ac writes method 0x0304
(alpha test) = 0. No code of this image ever writes method 0x0300 (dither), so the hardware default (dither on) stays for the
whole run. On a target with 8 bits per channel the switch changes nothing visible, so this is only the same state the PS1 patch forces.

The hook replaces the `std r11,24(r31)` that closes that command. The cave appends one more command, header `0x00040300` and value 0,
but only when the buffer has room for it (the same test the stock code makes before each command); otherwise it advances the pointer
as the stock instruction did and leaves everything as it was. Registers: r0, r9 and r12 are loaded again by the stock code that follows
(0x2805c0 reloads r12 and r9, r0 is set before use), r11 is the pointer after the stock command.
"""
from __future__ import annotations

from ppcasm import assemble

HOOK_VA = 0x2805BC  # stock: std r11,24(r31)
HOOK_STOCK = 0xF97F0018
RESUME = 0x2805C0
DITHER_HEADER = 0x00040300  # one word, method 0x0300 (dither enable)


def build(cave_va: int) -> tuple[list[tuple[int, int, int, str]], int]:
    """Return the (va, old, new, what) patches and the bytes used from `cave_va`."""
    lines: list[tuple] = [
        ("ld", "r9", 16, "r31"),  # end of the command buffer
        ("addi", "r12", "r11", 8),  # pointer after one more command
        ("cmpld", "r12", "r9"),
        ("bgt", "full"),
        ("lis", "r0", DITHER_HEADER >> 16), ("ori", "r0", "r0", DITHER_HEADER & 0xFFFF),
        ("li", "r9", 0),
        ("stw", "r0", 0, "r11"), ("stw", "r9", 4, "r11"),
        ("std", "r12", 24, "r31"),
        ("b", RESUME),
        ("label", "full"),
        ("std", "r11", 24, "r31"),  # the instruction the hook replaced
        ("b", RESUME),
    ]
    words = assemble(cave_va, lines)
    patches = [(cave_va + 4 * i, 0, w, "no dither cave code") for i, w in enumerate(words)]
    patches.append((HOOK_VA, HOOK_STOCK, assemble(HOOK_VA, [("b", cave_va)])[0], "jump to the no dither cave"))
    return patches, 4 * len(words)
