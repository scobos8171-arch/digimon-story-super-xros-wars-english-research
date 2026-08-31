"""Locate exact or control-code-wrapped Xros UI message records.

This is read-only.  It scans all MESPAK archives in an NDS ROM and writes
candidate records for the runtime-drawn hex command labels.  It deliberately
does not modify graphics, fonts, or the ROM.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "work" / "DigimonNDSRomEditor-master"))

from rom_research.nds_inventory import read_header, read_nitrofs
from rom_research.story_messages import parse_message_table
from rom_research.xros_pak import XrosPak, read_nitro_file


TARGETS = {
    "ステータス": "STATUS",
    "わざ": "MOVES",
    "そうび": "EQUIPMENT",
    "たいれつ": "FORMATION",
    "もちもの": "ITEMS",
    "マップ": "MAP",
    "じょうほう": "INFO",
    "もどる": "BACK",
    "バトルほうしゅう": "BATTLE RESULTS",
    "つぎへ": "NEXT",
}


def visible_edge(text: str, term: str) -> bool:
    """Accept a term by itself or wrapped in non-printing controls only."""
    position = text.find(term)
    if position < 0:
        return False
    before = text[:position]
    after = text[position + len(term):]
    return all(ord(ch) < 0x20 or ch.isspace() for ch in before + after)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("output_tsv", type=Path)
    args = parser.parse_args()

    with args.rom.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        archive_files = [
            item for item in files
            if item.path.replace("\\", "/").upper().startswith("MSG/MESPAK")
            and item.path.upper().endswith(".PAK")
        ]
        rows: list[tuple[str, int, int, str, str, str, str, str]] = []
        for item in archive_files:
            archive = XrosPak.from_bytes(read_nitro_file(handle, item))
            for pak_entry in range(len(archive.entries)):
                try:
                    offsets, strings = parse_message_table(
                        archive.unpacked_data(pak_entry), encoding="shift_jis"
                    )
                except (ValueError, IndexError):
                    continue
                for string_index, (offset, raw) in enumerate(zip(offsets, strings)):
                    text = raw.decode("shift_jis", errors="replace")
                    for japanese, english in TARGETS.items():
                        if japanese in text:
                            kind = "exact_or_controls" if visible_edge(text, japanese) else "substring"
                            rows.append((
                                item.path.replace("\\", "/"), pak_entry, string_index,
                                f"0x{offset:X}", japanese, english, kind,
                                text.encode("unicode_escape").decode("ascii"),
                            ))

    args.output_tsv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_tsv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow(("archive", "pak_entry", "string_index", "offset", "japanese", "english", "match", "decoded_escaped"))
        writer.writerows(rows)
    exact = sum(row[6] == "exact_or_controls" for row in rows)
    print(f"Scanned {len(archive_files)} message archives; {len(rows)} candidates, {exact} exact/control candidates")
    print(args.output_tsv.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
