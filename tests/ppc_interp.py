"""A small PowerPC interpreter that runs real emulator code and the code caves in tests.

It knows only the instructions those paths use and raises on anything else.
"""
from __future__ import annotations

import struct

from ps2_netemu_patch import va_to_off

M32 = 0xFFFFFFFF
M64 = (1 << 64) - 1


def _s16(x: int) -> int:
    return x - 0x10000 if x & 0x8000 else x


def _s64(x: int) -> int:
    return x - (1 << 64) if x & (1 << 63) else x


def _s32(x: int) -> int:
    x &= M32
    return x - (1 << 32) if x & 0x80000000 else x


class Cpu:
    """Registers, one CR field per cr0..cr7 (lt, gt, eq) and byte-addressed memory."""

    def __init__(self, elf: bytes):
        self.elf = elf
        self.r = [0] * 32
        self.cr = [(0, 0, 0)] * 8
        self.mem: dict[int, int] = {}
        self.lr = 0
        self.f = [0.0] * 32
        self.mocks: dict[int, object] = {}  # va -> python stand-in for a called function

    def code(self, pc: int) -> int:
        off = va_to_off(self.elf, pc, 4)
        return struct.unpack(">I", self.elf[off:off + 4])[0]

    def byte(self, addr: int) -> int:
        if addr in self.mem:
            return self.mem[addr]
        try:
            return self.elf[va_to_off(self.elf, addr, 1)]  # constants and TOC slots live in the ELF image
        except ValueError:
            return 0

    def rd(self, addr: int, n: int) -> int:
        return int.from_bytes(bytes(self.byte(addr + i) for i in range(n)), "big")

    def cstr(self, addr: int) -> str:
        out = bytearray()
        while self.byte(addr + len(out)):
            out.append(self.byte(addr + len(out)))
        return out.decode()

    def wr(self, addr: int, n: int, val: int) -> None:
        for i, b in enumerate(val.to_bytes(n, "big")):
            self.mem[addr + i] = b

    def ra0(self, ra: int) -> int:
        return 0 if ra == 0 else self.r[ra]

    def run(self, pc: int, stop: set[int]) -> int:
        """Execute from `pc` until pc lands in `stop`; returns that pc."""
        for _ in range(60000):
            if pc in stop:
                return pc
            w = self.code(pc)
            op, rt, ra, rb = w >> 26, (w >> 21) & 31, (w >> 16) & 31, (w >> 11) & 31
            nxt = pc + 4
            if op == 14:  # addi / li
                self.r[rt] = (self.ra0(ra) + _s16(w & 0xFFFF)) & M64
            elif op == 32:  # lwz
                self.r[rt] = self.rd((self.ra0(ra) + _s16(w & 0xFFFF)) & M64, 4)
            elif op == 34:  # lbz
                self.r[rt] = self.rd((self.ra0(ra) + _s16(w & 0xFFFF)) & M64, 1)
            elif op == 7:  # mulli
                self.r[rt] = (self.r[ra] * _s16(w & 0xFFFF)) & M64
            elif op == 38:  # stb
                self.wr((self.ra0(ra) + _s16(w & 0xFFFF)) & M64, 1, self.r[rt] & 0xFF)
            elif op == 40:  # lhz
                self.r[rt] = self.rd((self.ra0(ra) + _s16(w & 0xFFFF)) & M64, 2)
            elif op == 15:  # lis
                self.r[rt] = (self.ra0(ra) + (_s16(w & 0xFFFF) << 16)) & M64
            elif op == 24:  # ori (RA is the destination)
                self.r[ra] = self.r[rt] | (w & 0xFFFF)
            elif op == 62 and w & 3 in (0, 1):  # std / stdu
                ea = ((self.ra0(ra) if w & 3 == 0 else self.r[ra]) + _s16(w & 0xFFFC)) & M64
                self.wr(ea, 8, self.r[rt])
                if w & 3 == 1:
                    self.r[ra] = ea
            elif op == 58 and w & 3 == 0:  # ld
                self.r[rt] = self.rd((self.ra0(ra) + _s16(w & 0xFFFC)) & M64, 8)
            elif op == 10:  # cmplwi
                a, b = self.r[ra] & M32, w & 0xFFFF
                self.cr[(w >> 23) & 7] = (int(a < b), int(a > b), int(a == b))
            elif op == 21:  # rlwinm
                sh, mb, me = rb, (w >> 6) & 31, (w >> 1) & 31
                x = self.r[rt] & M32
                rot = ((x << sh) | (x >> (32 - sh))) & M32 if sh else x
                mask = ((1 << (me - mb + 1)) - 1) << (31 - me)
                self.r[ra] = rot & mask
            elif op in (48, 50, 52, 54):  # lfs lfd stfs stfd
                ea = (self.ra0(ra) + _s16(w & 0xFFFF)) & M64
                if op == 48:
                    self.f[rt] = struct.unpack(">f", struct.pack(">I", self.rd(ea, 4)))[0]
                elif op == 50:
                    self.f[rt] = struct.unpack(">d", struct.pack(">Q", self.rd(ea, 8)))[0]
                elif op == 52:
                    self.wr(ea, 4, struct.unpack(">I", struct.pack(">f", self.f[rt]))[0])
                else:
                    self.wr(ea, 8, struct.unpack(">Q", struct.pack(">d", self.f[rt]))[0])
            elif op in (59, 63):
                fa, fb, fc, xo5, xo10 = ra, rb, (w >> 6) & 31, (w >> 1) & 31, (w >> 1) & 0x3FF
                s32 = lambda x: struct.unpack(">f", struct.pack(">f", x))[0]
                if op == 59 and xo5 == 20:
                    self.f[rt] = s32(self.f[fa] - self.f[fb])
                elif op == 59 and xo5 == 21:
                    self.f[rt] = s32(self.f[fa] + self.f[fb])
                elif op == 59 and xo5 == 18:
                    self.f[rt] = s32(self.f[fa] / self.f[fb]) if self.f[fb] else float("inf")
                elif op == 59 and xo5 == 25:
                    self.f[rt] = s32(self.f[fa] * self.f[fc])
                elif op == 59 and xo5 == 29:
                    self.f[rt] = s32(self.f[fa] * self.f[fc] + self.f[fb])
                elif op == 63 and xo5 == 23:  # fsel
                    self.f[rt] = self.f[fc] if self.f[fa] >= 0 else self.f[fb]
                elif op == 63 and xo10 == 0:  # fcmpu
                    a, b = self.f[fa], self.f[fb]
                    self.cr[(w >> 23) & 7] = (int(a < b), int(a > b), int(a == b))
                elif op == 63 and xo10 == 846:  # fcfid
                    self.f[rt] = float(_s64(struct.unpack(">Q", struct.pack(">d", self.f[fb]))[0]))
                elif op == 63 and xo10 == 12:  # frsp
                    self.f[rt] = s32(self.f[fb])
                else:
                    raise NotImplementedError(f"{pc:#x}: float op {op}/{xo5}/{xo10} in {w:08x}")
            elif op == 36:  # stw
                self.wr((self.ra0(ra) + _s16(w & 0xFFFF)) & M64, 4, self.r[rt] & M32)
            elif op == 30 and (w >> 2) & 7 == 0:  # rldicl
                sh, mb = rb | (((w >> 1) & 1) << 5), ((w >> 6) & 31) | (((w >> 5) & 1) << 5)
                rot = ((self.r[rt] << sh) | (self.r[rt] >> (64 - sh))) & M64 if sh else self.r[rt]
                self.r[ra] = rot & ((1 << (64 - mb)) - 1)
            elif op == 31:
                xo = (w >> 1) & 0x3FF
                if xo == 19:  # mfcr
                    self.r[rt] = sum(((lt << 3) | (gt << 2) | (eq << 1)) << (4 * (7 - i)) for i, (lt, gt, eq) in enumerate(self.cr))
                elif xo == 266:  # add
                    self.r[rt] = (self.r[ra] + self.r[rb]) & M64
                elif xo == 235:  # mullw
                    self.r[rt] = ((self.r[ra] & M32) * (self.r[rb] & M32)) & M32
                elif xo == 534:  # lwbrx
                    ea = (self.ra0(ra) + self.r[rb]) & M64
                    self.r[rt] = int.from_bytes(self.rd(ea, 4).to_bytes(4, "big"), "little")
                elif xo == 40:  # subf
                    self.r[rt] = (self.r[rb] - self.r[ra]) & M64
                elif xo == 104:  # neg
                    self.r[rt] = (-self.r[ra]) & M64
                elif xo == 986:  # extsw (RS in the RT slot, RA is the destination)
                    self.r[ra] = _s32(self.r[rt]) & M64
                elif xo == 23:  # lwzx
                    self.r[rt] = self.rd((self.ra0(ra) + self.r[rb]) & M64, 4)
                elif xo == 444:  # or (mr)
                    self.r[ra] = self.r[rt] | self.r[rb]
                elif xo == 0:  # cmpw
                    a, b = _s32(self.r[ra]), _s32(self.r[rb])
                    self.cr[(w >> 23) & 7] = (int(a < b), int(a > b), int(a == b))
                elif xo == 339:  # mflr
                    self.r[rt] = self.lr
                elif xo == 467:  # mtlr
                    self.lr = self.r[rt]
                elif xo == 151:  # stwx
                    self.wr((self.ra0(ra) + self.r[rb]) & M64, 4, self.r[rt] & M32)
                else:
                    raise NotImplementedError(f"{pc:#x}: xo {xo} in {w:08x}")
            elif op == 11:  # cmpwi / cmpdi (L bit)
                a, b = (_s64(self.r[ra]) if (w >> 21) & 1 else _s32(self.r[ra])), _s16(w & 0xFFFF)
                self.cr[(w >> 23) & 7] = (int(a < b), int(a > b), int(a == b))
            elif op == 16:  # bc (only the two conditional forms used here)
                bo, bi = rt, ra
                bit = self.cr[bi // 4][bi % 4]
                taken = bit == 1 if bo == 12 else bit == 0 if bo == 4 else None
                if taken is None:
                    raise NotImplementedError(f"{pc:#x}: bo {bo}")
                if taken:
                    nxt = pc + _s16(w & 0xFFFC)
            elif op == 18:  # b / bl
                li = w & 0x03FFFFFC
                target = pc + (li - (1 << 26) if li & (1 << 25) else li)
                if w & 1:
                    self.lr = pc + 4
                if target in self.mocks:  # a call into emulator code that is stood in for
                    self.mocks[target](self)
                    for reg in range(4, 13):
                        self.r[reg] = 0xDEAD0000 + reg  # volatile registers are clobbered by a call
                else:
                    nxt = target
            elif w == 0x4E800020:  # blr
                nxt = self.lr
            else:
                raise NotImplementedError(f"{pc:#x}: opcode {op} in {w:08x}")
            pc = nxt
        raise AssertionError("did not stop")
