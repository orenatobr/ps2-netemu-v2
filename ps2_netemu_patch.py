"""Build a patched ps2_netemu.self from the stock one.

The SELF container is rewritten by selfio (layout kept, hashes recomputed). The edits are word
replacements at virtual addresses plus byte replacements in the data segment; every edit checks
the original bytes first and refuses to touch anything else.

Usage:
    python ps2_netemu_patch.py INPUT.self OUTPUT.self [--experiment] [--up-convert=0|1|2] [--hotkey]
"""
from __future__ import annotations

import hashlib
import logging
import struct
import sys
from dataclasses import dataclass

import cave_bufcard
import cave_bufpath
import cave_card
import cave_cardfile
import cave_cardname
import cave_crop
import cave_defname
import cave_hotkey
import cave_nodither
import cave_probe
import cave_serial
import cave_slots
import cave_table
import cave_wide
import cave_wrap
import selfio

logger = logging.getLogger(__name__)
STOCK_SHA256 = "bad3e45c9a81f25726e414b146ea5a112f28216ab4bdd2fd9f5c81b33d04c80a"
CAVE_VA = 0x2FF940  # first free byte after the stock text segment; the page is mapped up to 0x300000
CAVE_SIZE = 0x6C0
WIDE_CAVE_VA = CAVE_VA + CAVE_SIZE - 0x20  # after the largest card cave (the slots build ends at +0x694)
CARD_CAVE_VA = CAVE_VA + 0xA0  # the crop cave uses the first 0x98 bytes
SERIAL_CAVE_VA = CAVE_VA + 0x200  # the serial capture (528 bytes); the card cave of the serial plan sits at CARD_CAVE_VA
PATH_VA = CAVE_VA + 0x440  # 64 bytes: the card path of the disc, empty when none
NODITHER_CAVE_VA = CAVE_VA + 0x5C0  # after the buffer card cave (it ends at +0x5a0), 0x34 bytes
HOTKEY_CAVE_VA = CAVE_VA + 0x5F8  # after the no dither cave (it ends at +0x5f4), before the wide cave
SCRATCH_VA = 0x74E940  # writable: the unused tail of the last page of the data segment (made official by extend_data)
SCRATCH_EXTRA = 0x100


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


def extend_data(elf: bytes, extra: int = SCRATCH_EXTRA) -> bytes:
    """Grow the second loadable segment (RW data) by `extra` zero bytes: scratch memory for the card path.

    The segment ends at 0x74e930 and its last page is mapped up to 0x74f000, with nothing referring into the tail; the next
    segment is far away in memory and 0x26d0 bytes later in the file.
    """
    e_phoff, = struct.unpack(">Q", elf[0x20:0x28])
    phentsize, phnum = struct.unpack(">HH", elf[0x36:0x3A])
    p_type, _f, p_off, p_va, _pa, p_filesz, p_memsz, _al = struct.unpack(
        ">IIQQQQQQ", elf[e_phoff + phentsize:e_phoff + 2 * phentsize])
    if p_type != 1 or p_filesz != p_memsz or (p_va + p_filesz + extra) > ((p_va + p_filesz + 0xFFF) & ~0xFFF):
        raise ValueError("program header 1 is not the plain data segment, or the extension leaves its last page")
    if phnum > 2:
        _t, _f2, nxt_off, *_ = struct.unpack(">IIQQQQQQ", elf[e_phoff + 2 * phentsize:e_phoff + 3 * phentsize])
        if p_off + p_filesz + extra > nxt_off:
            raise ValueError("the extended data segment would overlap the next file segment")
    out = bytearray(elf)
    struct.pack_into(">QQ", out, e_phoff + phentsize + 32, p_filesz + extra, p_memsz + extra)
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


def card_edits(debug: bool = False, stop_after: str | None = None) -> tuple[Edit, ...]:
    """Feature: one memory card file per game, named after the ISO and shared by its discs (see cave_card)."""
    patches, used = cave_card.build(CARD_CAVE_VA, debug, stop_after)
    if CARD_CAVE_VA + used > CAVE_VA + CAVE_SIZE:
        raise ValueError("the card cave does not fit in the text page")
    return cave_edits(patches)


