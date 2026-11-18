# Changelog

Every release lists what changed here, newest first. The section of a version is its release notes: `installer/tools/release_notes.sh` prints it and `installer/tools/dist.sh` refuses to package a version that has none. The version lives in `VERSION`; the package and the app show it, the tag is `v<version>`.

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
