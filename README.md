# ps2_netemu v2

A patched `ps2_netemu.self` (the PS3's software PS2 emulator) and an installer package for it. The package is named after the
release: `ps2_netemu_v<version>.pkg` (the version lives in `VERSION`, the tag is `v<version>`, and [CHANGELOG.md](CHANGELOG.md) lists
what changed in each release).

## Status

Release `v2.13`. Checked on the console with the Grandia III and Dragon Quest VIII ISOs. The Screen Mode shortcut (SELECT + L1 + R1) was checked on the console in `v2.12`; one glitch is open (see the table).

| Feature | State |
|---|---|
| Fill the 4:3 frame: crop the black bands at the top and bottom of the picture | Confirmed on the TV: the screen is 100% filled |
| One memory card per game, named after the ISO title, no limit on the number of games | Confirmed: the game loaded its save and wrote to its own card, `PS2.VM2` stayed untouched |
| Memory card 1 always present | Confirmed: when the launcher leaves the path buffer of card 1 empty the shared `PS2.VM2` is used |
| Installer creating the missing cards from the ISOs | The Dragon Quest VIII card appeared on the console right after the package ran (not made by `tools/make_cards.py`); a run of the app with a brand new ISO is the check still to do |
| Installer works when webMAN already mounted `/dev_blind` | In `v2.05` (before, the app said "could not open the system files") |
| Menu value "Normal" keeps its stock name | In `v2.07` (v2.05 and v2.06 renamed it to `4:3`; `--labels` still does) |
| **Shortcut: hold SELECT + L1 + R1 in a game to switch the Screen Mode between Normal and Full Screen** | In `v2.12` and later, DualShock 3 only. Works on the console (the picture changes at once). **Open glitch:** going back to Normal leaves the side bars with a frozen copy of the Full Screen picture instead of black; the menu does not do that. See "The live Screen Mode and the shortcut" below. |
| 16:9 option in that menu (full screen stretch) | Not implemented as a menu item, see "16:9: what was found" below |
| No blur: texture sampler NEAREST instead of LINEAR in the texture binder | In `v2.08`. By reading the code and host tests; not seen on the TV |
| No dither: RSX dither switch (method `0x0300`) written as 0 in the state reset | In `v2.08`. Same caveat; on an 8 bits per channel target it should change nothing visible |
| Radiata Stories (US) experience points through webMAN | Fixed in `v2.09`, speed in `v2.10`: the app writes a CONFIG with the unpack hook and only the safe loop edit beside the ISO (see "Radiata Stories" below). Played on a console |
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

### Screen Mode is the "Up Convert" setting

The emulator has a debug overlay (`0x26d6bc` to `0x26d9d4`) that prints named settings: `Boot Type`, `Region Type`, `Lang Type`, `Color Space`,
`Video Mode`, `Display Type`, `Sound Type`, `Up Convert`, `Initial Up Convert` and `RGB Output Range`. "Up Convert" is the Screen Mode of the menu.
Found by static analysis only; nothing here was measured on a console.

* The settings object is at `0xb46100` (zero-filled data, filled at run time). 25 TOC slots point at it, among them `-0x36b0`, `-0x2ef8`
  and `-0x79a8`. Up Convert is the byte at `+0x28` (getter `0x11ab30`), Initial Up Convert the byte at `+0x29` (getter `0x11b2c8`), RGB Output
  Range the byte at `+0x2b` (getter `0x11b35c`). Every getter checks the initialised flag at `+0`.
* The values are 0 Off, 1 Normal and 2 Full Screen. The decoder at `0x262978` turns the byte into `+0x10 = (value == 0)` and `+0x14 = (value == 2)`,
  and the video start-up at `0x262ac4` stores `value == 2` at `+0x1c` of the display configuration at `0x306f380`.
* The only store to `+0x28` is the bulk copy of a settings block sent by the host (`0x11ac64`; the byte comes from block offset `0x2284`, copied
  by `lbz` at `0x11ad18` and `stb` at `0x11ad1c`). There is no setter.
* The readers are the video start-up (`0x262a58`, which reads the value once and passes Initial Up Convert on to two methods of the display
  object), the menu item states (`0x2784a4`, `0x2784e8`, `0x27c0a8`), the controller report builder (`0x120ee8`) and the overlay. No instruction in the
  image reads the byte inline: all 25 TOC slots that point at the object were checked for `lbz ...,0x28(...)` through `0x2b`.

What that means: nothing reads Up Convert while a frame is drawn, so flipping this byte at run time cannot change the picture. The shortcut
flips the live Screen Mode word instead (next section).

Other things learned on the way:

* The output size is set by `0x117490` from a mode index (case 0 is 640x480, cases 4 and 5 are 1280x720, cases 6 to 9 are 1920x1080) and sent to
  the host. The picture routine `0x282978` draws a quad over the whole output surface (viewport and scissor are `(0, 0, width, height)`), so where the
  4:3 pillar bars come from is still unknown.
* The DualShock 3 report parser is `0xe85a0`. Its input `r25` is the HID report (byte 2: SELECT, L3, R3, START and the d-pad; byte 3: L2, R2, L1, R1 and
  the face buttons) and its output `r27` follows the `CellPadData` layout: halfwords `+4` and `+6` are the two digital bytes, `+8` to `+0xe` the sticks and
  `+0x10` to `+0x26` the twelve pressure values. The generic path stores the digital halfwords at `0xe8714` and `0xe871c`; a button combination can be
  read there (`r0` and `r9` are rewritten by the next instructions, the other registers were not checked). Not used yet.
* The stock `ps2_netemu.self` can be rebuilt from `installer/payload/ps2_netemu_v2.bin`: unpack it, put back the stock words of the default edits
  (`crop_edits`, `bufcard_edits`, `nofilter_edits`, `nodither_edits`), remove the `0x6c0` text extension from program header 0 and repack with the
  payload as the container. The SHA-256 comes out as `bad3e45c...c80a`, so the file is the original.

#### The live Screen Mode and the shortcut

The value that changes while a game runs is not the `+0x28` byte. The video thread (`0x262a58`, loop at `0x262d00`) waits on an event group and, when
bit `0x00800000` comes back, asks the display object (`0x30700d0`) for the mode through its method at `+0x88` and stores `mode == 2` as the Full Screen
flag (`+0x1c` of the display configuration at `0x306f380`). Method `+0x88` of the real class (vtable `0x949cb8`, chosen by `0x27c83c`) reads the word at
`0x3172f70` (TOC slot `-0x2df0`) and `+0x90` writes it. That word is the live Screen Mode: 1 Normal, 2 Full Screen. The video start-up stores the
Initial Up Convert in it. No code of the emulator sets the event bit; it comes from the system, which is also why the menu works while a game runs.

`python ps2_netemu_patch.py ps2_netemu.self out.self --hotkey` (`cave_hotkey.py`) hooks the DualShock 3 parser at `0xe8720`. While SELECT, L1 and R1 are
held it switches that word between 1 and 2 once per press (one byte of state at `0x3175470`, in the zero filled tail of the data). It does not wake
the video thread; on the console the picture changes at once anyway, so the system raises the event often enough. Only the generic report path is hooked
(the DualShock 3 and similar); the two device types that branch earlier are not.

Open glitch (seen on the console in `v2.12`): after Full Screen and back to Normal the side bars keep a frozen copy of the Full Screen picture. Setting
Normal from the menu is clean, and the menu writes the same word (the two-option widget at `0x27831c` calls method `+0x90`), so something around the
menu (the game is paused and redrawn) clears the bars and the shortcut does not. The picture routine `0x282978` clears only when a stack flag is set and
its viewport covers the whole surface, so the bars are left by the composition layer (`0x276008`, the type routines at `0x2677b8`). Not solved.

#### Experiment: force Full Screen at the start

`python ps2_netemu_patch.py ps2_netemu.self out.self --up-convert=2` replaces the one `lbz` at `0x11ad18` with `li r0,2`, so the settings copy stores
Full Screen whatever the host sent (`--up-convert=1` stores Normal, `=0` Off). The build differs from the default one by exactly that word. It is not in the
package. The question it answers on a console: does the picture fill the screen from the first frame of a game? If it does, the Screen Mode is applied
when the video starts and a shortcut can only choose it for the next start. If it does not, the screen scaling is entirely on the host side.

## Radiata Stories: random experience through webMAN

A PS2 Classics package runs the game with the official CONFIG; an ISO mounted by webMAN runs with `<iso>.CONFIG`, which webMAN fills on the first
mount from its database (`CUSTOM`, then `NET`, `GX`, `SOFT`). For SLUS_212.62 the `CUSTOM` entry (112 bytes) is the `GX` one (revision `0x4457`, xgkick
delay 8, EE hook function `0x0A` at `0x124D94`, hook `0x0B` at `0x1AF618`) plus smoothing off (`0x44`), instruction cache emulation off (`0x21 0`) and four
`EE_INSN_REPLACE32` edits: `0x125004`, `0x1250A4` and `0x14205C` change `b -6` (`0x1000FFFA`) into `bne zero, zero` (`0x1400FFFA`), and `0x22F754` changes
`li v1,1` into `move v1,zero`. The hook `0x0A` is the TriAce unpack fix: the game unpacks data with VU0 and the result is 1 off in the emulator. The
edits at `0x125004` and `0x1250A4` are in the same routine (the game code at `0x124D90` is `sqc2 vf3,0(v0)`), so they remove the wait for that VU0 work and the
tables read afterwards (the experience tables) are wrong: a battle shows the experience ticking down to 1, resetting to the level 1 value and the characters never
level up. Source of the symptom: the PSX-Place thread "Radiata Stories Exp bug" (the PS2 Classics config works, the database one does not).

`configs.cpp` writes the `GX` content plus `0x44` and the one loop edit at `0x14205C` (78 bytes, since `v2.10`), and `isoinfo.cpp` reads the serial of each ISO
from its `SYSTEM.CNF`. Only the US serial is handled, because the hook addresses are the ones of that release. Played in a battle on a console: the experience
is right and characters level up. Turning the instruction cache emulation off (`0x21 0`) was tried for speed and broke the experience again.

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

## The controller turns off when a PS2 game starts (investigated, not changed)

On the owner's console the DualShock turns off when a PS2 game is loaded and has to be turned on again with the PS button. Whether the emulator could keep it on was looked at in the stock `ps2_netemu.self` (SHA-256 `bad3e45c...`). Nothing in the package changes it.

What the stock emulator has:
- Its own HID and Bluetooth layer. The module names are in its read-only data: `HidGamepadMgr`, `HidPadWrapper`, `pad_manager`, `pairing_manager`, `authentication_manager` / `HID_AUTH`, `status_manager`, `deci3_pad`, `mouse_manager`, `mediacontrolkey_manager`, a `_sys_hid_core_thread`, and Bluetooth command names (`BT_REG`, `BT_END`, `BT_BD0`, `BT_BR0`...). They sit in pointer tables of the read-only data (`0x74bc30` to `0x74c430`) that no instruction reaches by an address it builds or by the table of contents (`r2 = 0xc600`); only the data tables point to them.
- The in-game menu of the PS button, with the items "Reassign the Controller" and "Turn Off the Controller", and the message "Press the PS button.".
- No import of the usual pad library (none of its function ids is in the file) and no LV2 HID system call. The calls with large numbers (`0x1002`, `0x1234`, `0x1237`) are exits followed by an endless loop.
- A documented config command for the multitap and the order controllers are synced to the ports, nothing for powering a controller on or off.

What the public sources say: the stock PS2 Classics behaviour is to turn the controller off when the emulator starts and when it ends, with "Press the PS button" shown in a corner, because the console switches between the XMB and the emulator. The webMAN MOD source has nothing about it, and its list of known patches for this emulator only has the debug menu.

Why nothing was changed: no instruction in the emulator that powers the controller off at start could be found, and the Bluetooth link cannot be observed from the console (webMAN does not show it), so a patch would be blind and could break the controller input that works today. The turn off most likely happens before the emulator runs, on the system side.

It is not this patch: a word by word comparison of the stock emulator with the build shipped in the package (the one on the console) finds changes in only these places: the segment size in the header (`0x64`), the memory card check hook (`0x12c988`), five single words in the picture code (`0x28394c`, `0x2839a8`, `0x283ad8`, `0x283c08`, `0x283d2c`) and the code cave at `0x2ff940`. None of them is in the controller or HID code, so the controller behaves as in the stock emulator.

Confirmed on the console by the owner (2026-11-19): the original emulator, restored with the Triangle button of the installer, also turns the controller off when the same PS2 game starts, so this is the behaviour of the stock emulator and not of the patch. The webMAN MOD source was searched for the launch path of PS2 games and for pad and Bluetooth handling: its only pad code is for its own menus (`sys_hid_manager_read` in the VSH menu and sLaunch), nothing touches the controller when a PS2 game starts, so the launcher is not the cause either. That leaves the emulator's own start-up or the system switching to the PS2 emulation, which no patch of this package reaches.

A search of the emulator code for the Bluetooth HCI opcodes (Disconnect `0x0406`, Reset `0x0C03`, Write Scan Enable `0x0C1A`) found the numbers `1030` (`0x406`) and `3098` (`0xC1A`) only as the first argument of calls to one function (`0x8e924`) that also gets a string pointer from the table of contents and a small constant. That shape is a trace or log call (an id, a message, a value, a line), not an HCI command being sent, and the Reset opcode does not appear at all. So the search did not find a power-off to neutralise either.

The test that was used: restore the original emulator with the Triangle button of the installer, open the same PS2 game and see whether the controller also turns off. If it does, it is not this patch. If it does not, the patch is the cause and the next step is to bisect the patch edits one at a time.

## Experiments in the repository (not in the published package)

Behind flags of `ps2_netemu_patch.py`; the default build is crop plus `cave_bufcard.py`.

* `--bufpath` (`cave_bufpath.py`): only fills an empty slot 1 buffer with `PS2.VM2` (the smallest fix of the "no card" problem).
* `--slots-card`, `--table-card`, `--file-card`, `--wrap-card`, `--defname`: the earlier designs above.
* `--wide` (`cave_wide.py`): returns the video output width times 4/3. Meant for 16:9 games that squeeze the picture into the 4:3 frame
  (Dragon Quest VIII); on the console it gave a **black screen** (the getter is used for more than the picture rectangle), so it is
  not a way forward as it is. The 16:9 menu option is the open item (see Status).
* `--hotkey` (`cave_hotkey.py`): SELECT + L1 + R1 switches the live Screen Mode word between Normal and Full Screen. In the package since `v2.12`. See "The live Screen Mode and
  the shortcut".
* `--up-convert=0|1|2` (`up_convert_edits`): the settings copy stores that Screen Mode (Off, Normal, Full Screen) instead of the byte the host sent.
  See "Screen Mode is the Up Convert setting". Not checked on a console.

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
