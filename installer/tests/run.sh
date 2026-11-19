#!/bin/sh
# Builds and runs the host tests of the installer logic.
set -eu
cd "$(dirname "$0")/.."
out=$(mktemp -d)
c++ -std=c++20 -Wall -Wextra -Isource tests/installer_test.cpp source/installer.cpp source/fsx.cpp -o "$out/t"
"$out/t"
c++ -std=c++20 -Wall -Wextra -Isource tests/cards_test.cpp source/cards.cpp source/fsx.cpp -o "$out/c"
"$out/c"
c++ -std=c++20 -Wall -Wextra -Isource tests/configs_test.cpp source/configs.cpp source/isoinfo.cpp source/fsx.cpp -o "$out/g"
"$out/g"
rm -rf "$out"
