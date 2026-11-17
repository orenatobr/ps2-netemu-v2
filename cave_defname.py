"""Code cave: give memory card 1 a name when the launcher gives none.

0x12abc4(slot, name) opens the card of a slot: it builds the path with `snprintf(buf, 256, "%s%s.VM2", prefix, name)` and calls
the card function at 0x12a528. When `name` is NULL it skips all of that and reports "no card" (0x12ac4c to 0x12aca8). The name
comes from the launcher, not from the emulator: if the launcher passes none for slot 0 (memory card 1) the game sees no card,
whatever the files on the disk are, and even the original Sony image behaves like that.

This hook replaces a NULL name of slot 0 by DEFAULT_NAME (the shared card, /savedata/vmc/PS2.VM2), then goes on as the stock
code does. Anything else (another slot, a name that is given) is untouched. Only r27 (callee saved, set from r4 at 0x12abd4)
and cr7 change, and cr7 ends up as the stock compare of r27 would leave it.
"""
from __future__ import annotations

from ppcasm import assemble

HOOK_VA, HOOK_STOCK = 0x12AC4C, 0x2FBB0000  # cmpdi cr7, r27, 0
RESUME = 0x12AC50
DEFAULT_NAME = b"PS2"


def build(cave_va: int) -> tuple[list[tuple[int, int, int, str]], int]:
    """Return the (va, old, new, what) patches and the bytes used from `cave_va`."""
    name_va = cave_va
    code_va = cave_va + 4
    words = assemble(code_va, [
        ("cmpdi", "r27", 0), ("bne", "fin"), ("cmplwi", "r31", 0), ("bne", "fin"),
        ("lis", "r27", name_va >> 16), ("ori", "r27", "r27", name_va & 0xFFFF),
        ("label", "fin"), ("cmpdi", "r27", 0), ("b", RESUME),
    ])
    data = DEFAULT_NAME.ljust(4, b"\0")
    patches = [(name_va, 0, int.from_bytes(data, "big"), "default card name")]
    patches += [(code_va + 4 * i, 0, w, "default name code") for i, w in enumerate(words)]
    patches.append((HOOK_VA, HOOK_STOCK, assemble(HOOK_VA, [("b", code_va)])[0], "jump to the default name cave"))
    return patches, 4 + 4 * len(words)
