"""Read the version 2.01 PAK archives used by Digimon Story: Xros Wars.

The module intentionally keeps extraction explicit: the audit command records
metadata and validates entries, while ``export`` writes only the requested
entry.  This makes it useful for a ROM-porting workflow without dumping a
game's entire asset set by accident.
"""

from __future__ import annotations

import argparse
import csv
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterable

from rom_research.nds_inventory import NitroFile, read_header, read_nitrofs


PAK_VERSION = b"2.01"
PAK_HEADER_SIZE = 0x10
PAK_ENTRY_SIZE = 0x10
UNCOMPRESSED_FLAG = 0x80000000


@dataclass(frozen=True)
class XrosPakEntry:
    index: int
    offset: int
    uncompressed_size: int
    stored_size: int
    flags: int

    @property
    def is_uncompressed(self) -> bool:
        return bool(self.flags & UNCOMPRESSED_FLAG)


@dataclass(frozen=True)
class XrosPak:
    entries: tuple[XrosPakEntry, ...]
    data: bytes

    @classmethod
    def from_bytes(cls, data: bytes) -> "XrosPak":
        if len(data) < PAK_HEADER_SIZE:
            raise ValueError("PAK is shorter than its header")
        file_count = struct.unpack_from("<I", data, 0)[0]
        if data[4:8] != PAK_VERSION:
            raise ValueError(
                f"Unsupported PAK version {data[4:8]!r}; expected {PAK_VERSION!r}"
            )
        table_end = PAK_HEADER_SIZE + file_count * PAK_ENTRY_SIZE
        if table_end > len(data):
            raise ValueError("PAK entry table extends past the end of the archive")

        entries: list[XrosPakEntry] = []
        for index in range(file_count):
            cursor = PAK_HEADER_SIZE + index * PAK_ENTRY_SIZE
            offset, unpacked, stored, flags = struct.unpack_from("<IIII", data, cursor)
            if offset < table_end or offset + stored > len(data):
                raise ValueError(
                    f"PAK entry {index} points outside the archive "
                    f"(offset=0x{offset:X}, size=0x{stored:X})"
                )
            entries.append(XrosPakEntry(index, offset, unpacked, stored, flags))
        return cls(tuple(entries), data)

    @classmethod
    def from_file(cls, path: Path) -> "XrosPak":
        return cls.from_bytes(path.read_bytes())

    def stored_data(self, entry_or_index: XrosPakEntry | int) -> bytes:
        entry = self._entry(entry_or_index)
        return self.data[entry.offset:entry.offset + entry.stored_size]

    def unpacked_data(self, entry_or_index: XrosPakEntry | int) -> bytes:
        entry = self._entry(entry_or_index)
        stored = self.stored_data(entry)
        if entry.is_uncompressed:
            if len(stored) < entry.uncompressed_size:
                raise ValueError(
                    f"Uncompressed entry {entry.index} is shorter than declared"
                )
            return stored[:entry.uncompressed_size]
        return decompress_xros_lz(stored, entry.uncompressed_size)

    def _entry(self, entry_or_index: XrosPakEntry | int) -> XrosPakEntry:
        if isinstance(entry_or_index, XrosPakEntry):
            return entry_or_index
        try:
            return self.entries[entry_or_index]
        except IndexError as exc:
            raise IndexError(f"PAK entry index {entry_or_index} is out of range") from exc


def build_xros_pak(
    entries: Iterable[bytes],
    *,
    alignment: int = 0x10,
) -> bytes:
    """Build a valid 2.01 archive with uncompressed entries.

    The game explicitly supports uncompressed members.  Using that storage
    mode keeps generated archives deterministic and avoids introducing a
    second compressor while the research tools are still evolving.
    """

    if alignment <= 0 or alignment & (alignment - 1):
        raise ValueError("alignment must be a positive power of two")
    entry_data = tuple(bytes(entry) for entry in entries)
    table_end = PAK_HEADER_SIZE + len(entry_data) * PAK_ENTRY_SIZE
    cursor = (table_end + alignment - 1) & ~(alignment - 1)
    output = bytearray(cursor)
    struct.pack_into("<I", output, 0, len(entry_data))
    output[4:8] = PAK_VERSION
    for index, data in enumerate(entry_data):
        offset = cursor
        output.extend(data)
        cursor += len(data)
        aligned = (cursor + alignment - 1) & ~(alignment - 1)
        output.extend(b"\0" * (aligned - cursor))
        cursor = aligned
        struct.pack_into(
            "<IIII",
            output,
            PAK_HEADER_SIZE + index * PAK_ENTRY_SIZE,
            offset,
            len(data),
            len(data),
            UNCOMPRESSED_FLAG,
        )
    return bytes(output)


