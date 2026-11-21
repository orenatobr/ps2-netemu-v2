"""The hotkey experiment: SELECT + L1 + R1 switches the live Screen Mode between Normal (1) and Full Screen (2).

The tests run the real cave (and the instruction it replaced) in the PowerPC interpreter, with the pad report bytes the parser holds at the hook.
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ppc_interp import Cpu

import cave_hotkey as H
import ps2_netemu_patch as P
import selfio as S

TOC, MODE_ADDR = 0x751280, 0x3172F70
REPORT = 0x7000_0000
SELECT, L1, R1 = (0x01, 0), (0, 0x04), (0, 0x08)  # (first digital byte, second digital byte)


@pytest.fixture(scope="module")
def patched() -> bytes:
    path = os.environ.get("PS2_NETEMU_SELF")
    if not path:
        pytest.skip("stock SELF not provided")
    return P.apply_edits(P.extend_text(S.unpack(Path(path).read_bytes())), P.hotkey_edits())


def press(patched: bytes, d1: int, d2: int, mode: int = 0, state: int = 0) -> dict:
    """One report goes through the hook. Returns the mode, the state byte, the registers the parser keeps and where the cave ended."""
    cpu = Cpu(patched)
    cpu.r[2], cpu.r[25] = TOC, REPORT
    cpu.mem[REPORT + 8] = 0x5A  # the byte the replaced `lbz r9,8(r25)` loads
    cpu.wr(MODE_ADDR, 4, mode)
    cpu.mem[H.STATE_VA] = state
    cpu.r[0], cpu.r[9], cpu.r[8], cpu.r[10], cpu.r[11] = d1, d2, 0x11, 0x22, 0x33
    end = cpu.run(H.HOOK_VA, {H.RESUME})
    return {"end": end, "mode": cpu.rd(MODE_ADDR, 4), "state": cpu.byte(H.STATE_VA), "r0": cpu.r[0], "r9": cpu.r[9],
            "kept": (cpu.r[8], cpu.r[10], cpu.r[11], cpu.r[25], cpu.r[2])}


def both(*buttons: tuple[int, int]) -> tuple[int, int]:
    return sum(b[0] for b in buttons), sum(b[1] for b in buttons)


@pytest.mark.parametrize("mode,expected", [(0, 2), (1, 2), (2, 1), (7, 2)])
def test_the_combination_switches_between_normal_and_full_screen(patched, mode, expected):
    r = press(patched, *both(SELECT, L1, R1), mode=mode)
    assert r["mode"] == expected and r["state"] == 1


def test_holding_the_combination_switches_only_once(patched):
    first = press(patched, *both(SELECT, L1, R1), mode=1)
    again = press(patched, *both(SELECT, L1, R1), mode=first["mode"], state=first["state"])
    assert first["mode"] == 2 and again["mode"] == 2 and again["state"] == 1


def test_releasing_clears_the_state_and_the_next_press_switches_back(patched):
    on = press(patched, *both(SELECT, L1, R1), mode=1)
    off = press(patched, 0, 0, mode=on["mode"], state=on["state"])
    back = press(patched, *both(SELECT, L1, R1), mode=off["mode"], state=off["state"])
    assert off["mode"] == 2 and off["state"] == 0 and back["mode"] == 1


@pytest.mark.parametrize("buttons", [(SELECT,), (L1, R1), (SELECT, L1), (SELECT, R1), (L1,), (R1,), ()])
def test_a_partial_combination_does_nothing(patched, buttons):
    r = press(patched, *both(*buttons), mode=1)
    assert r["mode"] == 1 and r["state"] == 0


def test_other_buttons_held_with_the_combination_still_switch(patched):
    assert press(patched, 0xFF, 0xFF, mode=1)["mode"] == 2


def test_the_replaced_instruction_runs_and_the_parser_registers_are_kept(patched):
    for d1, d2 in ((0, 0), both(SELECT, L1, R1), both(SELECT, L1)):
        r = press(patched, d1, d2, mode=1)
        assert r["end"] == H.RESUME and r["r9"] == 0x5A and r["r0"] == d1
        assert r["kept"] == (0x11, 0x22, 0x33, REPORT, TOC)


def test_the_hook_replaces_exactly_one_stock_word(patched):
    stock_elf = P.extend_text(S.unpack(Path(os.environ["PS2_NETEMU_SELF"]).read_bytes()))
    off = P.va_to_off(patched, H.HOOK_VA, 4)
    assert stock_elf[off:off + 4] == bytes.fromhex("89390008") and patched[off:off + 4] != stock_elf[off:off + 4]


def test_the_cave_fits_between_the_no_dither_and_the_wide_caves():
    patches, used = H.build(P.HOTKEY_CAVE_VA)
    assert P.NODITHER_CAVE_VA + 0x34 <= P.HOTKEY_CAVE_VA and P.HOTKEY_CAVE_VA + used <= P.WIDE_CAVE_VA
    assert len(patches) == used // 4 + 1


def test_the_state_byte_is_inside_the_data_the_segment_maps():
    assert 0x3172FFC < H.STATE_VA < 0x3175478
