"""A tiny PowerPC assembler: just the instructions the code cave needs, with labels.

`assemble(base, lines)` takes a list of `(mnemonic, *operands)` tuples and `("label", name)` markers and
returns the 32-bit words. Branch targets are labels or absolute addresses. Anything else raises.
"""
from __future__ import annotations

REG = {f"r{i}": i for i in range(32)} | {f"f{i}": i for i in range(32)}


def _r(x: str) -> int:
    return REG[x]


def _i16(v: int) -> int:
    if not -0x8000 <= v <= 0xFFFF:
        raise ValueError(f"immediate {v} does not fit 16 bits")
    return v & 0xFFFF


def _bc(bo: int, bi: int, disp: int) -> int:
    if disp % 4 or not -0x8000 <= disp < 0x8000:
        raise ValueError(f"conditional branch displacement {disp}")
    return (16 << 26) | (bo << 21) | (bi << 16) | (disp & 0xFFFC)


def _b(disp: int, link: int) -> int:
    if disp % 4 or not -(1 << 25) <= disp < (1 << 25):
        raise ValueError(f"branch displacement {disp}")
    return (18 << 26) | (disp & 0x03FFFFFC) | link


CONDS = {"beq": (12, 30), "bne": (4, 30), "blt": (12, 28), "bge": (4, 28), "bgt": (12, 29), "ble": (4, 29)}  # cr7


