"""Run the card cave in the interpreter against the real emulator code, with the file calls stood in for."""
import os
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ppc_interp import Cpu

import cave_card as C
import ps2_netemu_patch as P
import selfio as S

BUF, STACK = 0x7000_0000, 0x7100_0000
SHARED = "/savedata/vmc/PS2.VM2"
PATH_VA = P.CARD_CAVE_VA + 16


def cnf(boot: str = "cdrom0:\\SLUS_213.45;1") -> bytes:
    return f"BOOT2 = {boot}\r\nVER = 1.00\r\nVMODE = NTSC\r\n".encode()


def iso(cnf_bytes: bytes | None, extra_files: int = 0, magic: bytes = b"CD001") -> bytes:
    """A 2048 byte sector ISO9660 image: volume descriptor at 16, root directory at 20, SYSTEM.CNF at 30."""
    img = bytearray(40 * 2048)
    img[16 * 2048:16 * 2048 + 6] = b"\x01" + magic
    root = struct.pack("<II", 20, 2048)
    img[16 * 2048 + 156:16 * 2048 + 156 + 34] = bytes([34, 0]) + root[:4] + root[:4][::-1] + root[4:] + root[4:][::-1] + b"\0" * 16
    records = b""

    def rec(name: bytes, lba: int, size: int) -> bytes:
        """An ISO9660 directory record: length, ext attr, extent (LE+BE), size (LE+BE), date, flags, unit, gap, volume
        sequence, name length, name."""
        body = struct.pack("<I", lba) + struct.pack(">I", lba) + struct.pack("<I", size) + struct.pack(">I", size)
        body += b"\0" * 7 + bytes([0, 0, 0]) + b"\x01\x00\x00\x01" + bytes([len(name)]) + name
        record = bytes([0, 0]) + body  # placeholders for the length and the ext attr length, filled below
        if len(record) % 2:
            record += b"\0"
        return bytes([len(record)]) + record[1:]

    records += rec(b"\0", 20, 2048) + rec(b"\1", 20, 2048)
    for i in range(extra_files):
        records += rec(f"FILE{i}.DAT;1".encode(), 31 + i, 100)
    if cnf_bytes is not None:
        records += rec(b"SYSTEM.CNF;1", 30, len(cnf_bytes))
        img[30 * 2048:30 * 2048 + len(cnf_bytes)] = cnf_bytes
    img[20 * 2048:20 * 2048 + len(records)] = records
    assert len(img) == 40 * 2048
    return bytes(img)


class Fs:
    """The emulator's file calls over a dict of path -> bytes (the stored ISO images and /tmp/cfg.bin)."""

    def __init__(self, files: dict[str, bytes]):
        self.files, self.fds, self.log = files, {}, []

    def install(self, cpu: Cpu) -> None:
        cpu.mocks[C.OPEN], cpu.mocks[C.READ], cpu.mocks[C.CLOSE] = self.open, self.read, self.close

    def open(self, cpu: Cpu) -> None:
        path = cpu.cstr(cpu.r[4])
        self.log.append(("open", path))
        if path in self.files:
            fd = 10 + len(self.fds)
            self.fds[fd] = path
            cpu.r[3] = fd
        else:
            cpu.r[3] = (1 << 64) - 1

    def read(self, cpu: Cpu) -> None:
        fd, off, buf, size = cpu.r[3], cpu.r[4], cpu.r[5], cpu.r[6]
        path = self.fds[fd]
        self.log.append(("read", path, off, size))
        if path != "/tmp/cfg.bin" and (off % C.ALIGN or size % C.ALIGN):  # the console is suspected to refuse these
            cpu.r[3] = (1 << 64) - 1
            return
        data = self.files[path][off:off + size]
        for i, b in enumerate(data):
            cpu.mem[buf + i] = b
        cpu.r[3] = len(data)

    def close(self, cpu: Cpu) -> None:
        self.log.append(("close", self.fds.pop(cpu.r[3])))


def cfg(path: str) -> bytes:
    return b"\x02" + path.encode() + b"\0" + b"\0" * 64


@pytest.fixture(scope="module")
def patched() -> bytes:
    path = os.environ.get("PS2_NETEMU_SELF")
    if not path:
        pytest.skip("stock SELF not provided")
    return P.apply_edits(P.extend_text(S.unpack(Path(path).read_bytes())), P.crop_edits() + P.card_edits())


def hook(patched: bytes, fs: Fs, slot: int = 0, r4: int = 0, p: str | None = SHARED) -> Cpu:
    cpu = Cpu(patched)
    fs.install(cpu)
    cpu.r[1], cpu.r[3], cpu.r[4] = STACK, slot, r4
    cpu.r[5] = 0 if p is None else BUF
    for i, b in enumerate((p or "").encode() + b"\0"):
        cpu.mem[BUF + i] = b
    for n in (6, 7, 8, 9, 10):
        cpu.r[n] = 0x1000 + n
    cpu.cr[4] = (1, 0, 1)
    cpu.lr = 0x4242
    assert cpu.run(C.HOOK_VA, {C.RESUME}) == C.RESUME
    return cpu


