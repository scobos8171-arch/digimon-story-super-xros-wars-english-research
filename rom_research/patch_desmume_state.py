"""Patch one ARM9 word inside a DeSmuME v12 compressed save state."""

from __future__ import annotations

import argparse
import struct
import zlib
from pathlib import Path


HEADER_SIZE = 32
WRAM_TAG = b"WRAM"
WRAM_SIZE = 0x400000


def patch_state(
    source: Path,
    output: Path,
    address: int,
    value: int,
    source_rom: Path | None = None,
    target_rom: Path | None = None,
) -> None:
    raw = bytearray(source.read_bytes())
    if raw[:16] != b"DeSmuME SState\0\0":
        raise ValueError("Not a DeSmuME save state")
    payload = bytearray(zlib.decompress(raw[HEADER_SIZE:]))
    tag = payload.find(WRAM_TAG)
    if tag < 0:
        raise ValueError("WRAM section not found")
    version, size = struct.unpack_from("<II", payload, tag + 4)
    if version != 1 or size != WRAM_SIZE:
        raise ValueError(f"Unexpected WRAM section version/size: {version}/{size}")
    ram_start = tag + 12
    ram_offset = address - 0x02000000
    if not 0 <= ram_offset <= WRAM_SIZE - 4:
        raise ValueError(f"Address 0x{address:08X} is outside main RAM")
    struct.pack_into("<I", payload, ram_start + ram_offset, value)
    if source_rom is not None and target_rom is not None:
        old_header = source_rom.read_bytes()[:0x200]
        new_header = target_rom.read_bytes()[:0x200]
        # GINF stores the ROM identity, while two WRAM copies represent the
        # cartridge header mapped into emulated memory.
        replacements = 0
        cursor = 0
        while True:
            cursor = payload.find(old_header, cursor)
            if cursor < 0:
                break
            payload[cursor:cursor + len(new_header)] = new_header
            replacements += 1
            cursor += len(new_header)
        for header_size in (0x160, 0x100, 0x40):
            old = old_header[:header_size]
            new = new_header[:header_size]
            cursor = 0
            while True:
                cursor = payload.find(old, cursor)
                if cursor < 0:
                    break
                payload[cursor:cursor + header_size] = new
                replacements += 1
                cursor += header_size
        if replacements == 0:
            raise ValueError("Source ROM identity was not found in save state")
    compressed = zlib.compress(bytes(payload), level=6)
    struct.pack_into("<I", raw, 24, len(payload))
    struct.pack_into("<I", raw, 28, len(compressed))
    output.write_bytes(raw[:HEADER_SIZE] + compressed)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("address", type=lambda value: int(value, 0))
    parser.add_argument("value", type=lambda value: int(value, 0))
    parser.add_argument("--source-rom", type=Path)
    parser.add_argument("--target-rom", type=Path)
    args = parser.parse_args()
    patch_state(
        args.source,
        args.output,
        args.address,
        args.value,
        args.source_rom,
        args.target_rom,
    )
    print(f"Patched {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
