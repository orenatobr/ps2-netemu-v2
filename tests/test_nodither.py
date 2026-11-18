"""No dither (RSX method 0x0300 = 0 appended to the state reset) and no blur (texture filter NEAREST)."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ppc_interp import Cpu

import cave_nodither as N
import ps2_netemu_patch as P
import selfio as S

STRUCT, FIFO, RET = 0x7000_0000, 0x7200_0000, 0x4242


@pytest.fixture(scope="module")
def stock() -> bytes:
    path = os.environ.get("PS2_NETEMU_SELF")
    if not path:
        pytest.skip("stock SELF not provided")
    return S.unpack(Path(path).read_bytes())


@pytest.fixture(scope="module")
def patched(stock: bytes) -> bytes:
    return P.apply_edits(P.extend_text(stock), P.nodither_edits())


def _put(cpu: Cpu, addr: int, val: int, n: int = 8) -> None:
    cpu.wr(addr, n, val)


def _run(patched: bytes, room: int):
    """Run the hooked instruction with `room` bytes left in the command buffer after the stock command."""
    cpu = Cpu(patched)
    _put(cpu, STRUCT + 24, FIFO + 8)  # the stock command (8 bytes at FIFO) is already counted
    _put(cpu, STRUCT + 16, FIFO + 8 + room)
    cpu.r[31], cpu.r[11], cpu.lr = STRUCT, FIFO + 8, RET
    cpu.wr(FIFO, 4, 0x00040304)
    cpu.wr(FIFO + 4, 4, 0)
    assert cpu.run(N.HOOK_VA, {N.RESUME}) == N.RESUME
    return cpu


def test_an_extra_dither_command_is_appended_when_there_is_room(patched):
    cpu = _run(patched, 8)
    assert cpu.rd(FIFO, 4) == 0x00040304 and cpu.rd(FIFO + 4, 4) == 0  # the stock command is intact
    assert cpu.rd(FIFO + 8, 4) == 0x00040300 and cpu.rd(FIFO + 12, 4) == 0  # dither enable = 0
    assert cpu.rd(STRUCT + 24, 8) == FIFO + 16


def test_nothing_is_added_when_the_buffer_is_full(patched):
    cpu = _run(patched, 7)
    assert cpu.rd(FIFO + 8, 4) == 0
    assert cpu.rd(STRUCT + 24, 8) == FIFO + 8  # same pointer as the stock instruction left


def test_the_hook_replaces_exactly_the_stock_instruction(stock):
    off = P.va_to_off(stock, N.HOOK_VA, 4)
    assert int.from_bytes(stock[off:off + 4], "big") == N.HOOK_STOCK


def test_the_texture_binder_now_writes_nearest(stock):
    out = P.apply_edits(stock, P.nofilter_edits())
    off = P.va_to_off(stock, 0x263AE8, 8)
    assert stock[off:off + 4].hex() == "3c000202" and out[off:off + 4].hex() == "3c000101"
    assert out[off + 4:off + 8] == stock[off + 4:off + 8]  # the ori 0x2000 that follows is untouched


def test_the_new_cave_fits_after_the_buffer_card_cave():
    import cave_bufcard
    assert P.CARD_CAVE_VA + cave_bufcard.build(P.CARD_CAVE_VA)[1] <= P.NODITHER_CAVE_VA
    assert P.NODITHER_CAVE_VA + N.build(P.NODITHER_CAVE_VA)[1] <= P.CAVE_VA + P.CAVE_SIZE
