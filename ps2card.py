"""Build a blank, formatted PS2 memory card in the PS3 `.VM2` layout (8 MB of data plus 16 bytes of ECC per page).

The layout was read from a real card made by the console (superblock `Sony PS2 Memory Card Format 1.2.0.0`, 8192
clusters of 2 pages, indirect FAT in cluster 8, FAT in clusters 9..40, allocatable area from cluster 41, root
directory at its first cluster) and the ECC rule was fitted on all 5060 written chunks of it. Pages that are not
written stay erased (0xFF data and spare).
"""
from __future__ import annotations

import struct

PAGE, SPARE, PAGES = 512, 16, 16384
CARD_BYTES = PAGES * (PAGE + SPARE)  # 8,650,752
CLUSTER_PAGES = 2
IFC_CLUSTER, FAT_FIRST, FAT_CLUSTERS, ALLOC_OFFSET = 8, 9, 32, 41
FREE, CHAIN_END = 0x7FFFFFFF, 0xFFFFFFFF
COLUMN_BITS = bytes((j << 4) | (7 - j) for j in range(8))  # column parity of bit j: 0x07, 0x16, ..., 0x70
_PARITY = [i.bit_count() & 1 for i in range(256)]
# The 512 bytes of page 0 of a real card (format parameters only: no saves, no names).
SUPERBLOCK = bytes.fromhex(
    "536f6e7920505332204d656d6f7279204361726420466f726d617420312e322e302e30000000000000020200100000ff"
    "0020000029000000c71f000000000000ff030000fe030000000000000000000008000000000000000000000000000000"
    "000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "00000000000000000000000000000000ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
    "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
    "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
    "022bffff000400000001000008000000ffffffff000000000000000000000000411f0000ffffffffffffffffffffffff"
    "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
    "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
    "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
)
TOD = bytes([0, 0, 0, 12, 16, 11]) + struct.pack("<H", 2026)  # 2026-11-16 12:00:00 (sec, min, hour, day, month, year)


def ecc(chunk: bytes) -> bytes:
    """Three ECC bytes (column parity, line parity 0, line parity 1) of a 128 byte chunk."""
    col, lp0, lp1 = 0x77, 0x7F, 0x7F
    for i, b in enumerate(chunk):
        for j in range(8):
            if b >> j & 1:
                col ^= COLUMN_BITS[j]
        if _PARITY[b]:
            lp0 ^= ~i & 0xFF
            lp1 ^= i
    return bytes([col, lp0 & 0x7F, lp1 & 0x7F])


def spare_for(data: bytes) -> bytes:
    """The 16 spare bytes of a written page: four ECC triples and four zero bytes."""
    return b"".join(ecc(data[i:i + 128]) for i in range(0, PAGE, 128)) + b"\0" * 4


def dirent(mode: int, length: int, name: bytes) -> bytes:
    """One 512 byte directory entry of the root directory (cluster 0, parent entry 0)."""
    return (struct.pack("<II", mode, length) + TOD + struct.pack("<II", 0, 0) + TOD + struct.pack("<I", 0)
            + b"\0" * 28 + name.ljust(32, b"\0")).ljust(512, b"\0")


def blank_card() -> bytes:
    """A formatted card with no saves."""
    pages: dict[int, bytes] = {0: SUPERBLOCK.ljust(PAGE, b"\0")}
    ifc = b"".join(struct.pack("<I", FAT_FIRST + i) for i in range(FAT_CLUSTERS)).ljust(2 * PAGE, b"\xff")
    fat = [FREE] * (FAT_CLUSTERS * 256)
    fat[0] = CHAIN_END  # the root directory fills one cluster
    fat_bytes = struct.pack(f"<{len(fat)}I", *fat)
    root = dirent(0x8427, 2, b".") + dirent(0xA426, 0, b"..")
    area = {IFC_CLUSTER: ifc, ALLOC_OFFSET: root}
    area.update({FAT_FIRST + i: fat_bytes[i * 1024:(i + 1) * 1024] for i in range(FAT_CLUSTERS)})
    for cluster, data in area.items():
        for k in range(CLUSTER_PAGES):
            pages[cluster * CLUSTER_PAGES + k] = data[k * PAGE:(k + 1) * PAGE]
    out = bytearray(b"\xff" * CARD_BYTES)
    for p, data in pages.items():
        out[p * (PAGE + SPARE):(p + 1) * (PAGE + SPARE)] = data + spare_for(data)
    return bytes(out)
