"""The fixed table cave: matches the ISO file name, stores nothing outside the stack."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cardfile import BUF, Files, hook

import cave_table as T
import ps2_netemu_patch as P
import selfio as S

ISOS = [
    "/dev_hdd0/PS2ISO/Grandia III (USA) (Disc 1).iso",
    "/dev_hdd0/PS2ISO/Grandia III (USA) (Disc 2).iso",
    "/dev_hdd0/PS2ISO/Final Fantasy X-2 (USA).iso",
]
GRANDIA = "/savedata/vmc/PS2_Grandia_III__USA_.VM2"


@pytest.fixture(scope="module")
def patched() -> bytes:
    path = os.environ.get("PS2_NETEMU_SELF")
    if not path:
        pytest.skip("stock SELF not provided")
    return P.apply_edits(P.extend_text(S.unpack(Path(path).read_bytes())), P.table_card_edits(ISOS))


def cfg(p: str, typed: bool = True) -> bytes:
    return (b"\x02" if typed else b"") + p.encode() + b"\0" + b"\0" * 64


@pytest.mark.parametrize("iso,card", [
    (ISOS[0], GRANDIA), (ISOS[1], GRANDIA), (ISOS[2], "/savedata/vmc/PS2_Final_Fantasy_X-2__USA_.VM2"),
])
@pytest.mark.parametrize("typed", [True, False])
def test_every_listed_iso_gets_its_game_card(patched, iso, card, typed):
    cpu = hook(patched, Files(cfg(iso, typed)))
    assert cpu.cstr(cpu.r[5]) == card


@pytest.mark.parametrize("content", [
    cfg("/dev_hdd0/PS2ISO/Unknown (USA).iso"), cfg("/dev_hdd0/PS2ISO/Grandia III (USA) (Disc 3).iso"),
    cfg("/dev_hdd0/PS2ISO/Grandia III (USA) (Disc 1).iso.bak"), b"", None, b"\x02\0",
])
def test_unlisted_or_unreadable_leaves_the_shared_card(patched, content):
    assert hook(patched, Files(content)).r[5] == BUF


def test_a_name_that_only_starts_like_an_entry_does_not_match(patched):
    assert hook(patched, Files(cfg("/x/Grandia III (USA) (Disc 1).is"))).r[5] == BUF


def test_nothing_is_stored_outside_the_stack(patched):
    cpu = hook(patched, Files(cfg(ISOS[0])))
    assert not [a for a in cpu.mem if P.CAVE_VA <= a < P.CAVE_VA + P.CAVE_SIZE]


def test_the_table_has_one_record_per_name():
    t = T.table(ISOS + [ISOS[0]])
    assert t.count(b"\0") == 2 * 3 + 1 and t.endswith(b"\0\0")


def test_it_fits_the_cave_with_a_few_dozen_names():
    many = [f"/dev_hdd0/PS2ISO/Some Game Number {n} (USA).iso" for n in range(12)]
    P.table_card_edits(many)
