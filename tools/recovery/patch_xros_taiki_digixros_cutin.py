#!/usr/bin/env python3
"""Replace only Taiki's hidden 144x32 デジクロス!! OBJ strip."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [
    str(ROOT / "tools" / "recovery"),
    str(ROOT / "work" / "DigimonNDSRomEditor-master"),
]

from build_xros_custom_ui_rom import GRAPHICS_PATH, PALETTE_PATH, parse_nclr  # noqa: E402
from rom_research.nds_inventory import read_header, read_nitrofs  # noqa: E402
from rom_research.xros_pak import XrosPak, find_nitro_file, read_nitro_file  # noqa: E402


ENTRY = 1993
NCGR_DATA_OFFSET = 0x30
# Runtime OBJ boundary is 128 bytes.  The three visible objects begin at
# character names 90, 98, and 106 relative to entry 1993's load base.
FIRST_OBJECTS = ((2 * 128, 64, 32, 0), (10 * 128, 64, 32, 64), (18 * 128, 16, 32, 128))
DIGIXROS_OBJECTS = ((90 * 128, 64, 32, 0), (98 * 128, 64, 32, 64), (106 * 128, 16, 32, 128))
JOBS = ((FIRST_OBJECTS, "LET'S GO, TEAM!!", "first_shout"), (DIGIXROS_OBJECTS, "DIGIXROS!!", "digixros"))
FONT = Path(r"C:\Windows\Fonts\arialbi.ttf")


def make_art(text: str, palette: tuple[tuple[int, int, int, int], ...]) -> tuple[Image.Image, list[int]]:
    scale = 4
    large = Image.new("RGBA", (144 * scale, 32 * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(large)
    size = 27 * scale
    while size > 8:
        font = ImageFont.truetype(str(FONT), size)
        box = draw.textbbox((0, 0), text, font=font, stroke_width=3 * scale)
        if box[2] - box[0] <= 140 * scale and box[3] - box[1] <= 29 * scale:
            break
        size -= 1
    width, height = box[2] - box[0], box[3] - box[1]
    x = (large.width - width) // 2 - box[0]
    y = (large.height - height) // 2 - box[1]

    # Pale yellow flare, dark-red keyline, and hot-red face mirror the source.
    draw.text(
        (x, y), text, font=font,
        fill=palette[4], stroke_width=3 * scale, stroke_fill=palette[7],
    )
    draw.text(
        (x, y), text, font=font,
        fill=palette[4], stroke_width=1 * scale, stroke_fill=palette[1],
    )
    # Small white highlight gives the same glossy anime-callout finish.
    draw.text((x, y - scale), text, font=font, fill=palette[15])
    draw.text((x, y), text, font=font, fill=palette[4])

    art = large.resize((144, 32), Image.Resampling.LANCZOS)
    indices: list[int] = []
    for pixel in art.getdata():
        if pixel[3] < 24:
            indices.append(0)
            continue
        pr, pg, pb, pa = pixel
        best = min(
            range(1, 16),
            key=lambda index: (
                (palette[index][0] - pr) ** 2
                + (palette[index][1] - pg) ** 2
                + (palette[index][2] - pb) ** 2
                + (palette[index][3] - pa) ** 2 // 4
            ),
        )
        indices.append(best)
    indexed = Image.new("RGBA", art.size)
    indexed.putdata([palette[index] for index in indices])
    return indexed, indices


def encode_objects(tile_data: bytearray, indices: list[int], objects) -> None:
    for start, width, height, screen_x in objects:
        for y in range(height):
            for x_pair in range(width // 2):
                x = x_pair * 2
                left = indices[y * 144 + screen_x + x]
                right = indices[y * 144 + screen_x + x + 1]
                offset = (
                    start
                    + (y // 8) * (width // 8) * 32
                    + (x // 8) * 32
                    + (y % 8) * 4
                    + (x % 8) // 2
                )
                tile_data[offset] = left | (right << 4)


def render_objects(tile_data: bytes, palette: tuple[tuple[int, int, int, int], ...], objects) -> Image.Image:
    out = Image.new("RGBA", (144, 32), (0, 0, 0, 0))
    for start, width, height, screen_x in objects:
        for y in range(height):
            for x in range(width):
                offset = start + (y // 8) * (width // 8) * 32 + (x // 8) * 32 + (y % 8) * 4 + (x % 8) // 2
                value = tile_data[offset]
                out.putpixel((screen_x + x, y), palette[value >> 4 if x & 1 else value & 0xF])
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("qa", type=Path)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()

    original = args.source.read_bytes()
    rom = bytearray(original)
    with args.source.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        graphics_item = find_nitro_file(files, GRAPHICS_PATH)
        graphics = XrosPak.from_bytes(read_nitro_file(handle, graphics_item))
        palettes = XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, PALETTE_PATH)))

    slot = graphics.entries[ENTRY]
    if not slot.is_uncompressed:
        raise ValueError("Entry 1993 unexpectedly became compressed")
    entry = bytearray(graphics.unpacked_data(ENTRY))
    palette = parse_nclr(palettes.unpacked_data(ENTRY))
    tile_data = bytearray(entry[NCGR_DATA_OFFSET:])
    previews = []
    for objects, text, label in JOBS:
        before = render_objects(tile_data, palette, objects)
        art, indices = make_art(text, palette)
        encode_objects(tile_data, indices, objects)
        after = render_objects(tile_data, palette, objects)
        if after.tobytes() != art.tobytes():
            raise AssertionError(f"Encoded {label} strip does not match the approved artwork")
        previews.append((label, before, after))

    entry[NCGR_DATA_OFFSET:] = tile_data
    pak = bytearray(graphics.data)
    if len(entry) != slot.stored_size:
        raise AssertionError("Entry 1993 size changed")
    pak[slot.offset:slot.offset + slot.stored_size] = entry
    rom[graphics_item.offset:graphics_item.offset + graphics_item.size] = pak

    changed = [index for index, (a, b) in enumerate(zip(original, rom)) if a != b]
    allowed_ranges = []
    for objects, _text, _label in JOBS:
        start = graphics_item.offset + slot.offset + NCGR_DATA_OFFSET + objects[0][0]
        end = graphics_item.offset + slot.offset + NCGR_DATA_OFFSET + objects[-1][0] + 16 * 32
        allowed_ranges.append((start, end))
    if not changed or any(not any(start <= index < end for start, end in allowed_ranges) for index in changed):
        raise AssertionError("ROM changes escaped Taiki's dedicated lettering strip")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.qa.mkdir(parents=True, exist_ok=True)
    for label, before, after in previews:
        before.save(args.qa / f"before_{label}_144x32.png")
        after.save(args.qa / f"after_{label}_144x32.png")
        after.resize((576, 128), Image.Resampling.NEAREST).save(args.qa / f"after_{label}_4x.png")
    args.output.write_bytes(rom)
    report = {
        "source": str(args.source.resolve()),
        "output": str(args.output.resolve()),
        "source_sha256": hashlib.sha256(original).hexdigest(),
        "output_sha256": hashlib.sha256(rom).hexdigest(),
        "archive": GRAPHICS_PATH,
        "entry": ENTRY,
        "runtime_strip": "characters 90/98/106, 128-byte OBJ mapping",
        "replacements": {label: text for _objects, text, label in JOBS},
        "changed_rom_bytes": len(changed),
        "arm9_unchanged": original[0x4000:0x4000] == bytes(rom[0x4000:0x4000]),
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
