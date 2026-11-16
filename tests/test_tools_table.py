import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import cave_slots as C
import tools_table as T

ISOS = ["/p/Grandia III (USA) (Disc 1).iso", "/p/Grandia III (USA) (Disc 2).iso", "/p/Alpha (USA).iso"]


def test_discs_of_a_game_share_a_slot_in_title_order():
    assert T.assign(ISOS) == {"Alpha (USA).iso": 0, "Grandia III (USA) (Disc 1).iso": 1, "Grandia III (USA) (Disc 2).iso": 1}


def test_table_ends_with_an_empty_record_and_has_fixed_size_records():
    t = T.table_bytes(ISOS)
    assert len(t) == 4 * C.RECORD and t[-C.RECORD:] == b"\0" * C.RECORD


def test_names_that_do_not_fit_are_left_out():
    assert T.assign(["/p/" + "x" * 200 + ".iso"]) == {}
