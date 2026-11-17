"""Create the memory cards that the games in /dev_hdd0/PS2ISO need, from the Mac, over FTP.

The emulator cannot create a card file and a PS3 app cannot run in the background, so this does the creation from outside:
for every ISO of the console it works out the card name with the rule of the patch (cave_wrap.card_file) and uploads a blank
formatted card (ps2card.blank_card) when that card does not exist yet. Cards that exist are never touched. Run it by hand
(`python tools/make_cards.py 192.168.1.85`) or from launchd/cron every few minutes.
"""
from __future__ import annotations

import ftplib
import logging
import sys
from collections.abc import Iterable
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import cave_wrap
import ps2card

logger = logging.getLogger("make_cards")
ISO_DIR, VMC_DIR = "/dev_hdd0/PS2ISO", "/dev_hdd0/savedata/vmc"


def missing_cards(isos: Iterable[str], existing: Iterable[str]) -> dict[str, str]:
    """Map each missing card file name to the first ISO that needs it (all discs of a game share one card)."""
    have = set(existing)
    out: dict[str, str] = {}
    for iso in sorted(isos):
        if not iso.lower().endswith((".iso", ".bin")):
            continue
        card = cave_wrap.card_file(iso)
        if card and card not in have and card not in out:
            out[card] = iso
    return out


def run(host: str) -> list[str]:
    """Create the missing cards on the console and return their names."""
    made: list[str] = []
    with ftplib.FTP(host, timeout=60) as ftp:
        ftp.login("root", "")
        isos = [n.rsplit("/", 1)[-1] for n in ftp.nlst(ISO_DIR)]
        existing = [n.rsplit("/", 1)[-1] for n in ftp.nlst(VMC_DIR)]
        for card, iso in missing_cards(isos, existing).items():
            logger.info("creating %s for %s", card, iso)
            ftp.storbinary(f"STOR {VMC_DIR}/{card}.new", BytesIO(ps2card.blank_card()))
            ftp.rename(f"{VMC_DIR}/{card}.new", f"{VMC_DIR}/{card}")
            made.append(card)
    return made


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    created = run(sys.argv[1] if len(sys.argv) > 1 else "192.168.1.85")
    logger.info("created %d card(s)", len(created))