def assemble(base: int, lines: list[tuple]) -> list[int]:
    labels: dict[str, int] = {}
    pc = base
    for ln in lines:
        if ln[0] == "label":
            labels[ln[1]] = pc
        else:
            pc += 4
    out: list[int] = []
    pc = base
    for ln in lines:
        m, *a = ln
        if m == "label":
            continue
        tgt = lambda x: labels[x] if isinstance(x, str) else x
        if m == "li":
            w = (14 << 26) | (_r(a[0]) << 21) | _i16(a[1])
        elif m == "lis":
            w = (15 << 26) | (_r(a[0]) << 21) | _i16(a[1])
        elif m == "addi":
            if a[1] == "r0":
                raise ValueError("addi with r0 as the source reads the literal 0; use li")
            w = (14 << 26) | (_r(a[0]) << 21) | (_r(a[1]) << 16) | _i16(a[2])
        elif m == "ori":
            w = (24 << 26) | (_r(a[1]) << 21) | (_r(a[0]) << 16) | _i16(a[2])
        elif m == "mr":
            w = (31 << 26) | (_r(a[1]) << 21) | (_r(a[0]) << 16) | (_r(a[1]) << 11) | (444 << 1)
        elif m == "add":
            w = (31 << 26) | (_r(a[0]) << 21) | (_r(a[1]) << 16) | (_r(a[2]) << 11) | (266 << 1)
        elif m == "cmpwi":
            w = (11 << 26) | (7 << 23) | (_r(a[0]) << 16) | _i16(a[1])
        elif m == "cmplwi":
            w = (10 << 26) | (7 << 23) | (_r(a[0]) << 16) | _i16(a[1])
        elif m == "cmpw":
            w = (31 << 26) | (7 << 23) | (_r(a[0]) << 16) | (_r(a[1]) << 11)
        elif m in ("lbz", "lwz", "stw", "stb"):
            op = {"lwz": 32, "lbz": 34, "stw": 36, "stb": 38}[m]
            w = (op << 26) | (_r(a[0]) << 21) | (_r(a[2]) << 16) | _i16(a[1])
        elif m in ("std", "stdu", "ld"):
            if a[1] % 4:
                raise ValueError("ds-form displacement must be a multiple of 4")
            op, low = {"std": (62, 0), "stdu": (62, 1), "ld": (58, 0)}[m]
            w = (op << 26) | (_r(a[0]) << 21) | (_r(a[2]) << 16) | (a[1] & 0xFFFC) | low
        elif m == "clrldi":
            n = a[2]
            w = (30 << 26) | (_r(a[1]) << 21) | (_r(a[0]) << 16) | ((n & 31) << 6) | (((n >> 5) & 1) << 5)
        elif m in CONDS:
            bo, bi = CONDS[m]
            w = _bc(bo, bi, tgt(a[0]) - pc)
        elif m == "b":
            w = _b(tgt(a[0]) - pc, 0)
        elif m == "bl":
            w = _b(tgt(a[0]) - pc, 1)
        elif m == "mulli":
            w = (7 << 26) | (_r(a[0]) << 21) | (_r(a[1]) << 16) | _i16(a[2])
        elif m == "mullw":
            w = (31 << 26) | (_r(a[0]) << 21) | (_r(a[1]) << 16) | (_r(a[2]) << 11) | (235 << 1)
        elif m == "lwbrx":  # lwbrx rt,ra|0,rb: a word, byte reversed
            w = (31 << 26) | (_r(a[0]) << 21) | (_r(a[1]) << 16) | (_r(a[2]) << 11) | (534 << 1)
        elif m == "lhz":
            w = (40 << 26) | (_r(a[0]) << 21) | (_r(a[2]) << 16) | _i16(a[1])
        elif m == "word":  # raw data (a string, a constant) placed inside the code
            w = a[0] & 0xFFFFFFFF
        elif m == "stwx":
            w = (31 << 26) | (_r(a[0]) << 21) | (_r(a[1]) << 16) | (_r(a[2]) << 11) | (151 << 1)
        elif m == "rlwinm":
            w = (21 << 26) | (_r(a[1]) << 21) | (_r(a[0]) << 16) | (a[2] << 11) | (a[3] << 6) | (a[4] << 1)
        elif m == "subf":
            w = (31 << 26) | (_r(a[0]) << 21) | (_r(a[1]) << 16) | (_r(a[2]) << 11) | (40 << 1)
        elif m in ("lfs", "lfd", "stfs", "stfd"):
            op = {"lfs": 48, "lfd": 50, "stfs": 52, "stfd": 54}[m]
            w = (op << 26) | (_r(a[0]) << 21) | (_r(a[2]) << 16) | _i16(a[1])
        elif m in ("fsubs", "fadds", "fdivs"):
            xo = {"fsubs": 20, "fadds": 21, "fdivs": 18}[m]
            w = (59 << 26) | (_r(a[0]) << 21) | (_r(a[1]) << 16) | (_r(a[2]) << 11) | (xo << 1)
        elif m == "fmuls":  # fmuls frt,fra,frc
            w = (59 << 26) | (_r(a[0]) << 21) | (_r(a[1]) << 16) | (_r(a[2]) << 6) | (25 << 1)
        elif m == "fmadds":  # fmadds frt,fra,frc,frb = fra*frc+frb
            w = (59 << 26) | (_r(a[0]) << 21) | (_r(a[1]) << 16) | (_r(a[3]) << 11) | (_r(a[2]) << 6) | (29 << 1)
        elif m == "fsel":  # fsel frt,fra,frc,frb = fra >= 0 ? frc : frb
            w = (63 << 26) | (_r(a[0]) << 21) | (_r(a[1]) << 16) | (_r(a[3]) << 11) | (_r(a[2]) << 6) | (23 << 1)
        elif m == "fcmpu":  # always cr7
            w = (63 << 26) | (7 << 23) | (_r(a[0]) << 16) | (_r(a[1]) << 11)
        elif m == "fcfid":
            w = (63 << 26) | (_r(a[0]) << 21) | (_r(a[1]) << 11) | (846 << 1)
        elif m == "frsp":
            w = (63 << 26) | (_r(a[0]) << 21) | (_r(a[1]) << 11) | (12 << 1)
        elif m == "mflr":
            w = 0x7C0802A6 | (_r(a[0]) << 21)
        elif m == "mtlr":
            w = 0x7C0803A6 | (_r(a[0]) << 21)
        elif m == "blr":
            w = 0x4E800020
        else:
            raise ValueError(f"unsupported mnemonic {m}")
        out.append(w)
        pc += 4
    return out
