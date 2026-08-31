#!/usr/bin/env python3
"""Rank structurally similar ARM functions from two Ghidra research indexes."""

from __future__ import annotations

import argparse
import csv
from difflib import SequenceMatcher
from pathlib import Path


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def ngrams(items: list[str], width: int = 3) -> set[tuple[str, ...]]:
    if len(items) < width:
        return {tuple(items)} if items else set()
    return {tuple(items[index : index + width]) for index in range(len(items) - width + 1)}


def similarity(source: dict[str, str], candidate: dict[str, str]) -> float:
    left = source.get("mnemonics", "").split(",")
    right = candidate.get("mnemonics", "").split(",")
    if not left or not right:
        return 0.0
    sequence = SequenceMatcher(None, left, right, autojunk=False).ratio()
    left_grams, right_grams = ngrams(left), ngrams(right)
    union = left_grams | right_grams
    jaccard = len(left_grams & right_grams) / len(union) if union else 0.0
    length_ratio = min(len(left), len(right)) / max(len(left), len(right))
    source_calls = int(source["callees"])
    candidate_calls = int(candidate["callees"])
    call_ratio = 1.0 - min(abs(source_calls - candidate_calls), 5) / 5.0
    return 0.45 * sequence + 0.35 * jaccard + 0.15 * length_ratio + 0.05 * call_ratio


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_index", type=Path)
    parser.add_argument("target_index", type=Path)
    parser.add_argument("source_function")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    source_rows = read_rows(args.source_index)
    target_rows = read_rows(args.target_index)
    source = next(
        (row for row in source_rows if row["name"] == args.source_function or row["address"] == args.source_function.lower().removeprefix("0x")),
        None,
    )
    if source is None:
        raise SystemExit(f"source function not found: {args.source_function}")

    ranked = sorted(
        ((similarity(source, row), row) for row in target_rows),
        key=lambda item: item[0],
        reverse=True,
    )[: args.limit]
    columns = ["rank", "score", "address", "name", "instructions", "callees", "mnemonic_sha256"]
    lines = ["\t".join(columns)]
    for rank, (score, row) in enumerate(ranked, 1):
        lines.append(
            "\t".join(
                [str(rank), f"{score:.6f}"] + [row[column] for column in columns[2:]]
            )
        )
    result = "\n".join(lines) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result, encoding="utf-8")
    print(result, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