def decompress_xros_lz(data: bytes, expected_size: int) -> bytes:
    """Decompress the game's 4 KiB sliding-window LZ stream."""

    if expected_size == 0:
        return b""
    if len(data) < 5:
        raise ValueError("Compressed entry is too short")

    output = bytearray()
    history = bytearray(0x1000)
    input_pos = 4  # The stream begins with an internal compressed-size field.

    while len(output) < expected_size:
        if input_pos >= len(data):
            raise ValueError(
                f"Compressed stream ended after {len(output)} of {expected_size} bytes"
            )
        bits = data[input_pos]
        input_pos += 1
        for _ in range(8):
            if len(output) >= expected_size:
                break
            if bits & 1:
                if input_pos >= len(data):
                    raise ValueError("Compressed stream ended in a literal")
                value = data[input_pos]
                input_pos += 1
                history[len(output) & 0xFFF] = value
                output.append(value)
            else:
                if input_pos + 1 >= len(data):
                    raise ValueError("Compressed stream ended in a back-reference")
                low = data[input_pos]
                high = data[input_pos + 1]
                input_pos += 2
                length = (high & 0x0F) + 3
                start = low | ((high & 0xF0) << 4)
                for copy_index in range(length):
                    if len(output) >= expected_size:
                        break
                    value = history[(start + copy_index + 0x12) & 0xFFF]
                    history[len(output) & 0xFFF] = value
                    output.append(value)
            bits >>= 1
    return bytes(output)


def compress_xros_lz(data: bytes) -> bytes:
    """Compress bytes for the game's 4 KiB Xros LZ decoder.

    The stream uses LSB-first flag bytes, 1 for a literal and 0 for a
    3..18-byte match.  Back-reference positions address the decoder's ring
    buffer with its native +0x12 bias.  A small hash chain keeps this usable
    for rebuilding the large sprite archives while producing deterministic
    output.
    """

    source = bytes(data)
    if not source:
        return struct.pack("<I", 4)

    chains: dict[bytes, list[int]] = {}
    output = bytearray(b"\0\0\0\0")
    position = 0

    while position < len(source):
        flag_at = len(output)
        output.append(0)
        flags = 0
        for bit in range(8):
            if position >= len(source):
                break

            best_start = -1
            best_length = 0
            if position + 3 <= len(source):
                key = source[position:position + 3]
                candidates = chains.get(key, ())
                minimum = max(0, position - 0x1000)
                for candidate in reversed(candidates):
                    if candidate < minimum:
                        break
                    length = 3
                    maximum = min(18, len(source) - position)
                    while length < maximum:
                        # Overlapping matches repeat bytes already present in
                        # the match, exactly like the decoder's ring buffer.
                        expected = source[candidate + (length % (position - candidate))]
                        if source[position + length] != expected:
                            break
                        length += 1
                    if length > best_length:
                        best_start, best_length = candidate, length
                        if length == maximum:
                            break

            if best_length >= 3:
                ring_position = best_start & 0xFFF
                encoded_start = (ring_position - 0x12) & 0xFFF
                output.append(encoded_start & 0xFF)
                output.append(((encoded_start >> 8) << 4) | (best_length - 3))
                consumed = best_length
            else:
                flags |= 1 << bit
                output.append(source[position])
                consumed = 1

            end = min(len(source), position + consumed)
            for added in range(position, end):
                if added + 3 <= len(source):
                    key = source[added:added + 3]
                    bucket = chains.setdefault(key, [])
                    bucket.append(added)
                    cutoff = added - 0x1000
                    while bucket and bucket[0] < cutoff:
                        bucket.pop(0)
            position = end
        output[flag_at] = flags

    struct.pack_into("<I", output, 0, len(output))
    return bytes(output)


def find_nitro_file(files: Iterable[NitroFile], requested_path: str) -> NitroFile:
    normalized = requested_path.replace("\\", "/").casefold()
    matches = [
        item
        for item in files
        if item.path.replace("\\", "/").casefold() == normalized
        or Path(item.path).name.casefold() == Path(normalized).name.casefold()
    ]
    if not matches:
        raise FileNotFoundError(f"NitroFS file not found: {requested_path}")
    if len(matches) > 1:
        joined = ", ".join(item.path for item in matches)
        raise ValueError(f"Archive name is ambiguous: {joined}")
    return matches[0]


