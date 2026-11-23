"""The emulator starts in Full Screen: the video start-up flag and the live Screen Mode word both start as 2.

The tests run the two real instructions of the video start-up (0x262a58) before and after the edit.
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ppc_interp import Cpu

import ps2_netemu_patch as P
import selfio as S

AFTER_FLAG, AFTER_LIVE = 0x262AD0, 0x262B7C  # the instruction after each edited one


@pytest.fixture(scope="module")
def stock_elf() -> bytes:
    path = os.environ.get("PS2_NETEMU_SELF")
    if not path:
        pytest.skip("stock SELF not provided")
    return S.unpack(Path(path).read_bytes())


def run_flag(elf: bytes, host_value: int) -> int:
    """Run the one instruction that keeps the Up Convert byte the host sent in r29 (0x262acc); return r29."""
    cpu = Cpu(elf)
    cpu.r[3] = host_value
    assert cpu.run(P.START_FLAG_VA, {AFTER_FLAG}) == AFTER_FLAG
    return cpu.r[29] & 0xFF


def run_live(elf: bytes, initial_up_convert: int) -> int:
    """Run the one instruction that prepares the argument of the +0x90 setter; return r4."""
    cpu = Cpu(elf)
    cpu.r[3] = initial_up_convert
    assert cpu.run(P.START_LIVE_VA, {AFTER_LIVE}) == AFTER_LIVE
    return cpu.r[4]


@pytest.mark.parametrize("host_value", [0, 1, 2])
def test_stock_follows_what_the_host_sent(stock_elf, host_value):
    assert run_flag(stock_elf, host_value) == host_value


@pytest.mark.parametrize("host_value", [0, 1, 2])
def test_patched_flag_is_full_screen_whatever_the_host_sent(stock_elf, host_value):
    assert run_flag(P.apply_edits(stock_elf, P.start_fullscreen_edits()), host_value) == 2  # also leaves the "Off" path (0)


@pytest.mark.parametrize("initial", [0, 1, 2])
def test_stock_passes_the_initial_up_convert_on(stock_elf, initial):
    assert run_live(stock_elf, initial) == initial


@pytest.mark.parametrize("initial", [0, 1, 2])
def test_patched_live_mode_starts_as_full_screen(stock_elf, initial):
    assert run_live(P.apply_edits(stock_elf, P.start_fullscreen_edits()), initial) == 2


def test_only_the_two_words_change(stock_elf):
    patched = P.apply_edits(stock_elf, P.start_fullscreen_edits())
    diff = {i for i in range(len(stock_elf)) if stock_elf[i] != patched[i]}
    allowed = {P.va_to_off(stock_elf, va, 4) + k for va in (P.START_FLAG_VA, P.START_LIVE_VA) for k in range(4)}
    assert diff and diff <= allowed


def test_refuses_a_file_that_is_not_the_stock_one(stock_elf):
    other = bytearray(stock_elf)
    off = P.va_to_off(stock_elf, P.START_LIVE_VA, 4)
    other[off:off + 4] = b"\0\0\0\0"
    with pytest.raises(ValueError):
        P.apply_edits(bytes(other), P.start_fullscreen_edits())
