"""Build a full localized Xros ROM with crash-safe visible canonical names.

The Skills screen requires the Shoutmon/Ballistamon records to remain encoded
as two-byte Shift-JIS characters.  Full-width Latin satisfies that requirement,
but the localized NFTR maps those codes to blank glyphs.  This tool preserves
the two-byte message records and aliases their NFTR mappings to the existing
visible ASCII glyphs.
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EDITOR = ROOT / "work" / "DigimonNDSRomEditor-master"
NFTR_TOOLS = ROOT / "work" / "reference" / "DSLEChsLocalization" / "scripts"
sys.path[:0] = [str(EDITOR), str(NFTR_TOOLS)]

from nftr import NFTR
from rom_research.nds_inventory import read_header, read_nitrofs
from rom_research.nitrofs_patch import replace_nitrofs_files
from rom_research.story_messages import build_message_table, parse_message_table
from rom_research.xros_pak import XrosPak, build_xros_pak, find_nitro_file, read_nitro_file

MESSAGE_PATH = "MSG/MESPAK00.PAK"
FONT_PATH = "FONT_NFTR.PAK"
NAMES = {535: "Shoutmon", 536: "Ballistamon"}


def read_file(rom: Path, name: str) -> bytes:
    with rom.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        return read_nitro_file(handle, find_nitro_file(files, name))


def fullwidth(text: str) -> str:
    return "".join(chr(ord(ch) + 0xFEE0) if 0x21 <= ord(ch) <= 0x7E else ch for ch in text)


def patch_messages(raw_pak: bytes) -> tuple[bytes, dict[str, object]]:
    pak = XrosPak.from_bytes(raw_pak)
    entries = [pak.unpacked_data(i) for i in range(len(pak.entries))]
    _offsets, parsed_strings = parse_message_table(entries[0], encoding="shift_jis")
    strings = list(parsed_strings)
    changed = {}
    for index, name in NAMES.items():
        before = strings[index].decode("shift_jis", errors="replace")
        safe_name = fullwidth(name)
        strings[index] = safe_name.encode("shift_jis")
        changed[str(index)] = {"before": before, "after": name, "stored": safe_name}
    entries[0] = build_message_table(entries[0], strings)
    return build_xros_pak(entries), changed


def patch_font(raw_pak: bytes) -> tuple[bytes, dict[str, object]]:
    pak = XrosPak.from_bytes(raw_pak)
    entries = [pak.unpacked_data(i) for i in range(len(pak.entries))]
    original_font = entries[0]
    font = NFTR(original_font)
    patched_font = bytearray(original_font)
    required = sorted(set("".join(NAMES.values())))
    aliases = {}
    for ascii_char in required:
        ascii_code = ord(ascii_char)
        wide_char = fullwidth(ascii_char)
        wide_code = int.from_bytes(wide_char.encode("shift_jis"), "big")
        ascii_glyph = next(
            (cmap.index_map[ascii_code] for cmap in font.cmaps if ascii_code in cmap.index_map),
            None,
        )
        if ascii_glyph is None:
            raise ValueError(f"ASCII glyph is missing for {ascii_char!r}")
        target_index = next(
            (index for index, cmap in enumerate(font.cmaps) if wide_code in cmap.index_map),
            None,
        )
        if target_index is None:
            raise ValueError(f"Full-width code is missing from NFTR: 0x{wide_code:04X}")
        target = font.cmaps[target_index]
        old_glyph = target.index_map[wide_code]
        if target.type_section != 1:
            raise ValueError(
                f"Expected editable type-1 CMAP for 0x{wide_code:04X}, got type {target.type_section}"
            )

        # Patch only the existing two-byte glyph-index field. Re-serializing
        # this NFTR is unsafe because the third-party writer recalculates an
        # internal CWDH link incorrectly for this game's multi-block font.
        cmap_file_offset = font.finf.cmap_offset - 8
        for earlier in font.cmaps[:target_index]:
            cmap_file_offset = earlier.cmap_offset - 8
        glyph_offset = cmap_file_offset + 0x14 + 2 * (wide_code - target.first_char_code)
        struct.pack_into(f"{font.endianess}H", patched_font, glyph_offset, ascii_glyph)
        aliases[wide_char] = {
            "shift_jis_code": f"0x{wide_code:04X}",
            "ascii": ascii_char,
            "old_glyph": old_glyph,
            "visible_glyph": ascii_glyph,
        }
    if len(patched_font) != len(original_font):
        raise AssertionError("In-place NFTR patch changed the font size")
    entries[0] = bytes(patched_font)
    return build_xros_pak(entries), aliases


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Working full localized ROM")
    parser.add_argument("output", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    message_pak, changed = patch_messages(read_file(args.source, MESSAGE_PATH))
    font_pak, aliases = patch_font(read_file(args.source, FONT_PATH))
    result = replace_nitrofs_files(
        args.source.read_bytes(),
        {MESSAGE_PATH: message_pak, FONT_PATH: font_pak},
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(result)

    # Read back both archives from the finished ROM before declaring success.
    out_message = read_file(args.output, MESSAGE_PATH)
    out_font = read_file(args.output, FONT_PATH)
    if out_message != message_pak or out_font != font_pak:
        raise AssertionError("Finished ROM failed archive readback verification")

    report = {
        "source": str(args.source.resolve()),
        "output": str(args.output.resolve()),
        "messages": changed,
        "font_aliases": aliases,
        "preserved_policy": "Only MESPAK00 and FONT_NFTR were replaced; UI sprites remain from source ROM.",
    }
    report_path = args.report or args.output.with_suffix(".json")
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