def serial_card_edits() -> tuple[Edit, ...]:
    """Feature: one memory card per game, named after the serial of the disc read from the SYSTEM.CNF the emulator already
    reads (cave_serial) and used for memory card 1 (cave_cardname). No file calls are made by the hooks."""
    serial, used_serial = cave_serial.build(SERIAL_CAVE_VA, PATH_VA)
    name, used_name = cave_cardname.build(CARD_CAVE_VA, PATH_VA)
    if CARD_CAVE_VA + used_name > SERIAL_CAVE_VA or SERIAL_CAVE_VA + used_serial > PATH_VA or PATH_VA + 64 > CAVE_VA + CAVE_SIZE:
        raise ValueError("the caves do not fit in the text page")
    return cave_edits(serial + name)


def static_card_edits(name: bytes = b"PS2_SLUS-21345", any_path: bool = False) -> tuple[Edit, ...]:
    """EXPERIMENT: memory card 1 always goes to /savedata/vmc/<name>.VM2, with no serial logic at all (cave_cardname with the
    path written in the cave). Tells whether a card with that name is safe, apart from the serial capture."""
    path = b"/savedata/vmc/" + name + b".VM2"
    patches, used = cave_cardname.build(CARD_CAVE_VA, PATH_VA, any_path)
    blob = path.ljust(64, b"\0")
    data = [(PATH_VA + i, 0, int.from_bytes(blob[i:i + 4], "big"), "fixed card path") for i in range(0, 64, 4)]
    if CARD_CAVE_VA + used > SERIAL_CAVE_VA:
        raise ValueError("the card cave overlaps the next one")
    return cave_edits(patches + data)


def file_card_edits() -> tuple[Edit, ...]:
    """Feature: one memory card per game, named after the ISO and shared by its discs (cave_cardfile). It only uses the
    redirect of the card path and the read of /tmp/cfg.bin, both proven on the console."""
    patches, used = cave_cardfile.build(CARD_CAVE_VA, SCRATCH_VA)
    if CARD_CAVE_VA + used > CAVE_VA + CAVE_SIZE:
        raise ValueError("the card cave does not fit in the text page")
    return cave_edits(patches)


def table_card_edits(isos: list[str]) -> tuple[Edit, ...]:
    """Feature candidate: card chosen from a fixed table of ISO names (cave_table), no run-time stores."""
    patches, used = cave_table.build(CARD_CAVE_VA, isos)
    if CARD_CAVE_VA + used > CAVE_VA + CAVE_SIZE:
        raise ValueError("the card table does not fit in the text page")
    return cave_edits(patches)


def slots_card_edits() -> tuple[Edit, ...]:
    """Feature: card chosen through the table file written by the installer, fixed slot paths (cave_slots)."""
    patches, used = cave_slots.build(CARD_CAVE_VA)
    if CARD_CAVE_VA + used > CAVE_VA + CAVE_SIZE:
        raise ValueError("the card slots cave does not fit in the text page")
    return cave_edits(patches)


def wrap_card_edits(stage: str = "full") -> tuple[Edit, ...]:
    """Feature: card named after the game, path built on the stack of a wrapper around the card function (cave_wrap)."""
    patches, used = cave_wrap.build(CARD_CAVE_VA, stage)
    if CARD_CAVE_VA + used > CAVE_VA + CAVE_SIZE:
        raise ValueError("the card wrapper does not fit in the text page")
    return cave_edits(patches)


def wide_edits() -> tuple[Edit, ...]:
    """EXPERIMENT: widen the picture destination by 4/3 (cave_wide). Added on top of a build with --wide."""
    return cave_edits(cave_wide.build(WIDE_CAVE_VA)[0])


# The "Up Convert" setting is the Screen Mode of the menu (0 Off, 1 Normal, 2 Full Screen). It lives in byte +0x28 of the settings object
# at 0xb46100, which the emulator fills from a block sent by the host: `lbz r0,0x2284(r29)` then `stb r0,0x28(r28)` (0x11ad18, 0x11ad1c).
UP_CONVERT_VA, UP_CONVERT_STOCK = 0x11AD18, 0x881D2284


