"""Encode translated ASCII as native two-byte Shift-JIS glyphs for Xros Wars.

The Japanese Xros renderer advances through message text as two-byte character
codes. Plain ASCII is therefore consumed in pairs and displayed as unrelated
Japanese glyphs. Full-width Latin characters are present in the stock Japanese
font and retain the renderer's expected two-byte representation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from rom_research.nds_inventory import read_header, read_nitrofs
from rom_research.nitrofs_patch import replace_nitrofs_files
from rom_research.story_messages import MESSAGE_ARCHIVES, build_message_table, parse_message_table
from rom_research.xros_pak import XrosPak, build_xros_pak, find_nitro_file, read_nitro_file


def to_fullwidth(text: str) -> str:
    # Python's strict Shift-JIS table does not encode four Unicode full-width
    # punctuation codepoints. These Japanese equivalents use the same visual
    # role and are present in the original game's character map.
    punctuation = {
        '"': "\u201d",
        "'": "\u2019",
        "-": "\u2212",
        "~": "\u301c",
    }
    converted: list[str] = []
    for character in text:
        code = ord(character)
        if character in punctuation:
            converted.append(punctuation[character])
        elif character == " ":
            converted.append("\u3000")
        elif 0x21 <= code <= 0x7E:
            converted.append(chr(code + 0xFEE0))
        else:
            converted.append(character)
    return "".join(converted)


def convert_string(raw: bytes) -> bytes:
    # The completed English build contains ASCII plus line/control bytes.
    # Decode strictly so binary/control-heavy records are left untouched.
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError:
        return raw
    return to_fullwidth(text).encode("shift_jis")


def build(source: Path, output: Path, manifest: Path) -> dict[str, object]:
    replacements: dict[str, bytes] = {}
    converted_strings = 0
    with source.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        for archive_name in MESSAGE_ARCHIVES:
            pak = XrosPak.from_bytes(
                read_nitro_file(handle, find_nitro_file(files, archive_name))
            )
            entries: list[bytes] = []
            changed_archive = False
            for entry_index in range(len(pak.entries)):
                original = pak.unpacked_data(entry_index)
                try:
                    _offsets, strings = parse_message_table(original, encoding="shift_jis")
                except ValueError:
                    entries.append(original)
                    continue
                patched = []
                changed_entry = False
                for raw in strings:
                    converted = convert_string(raw)
                    patched.append(converted)
                    if converted != raw:
                        converted_strings += 1
                        changed_entry = True
                entries.append(
                    build_message_table(original, patched) if changed_entry else original
                )
                changed_archive |= changed_entry
            if changed_archive:
                replacements[archive_name] = build_xros_pak(entries)

    rom = replace_nitrofs_files(source.read_bytes(), replacements)
    output.write_bytes(rom)
    result = {
        "source": str(source),
        "output": str(output),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "output_sha256": hashlib.sha256(rom).hexdigest(),
        "converted_strings": converted_strings,
        "archives": sorted(replacements),
        "renderer": "stock Xros two-byte Shift-JIS",
    }
    manifest.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.source, args.output, args.manifest), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
