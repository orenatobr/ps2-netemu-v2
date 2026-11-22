# Changelog

Every release lists what changed here, newest first. The section of a version is its release notes: `installer/tools/release_notes.sh` prints it and `installer/tools/dist.sh` refuses to package a version that has none. The version lives in `VERSION`; the package and the app show it, the tag is `v<version>`.

## v2.14
- Test build for the side bars: after Full Screen and back to Normal, v2.12 and v2.13 left a frozen copy of the Full Screen picture in the side bars. The controller report builder (`0x11ba80`) tells the host the pair (settings Up Convert byte, live Screen Mode) whenever they differ, and after going back to Normal the pair matched again, so the host was never told. Each press of SELECT + L1 + R1 now first copies the mode being left into the settings byte (`0xb46128`), so the host hears "from X to Y" in both directions (`cave_hotkey.py`, 2 more instructions).
- Not known: this rests on reading the code, not on a console. Please report whether the bars are black after going back to Normal. If they are not, the host redraw has another trigger and the next test is what the in-game menu does.
- Pre-release. `latest` stays on v2.13.

## v2.13
- The app showed "v2.10" in its title and in "Patched (v...)" on the v2.11 and v2.12 packages. The installer objects are built with the version and the payload hash as compiler flags, and the Makefile did not rebuild them when `VERSION` or the payload changed, so old objects were reused. Every object now depends on both files.
- The emulator image is the one of v2.12 (SELECT + L1 + R1 switches Normal and Full Screen). Confirmed on a console: the shortcut works.
- Still open: after going back to Normal from Full Screen, the side bars show a frozen copy of the Full Screen picture instead of black. Not fixed in this release.

## v2.12
- Test build of the shortcut: hold SELECT + L1 + R1 in a game to switch the Screen Mode between Normal and Full Screen. The emulator image hooks the DualShock 3 report parser (`0xe8720`) and flips the live Screen Mode word (`0x3172f70`) once per press (`ps2_netemu_patch.py --hotkey`). Everything else is the image of v2.10, so the Screen Mode starts as the system sets it.
- Not known: the video thread recalculates the Full Screen flag when the system raises an event, and nothing in this build raises it. The picture may change only at the next video mode change of the game, or not at all. Nothing was checked on a console. Please report what you see right after pressing the combination, and after the game changes its video mode.
- The shortcut works with the DualShock 3 report path only. Restore the original with the Triangle button of the app if anything misbehaves.
- The app lists the v2.11 image among the earlier builds, so this package installs over v2.11 and v2.10.

## v2.11
- Test build, not a finished feature. The emulator image stores Full Screen (2) as the "Up Convert" setting, the one behind the Screen Mode of the menu, whatever value the system sent when a game starts (`ps2_netemu_patch.py --up-convert=2`, one word at `0x11ad18`). Everything else is the image of v2.10.
- What to check on the console: start a game and see whether the picture fills the screen from the first frame. If it does, the Screen Mode is applied when the video starts. If it does not, the screen scaling is entirely on the system side. Either answer decides how the SELECT + R1 + L1 shortcut can be built.
- The shortcut itself is not in this build, and nothing here was checked on a console. The Screen Mode item of the menu is left as it was.
- The app lists the v2.10 image among the earlier builds, so this package installs over v2.10 and the original can be restored with Triangle.

## v2.10
- Radiata Stories through webMAN, speed: the CONFIG the app writes now also carries one of the three busy-wait loop edits of webMAN's CUSTOM entry, the one at 0x14205C, which sits far from the unpack function (0x124D94). The other two (0x125004 and 0x1250A4) stay out because they are the ones that made the experience wrong. The unpack hook is unchanged. A CONFIG written by v2.09 is upgraded and kept as `<iso>.CONFIG.bak`.
- Played on a console: the experience is right and characters level up. Also tried and rejected: turning the instruction cache emulation off (`0x21 0`) gave speed but broke the experience again.
- The emulator image is the one of v2.08.

