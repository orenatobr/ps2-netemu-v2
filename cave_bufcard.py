"""Code cave: per game memory card by writing the game card path into the path buffer of memory card 1.

At game start the card setup routine (0x12c17c...) opens the card of slot 0 from the path buffer at `object + 0x22e0` (256 bytes,
the emulator's own memory, valid for as long as the emulator runs). The launcher side fills it through 0x12abc4(slot, name); when
that does not happen the buffer is empty and the game sees no card (see cave_bufpath). This hook, on the check (0x12c988):

* does nothing when a marker byte (buffer + 0xFF) says it already ran, or when the buffer holds a path that is not in
  /savedata/vmc/ (the PS2 Classics layout);
* otherwise reads /tmp/cfg.bin (Cobra: a type byte, then the path of the mounted ISO), builds `/savedata/vmc/PS2_<title>.VM2` on
  its own stack frame (the same title rule as cave_wrap.card_name: no folder, no short extension, no `(Disc N)` tag, 52 bytes
  at most, only letters, digits, `_` and `-`), checks that the card exists (open, close) and copies the path into the buffer;
* when anything fails, an empty buffer gets the shared card path and a filled one is left as the launcher wrote it.

Nothing is stored outside the stack frame and the emulator's own path buffer. The stock `lbz` is repeated before returning.
"""
from __future__ import annotations

from ppcasm import assemble

HOOK_VA, HOOK_STOCK = 0x12C988, 0x881F22E0  # lbz r0, 0x22e0(r31)
RESUME = 0x12C98C
BUFFER, MARKER = 0x22E0, 0x22E0 + 0xFF
OPEN, READ, CLOSE = 0x1ECC5C, 0x1ED5CC, 0x1ECB10
PREFIX = b"/savedata/vmc/"
NAME_PREFIX = b"PS2_"
CFG_PATH = b"/tmp/cfg.bin"
SUFFIX = b".VM2"
DEFAULT_PATH = b"/savedata/vmc/PS2.VM2"
MAX_NAME = 52
PATH_SIZE = 80
S_BUF, BUF_SIZE = 0xC0, 0x100
S_FD, S_N = 0xB0, 0xB8
S_PATH = S_BUF + BUF_SIZE
FRAME = S_PATH + PATH_SIZE


