"""Reflow English story text for Xros's fixed-width Japanese renderer."""

from __future__ import annotations

import argparse
import hashlib
import json
import textwrap
from pathlib import Path

from rom_research.nds_inventory import read_header, read_nitrofs
from rom_research.nitrofs_patch import replace_nitrofs_files
from rom_research.story_messages import build_message_table, parse_message_table
from rom_research.xros_pak import XrosPak, build_xros_pak, find_nitro_file, read_nitro_file


# MESPAK00 contains roster names and much of the fixed-layout UI.
# MESPAK01 is also dominated by fixed-layout system text.
STORY_ARCHIVES = tuple(f"MSG/MESPAK{index:02d}.PAK" for index in range(2, 6))


def reflow(text: str, width: int, max_lines: int = 21) -> str:
    text = text.replace("Congratulations...?", "Congratulations!")
    output: list[str] = []
    for original_line in text.splitlines():
        line = " ".join(original_line.split())
        if not line:
            output.append("")
            continue
        output.extend(
            textwrap.wrap(
                line,
                width=width,
                break_long_words=True,
                break_on_hyphens=False,
                replace_whitespace=True,
                drop_whitespace=True,
            )
        )
    if len(output) > max_lines:
        output = output[:max_lines]
        last = output[-1]
        output[-1] = (last[: max(0, width - 3)].rstrip() + "...")[:width]
    return "\n".join(output)


def build(source: Path, output: Path, manifest: Path, width: int = 17) -> dict[str, object]:
    replacements: dict[str, bytes] = {}
    changed = 0
    lines_before = 0
    lines_after = 0
    with source.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        for archive_name in STORY_ARCHIVES:
            pak = XrosPak.from_bytes(
                read_nitro_file(handle, find_nitro_file(files, archive_name))
            )
            entries: list[bytes] = []
            archive_changed = False
            for entry_index in range(len(pak.entries)):
                original = pak.unpacked_data(entry_index)
                try:
                    _offsets, strings = parse_message_table(original, encoding="shift_jis")
                except ValueError:
                    entries.append(original)
                    continue
                patched = list(strings)
                entry_changed = False
                for string_index, raw in enumerate(strings):
                    try:
                        text = raw.decode("ascii")
                    except UnicodeDecodeError:
                        continue
                    if not any(character.isalpha() for character in text):
                        continue
                    flowed = reflow(text, width)
                    encoded = flowed.encode("ascii")
                    if encoded != raw:
                        patched[string_index] = encoded
                        changed += 1
                        lines_before += text.count("\n") + 1
                        lines_after += flowed.count("\n") + 1
                        entry_changed = True
                entries.append(
                    build_message_table(original, patched) if entry_changed else original
                )
                archive_changed |= entry_changed
            if archive_changed:
                replacements[archive_name] = build_xros_pak(entries)

    rom = replace_nitrofs_files(source.read_bytes(), replacements)
    output.write_bytes(rom)
    result = {
        "source": str(source),
        "output": str(output),
        "output_sha256": hashlib.sha256(rom).hexdigest(),
        "line_width": width,
        "changed_strings": changed,
        "lines_before": lines_before,
        "lines_after": lines_after,
        "archives": list(STORY_ARCHIVES),
    }
    manifest.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--width", type=int, default=17)
    args = parser.parse_args()
    print(json.dumps(build(args.source, args.output, args.manifest, args.width), indent=2))
