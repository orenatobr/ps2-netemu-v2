"""Run the crop cave in the interpreter against the real emulator code."""
import os
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ppc_interp import Cpu

import cave_crop as C
import ps2_netemu_patch as P
import selfio as S

pytestmark = pytest.mark.skipif("PS2_NETEMU_SELF" not in os.environ, reason="stock SELF not provided")
STACK = 0x7000_0000


def f32(x: float) -> int:
    return struct.unpack(">I", struct.pack(">f", x))[0]


@pytest.fixture(scope="module")
def patched() -> bytes:
    stock = Path(os.environ["PS2_NETEMU_SELF"]).read_bytes()
    elf = P.extend_text(S.unpack(stock))
    return P.apply_edits(elf, P.crop_edits())


def cpu_for(elf: bytes) -> Cpu:
    cpu = Cpu(elf)
    cpu.r[1] = STACK
    cpu.r[12] = 0x1234_5678_9ABC
    cpu.f[0] = 7.5
    return cpu


def test_the_height_hook_stores_the_crop_and_leaves_registers_alone(patched):
    cpu = cpu_for(patched)
    cpu.f[10] = 448.0
    assert cpu.run(C.FRSP_VA, {C.FRSP_RESUME}) == C.FRSP_RESUME
    assert cpu.f[27] == 448.0  # the stock frsp still ran
    assert cpu.rd(STACK + C.SLOT_VALUE, 4) == f32(448.0 * C.CROP)
    assert cpu.r[12] == 0x1234_5678_9ABC and cpu.f[0] == 7.5


@pytest.mark.parametrize("hook,resume", C.TOP_VERTICES)
def test_each_top_vertex_gets_the_crop_as_its_texture_y(patched, hook, resume):
    cpu = cpu_for(patched)
    cpu.wr(STACK + C.SLOT_VALUE, 4, f32(16.0))
    cpu.r[0] = 0
    assert cpu.run(hook, {resume}) == resume
    assert cpu.rd(STACK + 0xA4, 4) == f32(16.0)
    assert cpu.r[12] == 0x1234_5678_9ABC


def test_only_the_expected_words_changed(patched):
    stock = Path(os.environ["PS2_NETEMU_SELF"]).read_bytes()
    before = P.extend_text(S.unpack(stock))
    changed = {i & ~3 for i in range(len(before)) if before[i] != patched[i]}
    cave = {P.va_to_off(patched, C.CAVE_VA if hasattr(C, "CAVE_VA") else P.CAVE_VA, 4) + k for k in range(0, 0x6C0, 4)}
    outside = {P.va_to_off(patched, va, 4) for va in (C.FRSP_VA, *[h for h, _ in C.TOP_VERTICES])}
    assert changed <= cave | outside and outside <= changed
