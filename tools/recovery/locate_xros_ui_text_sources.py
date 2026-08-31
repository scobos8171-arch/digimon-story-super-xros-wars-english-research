#!/usr/bin/env python3
"""Locate Xros Wars UI strings in code, NitroFS files, and PAK members.

Raw ROM searches miss strings stored in compressed overlays or compressed PAK
members.  This tool searches the decompressed code files supplied by the
decompiler, every raw NitroFS file, and every member of a version 2.01 Xros
PAK.  It is deliberately read-only and emits provenance suitable for planning
a size-safe localization patch.
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ROM_RESEARCH = ROOT / "work" / "DigimonNDSRomEditor-master"
if str(ROM_RESEARCH) not in sys.path:
    sys.path.insert(0, str(ROM_RESEARCH))

from rom_research.nds_inventory import read_header, read_nitrofs  # noqa: E402
from rom_research.xros_pak import XrosPak  # noqa: E402


TERMS = {
    "status": "ステータス",
    "skills": "わざ",
    "equip": "そうび",
    "formation": "たいれつ",
    "items_inventory": "もちもの",
    "items": "アイテム",
    "map": "マップ",
    "info": "じょうほう",
    "back": "もどる",
    "orders": "めいれい",
    "digixros": "デジクロス",
    "battle_results": "バトルけっか",
    "battle_rewards": "バトルほうしゅう",
    "next": "つぎへ",
    "tactics": "さくせん",
    "wisdom": "かしこさ",
    "speed": "すばやさ",
    "defense": "まもり",
    "bond": "ゆうじょう",
}


@dataclass(frozen=True)
class Hit:
    term: str
    japanese: str
    encoding: str
    container: str
    member: str
    offset: int


def find_all(data: bytes, needle: bytes):
    cursor = 0
    while True:
        cursor = data.find(needle, cursor)
        if cursor < 0:
            return
        yield cursor
        cursor += 1


def scan_blob(container: str, member: str, data: bytes) -> list[Hit]:
    hits: list[Hit] = []
    for key, text in TERMS.items():
        for encoding in ("cp932", "utf-16le", "utf-8"):
            needle = text.encode(encoding)
            for offset in find_all(data, needle):
                hits.append(Hit(key, text, encoding, container, member, offset))
    return hits


def scan_code_tree(code_dir: Path) -> list[Hit]:
    hits: list[Hit] = []
    if not code_dir.exists():
        return hits
    for path in sorted(code_dir.rglob("*.bin")):
        hits.extend(scan_blob("decompressed_code", str(path), path.read_bytes()))
    return hits


def scan_rom(rom: Path) -> list[Hit]:
    hits: list[Hit] = []
    with rom.open("rb") as handle:
        header = read_header(handle)
        files = read_nitrofs(handle, header)
        for item in files:
            handle.seek(item.offset)
            data = handle.read(item.size)
            hits.extend(scan_blob("nitrofs", item.path, data))
            if len(data) < 8 or data[4:8] != b"2.01":
                continue
            try:
                pak = XrosPak.from_bytes(data)
            except ValueError:
                continue
            for entry in pak.entries:
                try:
                    unpacked = pak.unpacked_data(entry)
                except ValueError:
                    continue
                hits.extend(
                    scan_blob(
                        "xros_pak",
                        f"{item.path}::entry_{entry.index:04d}",
                        unpacked,
                    )
                )
    return hits


def write_tsv(path: Path, hits: list[Hit]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow(("term", "japanese", "encoding", "container", "member", "offset"))
        for hit in sorted(hits, key=lambda h: (h.term, h.container, h.member, h.offset)):
            writer.writerow(
                (hit.term, hit.japanese, hit.encoding, hit.container, hit.member, f"0x{hit.offset:X}")
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", type=Path)
    parser.add_argument("--code-dir", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    hits = scan_rom(args.rom)
    if args.code_dir:
        hits.extend(scan_code_tree(args.code_dir))
    write_tsv(args.out, hits)

    counts = {key: 0 for key in TERMS}
    for hit in hits:
        counts[hit.term] += 1
    print(f"Wrote {len(hits)} hits to {args.out}")
    for key, count in counts.items():
        print(f"{key}\t{count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
