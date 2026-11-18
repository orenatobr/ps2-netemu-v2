#!/bin/sh
# Renders the package icon with the release version (../VERSION) on the host: tools/icon.sh OUT.png
set -eu
cd "$(dirname "$0")/.."
out=${1:?usage: tools/icon.sh OUT.png}
bin=$(mktemp)
c++ -std=c++20 -Wall -DAPP_VERSION=\"$(cat ../VERSION)\" -Isource -Ithird_party/stb tools/icon.cpp source/gfx.cpp source/stb_impl.cpp -o "$bin"
"$bin" "$out"
rm -f "$bin"
