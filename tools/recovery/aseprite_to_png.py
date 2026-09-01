#!/usr/bin/env python3
"""Export a normal-blend 32-bit Aseprite sprite without needing Aseprite.

Designed for single-frame localization handoff assets.  It retains the source
canvas exactly and supports raw/compressed image cels on visible layers.
"""

from __future__ import annotations

import argparse
import struct
import zlib
from pathlib import Path

from PIL import Image


def u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def i16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<h", data, offset)[0]


def u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    data = args.source.read_bytes()
    if len(data) < 128 or u16(data, 4) != 0xA5E0:
        raise ValueError("not an Aseprite .ase/.aseprite file")
    frames, width, height, depth = u16(data, 6), u16(data, 8), u16(data, 10), u16(data, 12)
    if frames != 1 or depth != 32:
        raise ValueError(f"expected one 32-bit frame, got {frames} frame(s), {depth}-bit color")
    frame_size = u32(data, 128)
    if u16(data, 132) != 0xF1FA:
        raise ValueError("invalid Aseprite frame header")
    chunks = u32(data, 140) or u16(data, 134)
    cursor, frame_end = 144, 128 + frame_size
    layers: dict[int, tuple[bool, int]] = {}
    cels: list[tuple[int, int, int, int, Image.Image]] = []
    for _ in range(chunks):
        size, kind = u32(data, cursor), u16(data, cursor + 4)
        if size < 6 or cursor + size > frame_end:
            raise ValueError("invalid Aseprite chunk")
        body = cursor + 6
        if kind == 0x2004:  # layer
            flags, blend, opacity = u16(data, body), u16(data, body + 10), data[body + 12]
            layers[len(layers)] = (bool(flags & 1), opacity if blend == 0 else 0)
        elif kind == 0x2005:  # cel
            layer, x, y, opacity, cel_type = u16(data, body), i16(data, body + 2), i16(data, body + 4), data[body + 6], u16(data, body + 7)
            if cel_type in (0, 2):
                image_width, image_height = u16(data, body + 16), u16(data, body + 18)
                pixels = data[body + 20:cursor + size]
                if cel_type == 2:
                    pixels = zlib.decompress(pixels)
                if len(pixels) != image_width * image_height * 4:
                    raise ValueError("unexpected cel pixel payload length")
                cels.append((layer, x, y, opacity, Image.frombytes("RGBA", (image_width, image_height), pixels)))
        cursor += size
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    for layer, x, y, opacity, image in cels:
        visible, layer_opacity = layers.get(layer, (True, 255))
        if not visible or not layer_opacity:
            continue
        if opacity != 255 or layer_opacity != 255:
            image = image.copy()
            image.putalpha(image.getchannel("A").point(lambda alpha: alpha * opacity * layer_opacity // (255 * 255)))
        canvas.alpha_composite(image, (x, y))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(args.output)
    print(f"{width}x{height} -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
