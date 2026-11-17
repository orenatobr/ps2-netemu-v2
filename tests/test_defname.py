"""The default card name hook: a NULL name of slot 0 becomes "PS2"; nothing else changes."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ppc_interp import Cpu

import cave_defname as D
import ps2_netemu_patch as P
import selfio as S

RET = 0x4242


@pytest.fixture(scope="module")
def patched() -> bytes:
    path = os.environ.get("PS2_NETEMU_SELF")
    if not path:
        pytest.skip("stock SELF not provided")
    return P.apply_edits(P.extend_text(S.unpack(Path(path).read_bytes())), P.crop_edits() + P.defname_edits())


def run(patched: bytes, r27: int, r31: int):
    cpu = Cpu(patched)
    cpu.r[27], cpu.r[31], cpu.r[0] = r27, r31, 0x99
    cpu.cr[7] = (0, 0, 0)
    assert cpu.run(D.HOOK_VA, {D.RESUME}) == D.RESUME
    return cpu


def test_a_null_name_of_slot_0_becomes_the_default_name(patched):
    cpu = run(patched, 0, 0)
    assert cpu.cstr(cpu.r[27]) == "PS2" and cpu.cr[7] == (0, 1, 0)  # not equal to zero: the stock code goes on to open the card


@pytest.mark.parametrize("r27,r31", [(0, 1), (0x1234, 0), (0x1234, 1)])
def test_everything_else_keeps_the_stock_result(patched, r27, r31):
    cpu = run(patched, r27, r31)
    assert cpu.r[27] == r27 and cpu.cr[7] == ((0, 1, 0) if r27 else (0, 0, 1))


def test_no_other_register_changes(patched):
    cpu = run(patched, 0, 0)
    assert cpu.r[0] == 0x99 and cpu.r[31] == 0
