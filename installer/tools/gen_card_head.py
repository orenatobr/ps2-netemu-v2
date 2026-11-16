"""Write data/ps2_card_head.bin: the written pages (0..83, with ECC) of a blank formatted PS2 card.

The installer appends erased pages (0xFF) up to 8,650,752 bytes. Run from the repository root:
    python installer/tools/gen_card_head.py
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import ps2card

HEAD_PAGES = 84  # superblock, indirect FAT, 32 FAT clusters and the root directory cluster end at page 83
card = ps2card.blank_card()
head = card[:HEAD_PAGES * (ps2card.PAGE + ps2card.SPARE)]
assert card[len(head):] == b"\xff" * (len(card) - len(head))
(ROOT / "installer" / "data" / "ps2_card_head.bin").write_bytes(head)
print(f"wrote {len(head)} bytes")
