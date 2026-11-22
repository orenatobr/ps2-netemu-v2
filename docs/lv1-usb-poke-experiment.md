# Experiment: keep the controller on across the PS2 switch (lv1 poke)

Status: **tested on hardware, refuted**. Evilnat CEX 4.93 only. Not a fix.

Result (2026-11-22): with both words patched (confirmed by a live peek) the DualShock 3 still
turned off when entering PS2 mode. The port teardown at 0x23d830 is not what cuts the pad.
Not yet ruled out: the sibling port routines (0x23d4c4, 0x23d644, hypercall family 170 to 198),
and a reset done by a guest (lv2 or `ps2_netemu`). The stock emulator and the PS2 Classic path
behave the same, so the loss looks inherent to the partition switch. Workaround: press the PS
button after entering and after leaving PS2 mode.

## Why
Entering and leaving PS2 mode swaps the GameOS partition for the PS2 LPAR in lv1, and the
DualShock 3 link drops at both transitions (the stock emulator does the same). `ps2_netemu`
has no pad power-off code, so the cause is below this repository.

## Where (lv1 4.93, addresses from a live dump)
- Hypercall table at 0x372d08. Handler 170 = 0x305a38, 171 = 0x306eec (wrapper, argument <= 4)
  which calls 0x2373b0, which switches to 0x23d830 (change of USB controller owner).
- 0x23d830 zeroes the state of 6 ports through 0x23d3a8 (call at 0x23d94c) and writes 0 to the
  controller register +0xf00 (store at 0x23d97c). The owner's virtual method (0x2294d4) only
  releases software resources.
- Theory: that port teardown power-cycles the Bluetooth dongle. Refuted by the test above.

## How the dump was taken
1. `http://<ps3>/dump.ps3?lv1` (webMAN MOD) writes `/dev_hdd0/dump_lv1.bin` (16 MB, read only).
2. Fetch it over FTP. The dump maps 1:1 to lv1 virtual addresses.

## Try it (RAM only, reverts on reboot)
```
tools/lv1-usb-poke.sh status <ps3-ip>
tools/lv1-usb-poke.sh apply  <ps3-ip>   # nops 0x23d94c and 0x23d97c
# enter a PS2 game, watch the controller on entry and on exit
tools/lv1-usb-poke.sh revert <ps3-ip>
```
The script reads each word first and refuses to write if it is not the expected original
(`4bfffa5d`, `90090000`), so it stops on any other firmware. Skipping the teardown may leave the
port in a bad state or hang the console: reboot the PS3 to undo it.
