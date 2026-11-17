import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import make_cards as M


def test_every_missing_card_once_for_all_the_discs_of_a_game():
    isos = ["Grandia III (USA) (Disc 1).iso", "Grandia III (USA) (Disc 2).iso", "Final Fantasy X-2 (USA).iso", "notes.txt"]
    got = M.missing_cards(isos, [])
    assert set(got) == {"PS2_Grandia_III__USA_.VM2", "PS2_Final_Fantasy_X-2__USA_.VM2"}
    assert got["PS2_Grandia_III__USA_.VM2"] == "Grandia III (USA) (Disc 1).iso"


def test_existing_cards_are_never_listed():
    assert M.missing_cards(["Game.iso"], ["PS2_Game.VM2", "PS2.VM2"]) == {}


def test_titleless_and_foreign_files_are_ignored():
    assert M.missing_cards(["(Disc 1).iso", "x.CONFIG", "y.zip"], []) == {}
