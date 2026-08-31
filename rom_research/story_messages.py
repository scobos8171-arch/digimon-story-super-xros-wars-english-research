"""Inspect pointer-table messages used by Lost Evolution and Xros Wars."""

from __future__ import annotations

import argparse
import csv
import struct
from dataclasses import dataclass
from pathlib import Path

from rom_research.nds_inventory import read_header, read_nitrofs
from rom_research.xros_pak import XrosPak, read_nitro_file


MESSAGE_ARCHIVES = tuple(f"MSG/MESPAK{index:02d}.PAK" for index in range(6))


@dataclass(frozen=True)
class StoryMessage:
    archive: str
    pak_entry: int
    string_index: int
    offset: int
    raw: bytes
    text: str


def parse_message_table(
    data: bytes,
    *,
    encoding: str,
) -> tuple[tuple[int, ...], tuple[bytes, ...]]:
    if len(data) < 8:
        raise ValueError("Message table is shorter than its header")
    count = struct.unpack_from("<I", data, 4)[0]
    table_end = 8 + count * 4
    if count > 100_000 or table_end > len(data):
        raise ValueError("Message pointer table is invalid")
    offsets = struct.unpack_from(f"<{count}I", data, 8) if count else ()
    strings: list[bytes] = []
    previous = table_end
    for index, offset in enumerate(offsets):
        if offset < table_end or offset >= len(data):
            raise ValueError(f"Message {index} offset 0x{offset:X} is invalid")
        if offset < previous:
            raise ValueError("Message offsets are not ordered")
        next_offset = offsets[index + 1] if index + 1 < count else len(data)
        if next_offset < offset or next_offset > len(data):
            raise ValueError(f"Message {index} end offset is invalid")
        raw = data[offset:next_offset].rstrip(b"\0")
        strings.append(raw)
        previous = offset
    return tuple(offsets), tuple(strings)


def build_message_table(
    original: bytes,
    strings: list[bytes] | tuple[bytes, ...],
    *,
    alignment: int = 4,
) -> bytes:
    """Rebuild a pointer-table message entry while preserving its first word."""

    if len(original) < 8:
        raise ValueError("Original message table is shorter than its header")
    if alignment <= 0 or alignment & (alignment - 1):
        raise ValueError("alignment must be a positive power of two")
    count = len(strings)
    cursor = 8 + count * 4
    cursor = (cursor + alignment - 1) & ~(alignment - 1)
    output = bytearray(cursor)
    output[:4] = original[:4]
    struct.pack_into("<I", output, 4, count)
    for index, raw in enumerate(strings):
        struct.pack_into("<I", output, 8 + index * 4, cursor)
        output.extend(raw)
        output.append(0)
        cursor = len(output)
        aligned = (cursor + alignment - 1) & ~(alignment - 1)
        output.extend(b"\0" * (aligned - cursor))
        cursor = aligned
    return bytes(output)


def dump_messages(
    rom_path: Path,
    output_csv: Path,
    *,
    encoding: str,
) -> dict[str, int]:
    with rom_path.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        file_by_path = {
            item.path.replace("\\", "/").casefold(): item for item in files
        }
        archives = {
            archive_name: XrosPak.from_bytes(
                read_nitro_file(
                    handle,
                    file_by_path[archive_name.casefold()],
                )
            )
            for archive_name in MESSAGE_ARCHIVES
        }

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    message_count = 0
    table_count = 0
    with output_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            (
                "archive",
                "pak_entry",
                "string_index",
                "offset",
                "text",
                "raw_hex",
            )
        )
        for archive_name, archive in archives.items():
            for pak_entry in range(len(archive.entries)):
                data = archive.unpacked_data(pak_entry)
                try:
                    offsets, strings = parse_message_table(data, encoding=encoding)
                except ValueError:
                    continue
                table_count += 1
                for string_index, (offset, raw) in enumerate(zip(offsets, strings)):
                    text = raw.decode(encoding, errors="replace")
                    writer.writerow(
                        (
                            archive_name,
                            pak_entry,
                            string_index,
                            f"0x{offset:X}",
                            text.replace("\r", "\\r").replace("\n", "\\n"),
                            raw.hex(" "),
                        )
                    )
                    message_count += 1
    return {"tables": table_count, "messages": message_count}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("output_csv", type=Path)
    parser.add_argument("--encoding", default="shift_jis")
    args = parser.parse_args()
    result = dump_messages(args.rom, args.output_csv, encoding=args.encoding)
    print(
        f"Dumped {result['messages']} messages from {result['tables']} tables "
        f"to {args.output_csv}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
