#!/usr/bin/env python3
"""Find the seven field-hex Japanese labels in raw NitroFS files and PAK members."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "work" / "DigimonNDSRomEditor-master"))

from rom_research.nds_inventory import read_header, read_nitrofs  # noqa: E402
from rom_research.xros_pak import XrosPak, read_nitro_file  # noqa: E402

TERMS = {
    "status": "ステータス", "skills": "わざ", "equip": "そうび", "formation": "たいれつ",
    "items": "もちもの", "map": "マップ", "info": "じょうほう",
}


def hits(data: bytes, needle: bytes) -> list[int]:
    result, pos = [], 0
    while True:
        pos = data.find(needle, pos)
        if pos < 0: return result
        result.append(pos); pos += 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    needles = [(name, encoding, value.encode(encoding)) for name, value in TERMS.items() for encoding in ("utf-8", "cp932")]
    rows: list[dict[str, object]] = []
    with args.rom.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        for item in files:
            raw = read_nitro_file(handle, item)
            for term, encoding, needle in needles:
                for offset in hits(raw, needle):
                    rows.append({"term": f"{term}/{encoding}", "path": item.path, "container": "raw", "entry": "", "offset": f"0x{offset:X}"})
            try:
                pak = XrosPak.from_bytes(raw)
            except (ValueError, IndexError):
                continue
            for entry in pak.entries:
                try: data = pak.unpacked_data(entry)
                except ValueError: continue
                for term, encoding, needle in needles:
                    for offset in hits(data, needle):
                        rows.append({"term": f"{term}/{encoding}", "path": item.path, "container": "pak", "entry": entry.index, "offset": f"0x{offset:X}"})
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=("term", "path", "container", "entry", "offset"), delimiter="\t")
        writer.writeheader(); writer.writerows(rows)
    print(f"{len(rows)} hits written to {args.out}")
    for row in rows: print(row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
