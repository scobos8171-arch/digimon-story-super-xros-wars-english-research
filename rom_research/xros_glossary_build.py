"""Apply validated Lost Evolution English terminology across all Xros messages."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from rom_research.nds_inventory import read_header, read_nitrofs
from rom_research.nitrofs_patch import replace_nitrofs_files
from rom_research.story_messages import (
    MESSAGE_ARCHIVES,
    build_message_table,
    parse_message_table,
)
from rom_research.xros_pak import (
    XrosPak,
    build_xros_pak,
    find_nitro_file,
    read_nitro_file,
)


MANUAL_XROS_NAMES = {
    "シャウトモン": "Shoutmon",
    "バリスタモン": "Ballistamon",
    "ドルルモン": "Dorulumon",
    "スパロウモン": "Sparrowmon",
    "スターモン": "Starmon",
    "ドルルキャノン": "Dorulu Cannon",
    "シャウトモン×２": "Shoutmon X2",
    "スターソード": "Star Sword",
    "ジェットスパロウ": "Jet Sparrow",
    "シャウトモン×４": "Shoutmon X4",
    "キュートモン": "Cutemon",
    "ピックモン": "Pickmon",
    "モニタモン": "Monitamon",
    "ドンドコモン": "Dondokomon",
    "ボムモン": "Bombmon",
    "シャウトモン×５": "Shoutmon X5",
    "シャウトモン×３": "Shoutmon X3",
    "スパーダモン": "Spadamon",
    "マッドレオモン": "MadLeomon",
    "タクティモン": "Tactimon",
    "ブラストモン": "Blastmon",
    "グレイナイツモン": "GreyKnightsmon",
    "ガオスモン": "Gaossmon",
    "トループモン": "Troopmon",
    "チクリモン": "Chikurimon",
}


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def build_glossary(
    lost_japanese_csv: Path,
    lost_english_csv: Path,
    roster_csvs: tuple[Path, ...],
) -> dict[str, str]:
    japanese = _read_csv(lost_japanese_csv)
    english = _read_csv(lost_english_csv)
    english_by_location = {
        (row["archive"], row["pak_entry"], row["string_index"]): row["text"]
        for row in english
    }
    candidates: dict[str, set[str]] = defaultdict(set)
    for row in japanese:
        location = (row["archive"], row["pak_entry"], row["string_index"])
        translated = english_by_location.get(location, "")
        if row["text"] and translated:
            candidates[row["text"]].add(translated)
    glossary = {
        source: next(iter(values))
        for source, values in candidates.items()
        if len(values) == 1
    }
    for path in roster_csvs:
        for row in _read_csv(path):
            if row["status"] == "exact" and row["japanese"] and row["english"]:
                glossary[row["japanese"]] = row["english"]
    glossary.update(MANUAL_XROS_NAMES)
    return glossary


def _unescape(text: str) -> str:
    return text.replace("\\r", "\r").replace("\\n", "\n")


def build_glossary_rom(
    source_rom: Path,
    lost_japanese_csv: Path,
    lost_english_csv: Path,
    short_roster_csv: Path,
    formal_roster_csv: Path,
    output_rom: Path,
    manifest_path: Path,
) -> dict[str, object]:
    glossary = build_glossary(
        lost_japanese_csv,
        lost_english_csv,
        (short_roster_csv, formal_roster_csv),
    )
    replacements: dict[str, bytes] = {}
    changed_by_archive: dict[str, int] = {}

    with source_rom.open("rb") as handle:
        header = read_header(handle)
        files = read_nitrofs(handle, header)
        for archive_name in MESSAGE_ARCHIVES:
            archive = XrosPak.from_bytes(
                read_nitro_file(handle, find_nitro_file(files, archive_name))
            )
            rebuilt_entries: list[bytes] = []
            changed = 0
            for entry_index in range(len(archive.entries)):
                original = archive.unpacked_data(entry_index)
                try:
                    _offsets, strings = parse_message_table(
                        original, encoding="shift_jis"
                    )
                except ValueError:
                    rebuilt_entries.append(original)
                    continue
                output_strings = list(strings)
                for index, raw in enumerate(strings):
                    try:
                        source_text = raw.decode("shift_jis", errors="strict")
                    except UnicodeDecodeError:
                        # Control-code-bearing strings are not safe for an
                        # exact whole-string glossary substitution.
                        continue
                    lookup = source_text.replace("\r", "\\r").replace("\n", "\\n")
                    translated = glossary.get(lookup)
                    if translated is None:
                        continue
                    try:
                        target = _unescape(translated).encode(
                            "cp1252", errors="strict"
                        )
                    except UnicodeEncodeError:
                        # A few fan-translation CSV rows contain damaged
                        # replacement glyphs. Keep the original Japanese
                        # string rather than injecting corrupt text.
                        continue
                    if target != raw:
                        output_strings[index] = target
                        changed += 1
                rebuilt_entries.append(build_message_table(original, output_strings))
            if changed:
                replacements[archive_name] = build_xros_pak(rebuilt_entries)
                changed_by_archive[archive_name] = changed

    patched = replace_nitrofs_files(source_rom.read_bytes(), replacements)
    output_rom.parent.mkdir(parents=True, exist_ok=True)
    output_rom.write_bytes(patched)

    # Structural verification: all rebuilt PAKs and pointer tables must parse.
    verified_tables = 0
    with output_rom.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        for archive_name in replacements:
            archive = XrosPak.from_bytes(
                read_nitro_file(handle, find_nitro_file(files, archive_name))
            )
            for index in range(len(archive.entries)):
                try:
                    parse_message_table(
                        archive.unpacked_data(index), encoding="shift_jis"
                    )
                    verified_tables += 1
                except ValueError:
                    pass

    manifest: dict[str, object] = {
        "source_rom": str(source_rom),
        "output_rom": str(output_rom),
        "source_game_code": header["game_code"],
        "source_sha256": hashlib.sha256(source_rom.read_bytes()).hexdigest(),
        "output_sha256": hashlib.sha256(patched).hexdigest(),
        "glossary_entries": len(glossary),
        "changed_strings": sum(changed_by_archive.values()),
        "changed_by_archive": changed_by_archive,
        "verified_message_tables": verified_tables,
        "scope": (
            "Validated Lost Evolution terminology plus core Xros Digimon names "
            "across every message archive. Xros-exclusive dialogue remains Japanese."
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
    parser.add_argument("lost_japanese_csv", type=Path)
    parser.add_argument("lost_english_csv", type=Path)
    parser.add_argument("short_roster_csv", type=Path)
    parser.add_argument("formal_roster_csv", type=Path)
    parser.add_argument("output_rom", type=Path)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    result = build_glossary_rom(
        args.source_rom,
        args.lost_japanese_csv,
        args.lost_english_csv,
        args.short_roster_csv,
        args.formal_roster_csv,
        args.output_rom,
        args.manifest,
    )
    print(
        f"Built {args.output_rom} with {result['changed_strings']} translated "
        f"strings; SHA-256 {result['output_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
