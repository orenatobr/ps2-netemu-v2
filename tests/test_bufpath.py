"""The buffer path hook: an empty path buffer of memory card 1 gets the shared card path; a filled one is untouched."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ppc_interp import Cpu

import cave_bufpath as B
import ps2_netemu_patch as P
import selfio as S

BASE = 0x7000_0000


@pytest.fixture(scope="module")
def patched() -> bytes:
    path = os.environ.get("PS2_NETEMU_SELF")
    if not path:
        pytest.skip("stock SELF not provided")
    return P.apply_edits(P.extend_text(S.unpack(Path(path).read_bytes())), P.crop_edits() + P.bufpath_edits())


def run(patched: bytes, content: bytes):
    cpu = Cpu(patched)
    cpu.r[31], cpu.r[0] = BASE, 0x77
    for i, b in enumerate(content):
        cpu.mem[BASE + B.BUFFER + i] = b
    assert cpu.run(B.HOOK_VA, {B.RESUME}) == B.RESUME
    return cpu


def test_an_empty_buffer_gets_the_default_path(patched):
    cpu = run(patched, b"")
    assert cpu.cstr(BASE + B.BUFFER) == B.DEFAULT_PATH.decode()
    assert cpu.r[0] == ord("/")  # the stock lbz was repeated, so the stock compare sees a non-empty buffer


def test_a_filled_buffer_is_left_alone(patched):
    cpu = run(patched, b"/savedata/vmc/OTHER.VM2\0")
    assert cpu.cstr(BASE + B.BUFFER) == "/savedata/vmc/OTHER.VM2" and cpu.r[0] == ord("/")


def test_only_the_buffer_is_written(patched):
    cpu = run(patched, b"")
    written = sorted(a for a in cpu.mem if not (BASE + B.BUFFER <= a < BASE + B.BUFFER + len(B.DEFAULT_PATH) + 1))
    assert written == []


def test_the_path_fits_the_256_byte_buffer():
    assert len(B.DEFAULT_PATH) + 1 <= 0x100
