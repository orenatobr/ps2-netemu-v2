"""Code cave: crop the black bands at the top and the bottom of the PS2 picture and stretch the rest to the frame.

The routine at 0x282978 draws the game frame as a textured rectangle: the four positions run from
(0,0) to the output size and the four texture coordinates from (0,0) to the source size
(width f30, height f27, in texels). The bands come from the first and the last rows of that texture, so the two
top vertices get a texture y of `CROP_TOP * height` instead of 0 and the two bottom vertices one of
`(1 - CROP_BOTTOM) * height` instead of the full height. The picture keeps its 4:3 frame (the
pillar bars are the output viewport, untouched) and the visible rows are stretched over it.

Hooks, all inside 0x282978:
  * 0x28394c `frsp f27,f10` (source height known): store the two values in the free stack slots 0xf8 (top)
    and 0xc0 (bottom);
  * 0x2839a8 and 0x283ad8 `stw r0,0xa4(r1)` (texture y of the two top vertices): store the top value;
  * 0x283c08 and 0x283d2c `stfs f27,0xa4(r1)` (texture y of the two bottom vertices): store the bottom value.
The routine's stack has four unused 8-byte slots (0xb8, 0xc0, 0xf8, 0x100): 0xf8 and 0xc0 hold the values,
0x100 and 0xb8 save r12 and f0.
"""
from __future__ import annotations

import struct

from ppcasm import assemble

FRSP_VA, FRSP_STOCK = 0x28394C, 0xFF605018  # frsp f27,f10
FRSP_RESUME = 0x283950
TOP_VERTICES = ((0x2839A8, 0x2839AC), (0x283AD8, 0x283ADC))  # (hook, resume): stock `stw r0,0xa4(r1)`
STW_STOCK = 0x900100A4
BOTTOM_VERTICES = ((0x283C08, 0x283C0C), (0x283D2C, 0x283D30))  # stock `stfs f27,0xa4(r1)`
STFS_STOCK = 0xD36100A4
SLOT_VALUE, SLOT_BOTTOM, SLOT_R12, SLOT_F0 = 0xF8, 0xC0, 0x100, 0xB8
CROP_TOP = 16 / 448  # first guess: 16 rows of a 448 row picture
CROP_BOTTOM = 16 / 448  # the owner saw a band of the same size appear at the bottom once the top was cropped
CROP = CROP_TOP  # kept for callers that only know one value


def build(cave_va: int, crop_top: float = CROP_TOP,
          crop_bottom: float = CROP_BOTTOM) -> tuple[list[tuple[int, int, int, str]], int]:
    """Return the (va, old, new, what) patches and the number of bytes used from `cave_va`."""
    const_va = cave_va  # the two floats live first so their address is known
    lines: list[tuple] = []
    for hook, resume in TOP_VERTICES:
        lines += [
            ("label", f"v{hook:x}"),
            ("std", "r12", SLOT_R12, "r1"), ("lwz", "r12", SLOT_VALUE, "r1"), ("stw", "r12", 0xA4, "r1"),
            ("ld", "r12", SLOT_R12, "r1"), ("b", resume),
        ]
    for hook, resume in BOTTOM_VERTICES:
        lines += [
            ("label", f"v{hook:x}"),
            ("std", "r12", SLOT_R12, "r1"), ("lwz", "r12", SLOT_BOTTOM, "r1"), ("stw", "r12", 0xA4, "r1"),
            ("ld", "r12", SLOT_R12, "r1"), ("b", resume),
        ]
    lines += [
        ("label", "height"),
        ("frsp", "f27", "f10"),  # what the stock code did here
        ("std", "r12", SLOT_R12, "r1"), ("stfd", "f0", SLOT_F0, "r1"),
        ("lis", "r12", const_va >> 16), ("ori", "r12", "r12", const_va & 0xFFFF),
        ("lfs", "f0", 0, "r12"), ("fmuls", "f0", "f0", "f27"), ("stfs", "f0", SLOT_VALUE, "r1"),
        ("lfs", "f0", 4, "r12"), ("fmuls", "f0", "f0", "f27"), ("fsubs", "f0", "f27", "f0"),
        ("stfs", "f0", SLOT_BOTTOM, "r1"),
        ("lfd", "f0", SLOT_F0, "r1"), ("ld", "r12", SLOT_R12, "r1"), ("b", FRSP_RESUME),
    ]
    base = cave_va + 8  # two words for the constants
    words = assemble(base, lines)
    labels = {}
    pc = base
    for ln in lines:
        if ln[0] == "label":
            labels[ln[1]] = pc
        else:
            pc += 4
    patches = [(const_va, 0, struct.unpack(">I", struct.pack(">f", crop_top))[0], "top crop constant"),
               (const_va + 4, 0, struct.unpack(">I", struct.pack(">f", crop_bottom))[0], "bottom crop constant")]
    patches += [(base + 4 * i, 0, w, "crop cave code") for i, w in enumerate(words)]
    patches.append((FRSP_VA, FRSP_STOCK, assemble(FRSP_VA, [("b", labels["height"])])[0], "jump: compute the crop"))
    for hook, _ in TOP_VERTICES:
        patches.append((hook, STW_STOCK, assemble(hook, [("b", labels[f"v{hook:x}"])])[0], "jump: top vertex texture y"))
    for hook, _ in BOTTOM_VERTICES:
        patches.append((hook, STFS_STOCK, assemble(hook, [("b", labels[f"v{hook:x}"])])[0], "jump: bottom vertex texture y"))
    return patches, 8 + 4 * len(words)
