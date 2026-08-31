#!/usr/bin/env python3
"""Locate known Japanese UI labels in raw Xros ROM bytes.

Searches multiple likely encodings.  The output lets us identify the live
text table before any font or graphics edit is attempted.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


TERMS = {
    "status": "\u30b9\u30c6\u30fc\u30bf\u30b9",
    "skills": "\u308f\u3056",
    "equip": "\u305d\u3046\u3073",
    "formation": "\u305f\u3044\u308c\u3064",
    "items": "\u3082\u3061\u3082\u306e",
    "map": "\u30de\u30c3\u30d7",
    "info": "\u3058\u3087\u3046\u307b\u3046",
    "back": "\u3082\u3069\u308b",
    "orders": "\u3081\u3044\u308c\u3044",
    "digixros": "\u30c7\u30b8\u30af\u30ed\u30b9",
    "battle_results": "\u30d0\u30c8\u30eb\u3051\u3063\u304b",
    "wisdom": "\u304b\u3057\u3053\u3055",
    "speed": "\u3059\u3070\u3084\u3055",
    "defense": "\u307e\u3082\u308a",
    "bond": "\u3086\u3046\u3058\u3087\u3046",
}


def find_all(data: bytes, needle: bytes) -> list[int]:
    found: list[int] = []
    offset = 0
    while True:
        offset = data.find(needle, offset)
        if offset < 0:
            return found
        found.append(offset)
        offset += 1


def scan(path: Path) -> dict[str, object]:
    data = path.read_bytes()
    terms: dict[str, dict[str, list[str]]] = {}
    for key, text in TERMS.items():
        encodings: dict[str, list[str]] = {}
        for encoding in ("cp932", "utf-16le", "utf-8"):
            hits = find_all(data, text.encode(encoding))
            if hits:
                encodings[encoding] = [f"0x{hit:08X}" for hit in hits]
        if encodings:
            terms[key] = encodings
    return {"rom": str(path), "matches": terms}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", type=Path, nargs="+")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = [scan(path) for path in args.rom]
    rendered = json.dumps(report, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
