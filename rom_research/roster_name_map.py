"""Build a Lost Evolution Japanese-to-English name map for Xros Wars."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Message:
    archive: str
    pak_entry: int
    string_index: int
    text: str

    @property
    def location(self) -> tuple[str, int, int]:
        return self.archive, self.pak_entry, self.string_index


def read_messages(path: Path) -> list[Message]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [
            Message(
                row["archive"],
                int(row["pak_entry"]),
                int(row["string_index"]),
                row["text"],
            )
            for row in csv.DictReader(handle)
        ]


def build_translation_index(
    japanese: list[Message],
    english: list[Message],
) -> dict[str, tuple[tuple[str, tuple[str, int, int]], ...]]:
    english_by_location = {message.location: message.text for message in english}
    candidates: dict[str, set[tuple[str, tuple[str, int, int]]]] = defaultdict(set)
    for message in japanese:
        translated = english_by_location.get(message.location)
        if translated is None or not message.text or not translated:
            continue
        candidates[message.text].add((translated, message.location))
    return {
        source: tuple(sorted(values))
        for source, values in candidates.items()
    }


def export_xros_roster_map(
    xros: list[Message],
    translations: dict[str, tuple[tuple[str, tuple[str, int, int]], ...]],
    output: Path,
    *,
    archive: str,
    pak_entry: int,
    first_index: int,
    last_index: int,
) -> dict[str, int]:
    roster = [
        message
        for message in xros
        if message.archive == archive
        and message.pak_entry == pak_entry
        and first_index <= message.string_index <= last_index
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    matched = ambiguous = unmatched = 0
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            (
                "xros_string_index",
                "japanese",
                "english",
                "status",
                "lost_archive",
                "lost_pak_entry",
                "lost_string_index",
                "candidate_count",
            )
        )
        for message in roster:
            candidates = translations.get(message.text, ())
            distinct_english = sorted({candidate[0] for candidate in candidates})
            if not candidates:
                status = "xros_only_or_untranslated"
                translated = ""
                source = ("", "", "")
                unmatched += 1
            elif len(distinct_english) == 1:
                status = "exact"
                translated = distinct_english[0]
                source = candidates[0][1]
                matched += 1
            else:
                status = "ambiguous"
                translated = " | ".join(distinct_english)
                source = candidates[0][1]
                ambiguous += 1
            writer.writerow(
                (
                    message.string_index,
                    message.text,
                    translated,
                    status,
                    source[0],
                    source[1],
                    source[2],
                    len(candidates),
                )
            )
    return {
        "rows": len(roster),
        "matched": matched,
        "ambiguous": ambiguous,
        "unmatched": unmatched,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lost_japanese_csv", type=Path)
    parser.add_argument("lost_english_csv", type=Path)
    parser.add_argument("xros_japanese_csv", type=Path)
    parser.add_argument("output_csv", type=Path)
    parser.add_argument("--archive", default="MSG/MESPAK00.PAK")
    parser.add_argument("--pak-entry", type=int, default=0)
    parser.add_argument("--first-index", type=int, default=178)
    parser.add_argument("--last-index", type=int, default=575)
    args = parser.parse_args()

    translations = build_translation_index(
        read_messages(args.lost_japanese_csv),
        read_messages(args.lost_english_csv),
    )
    result = export_xros_roster_map(
        read_messages(args.xros_japanese_csv),
        translations,
        args.output_csv,
        archive=args.archive,
        pak_entry=args.pak_entry,
        first_index=args.first_index,
        last_index=args.last_index,
    )
    print(
        f"Mapped {result['matched']} of {result['rows']} Xros strings "
        f"({result['ambiguous']} ambiguous, {result['unmatched']} unmatched) "
        f"to {args.output_csv}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
