"""The Up Convert experiment: the settings copy stores a fixed Screen Mode value, nothing else changes.

The tests run the two real instructions of the emulator that copy the byte (0x11ad18 and 0x11ad1c) before and after the edit.
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

BLOCK, SETTINGS, DONE = 0x7000_0000, 0x7100_0000, 0x11AD20  # r29 = host block, r28 = settings object, address after the byte store
HOST_BYTE_OFF, UP_CONVERT_OFF = 0x2284, 0x28


@pytest.fixture(scope="module")
def stock_elf() -> bytes:
    path = os.environ.get("PS2_NETEMU_SELF")
    if not path:
        pytest.skip("stock SELF not provided")
    return S.unpack(Path(path).read_bytes())


def run_copy(elf: bytes, host_value: int) -> int:
    """Run the settings copy step with `host_value` in the host block and return the Up Convert byte it stored."""
    cpu = Cpu(elf)
    cpu.mem[BLOCK + HOST_BYTE_OFF] = host_value
    cpu.mem[SETTINGS + UP_CONVERT_OFF] = 0xEE  # a marker, to see that the byte really was written
    cpu.r[29], cpu.r[28] = BLOCK, SETTINGS
    assert cpu.run(P.UP_CONVERT_VA, {DONE}) == DONE
    return cpu.byte(SETTINGS + UP_CONVERT_OFF)


@pytest.mark.parametrize("host_value", [0, 1, 2])
def test_stock_copies_the_byte_the_host_sent(stock_elf, host_value):
    assert run_copy(stock_elf, host_value) == host_value


@pytest.mark.parametrize("mode", [0, 1, 2])
@pytest.mark.parametrize("host_value", [0, 1, 2])
def test_patched_stores_the_forced_mode_whatever_the_host_sent(stock_elf, mode, host_value):
    patched = P.apply_edits(stock_elf, P.up_convert_edits(mode))
    assert run_copy(patched, host_value) == mode


def test_only_the_one_word_changes(stock_elf):
    patched = P.apply_edits(stock_elf, P.up_convert_edits(2))
    diff = [i for i in range(len(stock_elf)) if stock_elf[i] != patched[i]]
    off = P.va_to_off(stock_elf, P.UP_CONVERT_VA, 4)
    assert diff and off <= min(diff) and max(diff) < off + 4
    assert patched[off:off + 4] == bytes.fromhex("38000002")


@pytest.mark.parametrize("mode", [-1, 3, 255])
def test_values_outside_the_menu_are_refused(mode):
    with pytest.raises(ValueError):
        P.up_convert_edits(mode)


def test_refuses_a_file_that_is_not_the_stock_one(stock_elf):
    other = bytearray(stock_elf)
    off = P.va_to_off(stock_elf, P.UP_CONVERT_VA, 4)
    other[off:off + 4] = b"\0\0\0\0"
    with pytest.raises(ValueError):
        P.apply_edits(bytes(other), P.up_convert_edits(2))
