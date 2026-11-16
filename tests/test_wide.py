"""The widening experiment: width * 4 / 3, nothing else changes."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ppc_interp import Cpu

import cave_wide as W
import ps2_netemu_patch as P
import selfio as S

STRUCT, WOUT, HOUT, RET = 0x7000_0000, 0x7100_0000, 0x7100_0010, 0x4242


@pytest.fixture(scope="module")
def patched() -> bytes:
    path = os.environ.get("PS2_NETEMU_SELF")
    if not path:
        pytest.skip("stock SELF not provided")
    return P.apply_edits(P.extend_text(S.unpack(Path(path).read_bytes())), P.crop_edits() + P.slots_card_edits() + P.wide_edits())


def getter(patched: bytes, width: int, height: int):
    cpu = Cpu(patched)
    for off, val in ((0x10, width), (0x14, height)):
        for i, b in enumerate(val.to_bytes(4, "big")):
            cpu.mem[STRUCT + off + i] = b
    cpu.mem[STRUCT + 0x20] = 1
    cpu.r[9], cpu.r[3], cpu.r[4], cpu.lr = STRUCT, WOUT, HOUT, RET
    assert cpu.run(W.HOOK_VA, {RET}) == RET
    return cpu, int.from_bytes(bytes(cpu.byte(WOUT + i) for i in range(4)), "big"), int.from_bytes(bytes(cpu.byte(HOUT + i) for i in range(4)), "big")


@pytest.mark.parametrize("width,expected", [(960, 1280), (720, 960), (640, 853), (1280, 1706), (0, 0)])
def test_width_is_scaled_by_four_thirds(patched, width, expected):
    assert getter(patched, width, 720)[1] == expected


def test_height_and_mode_byte_are_untouched(patched):
    cpu, _, h = getter(patched, 960, 720)
    assert h == 720 and cpu.r[3] == 1


def test_the_caves_do_not_overlap():
    top = P.CARD_CAVE_VA + max(__import__("cave_slots").build(P.CARD_CAVE_VA)[1], __import__("cave_wrap").build(P.CARD_CAVE_VA)[1])
    assert top <= P.WIDE_CAVE_VA and P.WIDE_CAVE_VA + 0x20 <= P.CAVE_VA + P.CAVE_SIZE
