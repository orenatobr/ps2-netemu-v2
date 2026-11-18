#!/bin/sh
# Collects the release files in ../dist after `make pkg`: the finalized package (the one CFW consoles
# install), the patched ps2_netemu.self and the checksums. The names carry the release version (../../VERSION),
# which must have a section in CHANGELOG.md: that section becomes the release notes (tools/release_notes.sh).
set -eu
cd "$(dirname "$0")/.."
version=$(cat ../VERSION)
sh tools/release_notes.sh "$version" > /dev/null
out=../dist
rm -rf "$out"
mkdir -p "$out"
cp PS2NetemuPatch.gnpdrm.pkg "$out/ps2_netemu_v$version.pkg"
cp payload/ps2_netemu_v2.bin "$out/ps2_netemu_v$version.self"
( cd "$out" && shasum -a 256 "ps2_netemu_v$version.pkg" "ps2_netemu_v$version.self" > SHA256SUMS && cat SHA256SUMS )
