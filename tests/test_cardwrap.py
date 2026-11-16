"""The wrapper cave: path built on its own stack, the original function called with it, then a clean return."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ppc_interp import Cpu

import cave_wrap as C
import ps2_netemu_patch as P
import selfio as S

BUF, STACK, RET = 0x7000_0000, 0x7100_0000, 0x4242
SHARED = "/savedata/vmc/PS2.VM2"
ISOS = [
    "/dev_hdd0/PS2ISO/Grandia III (USA) (Disc 2).iso",
    "/dev_hdd0/PS2ISO/Grandia III (USA) (Disc 1).iso",
    "/dev_hdd0/PS2ISO/Final Fantasy X-2 (USA).iso",
    "/dev_hdd0/PS2ISO/Name (USA) [Disc 3 of 4].bin",
    "/dev_hdd0/PS2ISO/Game.iso",
    "/dev_hdd0/PS2ISO/Game (disc 2).ISO",
    "/dev_hdd0/PS2ISO/Tales of Legendia (USA) (En,Ja) (Disc 1).iso",
    "/dev_hdd0/PS2ISO/Naruto: Ultimate Ninja! (USA).iso",
    "/dev_hdd0/PS2ISO/Sub/Folder/Game 2 (Europe).iso",
    "/dev_hdd0/PS2ISO/Gõ (USA).iso",
    "/dev_hdd0/PS2ISO/" + "A" * 200 + ".iso",
]


@pytest.fixture(scope="module")
def patched() -> bytes:
    path = os.environ.get("PS2_NETEMU_SELF")
    if not path:
        pytest.skip("stock SELF not provided")
    return P.apply_edits(P.extend_text(S.unpack(Path(path).read_bytes())), P.crop_edits() + P.wrap_card_edits())


class Files:
    """/tmp/cfg.bin and the existing card files, with the emulator's open/read/close stood in for."""

    def __init__(self, cfg: bytes | None, cards: set[str] | None = None, all_cards: bool = False):
        self.cfg, self.cards, self.all_cards, self.log, self.open_fds = cfg, cards or set(), all_cards, [], set()

    def install(self, cpu: Cpu) -> None:
        cpu.mocks[C.OPEN], cpu.mocks[C.READ], cpu.mocks[C.CLOSE] = self.open, self.read, self.close

    def open(self, cpu: Cpu) -> None:
        name = cpu.cstr(cpu.r[4])
        self.log.append(("open", name))
        if name == "/tmp/cfg.bin" and self.cfg is not None:
            cpu.r[3] = 7
        elif name in self.cards or (self.all_cards and name.startswith("/savedata/vmc/PS2_")):
            cpu.r[3] = 9
        else:
            cpu.r[3] = (1 << 64) - 1
        if cpu.r[3] < 1 << 63:
            self.open_fds.add(cpu.r[3])

    def read(self, cpu: Cpu) -> None:
        fd, off, buf, size = cpu.r[3], cpu.r[4], cpu.r[5], cpu.r[6]
        self.log.append(("read", fd, off, size))
        data = (self.cfg or b"")[off:off + size]
        for i, b in enumerate(data):
            cpu.mem[buf + i] = b
        cpu.r[3] = len(data)

    def close(self, cpu: Cpu) -> None:
        self.log.append(("close", cpu.r[3]))
        self.open_fds.discard(cpu.r[3])


def cfg(p: str, typed: bool = True) -> bytes:
    return (b"\x02" if typed else b"") + p.encode() + b"\0" + b"\0" * 64


class Seen:
    """What the original function would have seen on entry, and the state after it returned."""

    def __init__(self):
        self.entry = None


def call(patched: bytes, files: Files, slot: int = 0, r4: int = 0, p: str | None = SHARED, ret: int = 0x77):
    cpu = Cpu(patched)
    files.install(cpu)
    cpu.r[1], cpu.r[3], cpu.r[4] = STACK, slot, r4
    cpu.r[5] = 0 if p is None else BUF
    for i, b in enumerate((p or "").encode() + b"\0"):
        cpu.mem[BUF + i] = b
    for n in (6, 7, 8, 9, 10):
        cpu.r[n] = 0x1000 + n
    cpu.cr[4] = (1, 0, 1)
    cpu.lr = RET
    assert cpu.run(C.HOOK_VA, {C.RESUME}) == C.RESUME
    seen = Seen()
    seen.entry = {"r1": cpu.r[1], "r3": cpu.r[3], "r4": cpu.r[4], "r5": cpu.r[5], "r6": cpu.r[6], "r7": cpu.r[7],
                  "r9": cpu.r[9], "r10": cpu.r[10], "r12": cpu.r[12], "lr": cpu.lr,
                  "path": cpu.cstr(cpu.r[5]) if cpu.r[5] else None}
    cpu.r[3] = ret  # the original function returns
    assert cpu.run(cpu.lr, {RET}) == RET
    return cpu, seen


@pytest.mark.parametrize("iso", ISOS)
@pytest.mark.parametrize("typed", [True, False])
def test_the_original_function_gets_the_game_card_on_the_stack(patched, iso, typed):
    cpu, seen = call(patched, Files(cfg(iso, typed), all_cards=True))
    assert seen.entry["path"] == "/savedata/vmc/" + C.card_file(iso)
    assert STACK - C.FRAME <= seen.entry["r5"] < STACK  # inside the wrapper frame
    assert seen.entry["r1"] == STACK - C.FRAME


