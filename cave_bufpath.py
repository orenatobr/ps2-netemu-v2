"""Code cave: give memory card 1 a path when the launcher left its path buffer empty.

At game start the card setup routine (0x12c17c...) opens the card of slot 0 only if the byte at `object + 0x22e0` (the path
buffer of memory card 1, 256 bytes, the one 0x12a528 copies the path into) is not zero; otherwise it goes on without a card
and never calls 0x12a528. The buffer is filled by the launcher side through 0x12abc4(slot, name). When that does not happen
the game sees "no memory card in slot 1", whatever files are on the disk, and the original Sony image behaves the same.

This hook, placed on the check (0x12c988), writes DEFAULT_PATH into the buffer when it is empty and then repeats the stock
instruction, so the stock code opens the card as usual (and the card hooks that follow, 0x12a528, see a normal path). It only
writes into the emulator's own object, the memory the emulator writes that buffer in anyway, and uses r0 only.
"""
from __future__ import annotations

from ppcasm import assemble

HOOK_VA, HOOK_STOCK = 0x12C988, 0x881F22E0  # lbz r0, 0x22e0(r31)
RESUME = 0x12C98C
BUFFER = 0x22E0
DEFAULT_PATH = b"/savedata/vmc/PS2.VM2"


def build(cave_va: int, path: bytes = DEFAULT_PATH) -> tuple[list[tuple[int, int, int, str]], int]:
    """Return the (va, old, new, what) patches and the bytes used from `cave_va`."""
    lines: list[tuple] = [("lbz", "r0", BUFFER, "r31"), ("cmpwi", "r0", 0), ("bne", "done")]
    for i, ch in enumerate(path + b"\0"):
        lines += [("li", "r0", ch), ("stb", "r0", BUFFER + i, "r31")]
    lines += [("label", "done"), ("lbz", "r0", BUFFER, "r31"), ("b", RESUME)]
    words = assemble(cave_va, lines)
    patches = [(cave_va + 4 * i, 0, w, "buffer path cave") for i, w in enumerate(words)]
    patches.append((HOOK_VA, HOOK_STOCK, assemble(HOOK_VA, [("b", cave_va)])[0], "jump to the buffer path cave"))
    return patches, 4 * len(words)
