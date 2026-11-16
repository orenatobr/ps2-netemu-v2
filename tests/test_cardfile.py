"""The file-name card cave in the interpreter, with the emulator's file calls stood in for (only /tmp/cfg.bin is read)."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ppc_interp import Cpu

import cave_cardfile as C
import ps2_netemu_patch as P
import selfio as S

BUF, STACK = 0x7000_0000, 0x7100_0000
SHARED = "/savedata/vmc/PS2.VM2"
CASES = [
    "/dev_hdd0/PS2ISO/Grandia III (USA) (Disc 2).iso",
    "/dev_hdd0/PS2ISO/Grandia III (USA) (Disc 1).iso",
    "/dev_hdd0/PS2ISO/Final Fantasy X-2 (USA).iso",
    "/dev_hdd0/PS2ISO/Name (Disc 1) (USA).iso",
    "/dev_hdd0/PS2ISO/Name (USA) [Disc 3 of 4].bin",
    "/dev_hdd0/PS2ISO/Game.iso",
    "/dev_hdd0/PS2ISO/Game (disc 2).ISO",
    "/dev_hdd0/PS2ISO/Tales of Legendia (USA) (En,Ja) (Disc 1).iso",
    "/dev_hdd0/PS2ISO/Sub/Folder/Game 2 (Europe).iso",
    "/dev_hdd0/PS2ISO/Naruto: Ultimate Ninja! (USA) & More.iso",
    "/dev_hdd0/PS2ISO/" + "A" * 200 + ".iso",
]


@pytest.fixture(scope="module")
def patched() -> bytes:
    path = os.environ.get("PS2_NETEMU_SELF")
    if not path:
        pytest.skip("stock SELF not provided")
    return P.apply_edits(P.extend_data(P.extend_text(S.unpack(Path(path).read_bytes()))), P.crop_edits() + P.file_card_edits())


class Files:
    def __init__(self, cfg: bytes | None):
        self.cfg, self.log = cfg, []

    def install(self, cpu: Cpu) -> None:
        cpu.mocks[C.OPEN], cpu.mocks[C.READ], cpu.mocks[C.CLOSE] = self.open, self.read, self.close

    def open(self, cpu: Cpu) -> None:
        self.log.append(("open", cpu.r[3], cpu.cstr(cpu.r[4])))
        cpu.r[3] = (1 << 64) - 1 if self.cfg is None or cpu.cstr(cpu.r[4]) != "/tmp/cfg.bin" else 7

    def read(self, cpu: Cpu) -> None:
        fd, off, buf, size = cpu.r[3], cpu.r[4], cpu.r[5], cpu.r[6]
        self.log.append(("read", fd, off, size))
        data = (self.cfg or b"")[off:off + size]
        for i, b in enumerate(data):
            cpu.mem[buf + i] = b
        cpu.r[3] = len(data)

    def close(self, cpu: Cpu) -> None:
        self.log.append(("close", cpu.r[3]))


def cfg(path: str) -> bytes:
    return b"\x02" + path.encode() + b"\0" + b"\0" * 64


def hook(patched: bytes, files: Files, slot: int = 0, r4: int = 0, p: str | None = SHARED) -> Cpu:
    cpu = Cpu(patched)
    files.install(cpu)
    cpu.r[1], cpu.r[3], cpu.r[4] = STACK, slot, r4
    cpu.r[5] = 0 if p is None else BUF
    for i, b in enumerate((p or "").encode() + b"\0"):
        cpu.mem[BUF + i] = b
    for n in (6, 7, 8, 9, 10):
        cpu.r[n] = 0x1000 + n
    cpu.cr[4] = (1, 0, 1)
    cpu.lr = 0x4242
    assert cpu.run(C.HOOK_VA, {C.RESUME}) == C.RESUME
    return cpu


@pytest.mark.parametrize("iso", CASES)
def test_the_card_matches_the_reference_rule(patched, iso):
    cpu = hook(patched, Files(cfg(iso)))
    assert cpu.cstr(cpu.r[5]) == C.card_path(iso)


def test_every_disc_of_a_game_gets_the_same_card(patched):
    paths = {hook(patched, Files(cfg(f"/dev_hdd0/PS2ISO/Grandia III (USA) (Disc {n}).iso"))).cstr(P.SCRATCH_VA) for n in (1, 2, 3)}
    assert paths == {"/savedata/vmc/PS2_Grandia_III__USA_.VM2"}


def test_the_card_names_only_use_safe_characters(patched):
    for iso in CASES:
        name = C.card_path(iso)
        assert all(c.isascii() and (c.isalnum() or c in "/_.-") for c in name)


def test_the_file_is_opened_read_once_and_closed(patched):
    files = Files(cfg("/dev_hdd0/PS2ISO/Game.iso"))
    hook(patched, files)
    assert files.log == [("open", 0, "/tmp/cfg.bin"), ("read", 7, 0, C.BUF_SIZE), ("close", 7)]


def test_registers_stack_and_condition_register_are_as_the_stock_code_expects(patched):
    cpu = hook(patched, Files(cfg("/dev_hdd0/PS2ISO/Game.iso")))
    assert [cpu.r[n] for n in (3, 4, 6, 7, 8, 9, 10)] == [0, 0, *[0x1000 + n for n in (6, 7, 8, 9, 10)]]
    assert cpu.r[1] == STACK and cpu.lr == 0x4242 and (cpu.r[12] >> 12) & 0xF == 0b1010


def test_the_stack_stays_inside_the_small_frame(patched):
    cpu = hook(patched, Files(cfg("/dev_hdd0/PS2ISO/Game (Disc 2).iso")))
    low = min(a for a in cpu.mem if STACK - 0x10000 < a <= STACK)
    assert STACK - C.FRAME <= low and C.FRAME <= 0x1D0


@pytest.mark.parametrize("content", [None, b"", b"\x02\0\0\0", cfg("/dev_hdd0/PS2ISO/(Disc 1).iso")])
def test_no_usable_name_leaves_the_shared_card(patched, content):
    assert hook(patched, Files(content)).r[5] == BUF


@pytest.mark.parametrize("slot,r4,p", [
    (1, 0, SHARED),  # memory card 2 is left alone
    (0, 5, SHARED),  # r4 must be 0
    (0, 0, None),  # no path: the card object already holds one
    (0, 0, "/dev_hdd0/game/NPJA00000/USRDIR/SAVEDATA/SCEVMC0.VME"),  # PS2 Classics layout
    (0, 0, "/savedata/vmcX/PS2.VM2"),
])
def test_everything_else_goes_through_untouched_and_without_touching_files(patched, slot, r4, p):
    files = Files(cfg("/dev_hdd0/PS2ISO/Game.iso"))
    cpu = hook(patched, files, slot, r4, p)
    assert cpu.r[5] == (0 if p is None else BUF) and files.log == []


def test_reference_rule_examples():
    assert C.card_name("/x/Grandia III (USA) (Disc 2).iso") == "Grandia_III__USA_"
    assert C.card_name("/x/(Disc 1).iso") == ""


@pytest.mark.parametrize("iso", CASES[:4] + ["/x/Missing.iso"])
def test_nothing_is_ever_stored_into_the_code_page(patched, iso):
    cpu = hook(patched, Files(cfg(iso)))
    assert not [a for a in cpu.mem if P.CAVE_VA <= a < P.CAVE_VA + P.CAVE_SIZE]


def test_the_path_is_built_inside_the_extended_data_segment(patched):
    cpu = hook(patched, Files(cfg("/dev_hdd0/PS2ISO/Game.iso")))
    assert cpu.r[5] == P.SCRATCH_VA and P.SCRATCH_VA + C.PATH_SIZE <= 0x74F000


def test_the_data_segment_extension_stays_in_its_page_and_changes_only_the_sizes():
    path = os.environ.get("PS2_NETEMU_SELF")
    if not path:
        pytest.skip("stock SELF not provided")
    elf = S.unpack(Path(path).read_bytes())
    out = P.extend_data(elf)
    assert len(out) == len(elf)
    diff = [i for i in range(len(elf)) if elf[i] != out[i]]
    assert diff and all(i < 0x400 for i in diff)
