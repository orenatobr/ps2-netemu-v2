# ps2_netemu v2.00

A patched `ps2_netemu.self` (the PS3's software PS2 emulator) and an installer package for it. The package is always
`ps2_netemu_v2.00.pkg` (patch version 2.00); the release tag counts the published builds.

## Status

**The published package (`latest`, `ps2_netemu_v2.00.pkg`) contains only the image fix.** The per-game memory card is not in it.

| Feature | State |
|---|---|
| Fill the 4:3 frame: crop the black bands at the top and bottom of the picture | **In the published package. Confirmed on the console**: the screen is 100% filled |
| One memory card per game | **Not published, not working yet.** Redirecting the card to a fixed file works; choosing the file by the disc serial has taken the console down in tests, see below |
| Safe installer (backup, hash checks, restore) | In the published package |
| Installer creating the missing per-game cards from the ISOs | In the repository (host tests pass), not in the published package |

Known limitation of the card work: discs of the same game with different serials (Grandia III disc 1 is `SLUS-21334`, disc 2
is `SLUS-21345`) would get different cards, because the emulator side cannot see the ISO file names without reading the ISO
from inside the emulator, which is the part that failed on the console. The PS1 patch groups them by the `(Disc N)` name.

## What it is

`ps2_netemu.self` is not an ordinary PS3 application. It is a kernel-type SELF (`self_type` LV2, key set for version
`0x0004009000000000`): it has privileged instructions (`rfid`, `slbmte`, `tlbie`, `mtmsrd`) and talks to the system
through `sc` calls. When a PS2 game starts, the console restarts into this image and the network (webMAN, FTP) goes
away until the game is closed. That has two consequences for this project:

* the emulator cannot be inspected while it runs, so every change is found by static analysis and checked by what the
  owner sees on the TV and by the files the emulator leaves on the disk;
* a wrong patch only breaks PS2 ISO launching; the XMB keeps working and the original can be restored.

## Feature 1: the black bands at the top and the bottom

The routine at `0x282978` draws the game frame as a textured rectangle. Decoded from its vertex stream: the four
positions run from `(0,0)` to the output size (arguments `r5`, `r6`, which the caller reads from `0x115ee4`, the video
output size) and the four texture coordinates from `(0,0)` to the source size (`r9`, `r10`: width `f30`, height `f27`).
It is the only caller chain (`0x4a308` to `0x2859f8` to `0x282978`), so it is the picture of the game.
Confirmed on the console: adding 100 to the destination height moved the picture.

The bands are inside the texture (the first and the last rows of the GS output), so the fix is in the texture
coordinates: `cave_crop.py` stores `CROP_TOP * height` and `(1 - CROP_BOTTOM) * height` in free stack slots and gives
the two top vertices and the two bottom vertices those texture `y` values instead of `0` and `height` (five hooks,
code in the 0x6c0 spare bytes at the end of the text page). The visible rows are stretched over the same frame, so the
4:3 pillar bars (the output viewport) are untouched.

History on the console (Grandia III): cropping only the top made the band reappear at the bottom with the same size,
so the texture has a blank band on both ends; cropping 16 of 448 rows on each end fills the screen completely, with
nothing cut. Not yet known: whether every game and video mode (480i, 480p, PAL) has the same bands.

## Feature 2: one memory card per game

The same logic as the PS1 emulator patch: the card is named after the **serial** read from `SYSTEM.CNF` of the disc
(`SLUS-21345.VM2`), and a disc named `(Disc N)` (N from 2 to 9) uses the card of the `(Disc 1)` image with the same name
when that image exists.

How it works (`cave_card.py`): `0x12a528(slot, 0, path, ...)` receives the card path in `r5`. For memory card 1 and a
path in `/savedata/vmc/` (the shared card of ISO games) the hook

1. reads `/tmp/cfg.bin`, which Cobra fills with the path of the mounted ISO, with the emulator's own file calls
   (`0x1ecc5c` open, `0x1ed5cc` read at an offset, `0x1ecb10` close, the ones it uses for `ps2bootparam.dat`);
2. opens the image, reads the volume descriptor, walks the root directory record by record and reads `SYSTEM.CNF`;
3. turns `BOOT2 = cdrom0:\SLUS_213.45;1` into `SLUS-21345` and points `r5` at `/savedata/vmc/SLUS-21345.VM2`.

Anything it does not understand leaves the shared card. It uses a 512 byte stack frame and one 256 byte buffer.

Findings on the console (Grandia III disc 2):

* Redirecting `r5` works: a fixed path to a card made by `ps2card.py` was loaded, and the game saved in it.
* The emulator does **not** create a missing card, so the cards must exist. The installer creates them (below).
* Calling the emulator's file functions from the hook is safe when the frame and the reads are small (a first version
  with a 2.8 KB frame and 2 KB reads took the console down).
* The card file date does not move when the emulator writes: compare hashes, not dates.

`ps2card.py` builds a blank formatted card (`.VM2`: 8 MB of data plus 16 ECC bytes per page); the ECC rule was fitted on
all 1265 written pages of a real card and the blank card reproduces its superblock page exactly. `copy_save` copies a save
between cards (verified byte for byte). The installer (`installer/source/cards.cpp`) scans `/dev_hdd0/PS2ISO`, finds the
serial of each image with the same disc 1 rule and creates the cards that do not exist (it never touches an existing one).

Saves kept in the old shared `PS2.VM2` do not appear in a new per-game card. To start a game with its save, copy it into
the card with `ps2card.copy_save`.

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
