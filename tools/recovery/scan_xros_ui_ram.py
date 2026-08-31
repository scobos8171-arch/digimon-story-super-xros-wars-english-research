#!/usr/bin/env python3
"""Locate known Xros UI strings in a full DeSmuME ARM9 RAM capture."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


DEFAULT_TERMS = (
    "ステータス",
    "めいれい",
    "わざ",
    "そうび",
    "たいれつ",
    "もちもの",
    "マップ",
    "じょうほう",
    "デジクロス",
    "アイテム",
    "さくせん",
    "もどる",
    "バトルけっか",
    "つぎへ",
    "バトルほうしゅう",
    "Shoutmon",
    "Ballista",
    "Shoji",
)


def find_all(data: bytes, needle: bytes) -> list[int]:
    positions: list[int] = []
    start = 0
    while True:
        position = data.find(needle, start)
        if position < 0:
            return positions
        positions.append(position)
        start = position + 1


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser()
    parser.add_argument("capture", type=Path)
    parser.add_argument("--base", type=lambda value: int(value, 0), default=0x02000000)
    args = parser.parse_args()

    data = args.capture.read_bytes()
    for term in DEFAULT_TERMS:
        matches: list[tuple[str, int]] = []
        for encoding in ("shift_jis", "cp932", "utf-16le", "ascii"):
            try:
                encoded = term.encode(encoding)
            except UnicodeEncodeError:
                continue
            matches.extend((encoding, args.base + offset) for offset in find_all(data, encoded))
        formatted = ", ".join(f"{encoding}@0x{address:08X}" for encoding, address in matches)
        print(f"{term}: {formatted or 'not found in standard encodings'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