def build(cave_va: int) -> tuple[list[tuple[int, int, int, str]], int]:
    """Return the (va, old, new, what) patches and the bytes used from `cave_va`."""
    cfg_va = cave_va
    code_va = cave_va + 16
    s_path = S_PATH
    frame = FRAME
    save = [("std", f"r{n}", 0x70 + 8 * (n - 3), "r1") for n in range(3, 11)]
    load = [("ld", f"r{n}", 0x70 + 8 * (n - 3), "r1") for n in range(3, 11)]
    lines: list[tuple] = [
        ("lbz", "r12", MARKER, "r31"), ("cmpwi", "r12", 0), ("bne", "done"),
        ("lbz", "r0", BUFFER, "r31"), ("cmpwi", "r0", 0), ("beq", "compute"),
    ]
    for i, c in enumerate(PREFIX):
        lines += [("lbz", "r0", BUFFER + i, "r31"), ("cmpwi", "r0", c), ("bne", "done")]
    lines += [("label", "compute"), ("stdu", "r1", -frame, "r1"), ("mflr", "r0"), ("std", "r0", frame + 0x10, "r1"), *save]
    lines += [
        ("li", "r3", 0), ("lis", "r4", cfg_va >> 16), ("ori", "r4", "r4", cfg_va & 0xFFFF), ("bl", OPEN),
        ("cmpwi", "r3", 0), ("blt", "fallback"), ("std", "r3", S_FD, "r1"),
        ("li", "r4", 0), ("addi", "r5", "r1", S_BUF), ("li", "r6", BUF_SIZE), ("bl", READ), ("std", "r3", S_N, "r1"),
        ("ld", "r3", S_FD, "r1"), ("bl", CLOSE),
        ("ld", "r3", S_N, "r1"), ("cmpwi", "r3", 1), ("blt", "fallback"),
        ("addi", "r7", "r1", S_BUF), ("li", "r0", 0), ("stb", "r0", BUF_SIZE - 1, "r7"), ("mr", "r4", "r7"), ("li", "r6", 0),
        ("label", "first"),  # the first '/' within the first four bytes
        ("lbz", "r0", 0, "r4"), ("cmpwi", "r0", 0x2F), ("beq", "have"), ("cmpwi", "r0", 0), ("beq", "fallback"),
        ("addi", "r4", "r4", 1), ("addi", "r6", "r6", 1), ("cmpwi", "r6", 4), ("blt", "first"), ("b", "fallback"),
        ("label", "have"), ("mr", "r5", "r4"),
        ("label", "scan"),  # r5 = start of the last path component, r4 = end of the string
        ("lbz", "r0", 0, "r4"), ("cmpwi", "r0", 0), ("beq", "scanned"), ("addi", "r4", "r4", 1), ("cmpwi", "r0", 0x2F),
        ("bne", "scan"), ("mr", "r5", "r4"), ("b", "scan"),
        ("label", "scanned"), ("addi", "r6", "r4", -1),
        ("label", "ext"),  # cut a short extension at the last '.'
        ("cmpw", "r6", "r5"), ("ble", "noext"), ("subf", "r7", "r6", "r4"), ("cmpwi", "r7", 5), ("bgt", "noext"),
        ("lbz", "r0", 0, "r6"), ("cmpwi", "r0", 0x2E), ("beq", "cut"), ("addi", "r6", "r6", -1), ("b", "ext"),
        ("label", "cut"), ("mr", "r4", "r6"),
        ("label", "noext"),
        ("addi", "r8", "r1", s_path),
        *[x for i, ch in enumerate(PREFIX + NAME_PREFIX) for x in (("li", "r0", ch), ("stb", "r0", i, "r8"))],
        ("addi", "r9", "r8", len(PREFIX) + len(NAME_PREFIX)), ("li", "r10", 0),
        ("label", "cp"),
        ("cmpw", "r5", "r4"), ("bge", "endcopy"), ("lbz", "r0", 0, "r5"),
        ("cmpwi", "r0", 0x28), ("beq", "tag"), ("cmpwi", "r0", 0x5B), ("bne", "plain"),
        ("label", "tag"),  # '(' or '[' followed by Disc / disc
        ("lbz", "r6", 1, "r5"), ("cmpwi", "r6", 0x44), ("beq", "d1"), ("cmpwi", "r6", 0x64), ("bne", "plain"),
        ("label", "d1"),
        ("lbz", "r6", 2, "r5"), ("cmpwi", "r6", 0x69), ("bne", "plain"), ("lbz", "r6", 3, "r5"), ("cmpwi", "r6", 0x73),
        ("bne", "plain"), ("lbz", "r6", 4, "r5"), ("cmpwi", "r6", 0x63), ("bne", "plain"),
        ("label", "skipt"),
        ("cmpw", "r5", "r4"), ("bge", "tagdone"), ("lbz", "r0", 0, "r5"), ("addi", "r5", "r5", 1),
        ("cmpwi", "r0", 0x29), ("beq", "tagdone"), ("cmpwi", "r0", 0x5D), ("bne", "skipt"),
        ("label", "tagdone"),  # drop the space that came before the tag
        ("cmpwi", "r10", 0), ("ble", "cp"), ("lbz", "r0", -1, "r9"), ("cmpwi", "r0", 0x20), ("bne", "cp"),
        ("addi", "r9", "r9", -1), ("addi", "r10", "r10", -1), ("b", "cp"),
        ("label", "plain"),
        ("cmpwi", "r10", MAX_NAME), ("bge", "endcopy"), ("stb", "r0", 0, "r9"), ("addi", "r9", "r9", 1),
        ("addi", "r10", "r10", 1), ("addi", "r5", "r5", 1), ("b", "cp"),
        ("label", "endcopy"),  # no trailing spaces, at least one character
        ("cmpwi", "r10", 0), ("ble", "fallback"), ("lbz", "r0", -1, "r9"), ("cmpwi", "r0", 0x20), ("bne", "trimmed"),
        ("addi", "r9", "r9", -1), ("addi", "r10", "r10", -1), ("b", "endcopy"),
        ("label", "trimmed"),
        # every byte that is not a letter, a digit, '_' or '-' becomes '_'
        ("addi", "r8", "r8", len(PREFIX) + len(NAME_PREFIX)), ("mr", "r7", "r10"),
        ("label", "san"),
        ("cmpwi", "r7", 0), ("ble", "sandone"), ("lbz", "r0", 0, "r8"),
        ("cmpwi", "r0", 0x2D), ("beq", "sanok"), ("cmpwi", "r0", 0x5F), ("beq", "sanok"),
        ("cmpwi", "r0", 0x30), ("blt", "sanbad"), ("cmpwi", "r0", 0x39), ("ble", "sanok"),
        ("cmpwi", "r0", 0x41), ("blt", "sanbad"), ("cmpwi", "r0", 0x5A), ("ble", "sanok"),
        ("cmpwi", "r0", 0x61), ("blt", "sanbad"), ("cmpwi", "r0", 0x7A), ("ble", "sanok"),
        ("label", "sanbad"), ("li", "r0", 0x5F), ("stb", "r0", 0, "r8"),
        ("label", "sanok"), ("addi", "r8", "r8", 1), ("addi", "r7", "r7", -1), ("b", "san"),
        ("label", "sandone"),
    ]
    for i, c in enumerate(SUFFIX + b"\0"):
        lines += [("li", "r0", c), ("stb", "r0", i, "r9")]
    lines += [
        # the card of the game must exist: open it and close it again
        ("li", "r3", 0), ("addi", "r4", "r1", s_path), ("bl", OPEN), ("cmpwi", "r3", 0), ("blt", "fallback"), ("bl", CLOSE),
        # copy the path into the emulator's buffer
        ("addi", "r4", "r1", s_path), ("addi", "r5", "r31", BUFFER),
        ("label", "cpy"), ("lbz", "r0", 0, "r4"), ("stb", "r0", 0, "r5"), ("addi", "r4", "r4", 1), ("addi", "r5", "r5", 1),
        ("cmpwi", "r0", 0), ("bne", "cpy"), ("b", "marked"),
        # no card of the game: an empty buffer gets the shared card, a filled one stays as it is
        ("label", "fallback"), ("lbz", "r0", BUFFER, "r31"), ("cmpwi", "r0", 0), ("bne", "marked"),
    ]
    for i, ch in enumerate(DEFAULT_PATH + b"\0"):
        lines += [("li", "r0", ch), ("stb", "r0", BUFFER + i, "r31")]
    lines += [
        ("label", "marked"), ("li", "r0", 1), ("stb", "r0", MARKER, "r31"),
        *load, ("ld", "r0", frame + 0x10, "r1"), ("addi", "r1", "r1", frame), ("mtlr", "r0"),
        ("label", "done"), ("lbz", "r0", BUFFER, "r31"), ("b", RESUME),
    ]
    words = assemble(code_va, lines)
    data = CFG_PATH.ljust(16, b"\0")
    patches = [(cave_va + i, 0, int.from_bytes(data[i:i + 4], "big"), "buffer card data") for i in range(0, len(data), 4)]
    patches += [(code_va + 4 * i, 0, w, "buffer card code") for i, w in enumerate(words)]
    patches.append((HOOK_VA, HOOK_STOCK, assemble(HOOK_VA, [("b", code_va)])[0], "jump to the buffer card cave"))
    return patches, 16 + 4 * len(words)
