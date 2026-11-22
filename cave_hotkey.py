"""Code cave: SELECT + L1 + R1 switches the live Screen Mode between Normal (1) and Full Screen (2). EXPERIMENT.

The DualShock 3 report parser (0xe85a0, generic path) stores the two digital bytes of the report in the output buffer and goes on
at 0xe8720. At that point r0 is the first digital byte (SELECT is bit 0x01), r9 the second (L1 is 0x04, R1 is 0x08), r25 the report.
The hook at 0xe8720 replaces `lbz r9,8(r25)` by a jump here; the cave runs that instruction itself before it jumps back.

When the three buttons are held it reads the one byte of state at STATE_VA. A zero means the combination just started: the cave sets
the byte and switches the mode, a one means it is still held and nothing happens. Any report without the combination clears the byte.

Before it stores the new mode it copies the old one into the Up Convert byte of the settings object. The controller report builder (0x11ba80)
sends the host the pair (settings byte, live mode) whenever the two differ, so each press tells the host "from X to Y". Without it the pair
matched again after going back to Normal, the host heard nothing and the side bars kept a frozen picture (seen on a console in v2.12).

The mode is the global the display object reads through its `+0x88` method (TOC slot -0x2df0, address 0x3172f70). The video thread
recalculates the Full Screen flag from it on its next event. Nothing here wakes that thread, and none of it was checked on a console.

Registers: r3, r4 and r5 are free at the hook (the parser moved its arguments to saved registers at the start); r0 and r9 are kept.
The compares use cr7, which the parser sets again at 0xe8724.
"""
from __future__ import annotations

from ppcasm import assemble

HOOK_VA, HOOK_STOCK = 0xE8720, 0x89390008  # lbz r9,8(r25)
RESUME = 0xE8724
MODE_SLOT = -0x2DF0  # TOC slot holding the address of the live Screen Mode word (0x3172f70)
STATE_VA = 0x3175470  # one byte in the zero filled tail of the data (the segment ends at 0x3175478), no other code refers to it
SETTINGS_SLOT, UP_CONVERT = -0x2D80, 0x28  # TOC slot of the settings object (0xb46100) and its Up Convert byte
SELECT, L1_R1 = 0x01, 0x0C  # bits of the first and the second digital byte
NORMAL, FULL = 1, 2


def program() -> list[tuple]:
    return [
        ("rlwinm", "r3", "r0", 0, 31, 31), ("cmpwi", "r3", 0), ("beq", "release"),  # SELECT
        ("rlwinm", "r3", "r9", 0, 28, 29), ("cmpwi", "r3", L1_R1), ("bne", "release"),  # L1 and R1
        ("lis", "r4", STATE_VA >> 16), ("ori", "r4", "r4", STATE_VA & 0xFFFF),
        ("lbz", "r5", 0, "r4"), ("cmpwi", "r5", 0), ("bne", "out"),  # still held
        ("li", "r5", 1), ("stb", "r5", 0, "r4"),
        ("ld", "r4", MODE_SLOT, "r2"), ("lwz", "r5", 0, "r4"),
        ("ld", "r3", SETTINGS_SLOT, "r2"), ("stb", "r5", UP_CONVERT, "r3"),  # the settings byte keeps the mode being left
        ("cmpwi", "r5", FULL),
        ("li", "r5", FULL), ("bne", "store"), ("li", "r5", NORMAL),
        ("label", "store"), ("stw", "r5", 0, "r4"), ("b", "out"),
        ("label", "release"),
        ("lis", "r4", STATE_VA >> 16), ("ori", "r4", "r4", STATE_VA & 0xFFFF), ("li", "r5", 0), ("stb", "r5", 0, "r4"),
        ("label", "out"),
        ("lbz", "r9", 8, "r25"),  # the instruction the hook replaced
        ("b", RESUME),
    ]


def build(cave_va: int) -> tuple[list[tuple[int, int, int, str]], int]:
    """Return the (va, old, new, what) patches and the number of bytes used from `cave_va`."""
    words = assemble(cave_va, program())
    patches = [(cave_va + 4 * i, 0, w, "hotkey cave code") for i, w in enumerate(words)]
    patches.append((HOOK_VA, HOOK_STOCK, assemble(HOOK_VA, [("b", cave_va)])[0], "jump to the hotkey cave"))
    return patches, 4 * len(words)
