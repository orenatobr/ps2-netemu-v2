"""Code cave: memory card 1 named after the game, with the path built on the stack of a wrapper around the card function.

0x12a528(slot, 0, path, ...) is the emulator function that opens a memory card. It copies `path` (kept in r28) into a buffer of
its own at the start and only uses the pointer during the call, so the pointer may refer to a stack buffer of a caller that
is still on the stack. That is what this does, and why no memory outside the stack is ever written: the hook makes a frame,
builds `/savedata/vmc/PS2_<title>.VM2` in it and CALLS the original function (through a two word trampoline that runs the
instruction the hook replaced), then drops the frame and returns to the original caller. Every earlier build that wrote the
path somewhere else (the code page, a data segment extended past its stored size) took the console down.

The title comes from /tmp/cfg.bin (Cobra fills it with the mounted ISO: a type byte, then the path): the file name with no
folder, no short extension and no `(Disc N)` / `[Disc N]` tag (nor the space before it), cut at MAX_NAME bytes, no trailing
space, and every byte that is not a letter, a digit, `_` or `-` turned into `_`. The same rule is `card_name()`, which the
tests and the installer follow. All the discs of a game therefore share one card. The card must exist (the emulator does not
create it): the hook opens it first and leaves the shared card when it cannot, so a game without a card just uses PS2.VM2.
"""
from __future__ import annotations

from ppcasm import assemble

HOOK_VA, HOOK_STOCK = 0x12A528, 0x7D800026  # mfcr r12
RESUME = 0x12A52C
OPEN, READ, CLOSE = 0x1ECC5C, 0x1ED5CC, 0x1ECB10
PREFIX = b"/savedata/vmc/"
NAME_PREFIX = b"PS2_"
CFG_PATH = b"/tmp/cfg.bin"
SUFFIX = b".VM2"
MAX_NAME = 52  # 14 + 4 + 52 + 4 + 1 bytes fit PATH_SIZE
PATH_SIZE = 80
S_FD, S_N, S_BUF, BUF_SIZE = 0xB0, 0xB8, 0xC0, 0x100
S_PATH = S_BUF + BUF_SIZE
FRAME = S_PATH + PATH_SIZE  # 0x210, a multiple of 16
DATA_SIZE = 16
FIXED_PATH = b"/savedata/vmc/PS2_C00.VM2"  # stage "fixed" only


def _keep(c: int) -> bool:
    return 0x30 <= c <= 0x39 or 0x41 <= c <= 0x5A or 0x61 <= c <= 0x7A or c in (0x2D, 0x5F)


def card_name(iso_path: str) -> str:
    """The card name (no PS2_ prefix, no extension) for an ISO path, or '' (the reference the cave is tested against)."""
    base = iso_path.encode().rsplit(b"/", 1)[-1]
    dot = base.rfind(b".")
    if dot > 0 and len(base) - dot <= 5:
        base = base[:dot]
    out = bytearray()
    i = 0
    while i < len(base):
        if base[i:i + 1] in (b"(", b"[") and base[i + 1:i + 5] in (b"Disc", b"disc"):
            while i < len(base):
                i += 1
                if base[i - 1:i] in (b")", b"]"):
                    break
            if out and out[-1] == 0x20:
                out.pop()
            continue
        if len(out) >= MAX_NAME:
            break
        out.append(base[i])
        i += 1
    while out and out[-1] == 0x20:
        out.pop()
    return bytes(c if _keep(c) else 0x5F for c in out).decode()


def card_file(iso_path: str) -> str:
    """The card file name for an ISO path ('' when the ISO gives no title)."""
    name = card_name(iso_path)
    return f"PS2_{name}.VM2" if name else ""


