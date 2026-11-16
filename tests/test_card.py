"""Run the card cave in the interpreter against the real emulator code."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ppc_interp import Cpu

import cave_card as C
import ps2_netemu_patch as P
import selfio as S

pytestmark = pytest.mark.skipif("PS2_NETEMU_SELF" not in os.environ, reason="stock SELF not provided")
NEW = b"/savedata/vmc/SLUS-21452.VM2"


@pytest.fixture(scope="module")
def patched() -> bytes:
    stock = Path(os.environ["PS2_NETEMU_SELF"]).read_bytes()
    elf = P.extend_text(S.unpack(stock))
    return P.apply_edits(elf, P.crop_edits() + P.cave_edits(C.build(P.CARD_CAVE_VA, NEW)[0]))


def run(elf: bytes, slot: int, r4: int, path: str | None) -> Cpu:
    cpu = Cpu(elf)
    cpu.r[3], cpu.r[4] = slot, r4
    if path is None:
        cpu.r[5] = 0
    else:
        cpu.r[5] = 0x7000_0000
        for i, b in enumerate(path.encode() + b"\0"):
            cpu.mem[0x7000_0000 + i] = b
    cpu.cr[4] = (1, 0, 1)  # something recognisable in the saved condition register
    assert cpu.run(C.HOOK_VA, {C.RESUME}) == C.RESUME
    return cpu


def test_slot_1_with_the_shared_card_path_is_redirected(patched):
    cpu = run(patched, 0, 0, "/savedata/vmc/PS2.VM2")
    assert cpu.cstr(cpu.r[5]) == NEW.decode()


def test_the_condition_register_is_saved_as_the_stock_code_did(patched):
    cpu = run(patched, 0, 0, "/savedata/vmc/PS2.VM2")
    assert (cpu.r[12] >> 12) & 0xF == 0b1010  # cr4: lt and eq set


@pytest.mark.parametrize("slot,r4,path", [
    (1, 0, "/savedata/vmc/PS2.VM2"),  # memory card 2 is left alone
    (0, 5, "/savedata/vmc/PS2.VM2"),  # r4 must be 0
    (0, 0, None),  # no path: the card object already holds one
    (0, 0, "/dev_hdd0/game/NPJA00000/USRDIR/SAVEDATA/SCEVMC0.VME"),  # PS2 Classics layout
    (0, 0, "/savedata/vmcX/PS2.VM2"),
])
def test_everything_else_goes_through_untouched(patched, slot, r4, path):
    cpu = run(patched, slot, r4, path)
    assert cpu.r[5] == (0 if path is None else 0x7000_0000)


def test_the_path_must_start_with_the_vmc_folder():
    with pytest.raises(ValueError, match="start with"):
        C.build(P.CARD_CAVE_VA, b"/dev_hdd0/x.VM2")
