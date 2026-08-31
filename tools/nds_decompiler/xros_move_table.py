"""Extract the Super Xros Wars 44-byte move table from an ARM9 image.

The field names in this module deliberately distinguish verified access patterns
from fields whose semantics are still under investigation.  It does not require
or distribute a ROM; callers point it at an ARM9 binary extracted from their own
cartridge dump.
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
import unicodedata
from pathlib import Path


ARM9_LOAD_ADDRESS = 0x02000000
DEFAULT_TABLE_ADDRESS = 0x020FC204
DEFAULT_RECORD_COUNT = 0x4FC
RECORD_SIZE = 0x2C
DEFAULT_NAME_FIRST = 3191


def _u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def _i16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<h", data, offset)[0]


def _u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def decode_effect_descriptor(value: int) -> dict[str, int]:
    """Decode the bit fields consumed by overlay-0 move helper functions."""
    return {
        "raw": value,
        "opcode": value & 0x7F,
        "magnitude_or_chance": (value >> 7) & 0x7F,
        "target_flags": (value >> 14) & 0x03,
        "power_or_parameter": (value >> 16) & 0xFFFF,
    }


def decode_record(record_id: int, record: bytes, display_name: str | None = None) -> dict:
    if len(record) != RECORD_SIZE:
        raise ValueError(f"record {record_id} has {len(record)} bytes, expected {RECORD_SIZE}")

    decoded = {
        "id": record_id,
        "record_address": f"0x{DEFAULT_TABLE_ADDRESS + record_id * RECORD_SIZE:08X}",
        "raw_hex": record.hex(),
        "field_0x00_u16": _u16(record, 0x00),
        "cost_base_i16": _i16(record, 0x02),
        "default_element_u8": record[0x04],
        "damage_class_u8": record[0x05],
        "targeting_u8": record[0x06],
        "field_0x07_u8": record[0x07],
        "field_0x08_u16": _u16(record, 0x08),
        "field_0x0A_u8": record[0x0A],
        "field_0x0B_u8": record[0x0B],
        "effect_descriptors": [
            decode_effect_descriptor(_u32(record, 0x0C + index * 4))
            for index in range(2)
        ],
        "field_0x14_u16": _u16(record, 0x14),
        "field_0x16_i16": _i16(record, 0x16),
        "field_0x18_i16": _i16(record, 0x18),
        "field_0x1A_i16": _i16(record, 0x1A),
        "linked_effect_index_i32": struct.unpack_from("<i", record, 0x1C)[0],
        "field_0x20_u32": _u32(record, 0x20),
        "field_0x24_u16": _u16(record, 0x24),
        "animation_id_0x26_i16": _i16(record, 0x26),
        "field_0x28_u16": _u16(record, 0x28),
        "resource_id_0x2A_i16": _i16(record, 0x2A),
    }
    if display_name is not None:
        decoded["display_name"] = display_name
    return decoded


def extract_records(
    arm9: bytes,
    table_address: int = DEFAULT_TABLE_ADDRESS,
    record_count: int = DEFAULT_RECORD_COUNT,
    names: list[str] | None = None,
) -> list[dict]:
    table_offset = table_address - ARM9_LOAD_ADDRESS
    table_size = record_count * RECORD_SIZE
    if table_offset < 0 or table_offset + table_size > len(arm9):
        raise ValueError(
            f"move table 0x{table_address:08X}+0x{table_size:X} is outside ARM9 image "
            f"({len(arm9)} bytes loaded at 0x{ARM9_LOAD_ADDRESS:08X})"
        )
    return [
        decode_record(
            record_id,
            arm9[
                table_offset + record_id * RECORD_SIZE:
                table_offset + (record_id + 1) * RECORD_SIZE
            ],
            names[record_id] if names is not None and record_id < len(names) else None,
        )
        for record_id in range(record_count)
    ]


def load_move_names(message_pak: Path, first_index: int, count: int) -> list[str]:
    # Support direct execution (``py tools/nds_decompiler/xros_move_table.py``),
    # where Python otherwise places only this script's directory on sys.path.
    repository_root = Path(__file__).resolve().parents[2]
    if str(repository_root) not in sys.path:
        sys.path.insert(0, str(repository_root))
    from tools.rom_importer.archives import XrosPak
    from tools.rom_importer.profiles import decode_message_name, parse_message_table

    strings = parse_message_table(XrosPak(message_pak.read_bytes()).unpack(0))
    if first_index < 0 or first_index + count > len(strings):
        raise ValueError(
            f"move-name range {first_index}..{first_index + count - 1} exceeds "
            f"message table containing {len(strings)} strings"
        )
    return [
        unicodedata.normalize("NFKC", decode_message_name(strings[index]))
        for index in range(first_index, first_index + count)
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("arm9", type=Path, help="ARM9 binary extracted from a locally owned ROM")
    parser.add_argument("output", type=Path, help="Destination JSON file")
    parser.add_argument("--table-address", type=lambda value: int(value, 0), default=DEFAULT_TABLE_ADDRESS)
    parser.add_argument("--count", type=lambda value: int(value, 0), default=DEFAULT_RECORD_COUNT)
    parser.add_argument("--message-pak", type=Path, help="Optional MSG/MESPAK00.PAK for localized names")
    parser.add_argument("--name-first", type=int, default=DEFAULT_NAME_FIRST)
    args = parser.parse_args()

    names = load_move_names(args.message_pak, args.name_first, args.count) if args.message_pak else None
    records = extract_records(args.arm9.read_bytes(), args.table_address, args.count, names)
    payload = {
        "schema": "xros_move_table_v1",
        "source_arm9": str(args.arm9),
        "table_address": f"0x{args.table_address:08X}",
        "record_size": RECORD_SIZE,
        "record_count": len(records),
        "localized_name_first_index": args.name_first if args.message_pak else None,
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Extracted {len(records)} move records to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
