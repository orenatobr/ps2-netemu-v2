#!/bin/sh
# Prints the CHANGELOG.md section of one version (default: ../VERSION), for `gh release create --notes-file`.
# Fails when the version has no section or the section is empty, so a release cannot go out without notes.
set -eu
cd "$(dirname "$0")/../.."
version=${1:-$(cat VERSION)}
notes=$(awk -v h="## v$version" '$0 == h {on = 1; next} /^## / {on = 0} on' CHANGELOG.md | sed '/./,$!d')
if [ -z "$notes" ]; then
    echo "CHANGELOG.md has no notes for v$version" >&2
    exit 1
fi
printf '%s\n' "$notes"
