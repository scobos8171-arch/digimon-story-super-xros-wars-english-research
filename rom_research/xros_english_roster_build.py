"""Build a first-stage Xros Wars ROM with validated English roster names."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

from rom_research.nds_inventory import read_header, read_nitrofs
from rom_research.nitrofs_patch import replace_nitrofs_files
from rom_research.story_messages import build_message_table, parse_message_table
from rom_research.xros_pak import (
    XrosPak,
    build_xros_pak,
    find_nitro_file,
    read_nitro_file,
)


MESSAGE_ARCHIVE = "MSG/MESPAK00.PAK"


def _load_replacements(path: Path) -> dict[int, str]:
    replacements: dict[int, str] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["status"] != "exact" or not row["english"]:
                continue
            text = row["english"]
            try:
                text.encode("ascii")
            except UnicodeEncodeError:
                continue
            replacements[int(row["xros_string_index"])] = text
    return replacements


def build_english_roster_rom(
    source_rom: Path,
    short_names_csv: Path,
    formal_names_csv: Path,
    output_rom: Path,
    manifest_path: Path,
) -> dict[str, object]:
    replacements = _load_replacements(short_names_csv)
    replacements.update(_load_replacements(formal_names_csv))

    with source_rom.open("rb") as handle:
        header = read_header(handle)
        files = read_nitrofs(handle, header)
        archive_item = find_nitro_file(files, MESSAGE_ARCHIVE)
        archive = XrosPak.from_bytes(read_nitro_file(handle, archive_item))
    if len(archive.entries) != 1:
        raise ValueError(f"{MESSAGE_ARCHIVE} unexpectedly has multiple entries")

    original_table = archive.unpacked_data(0)
    _offsets, raw_strings = parse_message_table(
        original_table,
        encoding="shift_jis",
    )
    patched_strings = list(raw_strings)
    changed: dict[int, dict[str, str]] = {}
    for index, english in sorted(replacements.items()):
        if not 0 <= index < len(patched_strings):
            raise IndexError(f"String index {index} is outside MESPAK00")
        old = patched_strings[index]
        new = english.encode("ascii")
        if old == new:
            continue
        patched_strings[index] = new
        changed[index] = {
            "japanese": old.decode("shift_jis", errors="replace"),
            "english": english,
        }

    rebuilt_table = build_message_table(original_table, patched_strings)
    rebuilt_archive = build_xros_pak([rebuilt_table])
    patched_rom = replace_nitrofs_files(
        source_rom.read_bytes(),
        {MESSAGE_ARCHIVE: rebuilt_archive},
    )
    output_rom.parent.mkdir(parents=True, exist_ok=True)
    output_rom.write_bytes(patched_rom)

    # Re-open the generated ROM and prove the archive and every replacement.
    with output_rom.open("rb") as handle:
        output_files = read_nitrofs(handle, read_header(handle))
        output_archive = XrosPak.from_bytes(
            read_nitro_file(
                handle,
                find_nitro_file(output_files, MESSAGE_ARCHIVE),
            )
        )
    _new_offsets, verified_strings = parse_message_table(
        output_archive.unpacked_data(0),
        encoding="ascii",
    )
    for index, values in changed.items():
        if verified_strings[index] != values["english"].encode("ascii"):
            raise AssertionError(f"English name verification failed at {index}")

    manifest: dict[str, object] = {
        "source_rom": str(source_rom),
        "source_game_code": header["game_code"],
        "output_rom": str(output_rom),
        "source_sha256": hashlib.sha256(source_rom.read_bytes()).hexdigest(),
        "output_sha256": hashlib.sha256(patched_rom).hexdigest(),
        "message_archive": MESSAGE_ARCHIVE,
        "translated_name_count": len(changed),
        "message_count": len(verified_strings),
        "changes": changed,
        "scope": (
            "Stage 1 roster-name prototype only; battle logic, stats, encounters, "
            "story scripts, sprites, and progression are byte-identical to Xros Blue."
        ),
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_rom", type=Path)
    parser.add_argument("short_names_csv", type=Path)
    parser.add_argument("formal_names_csv", type=Path)
    parser.add_argument("output_rom", type=Path)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    result = build_english_roster_rom(
        args.source_rom,
        args.short_names_csv,
        args.formal_names_csv,
        args.output_rom,
        args.manifest,
    )
    print(
        f"Built {args.output_rom} with {result['translated_name_count']} "
        f"validated English roster strings; SHA-256 {result['output_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
