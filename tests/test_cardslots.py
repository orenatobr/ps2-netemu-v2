"""The slot table cave: fixed slot paths chosen through the table file, nothing stored outside the stack."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ppc_interp import Cpu
from test_cardfile import BUF, SHARED, STACK

import cave_slots as C
import ps2_netemu_patch as P
import selfio as S

NAMES = [
    (3, "Grandia III (USA) (Disc 1).iso"), (3, "Grandia III (USA) (Disc 2).iso"),
    (0, "Final Fantasy X-2 (USA).iso"), (31, "Last Game.iso"),
]
TABLE = b"".join(C.record(s, n) for s, n in NAMES) + b"\0" * C.RECORD


@pytest.fixture(scope="module")
def patched() -> bytes:
    path = os.environ.get("PS2_NETEMU_SELF")
    if not path:
        pytest.skip("stock SELF not provided")
    return P.apply_edits(P.extend_text(S.unpack(Path(path).read_bytes())), P.slots_card_edits())


class Files:
    """/tmp/cfg.bin and the table file, with the emulator's open/read/close stood in for."""

    def __init__(self, cfg: bytes | None, table: bytes | None = TABLE):
        self.files = {"/tmp/cfg.bin": cfg, C.TABLE_PATH.decode(): table}
        self.fds, self.log = {}, []

    def install(self, cpu: Cpu) -> None:
        cpu.mocks[C.OPEN], cpu.mocks[C.READ], cpu.mocks[C.CLOSE] = self.open, self.read, self.close

    def open(self, cpu: Cpu) -> None:
        name = cpu.cstr(cpu.r[4])
        self.log.append(("open", name))
        data = self.files.get(name)
        if data is None:
            cpu.r[3] = (1 << 64) - 1
            return
        fd = 10 + len(self.fds)
        self.fds[fd] = data
        cpu.r[3] = fd

    def read(self, cpu: Cpu) -> None:
        fd, off, buf, size = cpu.r[3], cpu.r[4], cpu.r[5], cpu.r[6]
        self.log.append(("read", fd, off, size))
        data = self.fds[fd][off:off + size]
        for i, b in enumerate(data):
            cpu.mem[buf + i] = b
        cpu.r[3] = len(data)

    def close(self, cpu: Cpu) -> None:
        self.log.append(("close", cpu.r[3]))
        self.fds.pop(cpu.r[3], None)


def cfg(p: str, typed: bool = True) -> bytes:
    return (b"\x02" if typed else b"") + p.encode() + b"\0" + b"\0" * 64


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


@pytest.mark.parametrize("name,slot", [(n, s) for s, n in NAMES])
@pytest.mark.parametrize("typed", [True, False])
def test_every_listed_iso_gets_its_slot(patched, name, slot, typed):
    cpu = hook(patched, Files(cfg("/dev_hdd0/PS2ISO/" + name, typed)))
    assert cpu.cstr(cpu.r[5]) == C.slot_path(slot)


def test_both_discs_share_one_card(patched):
    cards = set()
    for n in (1, 2):
        cpu = hook(patched, Files(cfg(f"/dev_hdd0/PS2ISO/Grandia III (USA) (Disc {n}).iso")))
        cards.add(cpu.cstr(cpu.r[5]))
    assert cards == {C.slot_path(3)}


@pytest.mark.parametrize("content", [
    cfg("/dev_hdd0/PS2ISO/Unknown (USA).iso"), cfg("/dev_hdd0/PS2ISO/Grandia III (USA) (Disc 1).iso.bak"),
    cfg("/dev_hdd0/PS2ISO/Last Game.is"), b"", None, b"\x02\0",
])
def test_unlisted_or_unreadable_leaves_the_shared_card(patched, content):
    assert hook(patched, Files(content)).r[5] == BUF


@pytest.mark.parametrize("table", [None, b"", b"\0" * C.RECORD, bytes([40]) + b"Game.iso".ljust(C.RECORD - 1, b"\0")])
def test_missing_empty_or_bad_table_leaves_the_shared_card(patched, table):
    assert hook(patched, Files(cfg("/x/Game.iso"), table)).r[5] == BUF


def test_a_table_without_the_end_record_stops_at_the_end_of_the_file(patched):
    table = C.record(5, "Other.iso") + C.record(6, "Game.iso")
    cpu = hook(patched, Files(cfg("/x/Game.iso"), table))
    assert cpu.cstr(cpu.r[5]) == C.slot_path(6)
    assert hook(patched, Files(cfg("/x/Nope.iso"), table)).r[5] == BUF


def test_every_file_opened_is_closed_and_the_stack_stays_small(patched):
    files = Files(cfg("/x/Game.iso"), C.record(2, "Game.iso") + b"\0" * C.RECORD)
    cpu = hook(patched, files)
    assert [e for e in files.log if e[0] == "open"] == [("open", "/tmp/cfg.bin"), ("open", C.TABLE_PATH.decode())]
    assert len([e for e in files.log if e[0] == "close"]) == 2 and not files.fds
    low = min(a for a in cpu.mem if STACK - 0x10000 < a <= STACK)
    assert STACK - C.FRAME <= low


@pytest.mark.parametrize("slot,r4,p", [
    (1, 0, SHARED), (0, 5, SHARED), (0, 0, None), (0, 0, "/dev_hdd0/game/NPJA00000/USRDIR/SAVEDATA/SCEVMC0.VME"),
])
def test_everything_else_goes_through_untouched_and_without_touching_files(patched, slot, r4, p):
    files = Files(cfg("/x/Game.iso"))
    assert hook(patched, files, slot, r4, p).r[5] == (0 if p is None else BUF) and files.log == []


def test_registers_and_condition_register_are_as_the_stock_code_expects(patched):
    cpu = hook(patched, Files(cfg("/x/Last Game.iso")))
    assert [cpu.r[n] for n in (3, 4, 6, 7, 8, 9, 10)] == [0, 0, *[0x1000 + n for n in (6, 7, 8, 9, 10)]]
    assert cpu.r[1] == STACK and cpu.lr == 0x4242 and (cpu.r[12] >> 12) & 0xF == 0b1010


def test_nothing_is_stored_outside_the_stack(patched):
    cpu = hook(patched, Files(cfg("/x/Last Game.iso")))
    assert not [a for a in cpu.mem if P.CAVE_VA <= a < P.CAVE_VA + P.CAVE_SIZE]


def test_records_are_fixed_size_and_reject_what_does_not_fit():
    assert len(C.record(1, "a.iso")) == C.RECORD
    assert C.record(C.NSLOTS, "a.iso") == C.record(1, "x" * 200) == C.record(1, "") == b""
