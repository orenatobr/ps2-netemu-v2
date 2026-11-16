#!/bin/sh
# Collects the release files in ../dist after `make pkg`: the finalized package (the one CFW consoles
# install), the patched ps1_netemu.self and the checksums.
set -eu
cd "$(dirname "$0")/.."
out=../dist
rm -rf "$out"
mkdir -p "$out"
cp PS1NetemuPatch.gnpdrm.pkg "$out/ps1_netemu_v2.00.pkg"
cp payload/ps1_netemu_v2.bin "$out/ps1_netemu_v2.00.self"
( cd "$out" && shasum -a 256 ps1_netemu_v2.00.pkg ps1_netemu_v2.00.self > SHA256SUMS && cat SHA256SUMS )
