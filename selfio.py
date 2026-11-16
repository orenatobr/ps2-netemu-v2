"""Read and rewrite a retail PS3 SELF (the ps2_netemu.self container) without changing its layout.

Each segment is decrypted, handed to the caller, recompressed to the same stored size and encrypted
again. The per-section HMAC-SHA1s and the ELF SHA-1 are recomputed; the ECDSA signature is the only
thing left stale.
"""
from __future__ import annotations

import hashlib
import hmac
import struct
import zlib
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

# LV2 key set that covers SELF version 0x0004002000000000 and up (public, from the RPCS3 project).
LV2_ERK = bytes.fromhex("0CAF212B6FA53C0DA7E2C575ADF61DBE68F34A33433B1B891ABF5C4251406A03")
LV2_RIV = bytes.fromhex("9B79374722AD888EB6A35A2DF25A8B3E")
LV2_MIN_VERSION = 0x0004002000000000
EMPTY_STORED_BLOCK = b"\x00\x00\x00\xff\xff"  # non-final, zero-length deflate block


def _ctr(key: bytes, iv: bytes, data: bytes) -> bytes:
    return Cipher(algorithms.AES(key), modes.CTR(iv)).encryptor().update(data)


@dataclass(frozen=True)
class Section:
    """A SELF data section: where it lives in the file and how it is stored."""

    off: int
    size: int
    phdr_index: int
    encrypted: bool
    compressed: bool
    key: bytes
    iv: bytes
    hash_pos: int  # where this section's HMAC-SHA1 sits in the decrypted metadata blob
    hmac_key: bytes


@dataclass(frozen=True)
class Metadata:
    """The decrypted metadata blob and what is needed to encrypt it back in place."""

    key: bytes
    iv: bytes
    blob: bytes
    file_off: int


def elf_digest_offset(d: bytes) -> int:
    """File offset of the ELF SHA-1 stored in the control info (type-1 block, after its header)."""
    control_off, = struct.unpack(">Q", d[0x58:0x60])
    return control_off + 0x30 + 0x10 + 0x14


def parse_all(d: bytes) -> tuple[list[Section], bytes, int, Metadata]:
    """Return the segment sections, the program headers, e_phoff and the decrypted metadata."""
    magic, _ver, _key_rev, hdr_type, meta_off, hdr_len, _ = struct.unpack(">4sIHHIQQ", d[:32])
    if magic != b"SCE\0" or hdr_type != 1:
        raise ValueError("not a SELF")
    app_off, = struct.unpack(">Q", d[0x28:0x30])
    _auth, _vendor, self_type, version = struct.unpack(">QIIQ", d[app_off:app_off + 24])
    if self_type != 3 or version < LV2_MIN_VERSION:
        raise ValueError(f"not an LV2 SELF this tool knows (type {self_type}, version 0x{version:x})")
    _v, _ai, elf_off, phdr_off, *_ = struct.unpack(">9Q", d[0x20:0x68])
    e_phoff = struct.unpack(">Q", d[elf_off + 0x20:elf_off + 0x28])[0]
    phentsize, phnum = struct.unpack(">HH", d[elf_off + 0x36:elf_off + 0x3A])
    info = Cipher(algorithms.AES(LV2_ERK), modes.CBC(LV2_RIV)).decryptor().update(d[meta_off + 0x20:meta_off + 0x60])
    blob = _ctr(info[0:16], info[32:48], d[meta_off + 0x60:hdr_len])
    nsec, nkeys = struct.unpack(">II", blob[0x0C:0x14])
    keys_off = 0x20 + nsec * 0x30
    keys = [blob[keys_off + 16 * i:][:16] for i in range(nkeys)]
    sections = []
    for i in range(nsec):
        off, size, typ, idx, _h, sha_idx, enc, kidx, iidx, comp = struct.unpack(
            ">QQ8I", blob[0x20 + i * 0x30:0x20 + (i + 1) * 0x30])
        if typ == 2:  # 2 = segment data
            sections.append(Section(
                off, size, idx, enc == 3, comp == 2,
                keys[kidx] if enc == 3 else b"", keys[iidx] if enc == 3 else b"",
                keys_off + 16 * sha_idx, b"".join(keys[sha_idx + 2:sha_idx + 6])))
    meta = Metadata(info[0:16], info[32:48], blob, meta_off + 0x60)
    return sections, d[phdr_off:phdr_off + phnum * phentsize], e_phoff, meta


def _phdr(phdrs: bytes, index: int) -> tuple[int, int]:
    """(p_offset, p_filesz) of program header `index`."""
    p_offset, = struct.unpack(">Q", phdrs[index * 56 + 8:index * 56 + 16])
    p_filesz, = struct.unpack(">Q", phdrs[index * 56 + 32:index * 56 + 40])
    return p_offset, p_filesz