def up_convert_edits(mode: int) -> tuple[Edit, ...]:
    """EXPERIMENT: the settings copy stores `mode` as the Up Convert value instead of the byte the host sent (li r0,mode).

    The video start-up reads that byte once, so this tells whether Full Screen (2) is applied at the start of a game.
    """
    if mode not in (0, 1, 2):
        raise ValueError("the Up Convert value is 0 (Off), 1 (Normal) or 2 (Full Screen)")
    return (word(UP_CONVERT_VA, UP_CONVERT_STOCK, 0x38000000 | mode, f"settings copy: Up Convert = {mode}"),)


def hotkey_edits() -> tuple[Edit, ...]:
    """EXPERIMENT: SELECT + L1 + R1 switches the live Screen Mode between Normal and Full Screen (cave_hotkey)."""
    patches, used = cave_hotkey.build(HOTKEY_CAVE_VA)
    if HOTKEY_CAVE_VA + used > WIDE_CAVE_VA:
        raise ValueError("the hotkey cave does not fit before the wide cave")
    return cave_edits(patches)


def defname_edits() -> tuple[Edit, ...]:
    """EXPERIMENT: a NULL card name for slot 0 becomes "PS2" (cave_defname), so the game always gets a card in slot 1."""
    return cave_edits(cave_defname.build(CARD_CAVE_VA)[0])


def bufpath_edits() -> tuple[Edit, ...]:
    """EXPERIMENT: an empty path buffer of memory card 1 gets /savedata/vmc/PS2.VM2 (cave_bufpath)."""
    return cave_edits(cave_bufpath.build(CARD_CAVE_VA)[0])


def bufcard_edits() -> tuple[Edit, ...]:
    """Feature candidate: the game card path is written into the path buffer of memory card 1 (cave_bufcard)."""
    patches, used = cave_bufcard.build(CARD_CAVE_VA)
    if CARD_CAVE_VA + used > CAVE_VA + CAVE_SIZE:
        raise ValueError("the buffer card cave does not fit in the text page")
    return cave_edits(patches)


# The value label of the emulator's "Screen Mode" item ("Normal") in each language table; the item has no other value. Same length
# replacement (padded with spaces) so the table of NUL separated strings keeps its layout.
SCREEN_MODE_LABELS = (
    (0x713E82, b"Normal"), (0x714690, b"Normal"), (0x714FED, b"Normal"), (0x7158A0, b"Normal"), (0x716227, b"Normale"),
    (0x717476, b"Normal"), (0x71ABC7, b"Normal"), (0x71B455, b"Normal"), (0x71BCA8, b"Normal"), (0x71C4AA, b"Normalne"),
    (0x71CD93, b"Normal"), (0x71D672, b"Normal"), (0x71DE82, b"Normal"),
)
SCREEN_MODE_NAME = b"4:3"


def screen_mode_label_edits() -> tuple[Edit, ...]:
    """Rename the only screen mode, "Normal", to "4:3" in every language table (what the picture crop makes it)."""
    return tuple(
        Edit(va, old, SCREEN_MODE_NAME.ljust(len(old), b" "), "screen mode label")
        for va, old in SCREEN_MODE_LABELS
    )


# The generic texture binder (0x263a04) writes the sampler filter of every texture it binds: 0x02022000 = min and mag LINEAR. The state
# reset of the draw code (0x280e08) uses 0x01012000 = min and mag NEAREST, the same word with 1 where the binder has 2.
def nofilter_edits() -> tuple[Edit, ...]:
    """Remove the blur: textures are sampled NEAREST instead of LINEAR (lis r0,514 becomes lis r0,257 in the texture binder)."""
    return (word(0x263AE8, 0x3C000202, 0x3C000101, "texture filter min/mag LINEAR -> NEAREST (0x02022000 -> 0x01012000)"),)


def nodither_edits() -> tuple[Edit, ...]:
    """Remove the dither: the RSX state reset also writes method 0x0300 (dither enable) = 0 (cave_nodither)."""
    patches, used = cave_nodither.build(NODITHER_CAVE_VA)
    if NODITHER_CAVE_VA + used > CAVE_VA + CAVE_SIZE:
        raise ValueError("the no dither cave does not fit in the text page")
    return cave_edits(patches)


