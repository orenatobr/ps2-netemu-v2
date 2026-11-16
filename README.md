# ps2_netemu v2.00

A patched `ps2_netemu.self` (the PS3's software PS2 emulator) and an installer package for it. The package is always
`ps2_netemu_v2.00.pkg` (patch version 2.00); the release tag counts the published builds.

## Status

| Feature | State |
|---|---|
| Remove the black band at the top of the picture, keeping the 4:3 frame | Implemented, **crop amount is a first guess** (see below) |
| One memory card per game | **Not implemented yet** (research done, see below) |
| Safe installer (backup, hash checks, restore) | Done |

## What it is

`ps2_netemu.self` is not an ordinary PS3 application. It is a kernel-type SELF (`self_type` LV2, key set for version
`0x0004009000000000`): it has privileged instructions (`rfid`, `slbmte`, `tlbie`, `mtmsrd`) and talks to the system
through `sc` calls. When a PS2 game starts, the console restarts into this image and the network (webMAN, FTP) goes
away until the game is closed. That has two consequences for this project:

* the emulator cannot be inspected while it runs, so every change is found by static analysis and checked by what the
  owner sees on the TV and by the files the emulator leaves on the disk;
* a wrong patch only breaks PS2 ISO launching; the XMB keeps working and the original can be restored.

## Feature 1: the black band at the top

The routine at `0x282978` draws the game frame as a textured rectangle. Decoded from its vertex stream: the four
positions run from `(0,0)` to the output size (arguments `r5`, `r6`, which the caller reads from `0x115ee4`, the video
output size) and the four texture coordinates from `(0,0)` to the source size (`r9`, `r10`: width `f30`, height `f27`).
It is the only caller chain (`0x4a308` to `0x2859f8` to `0x282978`), so it is the picture of the game.
Confirmed on the console: adding 100 to the destination height moved the picture.

The band is inside the texture (the first rows of the GS output), so the fix is in the texture coordinates:
`cave_crop.py` stores `CROP * height` in a free stack slot and gives the two top vertices that texture `y` instead of
0 (three hooks, code in the 0x6c0 spare bytes at the end of the text page). The visible rows are stretched over the
same frame, so the 4:3 pillar bars (the output viewport) are untouched.

`CROP = 16 / 448` is a first guess for the height of the band. It is tuned with the owner's report of what is left or
what is cut, as was done for the PS1 emulator. Not yet known: whether every game and video mode (480i, 480p, PAL) has
the same band.

## Feature 2: one memory card per game (research, not implemented)

What is known, for the next step:

* The card file name is built at `0x12abc4` as `"/savedata/vmc/" + name + ".VM2"` (format `%s%s.VM2`, `name` = argument
  `r4`, slot = `r3`) and opened by `0x12a528(slot, 0, path, ...)`, which also accepts a ready path. The shared card on
  the console is `/dev_hdd0/savedata/vmc/PS2.VM2` (8,650,752 bytes: 8 MB of data plus 16 bytes of ECC per 512 byte page).
* Experiment 1 asked for the card under another file name (`PS2_T_PS2.VM2`): the emulator did **not** create it. So it
  does not create a missing card by itself, or that name does not come through this path. Either way the cards have to
  exist before the game starts (the installer can create them from the ISOs) and the emulator must fall back to the
  shared card when the per-game one is missing.
* The game serial is not known to the emulator side except through the disc: `0x1339dc` reads `SYSTEM.CNF` from the
  emulated disc (root directory lookup, then the file into a buffer at `object + 0x1448`) and parses `PARAM4`/`VER`.
  A hook right after that read can capture `BOOT2 = cdrom0:\SLUS_xxx.xx;1` into a spare byte buffer.
* `/dev_hdd0/tmp/cfg.bin` (written by Cobra when the ISO is mounted) holds the ISO path, but the emulator image does not
  read it, so multi-disc grouping by file name is not available on this side. Discs with different serials get
  different cards.

## Install

1. Copy `ps2_netemu_v2.00.pkg` to the console (USB drive or `/dev_hdd0/packages`) and install it from the XMB
   (Game > Package Manager > Install Package Files).
2. Open **PS2 Emulator Patch**. Press **Cross** (or Circle with the Japanese layout) to install, **Triangle** to restore
   the original, the other face button to exit.

The app saves the original to `/dev_hdd0/ps2_netemu_stock.self` first and checks every write by hash. It refuses any
`ps2_netemu.self` that is not the one build the patch was made for (SHA-256 `bad3e45c...c80a`).

**If a PS2 game does not start after installing:** open the app and press Triangle, or copy
`/dev_hdd0/ps2_netemu_stock.self` over `/dev_flash/ps2emu/ps2_netemu.self` (webMAN: open `http://<ps3-ip>/dev_blind`
first, and FTP cannot rename over an existing file: delete the old one first).

## How the `.self` is made

`selfio.py` keeps the stock SELF container (header, offsets and sizes do not move). Each segment is decrypted with the
public LV2 key set (published by the RPCS3 project), patched, recompressed to the **same stored size** (zlib, padded
with empty blocks) and encrypted again. The three section HMAC-SHA1s and the ELF SHA-1 are recomputed. Checks that hold
on the real file: the original hashes validate with this code, and repacking the unmodified ELF gives a file that is
**identical byte for byte** to the original. The ECDSA signature is left as it was (the console does not check it).

```
pip install -r requirements-dev.txt
python ps2_netemu_patch.py ps2_netemu.self ps2_netemu_v2.00.self
PS2_NETEMU_SELF=ps2_netemu.self python -m pytest -q tests
```

You need the stock `ps2_netemu.self` (from `/dev_flash/ps2emu/`); it is not in this repository. `ppc_interp.py` (in
`tests/`) is a small PowerPC interpreter that runs the real emulator code with the patch applied.

## Build the package

Needs the [ps3dev](https://github.com/ps3dev/ps3dev) toolchain (`PS3DEV` and `PSL1GHT` set).

```
python ps2_netemu_patch.py ps2_netemu.self installer/payload/ps2_netemu_v2.bin
cd installer
make pkg            # PS2NetemuPatch.gnpdrm.pkg
tools/dist.sh       # ../dist/ps2_netemu_v2.00.pkg
tests/run.sh        # install/restore logic, runs on the Mac
```

`installer/` reuses the canvas, fonts and file helpers of [HomeTidy](https://github.com/orenatobr/hometidy-ps3) and is
licensed GPL-2.0 like it.

## Notes

The patched binary is Sony's code with a few words changed. Use it on your own console only; this repository is private
for that reason, so downloads need the owner's login.
