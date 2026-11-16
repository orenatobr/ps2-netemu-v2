"""Build a blank, formatted PS2 memory card in the PS3 `.VM2` layout (8 MB of data plus 16 bytes of ECC per page).

The layout was read from a real card made by the console (superblock `Sony PS2 Memory Card Format 1.2.0.0`, 8192
clusters of 2 pages, indirect FAT in cluster 8, FAT in clusters 9..40, allocatable area from cluster 41, root
directory at its first cluster) and the ECC rule was fitted on all 5060 written chunks of it. Pages that are not
written stay erased (0xFF data and spare).
"""
from __future__ import annotations

import struct
from itertools import pairwise

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


# --- copying a save between cards ---------------------------------------------------------------------------------

ENTRY = 512
IS_DIR, EXISTS = 0x0020, 0x8000


class Card:
    """A read view of a card: FAT, directories and files (clusters are `ALLOC_OFFSET` + relative number)."""

    def __init__(self, raw: bytes):
        if len(raw) != CARD_BYTES:
            raise ValueError("not a 8 MB card with ECC")
        self.raw = raw
        fat = b"".join(self.cluster(FAT_FIRST + i) for i in range(FAT_CLUSTERS))
        self.fat = struct.unpack(f"<{len(fat) // 4}I", fat)

    def cluster(self, absolute: int) -> bytes:
        """The 1024 data bytes of an absolute cluster."""
        return b"".join(self.raw[p * (PAGE + SPARE):p * (PAGE + SPARE) + PAGE]
                        for p in (absolute * CLUSTER_PAGES, absolute * CLUSTER_PAGES + 1))

    def chain(self, first: int) -> list[int]:
        """Relative clusters of the chain that starts at `first`."""
        out, c = [], first
        while c < len(self.fat) and c not in out:
            out.append(c)
            e = self.fat[c]
            if e == CHAIN_END or not e & 0x80000000:
                break
            c = e & 0x7FFFFFFF
        return out

    def read(self, first: int) -> bytes:
        return b"".join(self.cluster(ALLOC_OFFSET + c) for c in self.chain(first))

    def entries(self, first: int, count: int) -> list[bytes]:
        data = self.read(first)
        return [data[i * ENTRY:(i + 1) * ENTRY] for i in range(count)]


def entry_fields(e: bytes) -> tuple[int, int, int, bytes]:
    """(mode, length, first cluster, name) of a directory entry."""
    mode, length = struct.unpack("<II", e[:8])
    return mode, length, struct.unpack("<I", e[16:20])[0], e[64:96].split(b"\0")[0]


def with_cluster(e: bytes, cluster: int, dir_entry: int | None = None) -> bytes:
    """The entry with its first cluster (and optionally its entry number in the parent) replaced."""
    out = bytearray(e)
    out[16:20] = struct.pack("<I", cluster)
    if dir_entry is not None:
        out[20:24] = struct.pack("<I", dir_entry)
    return bytes(out)


def copy_save(src: bytes, save_name: str, dst: bytes | None = None) -> bytes:
    """Return `dst` (a blank card when omitted) with the save directory `save_name` of the card `src` copied into it.

    The directory and its files get fresh clusters in order; the root directory of the result lists the save. Raises
    KeyError when the save is not on `src`.
    """
    s = Card(src)
    d = Card(dst if dst is not None else blank_card())
    root_len = entry_fields(s.entries(0, 1)[0])[1]
    root = s.entries(0, root_len)
    want = save_name.encode()
    found = next((e for e in root[2:] if entry_fields(e)[0] & IS_DIR and entry_fields(e)[0] & EXISTS and entry_fields(e)[3] == want), None)
    if found is None:
        raise KeyError(save_name)
    _, length, first, _ = entry_fields(found)
    sub = s.entries(first, length)

    d_root_len = entry_fields(d.entries(0, 1)[0])[1]
    if d_root_len != 2:
        raise ValueError("the destination must be a card without saves")
    fat = list(d.fat)
    cards = bytearray(d.raw)
    free = iter(range(2, len(fat)))  # 0 and 1 are the two root clusters

    def alloc(n: int) -> list[int]:
        got = [next(free) for _ in range(n)]
        for a, b in pairwise(got):
            fat[a] = 0x80000000 | b
        fat[got[-1]] = CHAIN_END
        return got

    def write(relative: int, data: bytes) -> None:
        for k in range(CLUSTER_PAGES):
            p = (ALLOC_OFFSET + relative) * CLUSTER_PAGES + k
            page = data[k * PAGE:(k + 1) * PAGE]
            cards[p * (PAGE + SPARE):(p + 1) * (PAGE + SPARE)] = page + spare_for(page)

    # the save directory and its files
    dir_chain = alloc((length + 1) // 2)
    new_sub = [sub[0], sub[1]]
    for e in sub[2:]:
        _, ln, c, _ = entry_fields(e)
        data = b"".join(s.cluster(ALLOC_OFFSET + c2) for c2 in s.chain(c)) if ln else b""
        if data:
            fc = alloc((ln + 1023) // 1024)
            for i, rel in enumerate(fc):
                write(rel, data[i * 1024:(i + 1) * 1024].ljust(1024, b"\xff"))
            new_sub.append(with_cluster(e, fc[0]))
        else:
            new_sub.append(e)
    new_sub[0] = with_cluster(new_sub[0], 0, 2)  # "." knows it is entry 2 of the root
    blob = b"".join(new_sub).ljust(len(dir_chain) * 1024, b"\xff")
    for i, rel in enumerate(dir_chain):
        write(rel, blob[i * 1024:(i + 1) * 1024])
    # the root directory: ".", "..", the save
    root_dot = bytearray(root[0])
    root_dot[4:8] = struct.pack("<I", 3)
    fat[0], fat[1] = 0x80000001, CHAIN_END
    root_blob = (bytes(root_dot) + root[1] + with_cluster(found, dir_chain[0], 0)).ljust(2048, b"\xff")
    write(0, root_blob[:1024])
    write(1, root_blob[1024:])
    fat_bytes = struct.pack(f"<{len(fat)}I", *fat)
    for i in range(FAT_CLUSTERS):
        write_abs = FAT_FIRST + i
        for k in range(CLUSTER_PAGES):
            p = write_abs * CLUSTER_PAGES + k
            page = fat_bytes[i * 1024 + k * PAGE:i * 1024 + (k + 1) * PAGE]
            cards[p * (PAGE + SPARE):(p + 1) * (PAGE + SPARE)] = page + spare_for(page)
    return bytes(cards)
