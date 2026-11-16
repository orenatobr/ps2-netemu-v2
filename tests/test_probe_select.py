"""The select probe: the card follows the format of /tmp/cfg.bin and nothing is stored outside the stack frame."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cardfile import BUF, SHARED, Files, hook

import ps2_netemu_patch as P
import selfio as S

A, B = "/savedata/vmc/PS2_SLUS-21345.VM2", "/savedata/vmc/PS2_TEST.VM2"


@pytest.fixture(scope="module")
def patched() -> bytes:
    path = os.environ.get("PS2_NETEMU_SELF")
    if not path:
        pytest.skip("stock SELF not provided")
    return P.apply_edits(P.extend_text(S.unpack(Path(path).read_bytes())), P.probe_edits(select=True))


@pytest.mark.parametrize("cfg,card", [
    (b"\x02/dev_hdd0/PS2ISO/Game.iso\0" + b"\0" * 64, A),
    (b"/dev_hdd0/PS2ISO/Game.iso\0" + b"\0" * 64, B),
    (b"\x02\x02\x02\0", None),
    (b"", None),
    (None, None),
])
def test_the_card_follows_the_cfg_format(patched, cfg, card):
    cpu = hook(patched, Files(cfg))
    assert (cpu.cstr(cpu.r[5]) if card else cpu.r[5]) == (card or BUF)


def test_nothing_is_stored_outside_the_stack(patched):
    cpu = hook(patched, Files(b"\x02/x/Game.iso\0"))
    assert not [a for a in cpu.mem if P.CAVE_VA <= a < P.CAVE_VA + P.CAVE_SIZE]


def test_other_cards_are_untouched(patched):
    assert hook(patched, Files(b"\x02/x/Game.iso\0"), slot=1).r[5] == BUF
    assert SHARED
