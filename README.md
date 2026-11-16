# ps2_netemu v2.00

A patched `ps2_netemu.self` (the PS3's software PS2 emulator) and an installer package for it. The package is always
`ps2_netemu_v2.00.pkg` (patch version 2.00); the release tag counts the published builds.

## Status

**The published package (`latest`, `ps2_netemu_v2.00.pkg`) has both features, confirmed on the console (Grandia III disc 2).**

| Feature | State |
|---|---|
| Fill the 4:3 frame: crop the black bands at the top and bottom of the picture | Confirmed: the screen is 100% filled |
| One memory card per game | Confirmed: the game loaded the save and wrote to its own card (`PS2_C00.VM2`), the shared `PS2.VM2` stayed untouched |
| Safe installer (backup, hash checks, restore) | In the package |
| Installer creating the cards and the table from the ISOs | In the package (host tests pass; the table and the card of the tested game were put by hand over FTP) |

Limits: 32 games (the 33rd and later keep the shared `PS2.VM2`); an ISO file name longer than 126 bytes is left on the shared
card; cards are named by slot (`PS2_C00.VM2`), the file `PS2_CARDS.TBL` says which game each one is.

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

The card of a game is chosen by the **ISO file name**. All the discs of a game (names that differ only by a `(Disc N)` or
`[Disc N]` tag) share one card, so the save of disc 1 is there on disc 2 (Grandia III has a different disc serial on each
disc, which is why a serial based card, as in the PS1 patch, would split it).

How it works (`cave_slots.py`): the image carries 32 fixed card paths, `/savedata/vmc/PS2_C00.VM2` to `PS2_C31.VM2`, and
the hook only computes `slots + slot * 26`. Which slot a file name uses is in `/savedata/vmc/PS2_CARDS.TBL`, written by the
installer: 128 byte records (slot byte, ISO file name, NUL padding) ended by an empty record. `0x12a528(slot, 0, path, ...)`
receives the card path in `r5`; for memory card 1 and a path in `/savedata/vmc/` the hook

1. reads `/tmp/cfg.bin`, which Cobra fills with the mounted ISO (a type byte, then the path), with the emulator's own file
   calls (`0x1ecc5c` open, `0x1ed5cc` read at an offset, `0x1ecb10` close, the ones the function itself uses on the card);
2. takes the last path component and walks the table file record by record comparing names;
3. on a match points `r5` at the slot path. Anything else (no table, no match, unreadable file) leaves the shared card.

Nothing is ever stored outside the stack frame. This shape is the result of the console tests, in order:

* a fixed redirect of the card path works;
* a read of `/tmp/cfg.bin` followed by a fixed redirect works, and `cfg.bin` is a type byte plus the ISO path;
* choosing between fixed paths by what was read works (`--probe-select`, then a name table inside the image, `--table-card`);
* every build that **built the card path at run time** took the console down (path in the code page, path in a data
  segment extended past its original size, ISO reading with the serial from `SYSTEM.CNF`). The exact reason is not
  established; the path has to stay valid for the whole emulator function (`r28`), so a fixed string is the safe answer.
  Those experiments stay in the repository as `cave_cardfile.py` (`--file-card`), `cave_card.py` and `cave_serial.py`.

Other findings (Grandia III disc 2):

* The emulator does **not** create a missing card, so the cards must exist. The installer creates them.
* The card file date does not move when the emulator writes: compare hashes, not dates.

`ps2card.py` builds a blank formatted card (`.VM2`: 8 MB of data plus 16 ECC bytes per page); the ECC rule was fitted on
all 1265 written pages of a real card and the blank card reproduces its superblock page exactly. `copy_save` copies a save
between cards (verified byte for byte). The installer (`installer/source/cards.cpp`) scans `/dev_hdd0/PS2ISO`, updates the
`PS2_CARDS.TBL` (keeping the slots already given, so a game never changes card when others are added) and creates the cards that do not exist (it never touches an existing one).

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