def card(cpu: Cpu) -> str:
    return "" if cpu.r[5] == BUF else cpu.cstr(cpu.r[5])


G2 = "/dev_hdd0/PS2ISO/Grandia III (USA) (Disc 2).iso"
G1 = "/dev_hdd0/PS2ISO/Grandia III (USA) (Disc 1).iso"


def test_a_disc_without_disc_one_uses_its_own_serial(patched):
    fs = Fs({"/tmp/cfg.bin": cfg(G2), G2: iso(cnf())})
    assert card(hook(patched, fs)) == "/savedata/vmc/SLUS-21345.VM2"


@pytest.mark.skip(reason="step 3: the disc 1 lookup is not in the cave yet")
def test_disc_two_uses_the_card_of_disc_one_when_that_image_exists(patched):
    fs = Fs({"/tmp/cfg.bin": cfg(G2), G2: iso(cnf()), G1: iso(cnf("cdrom0:\\SLUS_213.34;1"))})
    assert card(hook(patched, fs)) == "/savedata/vmc/SLUS-21334.VM2"
    assert ("open", G1) in fs.log


def test_disc_one_itself_is_not_looked_up_again(patched):
    fs = Fs({"/tmp/cfg.bin": cfg(G1), G1: iso(cnf("cdrom0:\\SLUS_213.34;1"))})
    assert card(hook(patched, fs)) == "/savedata/vmc/SLUS-21334.VM2"
    assert [e for e in fs.log if e[0] == "open"] == [("open", "/tmp/cfg.bin"), ("open", G1)]


@pytest.mark.parametrize("path,first", [
    ("/x/Game (Disc 3).iso", "/x/Game (Disc 1).iso"),
    ("/x/Game [Disc 2].iso", "/x/Game [Disc 1].iso"),
    ("/x/Game (Disc 2 of 3) (USA).iso", "/x/Game (Disc 1 of 3) (USA).iso"),
    ("/x/Game (Disc 9).iso", "/x/Game (Disc 1).iso"),
])
def test_the_disc_one_image_is_the_same_name_with_a_one(path, first):
    assert C.disc_one(path) == first


@pytest.mark.parametrize("path", ["/x/Game.iso", "/x/Game (Disc 1).iso", "/x/Game (Disc 0).iso", "/x/Game (Disc).iso", "/x/(USA) Game.iso"])
def test_other_names_use_the_image_itself(patched, path):
    assert C.disc_one(path) is None
    fs = Fs({"/tmp/cfg.bin": cfg(path), path: iso(cnf("cdrom0:\\SLES_500.01;1"))})
    assert card(hook(patched, fs)) == "/savedata/vmc/SLES-50001.VM2"


@pytest.mark.parametrize("boot,serial", [
    ("cdrom0:\\SLUS_213.45;1", "SLUS-21345"),
    ("cdrom0:SCES_503.42;1", "SCES-50342"),
    ("cdrom0:/slps_250.01;1", "SLPS-25001"),
    ("cdrom0:\\SLUS_213.45", "SLUS-21345"),
])
def test_the_serial_format(patched, boot, serial):
    assert C.serial_from_cnf(cnf(boot)) == serial
    fs = Fs({"/tmp/cfg.bin": cfg("/x/G.iso"), "/x/G.iso": iso(cnf(boot))})
    assert card(hook(patched, fs)) == f"/savedata/vmc/{serial}.VM2"


def test_system_cnf_is_found_after_other_files_in_the_root(patched):
    fs = Fs({"/tmp/cfg.bin": cfg("/x/G.iso"), "/x/G.iso": iso(cnf(), extra_files=5)})
    assert card(hook(patched, fs)) == "/savedata/vmc/SLUS-21345.VM2"


@pytest.mark.parametrize("image", [
    iso(b"BOOT = cdrom:\\SLUS_006.62;1\r\n"),  # a PS1 disc: no BOOT2
    iso(None),  # no SYSTEM.CNF
    iso(cnf("cdrom0:\\AB;1")),  # too short
    iso(cnf(), magic=b"XXXXX"),  # not an ISO9660 volume
    b"",
])
def test_an_image_that_does_not_give_a_serial_leaves_the_shared_card(patched, image):
    fs = Fs({"/tmp/cfg.bin": cfg("/x/G.iso"), "/x/G.iso": image})
    assert card(hook(patched, fs)) == ""


@pytest.mark.parametrize("files", [{}, {"/tmp/cfg.bin": b""}, {"/tmp/cfg.bin": b"\x02\0\0\0"}, {"/tmp/cfg.bin": cfg("/x/Missing.iso")}])
def test_no_cfg_or_no_image_leaves_the_shared_card(patched, files):
    assert card(hook(patched, Fs(files))) == ""


