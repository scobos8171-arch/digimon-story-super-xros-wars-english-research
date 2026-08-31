"""Restore selected sprite archive entries from a clean Xros Blue ROM.

This is a narrowly scoped recovery tool for the localized build.  It preserves
all translated data except the explicitly selected NCER/NCGR entries and never
touches ARM code, overlays, message archives, palettes, or animation tables.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from build_xros_custom_ui_rom import (
    XrosPak,
    arm9_slice,
    build_xros_pak,
    find_nitro_file,
    encode_selected_cells,
    parse_ncer,
    parse_ncgr,
    parse_nclr,
    read_header,
    read_nitro_file,
    read_nitrofs,
    replace_nitrofs_files,
    render_full_cell,
)


ARCHIVES = ("SPR_NCER.PAK", "SPR_NCGR.PAK")


def read_archive(rom: Path, name: str) -> XrosPak:
    with rom.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        return XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, name)))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("clean_rom", type=Path)
    parser.add_argument("localized_rom", type=Path)
    parser.add_argument("output_rom", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("--entry", type=int, action="append", required=True)
    parser.add_argument(
        "--preserve-localized-pixels",
        action="store_true",
        help="re-encode localized NCGR pixels through the clean NCER geometry",
    )
    args = parser.parse_args()

    source = args.localized_rom.read_bytes()
    replacements: dict[str, bytes] = {}
    changes = []
    clean_cells = read_archive(args.clean_rom, "SPR_NCER.PAK")
    localized_cells = read_archive(args.localized_rom, "SPR_NCER.PAK")
    clean_graphics = read_archive(args.clean_rom, "SPR_NCGR.PAK")
    localized_graphics = read_archive(args.localized_rom, "SPR_NCGR.PAK")
    clean_palettes = read_archive(args.clean_rom, "SPR_NCLR.PAK")

    for archive_name in ARCHIVES:
        clean = read_archive(args.clean_rom, archive_name)
        localized = read_archive(args.localized_rom, archive_name)
        if len(clean.entries) != len(localized.entries):
            raise ValueError(f"{archive_name}: entry count differs")
        entries = [localized.unpacked_data(i) for i in range(len(localized.entries))]
        for index in sorted(set(args.entry)):
            before = entries[index]
            after = clean.unpacked_data(index)
            if archive_name == "SPR_NCGR.PAK" and args.preserve_localized_pixels:
                clean_cell_defs = parse_ncer(clean_cells.unpacked_data(index))
                localized_cell_defs = parse_ncer(localized_cells.unpacked_data(index))
                if len(clean_cell_defs) != len(localized_cell_defs):
                    raise ValueError(f"entry {index}: localized and clean cell counts differ")
                palette = parse_nclr(clean_palettes.unpacked_data(index))
                localized_ncgr = parse_ncgr(localized_graphics.unpacked_data(index))
                localized_canvases = [
                    render_full_cell(localized_ncgr, palette, cell)
                    for cell in localized_cell_defs
                ]
                clean_ncgr_bytes = clean_graphics.unpacked_data(index)
                after = encode_selected_cells(
                    clean_ncgr_bytes,
                    clean_cell_defs,
                    localized_canvases,
                    palette,
                    set(range(len(clean_cell_defs))),
                )
            entries[index] = after
            changes.append(
                {
                    "archive": archive_name,
                    "entry": index,
                    "localized_size": len(before),
                    "clean_size": len(after),
                    "localized_sha256": hashlib.sha256(before).hexdigest(),
                    "clean_sha256": hashlib.sha256(after).hexdigest(),
                }
            )
        replacements[archive_name] = build_xros_pak(entries)

    patched = replace_nitrofs_files(source, replacements)
    if arm9_slice(source) != arm9_slice(patched):
        raise AssertionError("ARM9 changed during sprite-entry recovery")
    args.output_rom.parent.mkdir(parents=True, exist_ok=True)
    args.output_rom.write_bytes(patched)
    report = {
        "clean_rom": str(args.clean_rom.resolve()),
        "localized_source": str(args.localized_rom.resolve()),
        "output_rom": str(args.output_rom.resolve()),
        "localized_source_sha256": hashlib.sha256(source).hexdigest(),
        "output_sha256": hashlib.sha256(patched).hexdigest(),
        "arm9_unchanged": True,
        "restored_entries": sorted(set(args.entry)),
        "localized_pixels_preserved": args.preserve_localized_pixels,
        "changes": changes,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "changes"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
