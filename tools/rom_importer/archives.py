from __future__ import annotations

import struct
from dataclasses import dataclass


def decompress_nintendo_rle(data: bytes) -> bytes:
    if len(data) < 4 or data[0] != 0x30:
        raise ValueError("Nintendo RLE stream is missing its 0x30 header")
    expected = int.from_bytes(data[1:4], "little")
    source = 4
    output = bytearray()
    while len(output) < expected:
        if source >= len(data):
            raise ValueError("Nintendo RLE stream ended early")
        control = data[source]
        source += 1
        if control & 0x80:
            length = (control & 0x7F) + 3
            if source >= len(data):
                raise ValueError("Nintendo RLE repeat byte is missing")
            output.extend([data[source]] * length)
            source += 1
        else:
            length = (control & 0x7F) + 1
            if source + length > len(data):
                raise ValueError("Nintendo RLE literal run is truncated")
            output.extend(data[source : source + length])
            source += length
    return bytes(output[:expected])


@dataclass(frozen=True)
class DuskPakEntry:
    offset: int
    size: int
    compressed: bool


class DuskPak:
    def __init__(self, data: bytes):
        self.data = data
        if len(data) < 4:
            raise ValueError("Dusk PAK header is truncated")
        count = struct.unpack_from("<I", data, 0)[0]
        table_end = 4 + count * 8
        if table_end > len(data):
            raise ValueError("Dusk PAK table extends beyond the archive")
        entries: list[DuskPakEntry] = []
        for index in range(count):
            offset, tagged = struct.unpack_from("<II", data, 4 + index * 8)
            size = tagged & 0x7FFFFFFF
            if offset < table_end or offset + size > len(data):
                raise ValueError(f"Dusk PAK entry {index} has an invalid range")
            entries.append(DuskPakEntry(offset, size, bool(tagged & 0x80000000)))
        self.entries = tuple(entries)

    def unpack(self, index: int) -> bytes:
        entry = self.entries[index]
        stored = self.data[entry.offset : entry.offset + entry.size]
        # A handful of Dusk archives tag the four-byte ``DMY!`` placeholder
        # as compressed even though it is deliberately raw.  The game treats
        # it as an empty/sentinel entry.  Require the actual Nintendo 0x30
        # signature before decoding so those valid placeholders survive.
        return (
            decompress_nintendo_rle(stored)
            if entry.compressed and stored[:1] == b"\x30"
            else stored
        )


@dataclass(frozen=True)
class XrosPakEntry:
    offset: int
    unpacked_size: int
    stored_size: int
    flags: int

    @property
    def uncompressed(self) -> bool:
        return bool(self.flags & 0x80000000)


def decompress_xros_lz(data: bytes, expected: int) -> bytes:
    if expected == 0:
        return b""
    if len(data) < 5:
        raise ValueError("Xros LZ stream is truncated")
    output = bytearray()
    history = bytearray(0x1000)
    source = 4
    while len(output) < expected:
        if source >= len(data):
            raise ValueError("Xros LZ stream ended early")
        flags = data[source]
        source += 1
        for _ in range(8):
            if len(output) >= expected:
                break
            if flags & 1:
                if source >= len(data):
                    raise ValueError("Xros LZ literal is truncated")
                value = data[source]
                source += 1
                history[len(output) & 0xFFF] = value
                output.append(value)
            else:
                if source + 1 >= len(data):
                    raise ValueError("Xros LZ back-reference is truncated")
                low, high = data[source], data[source + 1]
                source += 2
                length = (high & 0x0F) + 3
                start = low | ((high & 0xF0) << 4)
                for copy_index in range(length):
                    if len(output) >= expected:
                        break
                    value = history[(start + copy_index + 0x12) & 0xFFF]
                    history[len(output) & 0xFFF] = value
                    output.append(value)
            flags >>= 1
    return bytes(output)


class XrosPak:
    def __init__(self, data: bytes):
        self.data = data
        if len(data) < 0x10 or data[4:8] != b"2.01":
            raise ValueError("Unsupported Xros/Lost PAK header")
        count = struct.unpack_from("<I", data, 0)[0]
        table_end = 0x10 + count * 0x10
        if table_end > len(data):
            raise ValueError("Xros PAK table extends beyond the archive")
        entries: list[XrosPakEntry] = []
        for index in range(count):
            offset, unpacked, stored, flags = struct.unpack_from(
                "<IIII", data, 0x10 + index * 0x10
            )
            if offset < table_end or offset + stored > len(data):
                raise ValueError(f"Xros PAK entry {index} has an invalid range")
            entries.append(XrosPakEntry(offset, unpacked, stored, flags))
        self.entries = tuple(entries)

    def unpack(self, index: int) -> bytes:
        entry = self.entries[index]
        stored = self.data[entry.offset : entry.offset + entry.stored_size]
        if entry.uncompressed:
            if len(stored) < entry.unpacked_size:
                raise ValueError(f"Xros PAK entry {index} is shorter than declared")
            return stored[: entry.unpacked_size]
        return decompress_xros_lz(stored, entry.unpacked_size)
