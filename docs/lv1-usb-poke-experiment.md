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

## Verdict (2026-11-22)
Closed as a platform limitation, not a patchable bug in this project or in the Evilnat CFW.

- Three candidates were refuted on hardware: lv1 port teardown (0x23d94c and 0x23d97c), lv1 host
  controller reset (0x23dd4c), and lv2 usbd `request_port_power_off` (0x23c220, patched to return
  at once). In each case the pad still turned off. The stock emulator and the PS2 Classics path behave the same
  on the same console.
- Public reports describe the same behavior on original hardware: the pad turns off when a PS2
  game starts and the PS button brings it back (Push Square and GameSpot forums for PS2 discs,
  GameFAQs and PlayStationTrophies for PS2 Classics).
- The Evilnat Cobra source (8.5/4.93 CEX) only hooks disc and ISO access in the PS2 emulator
  stage. It has no pad, USB or Bluetooth code to change.
- The LPAR unload and vuart teardown strings in lv1 have no PPC code references in a 16 MB
  dump, so that logic is likely outside the lv1 text (unconfirmed).
- Not tried: patching `0x23d3a8` (common port-mode helper), and any dynamic trace of lv1 or the
  guest during the switch.

Workaround: press the PS button after entering and after leaving PS2 mode.

## Feasibility of keeping the pad on across the switch (static study, 2026-11-22)
Studied: the Evilnat 4.93 `lv2_kernel.self` (decrypted from the PUP, checked against the live lv2 by
peek), the console `vsh.self` (read over FTP, decrypted), and the stock `ps2_netemu.self`.

- **Entry (GameOS to PS2 emulator).** `ps2_netemu` carries its own copy of the system pad stack
  (`HidUsb`, `usbd pipe chain`, `_sys_hid_core_thread`, `HidGamepadMgr`, `pairing_manager`,
  `pad_manager`, `authentication_manager`, `BT_*` keys) and maps its own `ehci_mmio` and `ohci_mmio`
  windows (hypercalls 170, 172 and 174 in the function at `0x19c80`). It is a new guest with a new
  Bluetooth stack, so it cannot inherit the link state (channels, keys in use) that lived in the
  GameOS memory. No standard HCI command table (Reset, Set Event Mask, Write Scan Enable) exists in
  its data, and lv2 talks to the radio with vendor calls (`bt_port_control`, `bt_inquiry_start`,
  `bt_send_passkey`), so the reset cannot be located and skipped by pattern.
- **Exit (emulator to GameOS).** lv2 boots from scratch and its `usbd` and Bluetooth drivers
  initialize the radio again. A CFW can patch lv2 statically, but there is no known instruction that
  only "resets the pad link": it is the normal bring-up of the stack.
- **Reconnecting without the PS button.** The DualShock 3 connects to the console, not the other
  way around, and the pairing keys (`/setting/bt/controllerN/linkkey` in the system registry) do not
  let the host wake it.
- **Tested and refuted:** lv1 port teardown, lv1 host controller reset, lv2 `request_port_power_off`.
- **Not tried:** a `ps2_netemu` that does not touch USB at all (decisive for the entry side, needs a
  console test), the lv1 helper at `0x23d3a8`, and a dynamic trace of lv1 during the switch.

## Console state and restore procedure (diagnostic build)

Test files used on the Evilnat 4.93 CEX console (SHA-256):

| File | SHA-256 | Purpose |
|------|---------|---------|
| stock `ps2_netemu.self` | `bad3e45c9a81f25726e414b146ea5a112f28216ab4bdd2fd9f5c81b33d04c80a` | original, backed up by the installer at `/dev_hdd0/ps2_netemu_stock.self` |
| v2.15 patched build | `ea8b64fba410aa4fd87812047caf4216ef52b098ac3266d32371ebd280fcb968` | what the installer writes |
| `nousb.self` (diagnostic) | `c413f4d5df93367df312dd738362fe62b43efb581dabec0bbe038cba96acdbc1` | returns 0 at the USB open function (0x19c80); pad may not work in-game |

Restore the installed build or the stock one:

```
curl -s http://<ps3>/dev_blind -o /dev/null
curl -s -Q "DELE /dev_blind/ps2emu/ps2_netemu.self" ftp://<ps3>/ -o /dev/null
curl -s -T <file> ftp://<ps3>/dev_blind/ps2emu/ps2_netemu.self
```

Then check that the SHA-256 of the file read back over FTP matches the table.
The `nousb.self` result (pad lit or not on PS2 entry) is still unrecorded.
