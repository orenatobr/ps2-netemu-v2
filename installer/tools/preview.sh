#!/bin/sh
# Renders the installer screens to PNG on the host (no console needed).
set -eu
cd "$(dirname "$0")/.."
out=${1:-/tmp/ps1inst_preview}
mkdir -p "$out"
c++ -std=c++20 -Wall -Isource -Ithird_party/stb tools/preview.cpp source/ui.cpp source/gfx.cpp source/installer.cpp source/fsx.cpp source/stb_impl.cpp -o "$out/preview.bin"
"$out/preview.bin" "$out"
echo "$out"
