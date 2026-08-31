"""Nintendo DS backwards-LZ (BLZ) executable decompression."""

from __future__ import annotations

from collections import defaultdict, deque
import struct


def decompress_blz(data: bytes) -> bytes:
    """Decompress a DS ARM executable, or return it unchanged if not BLZ."""

    if len(data) < 8:
        return data
    compressed_length = int.from_bytes(data[-8:-5], "little")
    header_length = data[-5]
    added_length = int.from_bytes(data[-4:], "little")
    if (
        header_length < 8
        or compressed_length < header_length
        or compressed_length > len(data)
        or added_length == 0
    ):
        return data

    prefix_length = len(data) - compressed_length
    output = bytearray(data)
    output.extend(b"\0" * added_length)
    source_cursor = len(data) - header_length
    output_cursor = len(output)

    while output_cursor > prefix_length:
        if source_cursor <= prefix_length:
            raise ValueError("BLZ stream ended before decompression completed")
        source_cursor -= 1
        flags = data[source_cursor]
        for mask in (0x80, 0x40, 0x20, 0x10, 0x08, 0x04, 0x02, 0x01):
            if output_cursor <= prefix_length:
                break
            if flags & mask:
                if source_cursor - 2 < prefix_length:
                    raise ValueError("BLZ stream ended in a back-reference")
                source_cursor -= 2
                value = data[source_cursor] | (data[source_cursor + 1] << 8)
                length = (value >> 12) + 3
                displacement = (value & 0xFFF) + 3
                for _ in range(length):
                    if output_cursor <= prefix_length:
                        break
                    output_cursor -= 1
                    source_index = output_cursor + displacement
                    if source_index >= len(output):
                        raise ValueError("BLZ back-reference points outside output")
                    output[output_cursor] = output[source_index]
            else:
                if source_cursor <= prefix_length:
                    raise ValueError("BLZ stream ended in a literal")
                source_cursor -= 1
                output_cursor -= 1
                output[output_cursor] = data[source_cursor]
    return bytes(output)


def compress_blz(data: bytes, *, arm9: bool = False) -> bytes:
    """Compress executable data using deterministic backwards LZ.

    ARM9 executables keep their first 0x4000 bytes uncompressed, matching the
    convention used by Nintendo's SDK and the original game.
    """

    prefix_length = 0x4000 if arm9 else 0
    if len(data) <= prefix_length:
        return data
    prefix = data[:prefix_length]
    source = data[prefix_length:]
    positions: dict[bytes, deque[int]] = defaultdict(deque)
    tokens: list[tuple[bool, bytes]] = []
    cursor = len(source)

    def add_end(end: int) -> None:
        if end >= 3:
            key = source[end - 3:end]
            bucket = positions[key]
            bucket.appendleft(end)

    while cursor:
        best_length = 0
        best_displacement = 0
        if cursor >= 3:
            key = source[cursor - 3:cursor]
            bucket = positions.get(key, ())
            while bucket and bucket[-1] - cursor > 0x1002:
                bucket.pop()
            for candidate_end in bucket:
                displacement = candidate_end - cursor
                if displacement < 3:
                    continue
                if displacement > 0x1002:
                    break
                length = 3
                while (
                    length < 18
                    and cursor - length - 1 >= 0
                    and cursor - length - 1 + displacement < len(source)
                    and source[cursor - length - 1]
                    == source[cursor - length - 1 + displacement]
                ):
                    length += 1
                if length > best_length:
                    best_length = length
                    best_displacement = displacement
                    if length == 18:
                        break
        old_cursor = cursor
        if best_length >= 3:
            value = ((best_length - 3) << 12) | (best_displacement - 3)
            tokens.append((True, bytes((value >> 8, value & 0xFF))))
            cursor -= best_length
        else:
            tokens.append((False, bytes((source[cursor - 1],))))
            cursor -= 1
        for end in range(old_cursor, cursor, -1):
            add_end(end)

    read_stream = bytearray()
    for group_start in range(0, len(tokens), 8):
        group = tokens[group_start:group_start + 8]
        flags = 0
        for index, (compressed, _payload) in enumerate(group):
            if compressed:
                flags |= 0x80 >> index
        read_stream.append(flags)
        for _compressed, payload in group:
            read_stream.extend(payload)
    body = bytearray(reversed(read_stream))
    padding = 0
    while (len(prefix) + len(body) + 8) % 4:
        body.append(0xFF)
        padding += 1
    header_length = 8 + padding
    compressed_length = len(body) + 8
    output_size = len(prefix) + compressed_length
    extra_size = len(data) - output_size
    if extra_size <= 0:
        raise ValueError("BLZ output is not smaller than its input")
    footer = bytearray(8)
    footer[:3] = compressed_length.to_bytes(3, "little")
    footer[3] = header_length
    struct.pack_into("<I", footer, 4, extra_size)
    return bytes(prefix + body + footer)