## v2.09
- Radiata Stories (US, SLUS_212.62) through webMAN: the characters gained random experience and never leveled up. Cause found by comparing the two ways of running the game. A PS2 Classics package carries the official CONFIG of the game; an ISO mounted by webMAN gets the entry CUSTOM of webMAN's database copied beside it as `<iso>.CONFIG` on the first mount. That entry hooks the game's unpack function (0x124D94, a VU0 routine whose result is 1 off in the emulator) like the official one, but it also replaces three busy-wait loops (0x125004, 0x1250A4, 0x14205C) with a branch that is never taken, to gain speed. Two of them sit right next to the unpack function, so its VU0 results are used before they are ready and the experience tables come out wrong.
- The app now writes a CONFIG without those edits (revision, xgkick delay 8, the two EE hooks of the game, smoothing off, title id) beside every ISO whose boot serial, read from the SYSTEM.CNF inside the image, is Radiata Stories (US). A CONFIG with the loop edits is replaced and kept as `<iso>.CONFIG.bak`; a CONFIG the owner edited is left alone. Press the confirm button in the app after copying the ISO.
- Not measured on a console: the speed gain of the removed edits is lost (the game can stutter in crowded places, as it does with the PS2 Classics package), and the fix rests on reading the game code and the CONFIG command list, not on a played battle.
- The emulator image is the one of v2.08.

## v2.08
- No blur: the emulator's generic texture binder (`0x263a04`) wrote a LINEAR min and mag sampler filter (`0x02022000`) for every texture it binds; it now writes NEAREST (`0x01012000`, the word the state reset of the draw code already uses). One instruction changes (`lis r0,514` to `lis r0,257`).
- No dither: the RSX dither switch (method `0x0300`) was never written by the emulator, so the hardware default (on) stayed. The state reset now also writes it as 0 (a small cave that only appends the command when the command buffer has room, otherwise the stock code runs unchanged).
- Not measured on a console: the emulator restarts into itself when a game starts, so these two changes come from reading the code and from host tests that run the patched instructions. If a game looks wrong, restore the original with Triangle in the app; `--keep-filter` and `--keep-dither` rebuild the image without either change.
- The installer is the one of v2.07.

## v2.07
- The menu value "Normal" of Other settings > Screen mode is back to its stock name (v2.05 and v2.06 showed "4:3"). The item has three values, Off, Normal and Full Screen; only the picture crop of the Normal mode is ours.
- Same installer as v2.06. The emulator image has no label edits any more (the rename is behind `--labels`).
- Still open: the 16:9 stretch of Full Screen, see the README.

## v2.06
- The package, the app and the file names carry the real release version instead of "2.00": the app title and "Patched (v...)" line, the version in the XMB, the package icon (drawn at build time from `VERSION`) and the files `ps2_netemu_v<version>.pkg` and `.self`.
- Install and Restore show a progress bar with the stage (checking the package, reading, writing, verifying) and a percentage, and keep redrawing while the flash is written. Creating the memory cards (8 MB each, one per new ISO) has its own bar too. Before, the screen froze for the whole operation and looked like a crash.
- The app is in English only (the Portuguese texts are gone).
- The bottom bar shows controller button icons (cross, triangle, circle, matching the confirm button of the console) instead of the letters "X", "Triangle" and "O".
- The installer works with whatever emulator file is on the console: the stock one, the one patched by this release, any earlier build of this project (even when the backup of the original is missing, in which case it says there is nothing to restore), or any unknown file as long as the original is safe in `/dev_hdd0/ps2_netemu_stock.self`. An unknown file without a valid backup is still refused. It works whether `/dev_blind` was already mounted by webMAN or not, and leaves a mount it did not make alone.
- The changelog is now the source of each release's notes.
- Not in this release: the 16:9 "Full Screen" stretch. The menu item "Screen mode" has a single value in this emulator (the stock "Normal", shown as "4:3"); the code that builds the menu and the point where the emulator declares the aspect to the system were not found by static analysis, and a blind patch could stop PS2 games from starting. The findings are in the README.

## v2.05
- Installer fix: when webMAN already mounted `/dev_blind` the app no longer fails with "could not open the system files"; it uses that mount and leaves it as it found it.
- Menu: Other settings > Screen mode shows "4:3" instead of "Normal" in every language.
- Package icon says PS2 (it said PS1).
- Cards: one per game named after the ISO title, no limit on the number of games (the 32 slot limit was only in v2.03). `tools/make_cards.py` creates the missing cards from the Mac over FTP.

## v2.04
- One memory card per game, named after the ISO title (`PS2_<title>.VM2`); all discs of a game share one card.
- Memory card 1 is always present: when the launcher leaves the card path empty the shared `PS2.VM2` is used.
- 4:3 image fix kept: the blank bands at the top and the bottom of the picture are cropped and the rest stretched over the frame.

## v2.03
- One memory card per game through a table of 32 fixed slots (`PS2_C00.VM2` and up) kept by the installer. Confirmed on the console with Grandia III disc 2.

## v2.02
- Only the 4:3 image fix (crop of 16 of 448 rows at each end of the texture). Confirmed on the console: the screen is 100% filled.

## v2.01
- First build: the black band at the top of the picture is cropped and the rest stretched over the same 4:3 frame.
