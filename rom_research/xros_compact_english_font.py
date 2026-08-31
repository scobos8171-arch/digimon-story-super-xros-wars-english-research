"""Install compact Latin glyph cells into Xros's stock two-byte font.

Translated text remains encoded as full-width Shift-JIS, keeping the stable
Japanese renderer. Only the glyph bitmap and width tuple for each printable
English character are copied from Lost Evolution's English NFTR.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
from pathlib import Path

from PIL import Image

from rom_research.nds_inventory import read_header, read_nitrofs
from rom_research.nitrofs_patch import replace_nitrofs_files
from rom_research.xros_english_fonts import FONT_PATH, read_font_entries
from rom_research.xros_fullwidth_english import to_fullwidth
from rom_research.xros_pak import XrosPak, build_xros_pak, find_nitro_file, read_nitro_file


def sjis_code(character: str) -> int:
    encoded = character.encode("shift_jis")
    if len(encoded) == 1:
        return encoded[0]
    if len(encoded) == 2:
        return encoded[0] << 8 | encoded[1]
    raise ValueError(f"Unsupported Shift-JIS character: {character!r}")


def section_offsets(data: bytes, magic: bytes) -> list[int]:
    output: list[int] = []
    cursor = 0
    while True:
        cursor = data.find(magic, cursor)
        if cursor < 0:
            return output
        output.append(cursor)
        cursor += 4


def character_map(data: bytes) -> dict[int, int]:
    mapping: dict[int, int] = {}
    for offset in section_offsets(data, b"PAMC"):
        first, last, method = struct.unpack_from("<HHI", data, offset + 8)
        cursor = offset + 20
        if method == 0:
            first_glyph = struct.unpack_from("<H", data, cursor)[0]
            for code in range(first, last + 1):
                mapping[code] = first_glyph + code - first
        elif method == 1:
            for code in range(first, last + 1):
                glyph = struct.unpack_from("<H", data, cursor + 2 * (code - first))[0]
                if glyph != 0xFFFF:
                    mapping[code] = glyph
        elif method == 2:
            count = struct.unpack_from("<H", data, cursor)[0]
            cursor += 2
            for index in range(count):
                code, glyph = struct.unpack_from("<HH", data, cursor + 4 * index)
                mapping[code] = glyph
        else:
            raise ValueError(f"Unknown NFTR CMAP method {method}")
    return mapping


def glyph_layout(data: bytes) -> tuple[int, int, int, int, int]:
    cglp = section_offsets(data, b"PLGC")[0]
    cwdh = section_offsets(data, b"HDWC")[0]
    cell_size = struct.unpack_from("<H", data, cglp + 10)[0]
    first_glyph, last_glyph = struct.unpack_from("<HH", data, cwdh + 8)
    return cglp + 16, cell_size, cwdh + 16, first_glyph, last_glyph


def glyph_format(data: bytes) -> tuple[int, int, int]:
    """Return the NFTR cell width, height, and bits-per-pixel."""

    cglp = section_offsets(data, b"PLGC")[0]
    width, height = struct.unpack_from("<BB", data, cglp + 8)
    bpp = data[cglp + 14]
    if bpp not in (1, 2, 3, 4):
        raise ValueError(f"Unsupported NFTR bpp {bpp}")
    return width, height, bpp


def decode_cell(raw: bytes, width: int, height: int, bpp: int) -> Image.Image:
    """Decode one linear NFTR glyph cell to an 8-bit grayscale bitmap."""

    values: list[int] = []
    accumulator = 0
    available = 0
    for byte in raw:
        accumulator = (accumulator << 8) | byte
        available += 8
        while available >= bpp:
            available -= bpp
            values.append((accumulator >> available) & ((1 << bpp) - 1))
            accumulator &= (1 << available) - 1 if available else 0
    maximum = (1 << bpp) - 1
    image = Image.new("L", (width, height), 255)
    for index, value in enumerate(values[: width * height]):
        image.putpixel((index % width, index // width), 255 - round(value * 255 / maximum))
    return image


def encode_cell(image: Image.Image, bpp: int, cell_size: int) -> bytes:
    """Encode a grayscale bitmap into a fixed-size linear NFTR glyph cell."""

    maximum = (1 << bpp) - 1
    values = [
        max(0, min(maximum, round((255 - int(pixel)) * maximum / 255)))
        for pixel in image.getdata()
    ]
    output = bytearray()
    accumulator = 0
    available = 0
    for value in values:
        accumulator = (accumulator << bpp) | value
        available += bpp
        while available >= 8:
            available -= 8
            output.append((accumulator >> available) & 0xFF)
            accumulator &= (1 << available) - 1 if available else 0
    if available:
        output.append((accumulator << (8 - available)) & 0xFF)
    if len(output) > cell_size:
        raise ValueError(f"Encoded glyph is {len(output)} bytes; cell allows {cell_size}")
    output.extend(b"\0" * (cell_size - len(output)))
    return bytes(output)


def resample_cell(
    raw: bytes,
    donor_format: tuple[int, int, int],
    target_format: tuple[int, int, int],
    target_cell_size: int,
) -> bytes:
    """Fit a donor glyph into a differently sized target cell without antialiasing."""

    donor_width, donor_height, donor_bpp = donor_format
    target_width, target_height, target_bpp = target_format
    source = decode_cell(raw, donor_width, donor_height, donor_bpp)
    scale = min(target_width / donor_width, target_height / donor_height)
    resized_width = max(1, min(target_width, math.floor(donor_width * scale)))
    resized_height = max(1, min(target_height, math.floor(donor_height * scale)))
    source = source.resize((resized_width, resized_height), Image.Resampling.NEAREST)
    target = Image.new("L", (target_width, target_height), 255)
    target.paste(
        source,
        ((target_width - resized_width) // 2, target_height - resized_height),
    )
    return encode_cell(target, target_bpp, target_cell_size)


def build(
    source: Path,
    lost_english: Path,
    output: Path,
    manifest: Path,
    max_advance: int | None = None,
) -> dict[str, object]:
    with source.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        pak = XrosPak.from_bytes(
            read_nitro_file(handle, find_nitro_file(files, FONT_PATH))
        )
    entries = [pak.unpacked_data(index) for index in range(len(pak.entries))]
    donors = read_font_entries(lost_english)
    copied: list[dict[str, object]] = []
    patched_banks: list[int] = []
    skipped_banks: dict[int, str] = {}
    cell_sizes: dict[int, int] = {}
    for bank_index in range(min(len(entries), len(donors))):
        target = bytearray(entries[bank_index])
        donor = donors[bank_index]
        try:
            target_map = character_map(target)
            donor_map = character_map(donor)
            (
                target_cells,
                target_cell_size,
                target_widths,
                target_first,
                target_last,
            ) = glyph_layout(target)
            (
                donor_cells,
                donor_cell_size,
                donor_widths,
                donor_first,
                donor_last,
            ) = glyph_layout(donor)
            target_format = glyph_format(target)
            donor_format = glyph_format(donor)
        except (IndexError, struct.error, ValueError) as error:
            skipped_banks[bank_index] = str(error)
            continue
        bank_copies = 0
        for ascii_code in range(0x20, 0x7F):
            ascii_character = chr(ascii_code)
            target_character = to_fullwidth(ascii_character)
            target_code = sjis_code(target_character)
            donor_glyph = donor_map.get(ascii_code)
            target_glyph = target_map.get(target_code)
            if donor_glyph is None or target_glyph is None:
                continue
            if not donor_first <= donor_glyph <= donor_last:
                continue
            if not target_first <= target_glyph <= target_last:
                continue
            donor_cell = donor_cells + donor_glyph * donor_cell_size
            target_cell = target_cells + target_glyph * target_cell_size
            donor_raw = donor[donor_cell:donor_cell + donor_cell_size]
            if target_cell_size == donor_cell_size and target_format == donor_format:
                target[target_cell:target_cell + target_cell_size] = donor_raw
            else:
                target[target_cell:target_cell + target_cell_size] = resample_cell(
                    donor_raw,
                    donor_format,
                    target_format,
                    target_cell_size,
                )
            donor_width = donor_widths + 3 * (donor_glyph - donor_first)
            target_width = target_widths + 3 * (target_glyph - target_first)
            width = bytearray(donor[donor_width:donor_width + 3])
            if max_advance is not None:
                if ascii_character == " ":
                    width[:] = bytes((0, 1, 1))
                else:
                    width[0] = 0
                    width[1] = min(width[1], max_advance)
                    width[2] = min(width[2], max_advance)
            target[target_width:target_width + 3] = width
            copied.append(
                {
                    "bank": bank_index,
                    "ascii": ascii_character,
                    "target_code": f"0x{target_code:04X}",
                    "donor_glyph": donor_glyph,
                    "target_glyph": target_glyph,
                    "width": list(width),
                }
            )
            bank_copies += 1
        if bank_copies:
            entries[bank_index] = bytes(target)
            patched_banks.append(bank_index)
            cell_sizes[bank_index] = target_cell_size
    replacement = build_xros_pak(entries)
    rom = replace_nitrofs_files(source.read_bytes(), {FONT_PATH: replacement})
    output.write_bytes(rom)
    result = {
        "source": str(source),
        "output": str(output),
        "output_sha256": hashlib.sha256(rom).hexdigest(),
        "copied_glyphs": len(copied),
        "patched_banks": patched_banks,
        "skipped_banks": skipped_banks,
        "cell_sizes": cell_sizes,
        "max_advance": max_advance,
        "glyphs": copied,
    }
    manifest.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("lost_english", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--max-advance", type=int)
    args = parser.parse_args()
    result = build(
        args.source,
        args.lost_english,
        args.output,
        args.manifest,
        args.max_advance,
    )
    print(json.dumps({key: value for key, value in result.items() if key != "glyphs"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