def build(cave_va: int, stage: str = "full") -> tuple[list[tuple[int, int, int, str]], int]:
    """Return the (va, old, new, what) patches and the bytes used from `cave_va`.

    `stage` is for bisecting a console problem: "full" is the feature, "title" leaves out the check that the card exists, and
    "fixed" does not read cfg.bin at all and calls the original function with the fixed path FIXED_PATH built on a small stack.
    """
    buf = 0 if stage == "fixed" else BUF_SIZE
    s_path = S_BUF + buf
    frame = s_path + PATH_SIZE
    cfg_va = cave_va
    tramp_va = cave_va + DATA_SIZE  # mfcr r12 ; b RESUME: the replaced instruction, then the rest of the function
    code_va = tramp_va + 8
    save = [("std", f"r{n}", 0x70 + 8 * (n - 3), "r1") for n in range(3, 11)]
    load = [("ld", f"r{n}", 0x70 + 8 * (n - 3), "r1") for n in range(3, 11)]
    lines: list[tuple] = [
        # the checks that need no frame: anything else runs the original function untouched
        ("cmpwi", "r3", 0), ("bne", "orig"), ("cmpdi", "r4", 0), ("bne", "orig"), ("cmpdi", "r5", 0), ("beq", "orig"),
    ]
    for i, c in enumerate(PREFIX):
        lines += [("lbz", "r0", i, "r5"), ("cmpwi", "r0", c), ("bne", "orig")]
    lines += [
        ("stdu", "r1", -frame, "r1"), ("mflr", "r0"), ("std", "r0", frame + 0x10, "r1"), *save,
        *([("b", "fixedpath")] if stage == "fixed" else []),
        ("li", "r3", 0), ("lis", "r4", cfg_va >> 16), ("ori", "r4", "r4", cfg_va & 0xFFFF), ("bl", OPEN),
        ("cmpwi", "r3", 0), ("blt", "restore"), ("std", "r3", S_FD, "r1"),
        ("li", "r4", 0), ("addi", "r5", "r1", S_BUF), ("li", "r6", BUF_SIZE), ("bl", READ), ("std", "r3", S_N, "r1"),
        ("ld", "r3", S_FD, "r1"), ("bl", CLOSE),
        ("ld", "r3", S_N, "r1"), ("cmpwi", "r3", 1), ("blt", "restore"),
        ("addi", "r7", "r1", S_BUF), ("li", "r0", 0), ("stb", "r0", BUF_SIZE - 1, "r7"), ("mr", "r4", "r7"), ("li", "r6", 0),
        ("label", "first"),  # the first '/' within the first four bytes
        ("lbz", "r0", 0, "r4"), ("cmpwi", "r0", 0x2F), ("beq", "have"), ("cmpwi", "r0", 0), ("beq", "restore"),
        ("addi", "r4", "r4", 1), ("addi", "r6", "r6", 1), ("cmpwi", "r6", 4), ("blt", "first"), ("b", "restore"),
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
        ("cmpwi", "r10", 0), ("ble", "restore"), ("lbz", "r0", -1, "r9"), ("cmpwi", "r0", 0x20), ("bne", "trimmed"),
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
        # the card must exist: open it and close it again, or leave the shared card
        *([("li", "r3", 0), ("addi", "r4", "r1", s_path), ("bl", OPEN), ("cmpwi", "r3", 0), ("blt", "restore"), ("bl", CLOSE)]
          if stage == "full" else []),
        ("label", "setpath"), ("addi", "r5", "r1", s_path), ("std", "r5", 0x80, "r1"),
        # call the original function with the path in this frame, then return to its caller
        *load, ("bl", tramp_va), ("ld", "r0", frame + 0x10, "r1"), ("addi", "r1", "r1", frame), ("mtlr", "r0"), ("blr",),
        ("label", "restore"), *load, ("ld", "r0", frame + 0x10, "r1"), ("addi", "r1", "r1", frame), ("mtlr", "r0"),
        ("label", "orig"), ("b", tramp_va),
    ]
    if stage == "fixed":  # the path is the one of the image, copied to the stack a byte at a time; cfg.bin is not read
        start = next(i for i, ln in enumerate(lines) if ln == ("stdu", "r1", -frame, "r1"))
        end = next(i for i, ln in enumerate(lines) if ln == ("label", "setpath"))
        lines[start + 3 + len(save):end] = [  # everything between the saved registers and "setpath"
            *[x for i, ch in enumerate(FIXED_PATH + b"\0") for x in (("li", "r0", ch), ("stb", "r0", s_path + i, "r1"))],
        ]
    words = assemble(code_va, lines)
    data = CFG_PATH.ljust(16, b"\0")
    patches = [(cave_va + i, 0, int.from_bytes(data[i:i + 4], "big"), "card wrapper data") for i in range(0, len(data), 4)]
    tramp = assemble(tramp_va, [("mfcr", "r12"), ("b", RESUME)])
    patches += [(tramp_va + 4 * i, 0, w, "card wrapper trampoline") for i, w in enumerate(tramp)]
    patches += [(code_va + 4 * i, 0, w, "card wrapper code") for i, w in enumerate(words)]
    patches.append((HOOK_VA, HOOK_STOCK, assemble(HOOK_VA, [("b", code_va)])[0], "jump to the card wrapper"))
    return patches, DATA_SIZE + 8 + 4 * len(words)