def test_every_disc_of_a_game_gets_the_same_card(patched):
    paths = {call(patched, Files(cfg(f"/dev_hdd0/PS2ISO/Grandia III (USA) (Disc {n}).iso"), all_cards=True))[1].entry["path"]
             for n in (1, 2, 3)}
    assert paths == {"/savedata/vmc/PS2_Grandia_III__USA_.VM2"}


def test_the_other_arguments_and_the_condition_register_reach_the_original(patched):
    _, seen = call(patched, Files(cfg("/x/Game.iso"), all_cards=True))
    e = seen.entry
    assert [e["r3"], e["r4"], e["r6"], e["r7"], e["r9"], e["r10"]] == [0, 0, 0x1006, 0x1007, 0x1009, 0x100A]
    assert (e["r12"] >> 12) & 0xF == 0b1010


def test_it_returns_to_the_caller_with_the_result_and_the_stack_restored(patched):
    cpu, _ = call(patched, Files(cfg("/x/Game.iso"), all_cards=True), ret=0x1234)
    assert cpu.r[3] == 0x1234 and cpu.r[1] == STACK


def test_a_missing_card_leaves_the_shared_card_and_returns_normally(patched):
    cpu, seen = call(patched, Files(cfg("/x/Game.iso")))  # no card file exists
    assert seen.entry["r5"] == BUF and seen.entry["path"] == SHARED and seen.entry["r1"] == STACK
    assert cpu.r[1] == STACK and cpu.r[3] == 0x77


@pytest.mark.parametrize("content", [b"", None, b"\x02\0", cfg("/dev_hdd0/PS2ISO/(Disc 1).iso"), b"\x02relative.iso\0"])
def test_no_usable_name_leaves_the_shared_card(patched, content):
    _, seen = call(patched, Files(content, all_cards=True))
    assert seen.entry["path"] == SHARED and seen.entry["r1"] == STACK


@pytest.mark.parametrize("slot,r4,p", [
    (1, 0, SHARED), (0, 5, SHARED), (0, 0, None), (0, 0, "/dev_hdd0/game/NPJA00000/USRDIR/SAVEDATA/SCEVMC0.VME"),
])
def test_everything_else_runs_the_original_untouched_without_touching_files(patched, slot, r4, p):
    files = Files(cfg("/x/Game.iso"), all_cards=True)
    cpu, seen = call(patched, files, slot, r4, p)
    assert seen.entry["r5"] == (0 if p is None else BUF) and seen.entry["r1"] == STACK and files.log == []
    assert cpu.r[3] == 0x77 and cpu.r[1] == STACK


def test_every_file_opened_is_closed(patched):
    files = Files(cfg("/x/Game.iso"), all_cards=True)
    call(patched, files)
    assert [e[1] for e in files.log if e[0] == "open"] == ["/tmp/cfg.bin", "/savedata/vmc/PS2_Game.VM2"] and not files.open_fds


def test_nothing_is_stored_outside_the_stack(patched):
    cpu, _ = call(patched, Files(cfg("/x/Game (Disc 2).iso"), all_cards=True))
    assert not [a for a in cpu.mem if P.CAVE_VA <= a < P.CAVE_VA + P.CAVE_SIZE]
    assert all(STACK - C.FRAME - 0x100 <= a < STACK + 0x100 or a in range(BUF, BUF + 0x100) for a in cpu.mem)


def test_the_path_always_fits_its_buffer():
    longest = C.card_file("/x/" + "A" * 300 + ".iso")
    assert len("/savedata/vmc/" + longest) + 1 <= C.PATH_SIZE


def test_reference_rule_examples():
    assert C.card_name("/x/Grandia III (USA) (Disc 2).iso") == "Grandia_III__USA_"
    assert C.card_name("/x/(Disc 1).iso") == "" and C.card_file("/x/(Disc 1).iso") == ""
    assert C.card_name("/x/Gõ.iso") == "G__"  # a byte at a time, like the cave


@pytest.fixture(scope="module")
def staged() -> dict[str, bytes]:
    path = os.environ.get("PS2_NETEMU_SELF")
    if not path:
        pytest.skip("stock SELF not provided")
    base = S.unpack(Path(path).read_bytes())
    return {st: P.apply_edits(P.extend_text(base), P.crop_edits() + P.wrap_card_edits(st)) for st in ("title", "fixed")}


def test_stage_title_redirects_even_when_the_card_does_not_exist(staged):
    files = Files(cfg("/x/Game.iso"))  # no card file
    cpu, seen = call(staged["title"], files)
    assert seen.entry["path"] == "/savedata/vmc/PS2_Game.VM2" and cpu.r[1] == STACK
    assert [e[1] for e in files.log if e[0] == "open"] == ["/tmp/cfg.bin"]


def test_stage_fixed_calls_the_original_with_a_fixed_path_on_a_small_stack(staged):
    files = Files(cfg("/x/Game.iso"))
    cpu, seen = call(staged["fixed"], files, ret=0x55)
    assert seen.entry["path"] == C.FIXED_PATH.decode() and files.log == []
    assert STACK - 0x120 <= seen.entry["r1"] and seen.entry["r5"] >= seen.entry["r1"]
    assert cpu.r[1] == STACK and cpu.r[3] == 0x55
    assert [seen.entry[k] for k in ("r3", "r4", "r6", "r7", "r9", "r10")] == [0, 0, 0x1006, 0x1007, 0x1009, 0x100A]


@pytest.mark.parametrize("stage", ["title", "fixed"])
def test_staged_builds_leave_other_cards_alone(staged, stage):
    cpu, seen = call(staged[stage], Files(cfg("/x/Game.iso")), slot=1)
    assert seen.entry["r5"] == BUF and seen.entry["r1"] == STACK
