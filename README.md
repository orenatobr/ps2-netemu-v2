# ps2_netemu v2

A patched `ps2_netemu.self` (the PS3's software PS2 emulator) and an installer package for it. The package is named after the
release: `ps2_netemu_v<version>.pkg` (the version lives in `VERSION`, the tag is `v<version>`, and [CHANGELOG.md](CHANGELOG.md) lists
what changed in each release).

## Status

Release `v2.08`. Checked on the console with the Grandia III and Dragon Quest VIII ISOs.

| Feature | State |
|---|---|
| Fill the 4:3 frame: crop the black bands at the top and bottom of the picture | Confirmed on the TV: the screen is 100% filled |
| One memory card per game, named after the ISO title, no limit on the number of games | Confirmed: the game loaded its save and wrote to its own card, `PS2.VM2` stayed untouched |
| Memory card 1 always present | Confirmed: when the launcher leaves the path buffer of card 1 empty the shared `PS2.VM2` is used |
| Installer creating the missing cards from the ISOs | The Dragon Quest VIII card appeared on the console right after the package ran (not made by `tools/make_cards.py`); a run of the app with a brand new ISO is the check still to do |
| Installer works when webMAN already mounted `/dev_blind` | In `v2.05` (before, the app said "could not open the system files") |
| Menu value "Normal" keeps its stock name | In `v2.07` (v2.05 and v2.06 renamed it to `4:3`; `--labels` still does) |
| **16:9 option in that menu (full screen stretch)** | **Not implemented**, see "16:9: what was found" below. |
| No blur: texture sampler NEAREST instead of LINEAR in the texture binder | In `v2.08`. By reading the code and host tests; not seen on the TV |
| No dither: RSX dither switch (method `0x0300`) written as 0 in the state reset | In `v2.08`. Same caveat; on an 8 bits per channel target it should change nothing visible |
| Safe installer (backup, hash checks, restore) | In the package |
| Progress bar on Install, Restore and the card creation; button icons; English only; version from `VERSION` | In `v2.06`. Host tests cover the progress reports (bar never goes back, ends at 100%); not yet seen on the console |
| Installer works with any emulator file already there (stock, this release, any earlier build, unknown file with a backup), with `/dev_blind` mounted or not | In `v2.06`, covered by host tests with the real install logic; the list of earlier builds is the SHA-256 of every build made so far |

Limits: the emulator cannot create a card file, so a game without its card uses the shared `PS2.VM2`. The cards are made by the
app: after adding ISOs, open **PS2 Emulator Patch** and press Cross again (or run `tools/make_cards.py` from the Mac). New cards start
empty. The card name is cut at 52 bytes, so two different games that share their first 52 bytes would share a card.

## 16:9: what was found

The menu item "Screen mode" has three values on the console: Off, Normal and Full Screen (seen on the TV; an earlier reading of this image
that said "Normal is the only value" was wrong). What is known, all by static analysis (the console restarts into the emulator when a
game starts, so nothing could be measured live):

* The strings are one offset table (`0x712106`, 20 languages x 61 ids, index `lang*61 + id`); id 6 is "Off", id 7 is "Normal", id 8 is "Screen Mode"
  and id 57 is "Full Screen". The string getter `0x27dcf8` is reached through a function pointer and no code of this image loads those ids
  together, so the menu is built from data this analysis did not find. `ps2_emu.self` and `ps2_gxemu.self` carry the same strings.
* The picture routine `0x282978` draws into a surface of exactly the output size, with no x offset; the pillar bars are not made there.
* The output size and the video flags are filled from messages of the host (`0x1161b4`, `0x115f54`, `0x116ea4`). Widening the size
  returned by `0x115ee4` gives a black screen (`--wide`).
* The host sends settings bytes that the emulator stores in the device object (`+0xCC`, `+0xCD`, `+0xCE`, handler near `0x12fd40`); which one is the
  screen mode is not yet known.

A patch that guesses the aspect call could keep PS2 games from starting, so none is shipped. The way forward needs console
experiments (a build per hypothesis, checked on the TV).

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

The card of a game is named after the **ISO file name**: `PS2_<title>.VM2`, with no folder, no short extension and no
`(Disc N)` / `[Disc N]` tag (nor the space before it), cut at 52 bytes, and every byte that is not a letter, a digit, `_` or `-` turned into
`_`. All the discs of a game therefore share one card (Grandia III has a different serial on each disc, so a serial based card
would split the game), there is no limit on the number of games, and `Grandia III (USA) (Disc 2).iso` uses
`PS2_Grandia_III__USA_.VM2`.

### How the emulator picks the card (found by reading the image)

At game start a routine (`0x12c17c...`) opens the card of slot 0 only if the path buffer at `object + 0x22e0` (256 bytes, the
emulator's own memory) is not empty. The launcher fills that buffer through `0x12abc4(slot, name)`, which builds
`snprintf(buf, 256, "%s%s.VM2", "/savedata/vmc/", name)` and calls `0x12a528`. The emulator never creates a card file (its file open is
a request to the host with only a channel and a path).

### What the hook does (`cave_bufcard.py`, on the check at `0x12c988`)

1. Does nothing when a marker byte (`buffer + 0xFF`) says it already ran, or when the buffer holds a path outside `/savedata/vmc/`
   (the PS2 Classics layout).
2. Reads `/tmp/cfg.bin` (Cobra: a type byte, then the path of the mounted ISO) with the emulator's own file calls
   (`0x1ecc5c` open, `0x1ed5cc` read, `0x1ecb10` close), builds the card path on its own stack frame, checks that the card exists
   and copies the path into the buffer.
3. When anything fails, an empty buffer gets `/savedata/vmc/PS2.VM2` and a filled one is left as the launcher wrote it.

Nothing is stored outside the stack frame and the emulator's own path buffer.

### What was tried before, in order (kept as flags, not shipped)

* a fixed redirect of the card path, and a read of `cfg.bin` followed by a fixed redirect, worked;
* a name table inside the image (`--table-card`), then 32 fixed slot paths with a table file (`--slots-card`, published in `v2.03`),
  worked while the launcher filled the buffer;
* every build that **built the path at run time outside the emulator's own memory** took the console down (the code page, a data
  segment extended past its stored size) and a wrapper that called the original function from its own frame froze it (`--wrap-card`);
* a hook on `0x12a528` or on the name argument never mattered on the day the buffer came empty, because that function is not reached.

Other findings:

* The card file date does not move when the emulator writes: compare hashes, not dates.
* `ps2bootparam.dat` is the launcher's network configuration (it carries the Wi-Fi data of the console); it has no card information.

`ps2card.py` builds a blank formatted card (`.VM2`: 8 MB of data plus 16 ECC bytes per page); the ECC rule was fitted on
all 1265 written pages of a real card and the blank card reproduces its superblock page exactly. `copy_save` copies a save
between cards (verified byte for byte). The installer (`installer/source/cards.cpp`) scans `/dev_hdd0/PS2ISO`, updates the
`PS2_CARDS.TBL` (keeping the slots already given, so a game never changes card when others are added) and creates the cards that do not exist (it never touches an existing one).

Saves kept in the old shared `PS2.VM2` do not appear in a new per-game card. To start a game with its save, copy it into
the card with `ps2card.copy_save`.

## Experiments in the repository (not in the published package)

Behind flags of `ps2_netemu_patch.py`; the default build is crop plus `cave_bufcard.py`.

* `--bufpath` (`cave_bufpath.py`): only fills an empty slot 1 buffer with `PS2.VM2` (the smallest fix of the "no card" problem).
* `--slots-card`, `--table-card`, `--file-card`, `--wrap-card`, `--defname`: the earlier designs above.
* `--wide` (`cave_wide.py`): returns the video output width times 4/3. Meant for 16:9 games that squeeze the picture into the 4:3 frame
  (Dragon Quest VIII); on the console it gave a **black screen** (the getter is used for more than the picture rectangle), so it is
  not a way forward as it is. The 16:9 menu option is the open item (see Status).

## Creating the cards without opening the app

The emulator cannot create a card file and a PS3 app cannot run in the background, so the creation can also be done from the
Mac: `python tools/make_cards.py 192.168.1.85` lists `/dev_hdd0/PS2ISO` over FTP, works out the card name of every ISO with the
rule of the patch and uploads a blank card for each one that does not exist (existing cards are never touched). It can run on a
schedule (launchd or cron) while the Mac and the console are on the same network.

## Install

1. Copy `ps2_netemu_v<version>.pkg` to the console (USB drive or `/dev_hdd0/packages`) and install it from the XMB
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
python ps2_netemu_patch.py ps2_netemu.self ps2_netemu_v2.bin
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
tools/dist.sh       # ../dist/ps2_netemu_v<version>.pkg (needs a CHANGELOG.md section for the version)
tests/run.sh        # install/restore logic, runs on the Mac
```

`installer/` reuses the canvas, fonts and file helpers of [HomeTidy](https://github.com/orenatobr/hometidy-ps3) and is
licensed GPL-2.0 like it.

## Notes

The patched binary is Sony's code with a few words changed. Use it on your own console only; this repository is private
for that reason, so downloads need the owner's login.