def test_every_opened_file_is_closed(patched):
    fs = Fs({"/tmp/cfg.bin": cfg(G2), G2: iso(cnf()), G1: iso(cnf("cdrom0:\\SLUS_213.34;1"))})
    hook(patched, fs)
    assert not fs.fds
    bad = Fs({"/tmp/cfg.bin": cfg("/x/G.iso"), "/x/G.iso": iso(cnf(), magic=b"XXXXX")})
    hook(patched, bad)
    assert not bad.fds


def test_registers_stack_and_condition_register_are_as_the_stock_code_expects(patched):
    cpu = hook(patched, Fs({"/tmp/cfg.bin": cfg(G2), G2: iso(cnf())}))
    assert [cpu.r[n] for n in (3, 4, 6, 7, 8, 9, 10)] == [0, 0, *[0x1000 + n for n in (6, 7, 8, 9, 10)]]
    assert cpu.r[1] == STACK and cpu.lr == 0x4242 and (cpu.r[12] >> 12) & 0xF == 0b1010


@pytest.mark.parametrize("slot,r4,p", [
    (1, 0, SHARED),  # memory card 2 is left alone
    (0, 5, SHARED),  # r4 must be 0
    (0, 0, None),  # no path: the card object already holds one
    (0, 0, "/dev_hdd0/game/NPJA00000/USRDIR/SAVEDATA/SCEVMC0.VME"),  # PS2 Classics layout
    (0, 0, "/savedata/vmcX/PS2.VM2"),
])
def test_everything_else_goes_through_untouched_and_without_touching_files(patched, slot, r4, p):
    fs = Fs({"/tmp/cfg.bin": cfg(G2), G2: iso(cnf())})
    cpu = hook(patched, fs, slot, r4, p)
    assert cpu.r[5] == (0 if p is None else BUF) and fs.log == []



def test_the_stack_stays_inside_the_small_frame(patched):
    fs = Fs({"/tmp/cfg.bin": cfg(G2), G2: iso(cnf())})
    cpu = hook(patched, fs)
    low = min(a for a in cpu.mem if STACK - 0x10000 < a <= STACK)
    assert STACK - C.FRAME <= low and C.FRAME <= 0x500


def test_every_read_of_an_image_is_aligned(patched):
    fs = Fs({"/tmp/cfg.bin": cfg(G2), G2: iso(cnf())})
    hook(patched, fs)
    reads = [e for e in fs.log if e[0] == "read" and e[1] != "/tmp/cfg.bin"]
    assert reads and all(off % C.ALIGN == 0 and size % C.ALIGN == 0 for _, _, off, size in reads)


@pytest.fixture(scope="module")
def debug_patched() -> bytes:
    path = os.environ.get("PS2_NETEMU_SELF")
    if not path:
        pytest.skip("stock SELF not provided")
    return P.apply_edits(P.extend_text(S.unpack(Path(path).read_bytes())), P.crop_edits() + P.card_edits(debug=True))


def marker(cpu: Cpu) -> str:
    return "" if cpu.r[5] == BUF else cpu.cstr(cpu.r[5]).removeprefix("/savedata/vmc/").removesuffix(".VM2")


@pytest.mark.parametrize("files,stage", [
    ({}, "DBG_A"),
    ({"/tmp/cfg.bin": b""}, "DBG_B"),
    ({"/tmp/cfg.bin": b"\x02\0\0\0\0\0\0\0"}, "DBG_C"),
    ({"/tmp/cfg.bin": cfg("/x/Missing.iso")}, "DBG_D"),
    ({"/tmp/cfg.bin": cfg("/x/G.iso"), "/x/G.iso": iso(cnf(), magic=b"XXXXX")}, "DBG_E"),
    ({"/tmp/cfg.bin": cfg("/x/G.iso"), "/x/G.iso": iso(None)}, "DBG_G"),
    ({"/tmp/cfg.bin": cfg("/x/G.iso"), "/x/G.iso": iso(b"BOOT = cdrom:\\SLUS_006.62;1\r\n")}, "DBG_I"),
])
def test_the_debug_build_marks_the_stage_where_it_gave_up(debug_patched, files, stage):
    fs = Fs(files)
    assert marker(hook(debug_patched, fs)) == stage
    assert not fs.fds


def test_the_debug_build_marks_a_path_outside_the_vmc_folder(debug_patched):
    assert marker(hook(debug_patched, Fs({}), p="/dev_hdd0/savedata/vmc/PS2.VM2")) == "DBG_Y"


def test_the_debug_build_still_gives_the_serial_when_everything_works(debug_patched):
    assert marker(hook(debug_patched, Fs({"/tmp/cfg.bin": cfg(G2), G2: iso(cnf())}))) == "SLUS-21345"
