"""Tests for the blank PS2 memory card generator.

Set PS2_REAL_VM2 to a card made by the console to also check the ECC rule on every written page of it.
"""
import os
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import ps2card as C

PAGE_RAW = C.PAGE + C.SPARE


@pytest.fixture(scope="module")
def blank() -> bytes:
    return C.blank_card()


def page(card: bytes, p: int) -> bytes:
    return card[p * PAGE_RAW:p * PAGE_RAW + C.PAGE]


def spare(card: bytes, p: int) -> bytes:
    return card[p * PAGE_RAW + C.PAGE:(p + 1) * PAGE_RAW]


def test_size_matches_the_console_card_files(blank):
    assert len(blank) == 8_650_752


def test_superblock_starts_with_the_format_name(blank):
    assert page(blank, 0).startswith(b"Sony PS2 Memory Card Format 1.2.0.0")


def test_every_written_page_has_its_ecc_and_the_rest_stays_erased(blank):
    written = [p for p in range(C.PAGES) if blank[p * PAGE_RAW:(p + 1) * PAGE_RAW] != b"\xff" * PAGE_RAW]
    assert written == [0, *range(16, 84)]  # superblock, indirect FAT, 32 FAT clusters, root directory
    for p in written:
        assert spare(blank, p) == C.spare_for(page(blank, p))


def test_the_fat_is_free_except_the_root_directory_cluster(blank):
    fat = b"".join(page(blank, 2 * c) + page(blank, 2 * c + 1) for c in range(9, 41))
    entries = struct.unpack(f"<{len(fat) // 4}I", fat)
    assert entries[0] == C.CHAIN_END and set(entries[1:]) == {C.FREE}


def test_the_indirect_fat_lists_the_32_fat_clusters(blank):
    ifc = page(blank, 16) + page(blank, 17)
    assert list(struct.unpack("<32I", ifc[:128])) == list(range(9, 41))


def test_the_root_directory_has_only_dot_and_dotdot(blank):
    root = page(blank, 82) + page(blank, 83)
    (mode0, len0), (mode1, len1) = struct.unpack("<II", root[:8]), struct.unpack("<II", root[512:520])
    assert (mode0, len0, mode1, len1) == (0x8427, 2, 0xA426, 0)
    assert root[64:65] == b"." and root[512 + 64:512 + 66] == b".."


def test_ecc_of_an_erased_chunk_is_stable():
    assert C.ecc(b"\xff" * 128) == C.ecc(b"\xff" * 128) and len(C.ecc(b"\x00" * 128)) == 3


@pytest.mark.skipif("PS2_REAL_VM2" not in os.environ, reason="real card not provided")
def test_ecc_rule_matches_every_written_page_of_a_real_card():
    real = Path(os.environ["PS2_REAL_VM2"]).read_bytes()
    n = 0
    for p in range(C.PAGES):
        raw = real[p * PAGE_RAW:(p + 1) * PAGE_RAW]
        if raw == b"\xff" * PAGE_RAW:
            continue
        n += 1
        assert C.spare_for(raw[:C.PAGE]) == raw[C.PAGE:]
    assert n > 0
    assert C.blank_card()[:PAGE_RAW] == real[:PAGE_RAW]
