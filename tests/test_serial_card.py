"""Run the serial and card caves in the interpreter against the real emulator code."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ppc_interp import Cpu

import cave_cardname as C
import cave_serial as V
import ps2_netemu_patch as P
import selfio as S

pytestmark = pytest.mark.skipif("PS2_NETEMU_SELF" not in os.environ, reason="stock SELF not provided")
BUF, STACK = 0x7000_0000, 0x7100_0000


@pytest.fixture(scope="module")
def patched() -> bytes:
    stock = Path(os.environ["PS2_NETEMU_SELF"]).read_bytes()
    return P.apply_edits(P.extend_text(S.unpack(stock)), P.crop_edits() + P.serial_card_edits())


def disc(cnf: bytes, patched: bytes) -> tuple[Cpu, list]:
    """Run the call site of the parser with `cnf` in the buffer; returns the cpu and the mock's calls."""
    cpu = Cpu(patched)
    calls: list[tuple[int, int, int]] = []

    def parse(c: Cpu) -> None:
        calls.append((c.r[3], c.r[4], c.r[5]))
        c.r[3] = 1  # the original returns a flag

    cpu.mocks[V.PARSE_VA] = parse
    cpu.r[1], cpu.r[3], cpu.r[4], cpu.r[5] = STACK, 0x1234, BUF, len(cnf)
    for i, b in enumerate(cnf):
        cpu.mem[BUF + i] = b
    assert cpu.run(V.CALL_VA, {V.CALL_VA + 4}) == V.CALL_VA + 4
    return cpu, calls


def path(cpu: Cpu) -> str:
    return cpu.cstr(P.PATH_VA)


@pytest.mark.parametrize("cnf,expected", [
    (b"BOOT2 = cdrom0:\\SLUS_213.45;1\r\nVER = 1.00\r\nVMODE = NTSC\r\n", "SLUS-21345"),
    (b"BOOT2 = cdrom0:\\SCUS_974.08;1\r\nVER = 1.00\r\n", "SCUS-97408"),
    (b"VER = 1.00\r\nBOOT2=cdrom0:SLES_503.42;1\r\n", "SLES-50342"),
    (b"BOOT2 = cdrom0:/slps_250.01;1\r\n", "SLPS-25001"),  # lower case and a slash
    (b"BOOT2 = cdrom0:\\SLUS_213.45\r\n", "SLUS-21345"),  # no ';1'
])
def test_the_serial_becomes_the_card_name(patched, cnf, expected):
    cpu, _ = disc(cnf, patched)
    assert path(cpu) == f"/savedata/vmc/PS2_{expected}.VM2"


@pytest.mark.parametrize("cnf", [
    b"BOOT = cdrom:\\SLUS_006.62;1\r\nTCB = 4\r\n",  # a PS1 disc has no BOOT2
    b"BOOT2 = cdrom0:\\;1\r\n",  # nothing after the folder
    b"BOOT2 = cdrom0:\\AB;1\r\n",  # too short to be a serial
    b"\r\n\r\n",
])
def test_a_disc_without_a_usable_boot2_leaves_the_shared_card(patched, cnf):
    cpu, _ = disc(cnf, patched)
    assert path(cpu) == ""


def test_the_original_parser_still_runs_with_its_own_arguments_and_result(patched):
    cnf = b"BOOT2 = cdrom0:\\SLUS_213.45;1\r\n"
    cpu, calls = disc(cnf, patched)
    assert calls == [(0x1234, BUF, len(cnf))] and cpu.r[3] == 1


def test_a_new_disc_replaces_the_previous_path(patched):
    first, _ = disc(b"BOOT2 = cdrom0:\\SLUS_213.45;1\r\n", patched)
    cpu = Cpu(patched)
    cpu.mem.update(first.mem)  # the path is memory that survives between calls
    cpu.mocks[V.PARSE_VA] = lambda c: None
    cpu.r[1], cpu.r[4], cpu.r[5] = STACK, BUF, 8
    for i, b in enumerate(b"BOOT = x\r\n"):
        cpu.mem[BUF + i] = b
    cpu.run(V.CALL_VA, {V.CALL_VA + 4})
    assert path(cpu) == ""


def hook(patched: bytes, slot: int, r4: int, p: str | None, card_path: str) -> Cpu:
    cpu = Cpu(patched)
    for i, b in enumerate(card_path.encode() + b"\0"):
        cpu.mem[P.PATH_VA + i] = b
    cpu.r[3], cpu.r[4] = slot, r4
    cpu.r[5] = 0 if p is None else BUF
    for i, b in enumerate((p or "").encode() + b"\0"):
        cpu.mem[BUF + i] = b
    cpu.cr[4] = (1, 0, 1)
    assert cpu.run(C.HOOK_VA, {C.RESUME}) == C.RESUME
    return cpu


GAME = "/savedata/vmc/SLUS-21345.VM2"


def test_slot_1_with_the_shared_card_path_is_redirected_to_the_game_card(patched):
    cpu = hook(patched, 0, 0, "/savedata/vmc/PS2.VM2", GAME)
    assert cpu.cstr(cpu.r[5]) == GAME


def test_the_condition_register_is_saved_as_the_stock_code_did(patched):
    cpu = hook(patched, 0, 0, "/savedata/vmc/PS2.VM2", GAME)
    assert (cpu.r[12] >> 12) & 0xF == 0b1010  # cr4: lt and eq set


def test_without_a_serial_the_shared_card_stays(patched):
    cpu = hook(patched, 0, 0, "/savedata/vmc/PS2.VM2", "")
    assert cpu.r[5] == BUF


@pytest.mark.parametrize("slot,r4,p", [
    (1, 0, "/savedata/vmc/PS2.VM2"),  # memory card 2 is left alone
    (0, 5, "/savedata/vmc/PS2.VM2"),  # r4 must be 0
    (0, 0, None),  # no path: the card object already holds one
    (0, 0, "/dev_hdd0/game/NPJA00000/USRDIR/SAVEDATA/SCEVMC0.VME"),  # PS2 Classics layout
    (0, 0, "/savedata/vmcX/PS2.VM2"),
])
def test_everything_else_goes_through_untouched(patched, slot, r4, p):
    cpu = hook(patched, slot, r4, p, GAME)
    assert cpu.r[5] == (0 if p is None else BUF)


def test_the_static_card_experiment_always_points_slot_1_at_the_fixed_path():
    stock = Path(os.environ.get("PS2_NETEMU_SELF", ""))
    if not stock.is_file():
        pytest.skip("stock SELF not provided")
    patched = P.apply_edits(P.extend_text(S.unpack(stock.read_bytes())), P.crop_edits() + P.static_card_edits())

    def run(slot: int) -> Cpu:
        cpu = Cpu(patched)  # the fixed path is in the patched image: nothing is written to the cave memory
        cpu.r[3], cpu.r[4], cpu.r[5] = slot, 0, BUF
        for i, b in enumerate(b"/savedata/vmc/PS2.VM2\0"):
            cpu.mem[BUF + i] = b
        assert cpu.run(C.HOOK_VA, {C.RESUME}) == C.RESUME
        return cpu

    assert run(0).cstr(run(0).r[5]) == "/savedata/vmc/PS2_SLUS-21345.VM2"
    assert run(1).r[5] == BUF
