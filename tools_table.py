"""Write the table file (PS2_CARDS.TBL) for a list of ISOs: one slot per game, discs of a game share it."""
from __future__ import annotations

import sys

import cave_cardfile
import cave_slots


def assign(isos: list[str]) -> dict[str, int]:
    """Map each ISO file name to a slot: the game title (no disc tag) picks the slot, in sorted order. Names that do not fit are left out."""
    fits = [i for i in isos if cave_cardfile.card_name(i) and len(i.rsplit("/", 1)[-1].encode()) <= cave_slots.RECORD - 2]
    titles = sorted({cave_cardfile.card_name(i) for i in fits})[:cave_slots.NSLOTS]
    return {i.rsplit("/", 1)[-1]: titles.index(cave_cardfile.card_name(i)) for i in fits if cave_cardfile.card_name(i) in titles}


def table_bytes(isos: list[str]) -> bytes:
    """The content of PS2_CARDS.TBL (records, then the empty record that ends it)."""
    return b"".join(cave_slots.record(s, n) for n, s in assign(isos).items()) + b"\0" * cave_slots.RECORD


if __name__ == "__main__":
    sys.stdout.buffer.write(table_bytes(sys.argv[1:]))
