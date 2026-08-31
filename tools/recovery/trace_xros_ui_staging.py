#!/usr/bin/env python3
"""Summarize ARM9-RAM pointers into known live Xros UI staging ranges.

This is deliberately conservative: it never modifies a capture and limits
printed owners so a broad heap range cannot flood the terminal.
"""

from __future__ import annotations

import argparse
import struct
from collections import Counter, defaultdict
from pathlib import Path


RAM_BASE = 0x02000000


def parse_range(value: str) -> tuple[int, int]:
    start_text, end_text = value.split(":", 1)
    start = int(start_text, 0)
    end = int(end_text, 0)
    if end <= start:
        raise argparse.ArgumentTypeError("range end must be greater than start")
    return start, end


def u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("ram", type=Path)
    parser.add_argument("--range", dest="ranges", action="append", type=parse_range,
                        required=True, help="target address range START:END")
    parser.add_argument("--exact", action="append", default=[],
                        help="exact target address (repeatable)")
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--context", type=int, default=0,
                        help="neighboring 32-bit words shown around exact-pointer owners")
    args = parser.parse_args()

    data = args.ram.read_bytes()
    exact = {int(value, 0) for value in args.exact}
    exact_owners: dict[int, list[int]] = defaultdict(list)
    range_owners: dict[tuple[int, int], list[tuple[int, int]]] = defaultdict(list)
    owner_pages: Counter[tuple[tuple[int, int], int]] = Counter()

    for offset in range(0, len(data) - 3, 4):
        value = u32(data, offset)
        owner = RAM_BASE + offset
        if value in exact:
            exact_owners[value].append(owner)
        for target_range in args.ranges:
            start, end = target_range
            if start <= value < end:
                range_owners[target_range].append((owner, value))
                owner_pages[(target_range, owner & ~0xFFF)] += 1

    print(f"RAM: {args.ram} ({len(data):,} bytes)")
    for target in sorted(exact):
        owners = exact_owners.get(target, [])
        rendered = ", ".join(f"0x{x:08X}" for x in owners[: args.limit]) or "none"
        suffix = f" (+{len(owners) - args.limit} more)" if len(owners) > args.limit else ""
        print(f"exact 0x{target:08X}: {len(owners)} owner(s): {rendered}{suffix}")
        if args.context:
            for owner in owners[: args.limit]:
                owner_offset = owner - RAM_BASE
                first = max(0, owner_offset - args.context * 4)
                last = min(len(data), owner_offset + (args.context + 1) * 4)
                words = []
                for context_offset in range(first, last, 4):
                    value = u32(data, context_offset)
                    marker = "*" if context_offset == owner_offset else " "
                    words.append(
                        f"{marker}0x{RAM_BASE + context_offset:08X}=0x{value:08X}"
                    )
                print("    " + "  ".join(words))

    for target_range in args.ranges:
        start, end = target_range
        owners = range_owners[target_range]
        print(f"range 0x{start:08X}:0x{end:08X}: {len(owners)} pointer(s)")
        page_counts = [
            (page, count)
            for (stored_range, page), count in owner_pages.items()
            if stored_range == target_range
        ]
        page_counts.sort(key=lambda item: (-item[1], item[0]))
        for page, count in page_counts[: args.limit]:
            examples = [
                (owner, value) for owner, value in owners
                if (owner & ~0xFFF) == page
            ][:4]
            formatted = ", ".join(
                f"0x{owner:08X}->0x{value:08X}" for owner, value in examples
            )
            print(f"  owner page 0x{page:08X}: {count:4d}  {formatted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