def unpack(d: bytes) -> bytes:
    """Decrypt a retail SELF into a flat ELF file (with section headers)."""
    sections, phdrs, e_phoff, _ = parse_all(d)
    _v, _ai, elf_off, _po, shdr_off, *_ = struct.unpack(">9Q", d[0x20:0x68])
    ehdr = bytearray(d[elf_off:elf_off + 0x40])
    e_shoff = struct.unpack(">Q", ehdr[0x28:0x30])[0]
    shentsize, shnum = struct.unpack(">HH", ehdr[0x3A:0x3E])
    out = bytearray(ehdr)
    out += b"\0" * (e_phoff - len(out)) + phdrs
    for sec in sections:
        data = d[sec.off:sec.off + sec.size]
        if sec.encrypted:
            data = _ctr(sec.key, sec.iv, data)
        if sec.compressed:
            data = zlib.decompress(data)
        p_offset, _ = _phdr(phdrs, sec.phdr_index)
        out += b"\0" * (p_offset - len(out))
        out[p_offset:p_offset + len(data)] = data
    if shnum:
        out += b"\0" * (e_shoff - len(out))
        out += d[shdr_off:shdr_off + shnum * shentsize]
    return bytes(out)


def deflate_to_size(data: bytes, size: int) -> bytes:
    """Compress `data` as a zlib stream of exactly `size` bytes.

    Tries zlib settings until the stream fits and the leftover is a multiple of 5, then pads with
    empty non-final stored blocks right after the 2-byte zlib header. If no whole-stream setting
    lands on a multiple of 5, one sync flush at a varying point shifts the length by a few bytes.
    """
    def pad_to(stream: bytes) -> bytes | None:
        pad = size - len(stream)
        if pad < 0 or pad % len(EMPTY_STORED_BLOCK):
            return None
        out = stream[:2] + EMPTY_STORED_BLOCK * (pad // len(EMPTY_STORED_BLOCK)) + stream[2:]
        if len(out) != size or zlib.decompress(out) != data:
            raise AssertionError("padded stream does not round-trip")
        return out

    for level in (6, 9, 8, 7, 5, 4, 3, 2, 1):
        for mem in range(9, 0, -1):
            for strategy in (zlib.Z_DEFAULT_STRATEGY, zlib.Z_FILTERED):
                comp = zlib.compressobj(level, zlib.DEFLATED, 15, mem, strategy)
                out = pad_to(comp.compress(data) + comp.flush())
                if out:
                    return out
    for level in (9, 8, 7, 6):
        for mem in (9, 8):
            for cut in range(4096, len(data), 4096):
                comp = zlib.compressobj(level, zlib.DEFLATED, 15, mem)
                stream = comp.compress(data[:cut]) + comp.flush(zlib.Z_SYNC_FLUSH) + comp.compress(data[cut:]) + comp.flush()
                out = pad_to(stream)
                if out:
                    return out
    raise ValueError(f"cannot fit a {len(data)} byte segment into {size} compressed bytes")


def repack(orig_self: bytes, patched_elf: bytes) -> bytes:
    """Write the (patched) segments back into the stock SELF, keeping its layout.

    Section HMACs (inside the encrypted metadata) and the ELF SHA-1 in the control info are
    recomputed. The ECDSA signature cannot be, and is left as it was.
    """
    sections, phdrs, e_phoff, meta = parse_all(orig_self)
    phdr_off = struct.unpack(">Q", orig_self[0x38:0x40])[0]
    phdrs = patched_elf[e_phoff:e_phoff + len(phdrs)]  # sizes may have grown
    out = bytearray(orig_self)
    out[phdr_off:phdr_off + len(phdrs)] = phdrs
    blob = bytearray(meta.blob)
    for sec in sections:
        p_offset, p_filesz = _phdr(phdrs, sec.phdr_index)
        data = patched_elf[p_offset:p_offset + p_filesz]
        if sec.compressed:
            data = deflate_to_size(data, sec.size)
        if len(data) != sec.size:
            raise ValueError("segment size changed; the container would need new metadata")
        blob[sec.hash_pos:sec.hash_pos + 20] = hmac.new(sec.hmac_key, data, hashlib.sha1).digest()
        out[sec.off:sec.off + sec.size] = _ctr(sec.key, sec.iv, data) if sec.encrypted else data
    out[meta.file_off:meta.file_off + len(blob)] = _ctr(meta.key, meta.iv, bytes(blob))
    digest_off = elf_digest_offset(orig_self)
    out[digest_off:digest_off + 20] = hashlib.sha1(patched_elf).digest()
    return bytes(out)
