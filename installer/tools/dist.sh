#!/bin/sh
# Collects the release files in ../dist after `make pkg`: the finalized package (the one CFW consoles
# install), the patched ps2_netemu.self and the checksums.
set -eu
cd "$(dirname "$0")/.."
out=../dist
rm -rf "$out"
mkdir -p "$out"
cp PS2NetemuPatch.gnpdrm.pkg "$out/ps2_netemu_v2.00.pkg"
cp payload/ps2_netemu_v2.bin "$out/ps2_netemu_v2.00.self"
( cd "$out" && shasum -a 256 ps2_netemu_v2.00.pkg ps2_netemu_v2.00.self > SHA256SUMS && cat SHA256SUMS )
