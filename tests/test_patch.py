"""Tests for the ps2_netemu container tool and the edit applier.

Set PS2_NETEMU_SELF to the stock ps2_netemu.self to also run the checks on the real file.
"""
import hashlib
import hmac
import os
import random
import struct
import sys
import zlib
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import ps2_netemu_patch as P
import selfio as S


def synthetic_elf(size: int = 0x2000) -> bytes:
    """One PT_LOAD at va 0 (file offset 0x200) with counting bytes."""
    ehdr = bytearray(0x40)
    ehdr[:4] = b"\x7fELF"
    struct.pack_into(">Q", ehdr, 0x20, 0x40)
    struct.pack_into(">HH", ehdr, 0x36, 0x38, 1)
    phdr = struct.pack(">IIQQQQQQ", 1, 7, 0x200, 0, 0, size, size, 0x10000)
    return bytes(ehdr) + phdr + b"\0" * (0x200 - 0x40 - 0x38) + bytes(i & 0xFF for i in range(size))


def test_word_edit_changes_only_that_word():
    elf = synthetic_elf()
    old = struct.unpack(">I", elf[0x200 + 0x100:0x200 + 0x104])[0]
    out = P.apply_edits(elf, (P.word(0x100, old, 0x39230064, "x"),))
    diff = [i for i in range(len(elf)) if elf[i] != out[i]]
    assert diff and min(diff) >= 0x200 + 0x100 and max(diff) < 0x200 + 0x104
    assert out[0x200 + 0x100:0x200 + 0x104] == bytes.fromhex("39230064")


def test_edit_refuses_unexpected_bytes():
    with pytest.raises(ValueError, match="expected"):
        P.apply_edits(synthetic_elf(), (P.word(0x100, 0xDEADBEEF, 0, "x"),))


def test_edit_refuses_an_address_outside_the_segment():
    with pytest.raises(ValueError, match="loadable"):
        P.apply_edits(synthetic_elf(), (P.word(0x5000, 0, 0, "x"),))


@pytest.mark.parametrize("delta", [0, 5, 100, 1234])
def test_deflate_to_size_is_exact_and_lossless(delta):
    rng = random.Random(7)
    data = bytes(rng.choice(b"abcdefgh") for _ in range(50_000))
    size = len(zlib.compress(data, 6)) + delta
    out = S.deflate_to_size(data, size)
    assert len(out) == size and zlib.decompress(out) == data


def test_deflate_to_size_refuses_when_it_cannot_fit():
    with pytest.raises(ValueError, match="cannot fit"):
        S.deflate_to_size(os.urandom(5000), 100)


@pytest.fixture(scope="module")
def stock() -> bytes:
    path = os.environ.get("PS2_NETEMU_SELF")
    if not path:
        pytest.skip("stock ps2_netemu.self not provided")
    data = Path(path).read_bytes()
    assert hashlib.sha256(data).hexdigest() == P.STOCK_SHA256
    return data


def test_real_file_hashes_validate(stock):
    sections, _, _, meta = S.parse_all(stock)
    elf = S.unpack(stock)
    assert hashlib.sha1(elf).digest() == stock[S.elf_digest_offset(stock):S.elf_digest_offset(stock) + 20]
    for s in sections:
        raw = stock[s.off:s.off + s.size]
        data = S._ctr(s.key, s.iv, raw) if s.encrypted else raw
        assert hmac.new(s.hmac_key, data, hashlib.sha1).digest() == meta.blob[s.hash_pos:s.hash_pos + 20]


def test_real_file_unmodified_repack_is_identical(stock):
    assert S.repack(stock, S.unpack(stock)) == stock


def test_real_file_patch_keeps_layout_and_valid_hashes(stock):
    out = S.repack(stock, P.apply_edits(S.unpack(stock), P.EXPERIMENT))
    assert len(out) == len(stock)
    sections, _, _, meta = S.parse_all(out)
    elf = S.unpack(out)
    assert hashlib.sha1(elf).digest() == out[S.elf_digest_offset(out):S.elf_digest_offset(out) + 20]
    for s in sections:
        raw = out[s.off:s.off + s.size]
        data = S._ctr(s.key, s.iv, raw) if s.encrypted else raw
        assert hmac.new(s.hmac_key, data, hashlib.sha1).digest() == meta.blob[s.hash_pos:s.hash_pos + 20]
    changed = [i for i in range(len(elf)) if elf[i] != S.unpack(stock)[i]]
    assert 0 < len(changed) <= 32
