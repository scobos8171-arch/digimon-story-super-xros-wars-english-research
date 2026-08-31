"""Build complete English short/formal Xros Wars Digimon name tables."""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import quote

from rom_research.nds_inventory import read_header, read_nitrofs
from rom_research.nitrofs_patch import replace_nitrofs_files
from rom_research.story_messages import build_message_table, parse_message_table
from rom_research.xros_pak import XrosPak, build_xros_pak, find_nitro_file, read_nitro_file


ARCHIVE = "MSG/MESPAK00.PAK"


def translate_name(source: str) -> str:
    url = (
        "https://translate.googleapis.com/translate_a/single"
        "?client=gtx&sl=ja&tl=en&dt=t&q="
        + quote(source, safe="")
    )
    response = subprocess.run(
        ("curl.exe", "--ssl-no-revoke", "-sS", "--max-time", "30", url),
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    payload = json.loads(response.stdout)
    name = "".join(segment[0] for segment in payload[0] if segment[0]).strip()
    name = re.sub(r"\s+[Mm]on\b", "mon", name)
    name = name.replace(" Mon", "mon").replace(" Digimon", "mon")
    return name.encode("ascii", errors="ignore").decode("ascii") or "Unknown"


def read_names(path: Path, cache: dict[str, str]) -> list[tuple[int, str]]:
    rows = list(csv.DictReader(path.open(encoding="utf-8-sig", newline="")))
    output: list[tuple[int, str]] = []
    for row in rows:
        japanese = row["japanese"]
        english = row["english"] if row["status"] == "exact" else ""
        if not english or "?" in english:
            english = cache.get(japanese, "")
            if not english:
                english = translate_name(japanese)
                cache[japanese] = english
        english = english.encode("ascii", errors="ignore").decode("ascii").strip()
        if not english:
            english = "Unknown"
        output.append((int(row["xros_string_index"]), english))
    return output


def build(
    source: Path,
    short_csv: Path,
    formal_csv: Path,
    cache_path: Path,
    output: Path,
) -> None:
    cache = (
        json.loads(cache_path.read_text(encoding="utf-8"))
        if cache_path.exists()
        else {}
    )
    short = read_names(short_csv, cache)
    formal = read_names(formal_csv, cache)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")

    with source.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        pak = XrosPak.from_bytes(
            read_nitro_file(handle, find_nitro_file(files, ARCHIVE))
        )
    entries = [pak.unpacked_data(index) for index in range(len(pak.entries))]
    original = entries[0]
    _offsets, strings = parse_message_table(original, encoding="shift_jis")
    patched = list(strings)
    for index, name in short + formal:
        patched[index] = name.encode("ascii")
    entries[0] = build_message_table(original, patched)
    rom = replace_nitrofs_files(
        source.read_bytes(),
        {ARCHIVE: build_xros_pak(entries)},
    )
    output.write_bytes(rom)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("short_csv", type=Path)
    parser.add_argument("formal_csv", type=Path)
    parser.add_argument("cache", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    build(args.source, args.short_csv, args.formal_csv, args.cache, args.output)
