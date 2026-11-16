"""Build a patched ps2_netemu.self from the stock one.

The SELF container is rewritten by selfio (layout kept, hashes recomputed). The edits are word
replacements at virtual addresses plus byte replacements in the data segment; every edit checks
the original bytes first and refuses to touch anything else.

Usage:
    python ps2_netemu_patch.py INPUT.self OUTPUT.self [--experiment]
"""
from __future__ import annotations

import hashlib
import logging
import struct
import sys
from dataclasses import dataclass

import cave_card
import cave_crop
import cave_serial
import selfio

logger = logging.getLogger(__name__)
STOCK_SHA256 = "bad3e45c9a81f25726e414b146ea5a112f28216ab4bdd2fd9f5c81b33d04c80a"
CAVE_VA = 0x2FF940  # first free byte after the stock text segment; the page is mapped up to 0x300000
CAVE_SIZE = 0x6C0
CARD_CAVE_VA = CAVE_VA + 0x100  # the crop cave uses the first 0x100 bytes
SERIAL_CAVE_VA = CAVE_VA + 0x200
PATH_VA = CAVE_VA + 0x440  # 64 bytes: the card path of the disc, empty when none


@dataclass(frozen=True)
class Edit:
    """Replace `old` by `new` (same length) at virtual address `va`."""

    va: int
    old: bytes
    new: bytes
    what: str


def word(va: int, old: int, new: int, what: str) -> Edit:
    """A 32-bit big-endian word edit."""
    return Edit(va, struct.pack(">I", old), struct.pack(">I", new), what)


def va_to_off(elf: bytes, va: int, length: int) -> int:
    """File offset of `va` in the flat ELF (the range must sit inside one loadable segment)."""
    e_phoff, = struct.unpack(">Q", elf[0x20:0x28])
    phentsize, phnum = struct.unpack(">HH", elf[0x36:0x3A])
    for i in range(phnum):
        p_type, _f, p_off, p_va, _pa, p_filesz, _ms, _al = struct.unpack(
            ">IIQQQQQQ", elf[e_phoff + i * phentsize:e_phoff + (i + 1) * phentsize])
        if p_type == 1 and p_va <= va and va + length <= p_va + p_filesz:
            return p_off + va - p_va
    raise ValueError(f"va 0x{va:x}+{length} is not inside a loadable segment")


def extend_text(elf: bytes, extra: int = CAVE_SIZE) -> bytes:
    """Grow the first loadable segment (text, RWX) by `extra` zero bytes and return the new ELF.

    The stock text ends at 0x2ff940 and the next segment starts at 0x300000, so up to 0x6c0 bytes fit
    in the page the loader already maps. p_filesz and p_memsz of program header 0 are updated.
    """
    e_phoff, = struct.unpack(">Q", elf[0x20:0x28])
    phentsize, phnum = struct.unpack(">HH", elf[0x36:0x3A])
    p_type, _f, p_off, p_va, _pa, p_filesz, p_memsz, _al = struct.unpack(">IIQQQQQQ", elf[e_phoff:e_phoff + 56])
    if p_type != 1 or p_filesz != p_memsz or p_va != 0:
        raise ValueError("program header 0 is not the plain text segment")
    new = p_filesz + extra
    for i in range(1, phnum):
        t, _f2, o, v, *_ = struct.unpack(">IIQQQQQQ", elf[e_phoff + i * phentsize:e_phoff + (i + 1) * phentsize])
        if t == 1 and (v < new or o < p_off + new):
            raise ValueError("the extended text segment would overlap the next segment")
    out = bytearray(elf)
    struct.pack_into(">QQ", out, e_phoff + 32, new, new)
    return bytes(out)


def apply_edits(elf: bytes, edits: tuple[Edit, ...]) -> bytes:
    """Return a patched copy of `elf`; refuses to touch unexpected bytes."""
    out = bytearray(elf)
    for e in edits:
        if len(e.old) != len(e.new):
            raise ValueError(f"0x{e.va:x}: old and new differ in length")
        off = va_to_off(elf, e.va, len(e.old))
        found = bytes(out[off:off + len(e.old)])
        if found != e.old:
            raise ValueError(f"0x{e.va:x}: expected {e.old.hex()}, found {found.hex()}")
        out[off:off + len(e.new)] = e.new
        logger.info("patched 0x%x: %s -> %s (%s)", e.va, e.old.hex(), e.new.hex(), e.what)
    return bytes(out)


# EXPERIMENT 1 (not a feature): two probes whose effect is visible from outside.
#  - the shared card is requested under another file name, to learn whether the emulator creates a
#    missing card by itself;
#  - the rectangle of the full-screen draw routine at 0x282978 is moved down by 100 pixels, to learn
#    whether that routine draws the game picture.
EXPERIMENT = (
    Edit(0x300c58, b"%s%s.VM2\0" + b"\0" * 6, b"%sPS2_T_%s.VM2\0", "card file name format"),
    word(0x2838F0, 0x7D233214, 0x39230064, "quad y = y + 100 (addi r9,r3,100)"),
)


def cave_edits(patches: list[tuple[int, int, int, str]]) -> tuple[Edit, ...]:
    """Turn a cave module's (va, old, new, what) words into edits."""
    return tuple(word(va, old, new, what) for va, old, new, what in patches)


def crop_edits() -> tuple[Edit, ...]:
    """Feature: crop the black band at the top of the picture (see cave_crop)."""
    patches, used = cave_crop.build(CAVE_VA)
    if used > CAVE_SIZE:
        raise ValueError("the crop cave does not fit in the text page")
    return cave_edits(patches)


def card_edits() -> tuple[Edit, ...]:
    """Feature: one memory card file per game, named after the serial of the disc (see cave_serial, cave_card)."""
    serial, used_serial = cave_serial.build(SERIAL_CAVE_VA, PATH_VA)
    card, used_card = cave_card.build(CARD_CAVE_VA, PATH_VA)
    if CARD_CAVE_VA + used_card > SERIAL_CAVE_VA or SERIAL_CAVE_VA + used_serial > PATH_VA:
        raise ValueError("a cave overlaps the next one")
    if PATH_VA + 64 > CAVE_VA + CAVE_SIZE:
        raise ValueError("the caves do not fit in the text page")
    return cave_edits(serial + card)


def main(src: str, dst: str, edits: tuple[Edit, ...]) -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    with open(src, "rb") as fh:
        orig = fh.read()
    if hashlib.sha256(orig).hexdigest() != STOCK_SHA256:
        raise SystemExit("input is not the stock ps2_netemu.self this patch was made for")
    elf = selfio.unpack(orig)
    if any(e.va >= CAVE_VA for e in edits):  # only grow the segment when code lives in the cave
        elf = extend_text(elf)
    out = selfio.repack(orig, apply_edits(elf, edits))
    with open(dst, "wb") as fh:
        fh.write(out)
    logger.info("wrote %s (%d bytes) sha256=%s", dst, len(out), hashlib.sha256(out).hexdigest())


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    if "--experiment" in sys.argv:
        chosen = EXPERIMENT
    elif "--crop-only" in sys.argv:
        chosen = crop_edits()
    else:
        chosen = crop_edits() + card_edits()
    main(sys.argv[1], sys.argv[2], chosen)
