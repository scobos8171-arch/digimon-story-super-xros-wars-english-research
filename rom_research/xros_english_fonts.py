"""Port Lost Evolution's English NFTR fonts into Xros Wars."""

from pathlib import Path

from rom_research.nds_inventory import read_header, read_nitrofs
from rom_research.nitrofs_patch import replace_nitrofs_files
from rom_research.xros_pak import XrosPak, build_xros_pak, find_nitro_file, read_nitro_file


FONT_PATH = "FONT_NFTR.PAK"


def read_font_entries(rom: Path) -> list[bytes]:
    with rom.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        pak = XrosPak.from_bytes(
            read_nitro_file(handle, find_nitro_file(files, FONT_PATH))
        )
    return [pak.unpacked_data(index) for index in range(len(pak.entries))]


def build(
    source: Path,
    lost_english: Path,
    output: Path,
    indices: tuple[int, ...] = (0,),
) -> None:
    xros = read_font_entries(source)
    english = read_font_entries(lost_english)
    if len(xros) != 9 or len(english) != 8:
        raise ValueError(
            f"Unexpected font counts: Xros={len(xros)}, Lost English={len(english)}"
        )
    merged = list(xros)
    for index in indices:
        ported = bytearray(english[index])
        # FINF's default/fallback glyph index is game-specific. Preserve the
        # Xros value while importing Lost Evolution's English glyph maps.
        ported[0x1A:0x1C] = xros[index][0x1A:0x1C]
        merged[index] = bytes(ported)
    replacement = build_xros_pak(merged)
    rom = replace_nitrofs_files(source.read_bytes(), {FONT_PATH: replacement})
    output.write_bytes(rom)
    check = read_font_entries(output)
    if any(check[index] != merged[index] for index in indices):
        raise AssertionError("English font package failed readback verification")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("lost_english", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--indices", default="0")
    args = parser.parse_args()
    build(
        args.source,
        args.lost_english,
        args.output,
        tuple(int(value) for value in args.indices.split(",")),
    )
