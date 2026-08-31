"""Build a size-safe English Xros Wars ROM using one-byte Latin text.

Xros accepts single-byte Shift-JIS/ASCII characters, but its Japanese NFTR
fonts do not provide the complete Latin glyph map.  This builder narrows the
localized full-width Latin text back to ASCII and installs the corresponding
English Lost Evolution font banks.  Every rebuilt message archive is checked
against the retail ARM9 work-buffer maxima before the ROM is written.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from rom_research.nds_inventory import read_header, read_nitrofs
from rom_research.nitrofs_patch import replace_nitrofs_files
from rom_research.story_messages import (
    MESSAGE_ARCHIVES,
    build_message_table,
    parse_message_table,
)
from rom_research.xros_english_fonts import FONT_PATH, read_font_entries
from rom_research.xros_message_buffers import RETAIL_MAXIMA
from rom_research.xros_pak import (
    XrosPak,
    build_xros_pak,
    find_nitro_file,
    read_nitro_file,
)


PUNCTUATION_TO_ASCII = {
    "\u3000": " ",
    "\u201d": '"',
    "\u2019": "'",
    "\u2212": "-",
    "\u301c": "~",
}


def to_ascii_width(text: str) -> str:
    output: list[str] = []
    for character in text:
        code = ord(character)
        if character in PUNCTUATION_TO_ASCII:
            output.append(PUNCTUATION_TO_ASCII[character])
        elif 0xFF01 <= code <= 0xFF5E:
            output.append(chr(code - 0xFEE0))
        else:
            output.append(character)
    return "".join(output)


def _font_replacement(source: Path, lost_english: Path) -> bytes:
    xros = read_font_entries(source)
    english = read_font_entries(lost_english)
    if len(xros) != 9 or len(english) != 8:
        raise ValueError(
            f"Unexpected font counts: Xros={len(xros)}, Lost English={len(english)}"
        )
    merged = list(xros)
    for index in range(8):
        ported = bytearray(english[index])
        # Preserve Xros's game-specific fallback glyph index.
        ported[0x1A:0x1C] = xros[index][0x1A:0x1C]
        merged[index] = bytes(ported)
    return build_xros_pak(merged)


def build(
    source: Path,
    lost_english: Path,
    output: Path,
    manifest_path: Path,
) -> dict[str, object]:
    replacements: dict[str, bytes] = {
        FONT_PATH: _font_replacement(source, lost_english)
    }
    converted_strings = 0
    archive_maxima: list[int] = []
    with source.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        for archive_name in MESSAGE_ARCHIVES:
            pak = XrosPak.from_bytes(
                read_nitro_file(handle, find_nitro_file(files, archive_name))
            )
            entries: list[bytes] = []
            for entry_index in range(len(pak.entries)):
                original = pak.unpacked_data(entry_index)
                try:
                    _offsets, strings = parse_message_table(
                        original, encoding="shift_jis"
                    )
                except ValueError:
                    entries.append(original)
                    continue
                patched: list[bytes] = []
                for raw in strings:
                    try:
                        text = raw.decode("shift_jis")
                        narrowed = to_ascii_width(text).encode("shift_jis")
                    except (UnicodeDecodeError, UnicodeEncodeError):
                        narrowed = raw
                    patched.append(narrowed)
                    if narrowed != raw:
                        converted_strings += 1
                entries.append(build_message_table(original, patched))
            maximum = max(len(entry) for entry in entries)
            archive_index = len(archive_maxima)
            if maximum > RETAIL_MAXIMA[archive_index]:
                raise ValueError(
                    f"{archive_name} needs 0x{maximum:X} bytes but the retail "
                    f"buffer is only 0x{RETAIL_MAXIMA[archive_index]:X}"
                )
            archive_maxima.append(maximum)
            replacements[archive_name] = build_xros_pak(entries)

    source_data = source.read_bytes()
    rom = replace_nitrofs_files(source_data, replacements)
    # This fix must stay data-only. The ARM9 and overlays are intentionally
    # untouched so battle mechanics remain cartridge-identical.
    with source.open("rb") as handle:
        source_header = read_header(handle)
    arm9_offset = int(source_header["arm9_offset"])
    arm9_size = int(source_header["arm9_size"])
    if rom[arm9_offset:arm9_offset + arm9_size] != source_data[
        arm9_offset:arm9_offset + arm9_size
    ]:
        raise AssertionError("ARM9 changed during a data-only localization build")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(rom)
    result: dict[str, object] = {
        "source_rom": str(source.resolve()),
        "lost_english_font_donor": str(lost_english.resolve()),
        "output_rom": str(output.resolve()),
        "source_sha256": hashlib.sha256(source_data).hexdigest(),
        "output_sha256": hashlib.sha256(rom).hexdigest(),
        "converted_strings": converted_strings,
        "message_archives": list(MESSAGE_ARCHIVES),
        "archive_maxima": [f"0x{value:X}" for value in archive_maxima],
        "retail_buffer_maxima": [f"0x{value:X}" for value in RETAIL_MAXIMA],
        "font_banks_replaced": list(range(8)),
        "arm9_unchanged": True,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("lost_english", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    result = build(
        args.source, args.lost_english, args.output, args.manifest
    )
    print(
        f"Built {args.output}; maxima {result['archive_maxima']}; "
        f"SHA-256 {result['output_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
