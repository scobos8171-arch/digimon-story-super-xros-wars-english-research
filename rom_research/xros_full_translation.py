"""Translate every safely decodable Xros message and build one English ROM."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import hashlib
import json
import re
import subprocess
import time
from urllib.parse import quote
from pathlib import Path

from deep_translator import GoogleTranslator

from rom_research.nds_inventory import read_header, read_nitrofs
from rom_research.nitrofs_patch import replace_nitrofs_files
from rom_research.story_messages import MESSAGE_ARCHIVES, build_message_table, parse_message_table
from rom_research.xros_glossary_build import build_glossary
from rom_research.xros_pak import XrosPak, build_xros_pak, find_nitro_file, read_nitro_file


JAPANESE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")
NEWLINE_TOKEN = " ZXQNEWLINEQXZ "


def load_cache(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_cache(path: Path, cache: dict[str, str]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


def normalize(text: str) -> str:
    replacements = {
        "Dejimon": "Digimon",
        "Digicloth": "DigiXros",
        "Digi Cross": "DigiXros",
        "DigiCross": "DigiXros",
        "Cross Loader": "Xros Loader",
        "Shout Mon": "Shoutmon",
        "Ballista Mon": "Ballistamon",
        "Doruru Mon": "Dorulumon",
        "Spada Mon": "Spadamon",
        "Cutie Mon": "Cutemon",
        "Kudou Taiki": "Taiki Kudo",
        "Kudo Taiki": "Taiki Kudo",
        "Hinomoto Akari": "Akari Hinomoto",
        "Tsurugi Zenjiro": "Zenjiro Tsurugi",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    text = text.replace(NEWLINE_TOKEN.strip(), "\n").strip()
    return (
        text.replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u2026", "...")
    )


def translate_corpus(
    japanese_csv: Path,
    cache_path: Path,
    glossary: dict[str, str],
    *,
    checkpoint_every: int = 20,
) -> dict[str, str]:
    cache = load_cache(cache_path)
    with japanese_csv.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    unique = []
    seen: set[str] = set()
    for row in rows:
        text = row["text"]
        if JAPANESE.search(text) and text not in seen:
            seen.add(text)
            unique.append(text)

    # Seed exact, human-edited Lost Evolution translations first.
    for text in unique:
        escaped = text.replace("\r", "\\r").replace("\n", "\\n")
        if text not in cache and escaped in glossary:
            cache[text] = glossary[escaped].replace("\\r", "\r").replace("\\n", "\n")
    save_cache(cache_path, cache)

    pending = [text for text in unique if text not in cache]

    def translate_one(text: str) -> tuple[str, str]:
        request = text.replace("\\r", "").replace("\\n", NEWLINE_TOKEN)
        for attempt in range(6):
            try:
                url = (
                    "https://translate.googleapis.com/translate_a/single"
                    "?client=gtx&sl=ja&tl=en&dt=t&q="
                    + quote(request, safe="")
                )
                response = subprocess.run(
                    (
                        "curl.exe",
                        "--ssl-no-revoke",
                        "-sS",
                        "--max-time",
                        "30",
                        url,
                    ),
                    check=True,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                )
                payload = json.loads(response.stdout)
                translated = "".join(
                    segment[0] for segment in payload[0] if segment[0]
                )
                if not translated:
                    raise RuntimeError("translation service returned an empty string")
                return text, normalize(translated)
            except Exception:
                if attempt == 5:
                    raise
                time.sleep(2 ** attempt)
        raise AssertionError("unreachable")

    completed = 0
    with ThreadPoolExecutor(max_workers=16) as executor:
        futures = [executor.submit(translate_one, text) for text in pending]
        for future in as_completed(futures):
            source, translated = future.result()
            cache[source] = translated
            completed += 1
            if completed % checkpoint_every == 0:
                save_cache(cache_path, cache)
                print(
                    f"cached {len(cache)}/{len(unique)} unique strings",
                    flush=True,
                )
    save_cache(cache_path, cache)
    return cache


def build_rom(
    source_rom: Path,
    cache: dict[str, str],
    output_rom: Path,
    manifest_path: Path,
) -> dict[str, object]:
    replacements: dict[str, bytes] = {}
    changed = 0
    skipped = 0
    with source_rom.open("rb") as handle:
        header = read_header(handle)
        files = read_nitrofs(handle, header)
        for archive_name in MESSAGE_ARCHIVES:
            pak = XrosPak.from_bytes(
                read_nitro_file(handle, find_nitro_file(files, archive_name))
            )
            entries: list[bytes] = []
            archive_changed = False
            for entry_index in range(len(pak.entries)):
                original = pak.unpacked_data(entry_index)
                try:
                    _offsets, strings = parse_message_table(original, encoding="shift_jis")
                except ValueError:
                    entries.append(original)
                    continue
                patched = list(strings)
                for string_index, raw in enumerate(strings):
                    try:
                        source = raw.decode("shift_jis", errors="strict")
                    except UnicodeDecodeError:
                        skipped += 1
                        continue
                    key = source.replace("\r", "\\r").replace("\n", "\\n")
                    target = cache.get(key) or cache.get(source)
                    if target is None or not JAPANESE.search(source):
                        continue
                    encoded = normalize(target).encode("ascii", errors="replace")
                    if encoded != raw:
                        patched[string_index] = encoded
                        changed += 1
                        archive_changed = True
                entries.append(build_message_table(original, patched))
            if archive_changed:
                replacements[archive_name] = build_xros_pak(entries)

    rom = replace_nitrofs_files(source_rom.read_bytes(), replacements)
    output_rom.write_bytes(rom)
    verified = 0
    with output_rom.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        for archive_name in replacements:
            pak = XrosPak.from_bytes(
                read_nitro_file(handle, find_nitro_file(files, archive_name))
            )
            for entry_index in range(len(pak.entries)):
                try:
                    parse_message_table(pak.unpacked_data(entry_index), encoding="shift_jis")
                    verified += 1
                except ValueError:
                    pass
    result = {
        "source_rom": str(source_rom),
        "output_rom": str(output_rom),
        "source_sha256": hashlib.sha256(source_rom.read_bytes()).hexdigest(),
        "output_sha256": hashlib.sha256(rom).hexdigest(),
        "translated_message_rows": changed,
        "archives_rebuilt": sorted(replacements),
        "verified_message_tables": verified,
        "undecodable_strings_skipped": skipped,
        "gameplay_changes": "None",
    }
    manifest_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_rom", type=Path)
    parser.add_argument("xros_japanese_csv", type=Path)
    parser.add_argument("lost_japanese_csv", type=Path)
    parser.add_argument("lost_english_csv", type=Path)
    parser.add_argument("short_roster_csv", type=Path)
    parser.add_argument("formal_roster_csv", type=Path)
    parser.add_argument("cache", type=Path)
    parser.add_argument("output_rom", type=Path)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    glossary = build_glossary(
        args.lost_japanese_csv,
        args.lost_english_csv,
        (args.short_roster_csv, args.formal_roster_csv),
    )
    cache = translate_corpus(args.xros_japanese_csv, args.cache, glossary)
    result = build_rom(args.source_rom, cache, args.output_rom, args.manifest)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
