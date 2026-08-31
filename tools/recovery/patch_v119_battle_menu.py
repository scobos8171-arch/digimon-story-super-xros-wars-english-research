"""v119: battle menu leftover Japanese + bad tactic names.

- Overlay 0 HUD: フルパワ/とんずら/せつやく/ガード (capture-proven slots)
- Tactic labels in MESPAK01: FULL POWER / CONSERVE / GUARD / FLEE
- Results NEXT/FINISH/SKIP pills (entry 2002)
ARM9 unchanged. Overlay is appended at the ROM tail (existing overlay-0 tool).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "work" / "DigimonNDSRomEditor-master"))
sys.path.insert(0, str(ROOT / "tools" / "recovery"))
from build_xros_custom_ui_rom import (  # noqa: E402
    CELLS_PATH,
    GRAPHICS_PATH,
    PALETTE_PATH,
    edit_canvas,
    encode_selected_cells,
    parse_ncer,
    parse_ncgr,
    parse_nclr,
    render_full_cell,
)
from patch_xros_overlay0_runtime_labels import build as patch_overlay0  # noqa: E402
from rom_research.nds_inventory import read_header, read_nitrofs  # noqa: E402
from rom_research.nitrofs_patch import replace_nitrofs_files  # noqa: E402
from rom_research.story_messages import build_message_table, parse_message_table  # noqa: E402
from rom_research.xros_pak import (  # noqa: E402
    XrosPak,
    build_xros_pak,
    find_nitro_file,
    read_nitro_file,
)

JP = ROOT / "work" / "roms" / "xros_blue.nds"
SRC = (
    ROOT
    / "outputs"
    / "Xros Evolution Complete US v117 DIGIXROS WORDING"
    / "Game"
    / "Digimon Story Xros Evolution - COMPLETE US v117 DIGIXROS WORDING.nds"
)
OUT = ROOT / "outputs" / "Xros Evolution Complete US v119 BATTLE MENU"
DOWNLOADS = Path(r"C:\Users\YOUR_NAME\Downloads\Digimon Story Xros Evolution - COMPLETE US v119 BATTLE MENU.nds")

MESSAGE_REPAIRS = {
    (1, 1, 40): "Trying to flee!",
    (1, 1, 44): "Couldn't flee!",
    (1, 1, 45): "Fled successfully!",
    (1, 1, 91): "FULL POWER",
    (1, 1, 92): "CONSERVE",
    (1, 1, 93): "GUARD",
    (1, 1, 94): "FLEE",
    (1, 1, 95): "Fight at full power using your strongest moves.",
    (1, 1, 96): "Uses more MP when attacking.",
    (1, 1, 97): "Guard to take much less damage from attacks.",
    (1, 1, 98): "Flee to end the battle.",
    (1, 1, 99): "FULL POWER",
    (1, 1, 101): "GUARD",
    (1, 1, 102): "FLEE",
}

SPRITE_2002 = {
    0: {
        "text": "NEXT",
        "mode": "frame",
        "clear": (16, 2, 56, 16),
        "fill_strategy": "row_gradient",
        "row_reference_x": 8,
        "font_style": "hex_4x7",
        "shadow": True,
        "outline": False,
        "text_rect": (16, 4, 56, 15),
    },
    1: {
        "text": "FINISH",
        "mode": "frame",
        "clear": (16, 2, 56, 16),
        "fill_strategy": "row_gradient",
        "row_reference_x": 8,
        "font_style": "hex_4x7",
        "shadow": True,
        "outline": False,
        "text_rect": (16, 4, 56, 15),
    },
    2: {
        "text": "SKIP",
        "mode": "frame",
        "clear": (16, 2, 56, 16),
        "fill_strategy": "row_gradient",
        "row_reference_x": 8,
        "font_style": "hex_4x7",
        "shadow": True,
        "outline": False,
        "text_rect": (16, 4, 56, 15),
    },
}


def arm9_slice(data: bytes) -> bytes:
    class Reader:
        def __init__(self, raw: bytes):
            self.raw, self.pos = raw, 0

        def seek(self, pos: int) -> int:
            self.pos = pos
            return pos

        def read(self, size: int = -1) -> bytes:
            if size < 0:
                size = len(self.raw) - self.pos
            value = self.raw[self.pos : self.pos + size]
            self.pos += len(value)
            return value

    header = read_header(Reader(data))
    start = int(header["arm9_offset"])
    return data[start : start + int(header["arm9_size"])]


def load_paks(path: Path):
    with path.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        item = find_nitro_file(files, GRAPHICS_PATH)
        gfx = XrosPak.from_bytes(read_nitro_file(handle, item))
        pal = XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, PALETTE_PATH)))
        cel = XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, CELLS_PATH)))
    return item, gfx, pal, cel


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    qa = OUT / "QA"
    qa.mkdir(exist_ok=True)
    overlay_rom = OUT / "_overlay_temp.nds"
    overlay_manifest = OUT / "overlay_manifest.json"
    patch_overlay0(SRC, overlay_rom, overlay_manifest)
    rom = bytearray(overlay_rom.read_bytes())
    arm9 = arm9_slice(SRC.read_bytes())
    if arm9 != arm9_slice(bytes(rom)):
        raise AssertionError("ARM9 changed during overlay patch")

    jp_item, jp_gfx, jp_pal, jp_cel = load_paks(JP)
    with overlay_rom.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        gfx_item = find_nitro_file(files, GRAPHICS_PATH)
        gfx = XrosPak.from_bytes(read_nitro_file(handle, gfx_item))
        pal = XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, PALETTE_PATH)))
        cel = XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, CELLS_PATH)))
    del jp_item
    slot = gfx.entries[2002]
    if not slot.is_uncompressed:
        raise ValueError("2002 compressed")
    nclr = parse_nclr(pal.unpacked_data(2002))
    cells = parse_ncer(cel.unpacked_data(2002))
    jp_nclr = parse_nclr(jp_pal.unpacked_data(2002))
    jp_cells = parse_ncer(jp_cel.unpacked_data(2002))
    jp_ncgr = parse_ncgr(jp_gfx.unpacked_data(2002))
    us_bytes = gfx.unpacked_data(2002)
    canvases = [render_full_cell(parse_ncgr(us_bytes), nclr, cells[i]) for i in range(len(cells))]
    selected = set()
    for cell, spec in SPRITE_2002.items():
        donor = render_full_cell(jp_ncgr, jp_nclr, jp_cells[cell])
        painted = edit_canvas(donor, spec, nclr, None)
        donor.save(qa / f"jp_2002_{cell:02d}.png")
        painted.save(qa / f"en_2002_{cell:02d}.png")
        canvases[cell] = painted
        selected.add(cell)
        print("2002", cell, spec["text"], painted.size)
    encoded = encode_selected_cells(us_bytes, cells, canvases, nclr, selected)
    if len(encoded) != slot.stored_size:
        raise ValueError(f"2002 {len(encoded)} != {slot.stored_size}")
    pak = bytearray(gfx.data)
    pak[slot.offset : slot.offset + slot.stored_size] = encoded
    rom[gfx_item.offset : gfx_item.offset + gfx_item.size] = pak
    patched_gfx = parse_ncgr(encoded)
    for cell in selected:
        render_full_cell(patched_gfx, nclr, cells[cell]).save(qa / f"rom_2002_{cell:02d}.png")

    replacements: dict[str, bytes] = {}
    applied = []
    with overlay_rom.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        item = find_nitro_file(files, "MSG/MESPAK01.PAK")
        pak_msg = XrosPak.from_bytes(read_nitro_file(handle, item))
    entries = [pak_msg.unpacked_data(i) for i in range(len(pak_msg.entries))]
    original = entries[1]
    _off, strings = parse_message_table(original, encoding="shift_jis")
    patched_strings = list(strings)
    for (_pak, entry, idx), english in MESSAGE_REPAIRS.items():
        before = patched_strings[idx].decode("shift_jis", errors="replace")
        patched_strings[idx] = english.encode("ascii")
        applied.append({"key": [1, entry, idx], "before": before, "after": english})
    entries[1] = build_message_table(original, patched_strings)
    replacements["MSG/MESPAK01.PAK"] = build_xros_pak(entries)
    rom_bytes = replace_nitrofs_files(bytes(rom), replacements)
    if arm9 != arm9_slice(rom_bytes):
        raise AssertionError("ARM9 changed during message patch")
    dest = OUT / "Game" / "Digimon Story Xros Evolution - COMPLETE US v119 BATTLE MENU.nds"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(rom_bytes)
    DOWNLOADS.write_bytes(rom_bytes)
    overlay_rom.unlink(missing_ok=True)
    (OUT / "manifest.json").write_text(json.dumps({"applied": applied}, indent=2), encoding="utf-8")
    print("wrote", dest)
    print("wrote", DOWNLOADS)


if __name__ == "__main__":
    main()
