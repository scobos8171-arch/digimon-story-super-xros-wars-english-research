#!/usr/bin/env python3
"""Extract memory blocks from zlib-compressed DeSmuME .dst save states."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import zlib
from pathlib import Path


STATE_MAGIC = b"DeSmuME SState\x00\x00"
BLOCK_TAGS = {b"ITCM", b"DTCM", b"WRAM", b"WRAX", b"9REG", b"VMEM", b"OAMS", b"LCDM"}


def unpack_state(path: Path) -> bytes:
    payload = path.read_bytes()
    if not payload.startswith(STATE_MAGIC):
        return payload
    # DeSmuME's current state format uses a 32-byte header followed by zlib.
    return zlib.decompress(payload[32:])


def parse_memory_blocks(raw: bytes) -> dict[str, bytes]:
    start = raw.find(b"ITCM")
    if start < 0:
        raise ValueError("ITCM block was not found in the state")
    blocks: dict[str, bytes] = {}
    cursor = start
    while cursor + 12 <= len(raw):
        tag = raw[cursor : cursor + 4]
        if tag not in BLOCK_TAGS:
            break
        count, element_size = struct.unpack_from("<II", raw, cursor + 4)
        byte_count = count * element_size
        data_start = cursor + 12
        data_end = data_start + byte_count
        if data_end > len(raw):
            raise ValueError(f"truncated {tag.decode()} block")
        blocks[tag.decode("ascii")] = raw[data_start:data_end]
        cursor = data_end
    return blocks


def overlay_matches(main_ram: bytes, overlays: Path | None) -> list[dict[str, object]]:
    if overlays is None or not overlays.exists():
        return []
    results = []
    for path in sorted(overlays.glob("overlay_*_0x*.bin")):
        try:
            address = int(path.stem.rsplit("_0x", 1)[1], 16)
        except (IndexError, ValueError):
            continue
        data = path.read_bytes()
        offset = address - 0x02000000
        if offset < 0 or offset + len(data) > len(main_ram):
            continue
        live = main_ram[offset : offset + len(data)]
        equal_bytes = sum(left == right for left, right in zip(live, data))
        equal_ratio = equal_bytes / len(data) if data else 1.0
        # A loaded DS overlay can contain a very small number of relocated or
        # runtime-patched words.  Requiring byte-for-byte equality hid overlay
        # 0 in the v3 Xros build even though 99.9688% of its 160 KiB image
        # matched at the declared load address.  Keep exact_match for forensic
        # reporting and expose loaded_match as the practical detector.
        loaded_match = live == data or (len(data) >= 0x1000 and equal_ratio >= 0.999)
        results.append(
            {
                "file": str(path),
                "load_address": f"0x{address:08x}",
                "bytes": len(data),
                "exact_match": live == data,
                "loaded_match": loaded_match,
                "different_bytes": len(data) - equal_bytes,
                "equal_byte_ratio": round(equal_ratio, 6),
            }
        )
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("state", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--overlays", type=Path)
    args = parser.parse_args()

    raw = unpack_state(args.state)
    blocks = parse_memory_blocks(raw)
    args.output.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, object] = {"source": str(args.state), "blocks": {}}
    for tag, data in blocks.items():
        destination = args.output / f"{tag.lower()}.bin"
        destination.write_bytes(data)
        manifest["blocks"][tag] = {
            "file": destination.name,
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
    if "WRAM" in blocks:
        manifest["main_ram_base"] = "0x02000000"
        manifest["overlay_matches"] = overlay_matches(blocks["WRAM"], args.overlays)
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
