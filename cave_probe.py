"""EXPERIMENT (step 1): can the emulator's own file calls be used from the card hook?

Same hook as cave_card. When the slot is 0, `r4` is 0 and `r5` starts with /savedata/vmc/, the cave opens /tmp/cfg.bin, reads
256 bytes and closes it (a small stack frame, no ISO parsing). If it read anything, `r5` becomes the fixed path
`/savedata/vmc/PS2_TEST.VM2`; otherwise `r5` is left alone. Which card file the game writes to tells whether the calls worked.
"""
from __future__ import annotations

from ppcasm import assemble

HOOK_VA, HOOK_STOCK = 0x12A528, 0x7D800026  # mfcr r12
RESUME = 0x12A52C
OPEN, READ, CLOSE = 0x1ECC5C, 0x1ED5CC, 0x1ECB10
PATH = b"/savedata/vmc/PS2_TEST.VM2"
PATH_A = b"/savedata/vmc/PS2_SLUS-21345.VM2"  # select mode: the cfg.bin path starts at byte 1 (a type byte first)
CFG = b"/tmp/cfg.bin"
FRAME, S_FD, S_N, S_BUF = 0x1D0, 0xB0, 0xB8, 0xC0
DATA_SIZE = 112


def build(cave_va: int, select: bool = False) -> tuple[list[tuple[int, int, int, str]], int]:
    """Return the (va, old, new, what) patches and the bytes used from `cave_va`.

    With `select` the card is chosen by the content of /tmp/cfg.bin (no store anywhere but the stack frame): PATH_A when byte 1
    is '/', PATH (the test card) when byte 0 is '/', otherwise the shared card stays.
    """
    cfg_va, path_va, path_a_va = cave_va, cave_va + 16, cave_va + 64
    code_va = cave_va + DATA_SIZE
    save = [("std", f"r{n}", 0x70 + 8 * (n - 3), "r1") for n in range(3, 11)]
    load = [("ld", f"r{n}", 0x70 + 8 * (n - 3), "r1") for n in range(3, 11)]
    lines: list[tuple] = [
        ("stdu", "r1", -FRAME, "r1"), ("mflr", "r0"), ("std", "r0", FRAME + 0x10, "r1"), *save,
        ("cmpwi", "r3", 0), ("bne", "restore"), ("cmpdi", "r4", 0), ("bne", "restore"), ("cmpdi", "r5", 0), ("beq", "restore"),
    ]
    for i, c in enumerate(b"/savedata/vmc/"):
        lines += [("lbz", "r0", i, "r5"), ("cmpwi", "r0", c), ("bne", "restore")]
    lines += [
        ("li", "r3", 0), ("lis", "r4", cfg_va >> 16), ("ori", "r4", "r4", cfg_va & 0xFFFF), ("bl", OPEN),
        ("cmpwi", "r3", 0), ("blt", "restore"), ("std", "r3", S_FD, "r1"),
        ("li", "r4", 0), ("addi", "r5", "r1", S_BUF), ("li", "r6", 0x100), ("bl", READ), ("std", "r3", S_N, "r1"),
        ("ld", "r3", S_FD, "r1"), ("bl", CLOSE),
        ("ld", "r3", S_N, "r1"), ("cmpwi", "r3", 1), ("blt", "restore"),
        *([("lbz", "r0", S_BUF + 1, "r1"), ("cmpwi", "r0", 0x2F), ("beq", "usea"), ("lbz", "r0", S_BUF, "r1"), ("cmpwi", "r0", 0x2F),
           ("bne", "restore")] if select else []),
        ("lis", "r5", path_va >> 16), ("ori", "r5", "r5", path_va & 0xFFFF), ("b", "setp"),
        ("label", "usea"), ("lis", "r5", path_a_va >> 16), ("ori", "r5", "r5", path_a_va & 0xFFFF),
        ("label", "setp"), ("std", "r5", 0x80, "r1"),
        ("label", "restore"), *load, ("ld", "r0", FRAME + 0x10, "r1"), ("addi", "r1", "r1", FRAME), ("mtlr", "r0"),
        ("mfcr", "r12"), ("b", RESUME),
    ]
    words = assemble(code_va, lines)
    data = CFG.ljust(16, b"\0") + PATH.ljust(48, b"\0") + PATH_A.ljust(48, b"\0")
    patches = [(cave_va + i, 0, int.from_bytes(data[i:i + 4], "big"), "probe data") for i in range(0, len(data), 4)]
    patches += [(code_va + 4 * i, 0, w, "probe code") for i, w in enumerate(words)]
    patches.append((HOOK_VA, HOOK_STOCK, assemble(HOOK_VA, [("b", code_va)])[0], "jump to the probe"))
    return patches, DATA_SIZE + 4 * len(words)
