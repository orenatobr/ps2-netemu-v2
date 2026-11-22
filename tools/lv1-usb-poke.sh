#!/usr/bin/env bash
# EXPERIMENTAL. Volatile lv1 patch (RAM only, undone by a PS3 reboot) for Evilnat 4.93 CEX.
# Usage: lv1-usb-poke.sh <apply|revert|status> <ps3-ip>
# Needs webMAN MOD (HTTP on port 80). Reads each word first and refuses to write if it differs.
set -euo pipefail
cmd=${1:-}; ip=${2:-}
[ -n "$cmd" ] && [ -n "$ip" ] || { echo "usage: $0 <apply|revert|status> <ps3-ip>" >&2; exit 2; }
SITES="23d94c:4bfffa5d:60000000 23d97c:90090000:60000000" # addr:original:patched

peek() { # prints the 4-byte word at $1 (lowercase hex)
  local a=$1 base line
  base=$(printf '%08X' $(( 0x$a & ~0xF )))
  line=$(curl -s -m 10 "http://$ip/peek.lv1?$a" | tr -d '\r' | grep -o "$base [0-9A-F ]\{48\}" | head -1)
  [ -n "$line" ] || { echo "cannot read lv1 at $a" >&2; exit 1; }
  echo "$line" | awk -v o=$(( 0x$a & 0xF )) '{for(i=0;i<4;i++) printf "%s", tolower($(2+o+i)); print ""}'
}

for s in $SITES; do
  IFS=: read -r addr orig patched <<<"$s"
  cur=$(peek "$addr")
  case $cmd in
    status) echo "$addr = $cur (original $orig, patched $patched)" ;;
    apply)  [ "$cur" = "$patched" ] && { echo "$addr already patched"; continue; }
            [ "$cur" = "$orig" ] || { echo "$addr holds $cur, not the expected $orig: aborting" >&2; exit 1; }
            curl -s -m 10 -o /dev/null "http://$ip/poke.lv1?$addr=$patched"; echo "$addr -> $(peek "$addr")" ;;
    revert) [ "$cur" = "$orig" ] && { echo "$addr already original"; continue; }
            curl -s -m 10 -o /dev/null "http://$ip/poke.lv1?$addr=$orig"; echo "$addr -> $(peek "$addr")" ;;
    *) echo "unknown command $cmd" >&2; exit 2 ;;
  esac
done
