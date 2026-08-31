#!/usr/bin/env python3
"""Lost Evolution ASCII decoder, ported to Super Xros ARM9.

LE patch: ARM9 0x39CB0  ldrh r1,[r4]  ->  mov r1,#0
Xros Blue has the same instruction at 0x02039CB0.  Isolated ROM only.
This does not replace hex strings by itself; it lets 1-byte ASCII survive
the 16-bit character walk.  Japanese that still uses 2-byte SJIS on that
path may break.  Cold-boot Skills before stacking anything else.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "work" / "DigimonNDSRomEditor-master"))
from rom_research.nds_code_compression import compress_blz, decompress_blz

ARM9_OFFSET = 0x39CB0
EXPECTED = bytes.fromhex("B010D4E1")  # ldrh r1, [r4]
REPLACEMENT = bytes.fromhex("0010A0E3")  # mov r1, #0


def crc16(data: bytes | bytearray) -> int:
    value = 0xFFFF
    for byte in data:
        value ^= byte
        for _ in range(8):
            value = (value >> 1) ^ (0xA001 if value & 1 else 0)
    return value & 0xFFFF


def build(source: Path, output: Path, manifest: Path) -> dict[str, object]:
    rom = bytearray(source.read_bytes())
    arm9_off = struct.unpack_from("<I", rom, 0x20)[0]
    arm9_size = struct.unpack_from("<I", rom, 0x2C)[0]
    stored = bytes(rom[arm9_off : arm9_off + arm9_size])
    decoded = bytearray(decompress_blz(stored))
    actual = bytes(decoded[ARM9_OFFSET : ARM9_OFFSET + 4])
    if actual != EXPECTED:
        raise ValueError(
            f"ASCII decoder site changed: expected {EXPECTED.hex()}, got {actual.hex()} "
            f"at ARM9+0x{ARM9_OFFSET:X}"
        )
    decoded[ARM9_OFFSET : ARM9_OFFSET + 4] = REPLACEMENT
    rebuilt = compress_blz(bytes(decoded))
    if decompress_blz(rebuilt)[ARM9_OFFSET : ARM9_OFFSET + 4] != REPLACEMENT:
        raise ValueError("BLZ round-trip lost the decoder patch")
    if len(rebuilt) > arm9_size:
        raise ValueError(f"compressed ARM9 grew {len(rebuilt) - arm9_size} bytes")
    struct.pack_into("<I", rom, 0x2C, len(rebuilt))
    rom[arm9_off : arm9_off + len(rebuilt)] = rebuilt
    struct.pack_into("<H", rom, 0x15E, crc16(rom[0:0x15E]))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(rom)
    result = {
        "source_rom": str(source.resolve()),
        "output_rom": str(output.resolve()),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "arm9_patch": {
            "ram": "0x02039CB0",
            "from": "ldrh r1,[r4]",
            "to": "mov r1,#0",
        },
        "arm9_stored_old": arm9_size,
        "arm9_stored_new": len(rebuilt),
    }
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.source, args.output, args.manifest), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
