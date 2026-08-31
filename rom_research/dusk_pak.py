"""Read and rebuild the compact PAK archives used by Dawn and Dusk."""

from __future__ import annotations

import struct
from dataclasses import dataclass


COMPRESSED_FLAG = 0x80000000
SIZE_MASK = 0x7FFFFFFF


@dataclass(frozen=True)
class DuskPakEntry:
    index: int
    offset: int
    stored_size: int
    compressed: bool


@dataclass(frozen=True)
class DuskPak:
    entries: tuple[DuskPakEntry, ...]
    data: bytes

    @classmethod
    def from_bytes(cls, data: bytes) -> "DuskPak":
        if len(data) < 4:
            raise ValueError("PAK is shorter than its header")
        count = struct.unpack_from("<I", data, 0)[0]
        table_end = 4 + count * 8
        if table_end > len(data):
            raise ValueError("PAK entry table extends past the archive")
        entries: list[DuskPakEntry] = []
        for index in range(count):
            offset, tagged_size = struct.unpack_from("<II", data, 4 + index * 8)
            stored_size = tagged_size & SIZE_MASK
            if offset < table_end or offset + stored_size > len(data):
                raise ValueError(
                    f"PAK entry {index} points outside the archive "
                    f"(offset=0x{offset:X}, size=0x{stored_size:X})"
                )
            entries.append(
                DuskPakEntry(
                    index=index,
                    offset=offset,
                    stored_size=stored_size,
                    compressed=bool(tagged_size & COMPRESSED_FLAG),
                )
            )
        return cls(tuple(entries), data)

    def stored_data(self, entry_or_index: DuskPakEntry | int) -> bytes:
        entry = self._entry(entry_or_index)
        return self.data[entry.offset:entry.offset + entry.stored_size]

    def unpacked_data(self, entry_or_index: DuskPakEntry | int) -> bytes:
        entry = self._entry(entry_or_index)
        data = self.stored_data(entry)
        return decompress_nintendo_rle(data) if entry.compressed else data

    def rebuild(
        self,
        replacements: dict[int, bytes],
        *,
        appended_entries: tuple[tuple[bytes, bool], ...] = (),
    ) -> bytes:
        """Rebuild the archive and optionally append new entries.

        ``replacements`` contains unpacked entry data and is recompressed with
        Nintendo RLE. ``appended_entries`` is a tuple of
        ``(unpacked_data, compress)`` pairs.  Keeping the compression choice
        explicit is important for BTCHR.PAK: each five-entry sprite group has
        a small metadata record that is normally stored verbatim, followed by
        four compressed Nitro graphics resources.
        """

        invalid = sorted(set(replacements) - set(range(len(self.entries))))
        if invalid:
            raise IndexError(f"Replacement entry indices are out of range: {invalid}")
        stored_entries: list[tuple[bytes, bool]] = []
        for entry in self.entries:
            if entry.index in replacements:
                stored_entries.append(
                    (compress_nintendo_rle(replacements[entry.index]), True)
                )
            else:
                stored_entries.append((self.stored_data(entry), entry.compressed))
        for unpacked, compressed in appended_entries:
            stored = compress_nintendo_rle(unpacked) if compressed else bytes(unpacked)
            stored_entries.append((stored, compressed))

        data_offset = 4 + len(stored_entries) * 8
        table = bytearray(struct.pack("<I", len(stored_entries)))
        payload = bytearray()
        for stored, compressed in stored_entries:
            tagged_size = len(stored) | (COMPRESSED_FLAG if compressed else 0)
            table.extend(struct.pack("<II", data_offset + len(payload), tagged_size))
            payload.extend(stored)
        return bytes(table + payload)

    def _entry(self, entry_or_index: DuskPakEntry | int) -> DuskPakEntry:
        if isinstance(entry_or_index, DuskPakEntry):
            return entry_or_index
        try:
            return self.entries[entry_or_index]
        except IndexError as exc:
            raise IndexError(f"PAK entry index {entry_or_index} is out of range") from exc


def decompress_nintendo_rle(data: bytes) -> bytes:
    """Decompress Nintendo DS type-0x30 run-length encoding."""

    if len(data) < 4 or data[0] != 0x30:
        raise ValueError("Compressed PAK entry does not have an RLE 0x30 header")
    expected_size = int.from_bytes(data[1:4], "little")
    input_pos = 4
    output = bytearray()
    while len(output) < expected_size:
        if input_pos >= len(data):
            raise ValueError(
                f"RLE stream ended after {len(output)} of {expected_size} bytes"
            )
        control = data[input_pos]
        input_pos += 1
        if control & 0x80:
            length = (control & 0x7F) + 3
            if input_pos >= len(data):
                raise ValueError("RLE stream ended before its repeated byte")
            output.extend([data[input_pos]] * length)
            input_pos += 1
        else:
            length = (control & 0x7F) + 1
            if input_pos + length > len(data):
                raise ValueError("RLE stream ended during a literal run")
            output.extend(data[input_pos:input_pos + length])
            input_pos += length
        if len(output) > expected_size:
            del output[expected_size:]
    return bytes(output)


def compress_nintendo_rle(data: bytes) -> bytes:
    """Greedy Nintendo DS RLE encoder compatible with type-0x30 streams."""

    if len(data) > 0xFFFFFF:
        raise ValueError("Nintendo RLE's 24-bit size field cannot hold this entry")
    output = bytearray(b"\x30" + len(data).to_bytes(3, "little"))
    position = 0

    def run_length(start: int) -> int:
        end = min(len(data), start + 130)
        cursor = start + 1
        while cursor < end and data[cursor] == data[start]:
            cursor += 1
        return cursor - start

    while position < len(data):
        repeated = run_length(position)
        if repeated >= 3:
            output.append(0x80 | (repeated - 3))
            output.append(data[position])
            position += repeated
            continue

        literal_start = position
        position += repeated
        while position < len(data) and position - literal_start < 128:
            next_run = run_length(position)
            if next_run >= 3:
                break
            position += min(next_run, 128 - (position - literal_start))
        length = position - literal_start
        output.append(length - 1)
        output.extend(data[literal_start:position])
    return bytes(output)