def probe_edits(select: bool = False) -> tuple[Edit, ...]:
    """EXPERIMENT: step 1 of the card hook, file calls only (see cave_probe); `select` picks the card by the cfg.bin format."""
    return cave_edits(cave_probe.build(CARD_CAVE_VA, select)[0])


def main(src: str, dst: str, edits: tuple[Edit, ...], scratch: bool = False) -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    with open(src, "rb") as fh:
        orig = fh.read()
    if hashlib.sha256(orig).hexdigest() != STOCK_SHA256:
        raise SystemExit("input is not the stock ps2_netemu.self this patch was made for")
    elf = selfio.unpack(orig)
    if any(e.va >= CAVE_VA for e in edits):  # only grow the segment when code lives in the cave
        elf = extend_text(elf)
    if scratch:
        elf = extend_data(elf)
    out = selfio.repack(orig, apply_edits(elf, edits))
    with open(dst, "wb") as fh:
        fh.write(out)
    logger.info("wrote %s (%d bytes) sha256=%s", dst, len(out), hashlib.sha256(out).hexdigest())


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    if "--experiment" in sys.argv:
        chosen = EXPERIMENT
    elif any(a.startswith("--stop-after=") for a in sys.argv):
        stage = next(a for a in sys.argv if a.startswith("--stop-after=")).split("=", 1)[1]
        chosen = crop_edits() + card_edits(stop_after=stage)
    elif "--debug-card" in sys.argv:
        chosen = crop_edits() + card_edits(debug=True)
    elif "--static-card" in sys.argv:
        chosen = crop_edits() + static_card_edits()
    elif "--iso-card" in sys.argv:
        chosen = crop_edits() + card_edits()
    elif "--table-card" in sys.argv:
        chosen = crop_edits() + table_card_edits([a for a in sys.argv[3:] if not a.startswith("--")])
    elif "--probe-select" in sys.argv:
        chosen = crop_edits() + probe_edits(select=True)
    elif "--probe" in sys.argv:
        chosen = crop_edits() + probe_edits()
    elif "--crop-only" in sys.argv:
        chosen = crop_edits()
    elif "--serial-card" in sys.argv:
        chosen = crop_edits() + serial_card_edits()
    elif any(a.startswith("--wrap-stage=") for a in sys.argv):
        chosen = crop_edits() + wrap_card_edits(next(a.split("=")[1] for a in sys.argv if a.startswith("--wrap-stage=")))
    elif "--file-card" in sys.argv:
        chosen = crop_edits() + file_card_edits()
    elif "--bufcard" in sys.argv:
        chosen = crop_edits() + bufcard_edits()
    elif "--bufpath" in sys.argv:
        chosen = crop_edits() + bufpath_edits()
    elif "--defname" in sys.argv:
        chosen = crop_edits() + defname_edits()
    elif "--wrap-card" in sys.argv:
        chosen = crop_edits() + wrap_card_edits()
    else:
        chosen = crop_edits() + bufcard_edits()
    if "--wide" in sys.argv:
        chosen = chosen + wide_edits()
    if "--hotkey" in sys.argv:
        chosen = chosen + hotkey_edits()
    if any(a.startswith("--up-convert=") for a in sys.argv):
        chosen = chosen + up_convert_edits(int(next(a.split("=")[1] for a in sys.argv if a.startswith("--up-convert="))))
    if not any(a in sys.argv for a in ("--keep-filter", "--crop-only", "--probe", "--probe-select")):
        chosen = chosen + nofilter_edits()
    if not any(a in sys.argv for a in ("--keep-dither", "--crop-only", "--probe", "--probe-select")):
        chosen = chosen + nodither_edits()
    if "--labels" in sys.argv:  # opt-in: the menu value keeps its stock name "Normal" (the item is Off / Normal / Full Screen)
        chosen = chosen + screen_mode_label_edits()
    main(sys.argv[1], sys.argv[2], chosen, scratch="--file-card" in sys.argv)
