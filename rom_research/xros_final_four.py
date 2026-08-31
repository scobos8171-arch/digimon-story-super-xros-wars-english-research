"""Replace the four malformed Japanese skill names left in MESPAK00."""

from pathlib import Path

from rom_research.nds_inventory import read_header, read_nitrofs
from rom_research.nitrofs_patch import replace_nitrofs_files
from rom_research.story_messages import build_message_table, parse_message_table
from rom_research.xros_pak import XrosPak, build_xros_pak, find_nitro_file, read_nitro_file


def patch(source: Path, output: Path) -> None:
    archive_name = "MSG/MESPAK00.PAK"
    with source.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        pak = XrosPak.from_bytes(
            read_nitro_file(handle, find_nitro_file(files, archive_name))
        )
    entries = [pak.unpacked_data(index) for index in range(len(pak.entries))]
    original = entries[0]
    _offsets, strings = parse_message_table(original, encoding="shift_jis")
    patched = list(strings)
    replacements = {
        1490: b"Giga Destroyer II",
        2191: b"Blaster Tail II",
        2766: b"G Destroyer II",
        3467: b"Blaster Tail II",
    }
    for index, value in replacements.items():
        patched[index] = value
    entries[0] = build_message_table(original, patched)
    rom = replace_nitrofs_files(
        source.read_bytes(),
        {archive_name: build_xros_pak(entries)},
    )
    output.write_bytes(rom)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    patch(args.source, args.output)
