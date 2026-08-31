"""Override one Xros message record while preserving all other donor records."""

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


def read_file(rom: Path, name: str) -> bytes:
    with rom.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        return read_nitro_file(handle, find_nitro_file(files, name))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("donor", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("--archive", type=int, default=0)
    parser.add_argument("--entry", type=int, default=0)
    parser.add_argument("--index", type=int, required=True)
    parser.add_argument("--text", required=True)
    parser.add_argument("--encoding", default="ascii")
    parser.add_argument("--diagnostic-clean-base", action="store_true")
    args = parser.parse_args()

    archive_name = f"MSG/MESPAK{args.archive:02d}.PAK"
    source_rom = args.base if args.diagnostic_clean_base else args.donor
    source_pak = XrosPak.from_bytes(read_file(source_rom, archive_name))
    entries = [source_pak.unpacked_data(index) for index in range(len(source_pak.entries))]
    entry = entries[args.entry]
    _offsets, strings = parse_message_table(entry, encoding="shift_jis")
    patched = list(strings)
    before = patched[args.index].decode("shift_jis", errors="replace")
    patched[args.index] = args.text.encode(args.encoding)
    entries[args.entry] = build_message_table(entry, patched)
    rebuilt = build_xros_pak(entries)
    replacements = {archive_name: rebuilt}
    if args.diagnostic_clean_base:
        replacements["FONT_NFTR.PAK"] = read_file(args.donor, "FONT_NFTR.PAK")
    output_data = replace_nitrofs_files(source_rom.read_bytes(), replacements)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output_data)
    result = {
        "source_rom": str(source_rom.resolve()),
        "output": str(args.output.resolve()),
        "archive": args.archive,
        "entry": args.entry,
        "index": args.index,
        "before": before,
        "after": args.text,
        "encoding": args.encoding,
        "diagnostic_clean_base": args.diagnostic_clean_base,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
