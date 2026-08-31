"""Build a ROM with selected MESPAK00 string ranges from a localized donor.

All records outside the selected half come from the clean base ROM. The message
table and PAK are rebuilt with valid pointers and alignment for diagnostic use.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EDITOR = ROOT / "work" / "DigimonNDSRomEditor-master"
sys.path.insert(0, str(EDITOR))

from rom_research.nds_inventory import read_header, read_nitrofs
from rom_research.nitrofs_patch import replace_nitrofs_files
from rom_research.story_messages import build_message_table, parse_message_table
from rom_research.xros_pak import XrosPak, build_xros_pak, find_nitro_file, read_nitro_file


ARCHIVE = "MSG/MESPAK00.PAK"


def archive_bytes(rom: Path, name: str) -> bytes:
    with rom.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        return read_nitro_file(handle, find_nitro_file(files, name))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("donor", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("--start", type=int, required=True)
    parser.add_argument("--end", type=int, required=True, help="Exclusive end index")
    parser.add_argument("--include-font", action="store_true")
    parser.add_argument(
        "--pad-selected-to-clean-length",
        action="store_true",
        help="NUL-pad shorter localized records to their clean raw byte length",
    )
    args = parser.parse_args()

    clean_pak = XrosPak.from_bytes(archive_bytes(args.base, ARCHIVE))
    donor_pak = XrosPak.from_bytes(archive_bytes(args.donor, ARCHIVE))
    if len(clean_pak.entries) != 1 or len(donor_pak.entries) != 1:
        raise ValueError("MESPAK00 must contain exactly one message-table entry")
    clean_entry = clean_pak.unpacked_data(0)
    donor_entry = donor_pak.unpacked_data(0)
    _clean_offsets, clean_strings = parse_message_table(clean_entry, encoding="shift_jis")
    _donor_offsets, donor_strings = parse_message_table(donor_entry, encoding="shift_jis")
    if len(clean_strings) != len(donor_strings):
        raise ValueError("Clean and donor message counts differ")
    if not (0 <= args.start <= args.end <= len(clean_strings)):
        raise ValueError("Selected range is outside the message table")

    mixed = list(clean_strings)
    mixed[args.start:args.end] = donor_strings[args.start:args.end]
    padded_indices: list[int] = []
    if args.pad_selected_to_clean_length:
        for index in range(args.start, args.end):
            clean_length = len(clean_strings[index])
            if len(mixed[index]) < clean_length:
                mixed[index] += b"\0" * (clean_length - len(mixed[index]))
                padded_indices.append(index)
    rebuilt_entry = build_message_table(clean_entry, mixed)
    replacements = {ARCHIVE: build_xros_pak([rebuilt_entry])}
    if args.include_font:
        replacements["FONT_NFTR.PAK"] = archive_bytes(args.donor, "FONT_NFTR.PAK")
    patched = replace_nitrofs_files(args.base.read_bytes(), replacements)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(patched)
    result = {
        "base": str(args.base.resolve()),
        "donor": str(args.donor.resolve()),
        "output": str(args.output.resolve()),
        "localized_range": [args.start, args.end],
        "message_count": len(clean_strings),
        "included_font": args.include_font,
        "padded_indices": padded_indices,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
