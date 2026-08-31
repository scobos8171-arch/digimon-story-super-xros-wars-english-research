#!/usr/bin/env python3
"""Extract Xros Wars NCGMOVIE tile-movie frames to editable PNGs."""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "work" / "DigimonNDSRomEditor-master"))
sys.path.insert(0, str(ROOT / "tools" / "rom_importer"))

from rom_research.nds_inventory import read_header, read_nitrofs  # noqa: E402
from rom_research.xros_pak import read_nitro_file  # noqa: E402
from rom_research.xros_sprite import parse_ncgr, parse_nclr  # noqa: E402
from nitro import parse_nscr, render_screen  # noqa: E402


def decompress_lz11(source: bytes) -> bytes:
    """Decode the Nintendo LZ11 blocks used by the NCGMOVIE container."""
    if len(source) < 4 or source[0] != 0x11:
        raise ValueError("expected an LZ11 block")
    target_size = source[1] | source[2] << 8 | source[3] << 16
    cursor = 4
    output = bytearray()
    while len(output) < target_size:
        if cursor >= len(source):
            raise ValueError("truncated LZ11 flags")
        flags = source[cursor]
        cursor += 1
        for bit in range(7, -1, -1):
            if len(output) >= target_size:
                break
            if not flags & (1 << bit):
                if cursor >= len(source):
                    raise ValueError("truncated LZ11 literal")
                output.append(source[cursor])
                cursor += 1
                continue
            if cursor >= len(source):
                raise ValueError("truncated LZ11 reference")
            first = source[cursor]
            cursor += 1
            high = first >> 4
            if high == 0:
                second, third = source[cursor : cursor + 2]
                cursor += 2
                length = ((first & 0x0F) << 4 | second >> 4) + 0x11
                distance = ((second & 0x0F) << 8 | third) + 1
            elif high == 1:
                second, third, fourth = source[cursor : cursor + 3]
                cursor += 3
                length = ((first & 0x0F) << 12 | second << 4 | third >> 4) + 0x111
                distance = ((third & 0x0F) << 8 | fourth) + 1
            else:
                second = source[cursor]
                cursor += 1
                length = high + 1
                distance = ((first & 0x0F) << 8 | second) + 1
            if distance > len(output):
                raise ValueError("invalid LZ11 back-reference")
            for _ in range(length):
                output.append(output[-distance])
                if len(output) >= target_size:
                    break
    return bytes(output)


def read_blocks(data: bytes) -> list[bytes]:
    count = struct.unpack_from("<I", data, 0)[0]
    records = [struct.unpack_from("<IIII", data, 0x10 + index * 16) for index in range(count)]
    blocks: list[bytes] = []
    for offset, stored_size, _unpacked_size, _flags in records:
        payload = data[offset : offset + stored_size]
        blocks.append(decompress_lz11(payload))
    return blocks


def make_contact_sheet(frames: list[Image.Image]) -> Image.Image:
    columns, thumb_size = 6, (128, 96)
    rows = (len(frames) + columns - 1) // columns
    sheet = Image.new("RGBA", (columns * thumb_size[0], rows * thumb_size[1]), (0, 0, 0, 255))
    for index, frame in enumerate(frames):
        thumbnail = frame.resize(thumb_size, Image.Resampling.NEAREST)
        sheet.alpha_composite(thumbnail, ((index % columns) * thumb_size[0], (index // columns) * thumb_size[1]))
    return sheet


def extract_movie(data: bytes, destination: Path) -> int:
    blocks = read_blocks(data)
    if len(blocks) < 3 or blocks[0][:4] != b"RCSN" or blocks[1][:4] != b"RLCN":
        raise ValueError("unexpected NCGMOVIE layout")
    screen_map = parse_nscr(blocks[0])
    palette = parse_nclr(blocks[1])
    frames: list[Image.Image] = []
    destination.mkdir(parents=True, exist_ok=True)
    for index, block in enumerate(blocks[2:]):
        if block[:4] != b"RGCN":
            raise ValueError(f"block {index + 2} is not an NCGR frame")
        frame = render_screen(parse_ncgr(block), palette, screen_map).crop((0, 0, 256, 192))
        frame.save(destination / f"frame_{index:03d}.png")
        frames.append(frame)
    make_contact_sheet(frames).save(destination / "contact_sheet.png")
    return len(frames)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    with args.rom.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        movies = [entry for entry in files if entry.path.startswith("NCGMOVIE/")]
        for entry in movies:
            count = extract_movie(read_nitro_file(handle, entry), args.output_dir / Path(entry.path).stem)
            print(f"{entry.path}: {count} frames")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
