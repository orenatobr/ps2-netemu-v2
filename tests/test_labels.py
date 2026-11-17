"""The screen mode value label is renamed from Normal to 4:3 without moving anything in the string tables."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import ps2_netemu_patch as P
import selfio as S


@pytest.fixture(scope="module")
def images() -> tuple[bytes, bytes]:
    path = os.environ.get("PS2_NETEMU_SELF")
    if not path:
        pytest.skip("stock SELF not provided")
    stock = S.unpack(Path(path).read_bytes())
    return stock, P.apply_edits(stock, P.screen_mode_label_edits())


def test_every_label_is_renamed_and_nothing_else_changes(images):
    stock, patched = images
    changed = {i for i in range(len(stock)) if stock[i] != patched[i]}
    expected = {off + k for va, old in P.SCREEN_MODE_LABELS for off in [P.va_to_off(stock, va, len(old))] for k in range(len(old))}
    assert changed <= expected and len(patched) == len(stock)
    for va, old in P.SCREEN_MODE_LABELS:
        off = P.va_to_off(stock, va, len(old))
        assert patched[off:off + len(old)].rstrip(b" ") == b"4:3" and patched[off + len(old)] == 0


def test_the_string_after_each_label_still_starts_where_it_did(images):
    stock, patched = images
    for va, old in P.SCREEN_MODE_LABELS:
        off = P.va_to_off(stock, va, len(old)) + len(old) + 1
        assert stock[off:off + 4] == patched[off:off + 4]


def test_the_portuguese_label_is_in_place(images):
    _, patched = images
    off = P.va_to_off(patched, 0x71CD93, 6)
    assert patched[off - 11:off + 21] == b"Desativado\x004:3   \x00Modo de tela\x00-\x00" or patched[off:off + 6] == b"4:3   "
