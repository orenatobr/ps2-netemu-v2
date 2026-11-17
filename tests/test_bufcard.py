"""The buffer card hook: the game card path goes into the emulator's path buffer; every failure keeps a sane buffer."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ppc_interp import Cpu
from test_cardwrap import Files, cfg

import cave_bufcard as B
import cave_wrap as W
import ps2_netemu_patch as P
import selfio as S

BASE, STACK, DEFAULT = 0x7000_0000, 0x7100_0000, B.DEFAULT_PATH.decode()


@pytest.fixture(scope="module")
def patched() -> bytes:
    path = os.environ.get("PS2_NETEMU_SELF")
    if not path:
        pytest.skip("stock SELF not provided")
    return P.apply_edits(P.extend_text(S.unpack(Path(path).read_bytes())), P.crop_edits() + P.bufcard_edits())


def run(patched: bytes, files: Files, buffer: bytes = b"", marker: int = 0):
    cpu = Cpu(patched)
    files.install(cpu)
    cpu.r[1], cpu.r[31], cpu.r[0], cpu.lr = STACK, BASE, 0x77, 0x4242
    for n in (3, 4, 5, 6, 7, 8, 9, 10):
        cpu.r[n] = 0x1000 + n
    for i, b in enumerate(buffer + b"\0"):
        cpu.mem[BASE + B.BUFFER + i] = b
    cpu.mem[BASE + B.MARKER] = marker
    assert cpu.run(B.HOOK_VA, {B.RESUME}) == B.RESUME
    return cpu


def buf(cpu: Cpu) -> str:
    return cpu.cstr(BASE + B.BUFFER)


GRANDIA = "/dev_hdd0/PS2ISO/Grandia III (USA) (Disc 2).iso"


@pytest.mark.parametrize("buffer", [b"", b"/savedata/vmc/PS2.VM2", b"/savedata/vmc/PS2_Other.VM2"])
def test_the_game_card_replaces_an_empty_or_vmc_buffer(patched, buffer):
    cpu = run(patched, Files(cfg(GRANDIA), all_cards=True), buffer)
    assert buf(cpu) == "/savedata/vmc/" + W.card_file(GRANDIA) and cpu.mem[BASE + B.MARKER] == 1


def test_every_disc_of_a_game_gets_the_same_card(patched):
    got = {buf(run(patched, Files(cfg(f"/dev_hdd0/PS2ISO/Grandia III (USA) (Disc {n}).iso"), all_cards=True))) for n in (1, 2, 3)}
    assert got == {"/savedata/vmc/PS2_Grandia_III__USA_.VM2"}


def test_a_missing_game_card_leaves_the_shared_card(patched):
    cpu = run(patched, Files(cfg(GRANDIA)))  # no card file exists
    assert buf(cpu) == DEFAULT and cpu.mem[BASE + B.MARKER] == 1


def test_a_missing_game_card_leaves_a_launcher_path_as_it_is(patched):
    cpu = run(patched, Files(cfg(GRANDIA)), b"/savedata/vmc/Launcher.VM2")
    assert buf(cpu) == "/savedata/vmc/Launcher.VM2"


@pytest.mark.parametrize("content", [None, b"", b"\x02\0", cfg("/dev_hdd0/PS2ISO/(Disc 1).iso")])
def test_an_unreadable_or_titleless_cfg_leaves_the_shared_card(patched, content):
    assert buf(run(patched, Files(content, all_cards=True))) == DEFAULT


def test_a_path_that_is_not_in_the_vmc_folder_is_never_touched(patched):
    files = Files(cfg(GRANDIA), all_cards=True)
    cpu = run(patched, files, b"/dev_hdd0/game/NPJA00000/USRDIR/SAVEDATA/SCEVMC0.VME")
    assert buf(cpu) == "/dev_hdd0/game/NPJA00000/USRDIR/SAVEDATA/SCEVMC0.VME" and files.log == []


def test_after_the_marker_nothing_runs_again(patched):
    files = Files(cfg(GRANDIA), all_cards=True)
    cpu = run(patched, files, b"/savedata/vmc/Whatever.VM2", marker=1)
    assert buf(cpu) == "/savedata/vmc/Whatever.VM2" and files.log == []


def test_registers_stack_and_the_stock_instruction(patched):
    cpu = run(patched, Files(cfg(GRANDIA), all_cards=True))
    assert cpu.r[1] == STACK and cpu.lr == 0x4242 and cpu.r[31] == BASE
    assert [cpu.r[n] for n in (3, 4, 5, 6, 7, 8, 9, 10)] == [0x1000 + n for n in (3, 4, 5, 6, 7, 8, 9, 10)]
    assert cpu.r[0] == ord("/")  # the stock lbz was repeated


def test_only_the_stack_and_the_buffer_are_written(patched):
    cpu = run(patched, Files(cfg(GRANDIA), all_cards=True))
    outside = [a for a in cpu.mem if not (STACK - B.FRAME - 0x10 <= a < STACK + 0x20 or BASE + B.BUFFER <= a <= BASE + B.MARKER)]
    assert outside == []


def test_every_file_opened_is_closed(patched):
    files = Files(cfg(GRANDIA), all_cards=True)
    run(patched, files)
    assert not files.open_fds


def test_the_path_fits_the_buffer_and_the_marker_is_outside_it():
    assert len("/savedata/vmc/" + W.card_file("/x/" + "A" * 300 + ".iso")) + 1 <= W.PATH_SIZE
    assert B.MARKER - B.BUFFER == 0xFF
