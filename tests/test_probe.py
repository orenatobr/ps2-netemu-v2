"""The step 1 probe, run in the interpreter with the file calls stood in for."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ppc_interp import Cpu

import cave_probe as C
import ps2_netemu_patch as P
import selfio as S

BUF, STACK = 0x7000_0000, 0x7100_0000


@pytest.fixture(scope="module")
def patched() -> bytes:
    path = os.environ.get("PS2_NETEMU_SELF")
    if not path:
        pytest.skip("stock SELF not provided")
    return P.apply_edits(P.extend_text(S.unpack(Path(path).read_bytes())), P.crop_edits() + P.probe_edits())


def run(patched: bytes, cfg: bytes | None, slot: int = 0, path: str = "/savedata/vmc/PS2.VM2") -> Cpu:
    cpu = Cpu(patched)

    def open_(c: Cpu) -> None:
        c.r[3] = (1 << 64) - 1 if cfg is None else 5

    def read(c: Cpu) -> None:
        for i, b in enumerate((cfg or b"")[: c.r[6]]):
            c.mem[c.r[5] + i] = b
        c.r[3] = len(cfg or b"")

    cpu.mocks[C.OPEN], cpu.mocks[C.READ], cpu.mocks[C.CLOSE] = open_, read, lambda c: None
    cpu.r[1], cpu.r[3], cpu.r[4], cpu.r[5] = STACK, slot, 0, BUF
    for i, b in enumerate(path.encode() + b"\0"):
        cpu.mem[BUF + i] = b
    cpu.lr = 0x4242
    assert cpu.run(C.HOOK_VA, {C.RESUME}) == C.RESUME
    return cpu


def test_a_successful_read_redirects_to_the_test_card(patched):
    cpu = run(patched, b"\x02/dev_hdd0/PS2ISO/G.iso\0")
    assert cpu.cstr(cpu.r[5]) == "/savedata/vmc/PS2_TEST.VM2"


@pytest.mark.parametrize("cfg", [None, b""])
def test_a_failed_open_or_empty_read_leaves_the_shared_card(patched, cfg):
    assert run(patched, cfg).r[5] == BUF


def test_other_slots_and_stack_are_untouched(patched):
    cpu = run(patched, b"\x02x", slot=1)
    assert cpu.r[5] == BUF and cpu.r[1] == STACK and cpu.lr == 0x4242