def read_nitro_file(handle: BinaryIO, item: NitroFile) -> bytes:
    handle.seek(item.offset)
    data = handle.read(item.size)
    if len(data) != item.size:
        raise ValueError(f"Could not read all of {item.path}")
    return data


def identify_entry(data: bytes) -> str:
    signatures = {
        b"RGCN": "NCGR",
        b"RLCN": "NCLR",
        b"RECN": "NCER",
        b"RNAN": "NANR",
        b"RCSN": "NSCR",
        b"BMD0": "NSBMD",
        b"BTX0": "NSBTX",
    }
    for signature, label in signatures.items():
        if data.startswith(signature):
            return label
    if not data:
        return "empty"
    return data[:4].hex(" ").upper()


def audit_archive(
    rom_handle: BinaryIO,
    item: NitroFile,
    output_path: Path,
) -> dict[str, int | str]:
    archive = XrosPak.from_bytes(read_nitro_file(rom_handle, item))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    compressed = 0
    failures = 0
    formats: dict[str, int] = {}
    with output_path.open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(
            [
                "entry",
                "archive_offset",
                "uncompressed_size",
                "stored_size",
                "storage",
                "flags",
                "detected_format",
                "validation",
            ]
        )
        for entry in archive.entries:
            if not entry.is_uncompressed:
                compressed += 1
            validation = "ok"
            try:
                unpacked = archive.unpacked_data(entry)
                detected = identify_entry(unpacked)
                formats[detected] = formats.get(detected, 0) + 1
            except ValueError as exc:
                failures += 1
                detected = ""
                validation = str(exc)
            writer.writerow(
                [
                    entry.index,
                    f"0x{entry.offset:08X}",
                    entry.uncompressed_size,
                    entry.stored_size,
                    "uncompressed" if entry.is_uncompressed else "Xros LZ",
                    f"0x{entry.flags:08X}",
                    detected,
                    validation,
                ]
            )
    return {
        "archive": item.path,
        "entries": len(archive.entries),
        "compressed": compressed,
        "uncompressed": len(archive.entries) - compressed,
        "failures": failures,
        "formats": ", ".join(
            f"{name}:{count}" for name, count in sorted(formats.items())
        ),
    }


def audit_rom(rom_path: Path, output_dir: Path, archive_names: list[str]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    summaries: list[dict[str, int | str]] = []
    with rom_path.open("rb") as handle:
        header = read_header(handle)
        files = read_nitrofs(handle, header)
        selected = (
            [find_nitro_file(files, name) for name in archive_names]
            if archive_names
            else [
                item
                for item in files
                if item.path.upper().endswith(".PAK")
                and _is_xros_pak(handle, item)
            ]
        )
        for item in selected:
            safe_name = Path(item.path).name.replace(".", "_")
            summaries.append(
                audit_archive(handle, item, output_dir / f"{safe_name} entries.csv")
            )

    summary_path = output_dir / "Xros PAK audit summary.csv"
    with summary_path.open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(
            output,
            fieldnames=[
                "archive",
                "entries",
                "compressed",
                "uncompressed",
                "failures",
                "formats",
            ],
        )
        writer.writeheader()
        writer.writerows(summaries)
    return summary_path


def _is_xros_pak(handle: BinaryIO, item: NitroFile) -> bool:
    handle.seek(item.offset + 4)
    return handle.read(4) == PAK_VERSION


def export_entry(
    rom_path: Path,
    archive_name: str,
    entry_index: int,
    output_path: Path,
) -> None:
    with rom_path.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        item = find_nitro_file(files, archive_name)
        archive = XrosPak.from_bytes(read_nitro_file(handle, item))
        data = archive.unpacked_data(entry_index)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(data)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    audit = subparsers.add_parser("audit", help="validate archives and write CSV indexes")
    audit.add_argument("rom", type=Path)
    audit.add_argument("output_dir", type=Path)
    audit.add_argument(
        "--archive",
        action="append",
        default=[],
        help="NitroFS path or basename; repeat to audit selected archives",
    )

    export = subparsers.add_parser("export", help="export one decompressed PAK entry")
    export.add_argument("rom", type=Path)
    export.add_argument("archive")
    export.add_argument("entry", type=int)
    export.add_argument("output", type=Path)

    args = parser.parse_args()
    if args.command == "audit":
        summary = audit_rom(args.rom, args.output_dir, args.archive)
        print(f"PAK audit written to {summary}")
    else:
        export_entry(args.rom, args.archive, args.entry, args.output)
        print(f"Entry {args.entry} written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
