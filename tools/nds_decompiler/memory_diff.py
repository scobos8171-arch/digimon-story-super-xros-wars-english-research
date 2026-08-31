#!/usr/bin/env python3
"""Report changed runs between two equally-sized runtime memory dumps."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def changed_runs(left: bytes, right: bytes, minimum: int = 1) -> list[dict[str, object]]:
    if len(left) != len(right):
        raise ValueError("memory dumps must have equal lengths")
    runs: list[dict[str, object]] = []
    start: int | None = None
    for index, (a, b) in enumerate(zip(left, right)):
        if a != b and start is None:
            start = index
        elif a == b and start is not None:
            if index - start >= minimum:
                runs.append(_describe(left, right, start, index))
            start = None
    if start is not None and len(left) - start >= minimum:
        runs.append(_describe(left, right, start, len(left)))
    return runs


def _describe(left: bytes, right: bytes, start: int, end: int) -> dict[str, object]:
    return {
        "offset": f"0x{start:06x}",
        "address": f"0x{0x02000000 + start:08x}",
        "length": end - start,
        "before": left[start : min(end, start + 32)].hex(),
        "after": right[start : min(end, start + 32)].hex(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("--minimum", type=int, default=1)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    runs = changed_runs(args.before.read_bytes(), args.after.read_bytes(), args.minimum)
    result = {"before": str(args.before), "after": str(args.after), "changed_runs": runs}
    text = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
