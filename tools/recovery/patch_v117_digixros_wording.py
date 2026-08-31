"""v117: DigiFusion -> DigiXros. Jogress stays Jogress.

Sprite 131 is ジョグレスアップ (wrongly painted DIGIFUSION UP) -> JOGRESS UP.
Sprite 127:6 is デジフュージョンじょうほう (DIGIFUSION!) -> DIGIXROS!
Message banks: replace DigiFusion/digifusion/DIGIFUSION only.
ARM9 unchanged. SPR members in-place. Message paks rebuilt.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from PIL import Image

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
    / "Xros Evolution Complete US v116 RING CAPTIONS CENTERED"
    / "Game"
    / "Digimon Story Xros Evolution - COMPLETE US v116 RING CAPTIONS CENTERED.nds"
)
OUT = ROOT / "outputs" / "Xros Evolution Complete US v117 DIGIXROS WORDING"
DOWNLOADS = Path(r"C:\Users\YOUR_NAME\Downloads\Digimon Story Xros Evolution - COMPLETE US v117 DIGIXROS WORDING.nds")

SPRITE_JOBS = {
    131: {
        0: {
            "text": "JOGRESS UP",
            "mode": "text",
            "font_style": "compact_3x5",
            "font_scale": 1,
            "font_scale_x": 1,
            "font_scale_y": 1,
            "outline": True,
            "text_tone": "light",
            "use_us_bbox": True,
        },
        1: {
            "text": "JOGRESS UP",
            "mode": "text",
            "font_style": "compact_3x5",
            "font_scale": 1,
            "font_scale_x": 1,
            "font_scale_y": 1,
            "outline": True,
            "text_tone": "light",
            "use_us_bbox": True,
        },
    },
    127: {
        6: {
            "text": "DIGIXROS!",
            "mode": "text",
            "font_style": "compact_3x5",
            "font_scale": 1,
            "font_scale_x": 1,
            "font_scale_y": 1,
            "outline": True,
            "text_tone": "light",
            "use_us_bbox": True,
        },
    },
}

FUSION_REPLACEMENTS = (
    ("DIGIFUSIONS", "DIGIXROS"),
    ("DigiFusions", "DigiXros"),
    ("digifusions", "DigiXros"),
    ("DIGIFUSION", "DIGIXROS"),
    ("DigiFusion", "DigiXros"),
    ("Digifusion", "DigiXros"),
    ("digifusion", "DigiXros"),
)


TUTORIAL_FUSION = (
    ("Fusion Techniques", "DigiXros Techniques"),
    ("Fusion Technique", "DigiXros Technique"),
    ("Fusion System", "DigiXros System"),
    ("Fusion creates", "DigiXros creates"),
    ("use\nFusion to create", "use\nDigiXros to create"),
    ("mean by Fusion", "mean by DigiXros"),
    ("Fusion is a", "DigiXros is a"),
    ("a\nfusion\nexperiment", "a\nDigiXros\nexperiment"),
    ("learn a fusion\nskill", "learn a DigiXros\nskill"),
    ("a fusion\nskill", "a DigiXros\nskill"),
    ("fusion digimon list", "DigiXros Digimon list"),
    ("?^0fusion", "?^0DigiXros"),
    ("？＾０ｆｕｓｉｏｎ", "?^0DigiXros"),
)


def rewrite_fusion(text: str) -> str:
    updated = text
    for old, new in FUSION_REPLACEMENTS:
        updated = updated.replace(old, new)
    stripped = updated.strip()
    if stripped in {"Fusion", "fusion", "Ｇａｔｔａｉ"}:
        return "DigiXros"
    for old, new in TUTORIAL_FUSION:
        updated = updated.replace(old, new)
    return updated


def load_paks(path: Path):
    with path.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        item = find_nitro_file(files, GRAPHICS_PATH)
        gfx = XrosPak.from_bytes(read_nitro_file(handle, item))
        pal = XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, PALETTE_PATH)))
        cel = XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, CELLS_PATH)))
    return item, gfx, pal, cel


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


def patch_sprites(rom: bytearray, qa: Path) -> None:
    jp_item, jp_gfx, jp_pal, jp_cel = load_paks(JP)
    us_item, us_gfx, us_pal, us_cel = load_paks(SRC)
    del jp_item
    pak = bytearray(us_gfx.data)
    for entry, specs in SPRITE_JOBS.items():
        slot = us_gfx.entries[entry]
        if not slot.is_uncompressed:
            raise ValueError(f"entry {entry} is compressed")
        nclr = parse_nclr(us_pal.unpacked_data(entry))
        cells = parse_ncer(us_cel.unpacked_data(entry))
        jp_nclr = parse_nclr(jp_pal.unpacked_data(entry))
        jp_cells = parse_ncer(jp_cel.unpacked_data(entry))
        jp_ncgr = parse_ncgr(jp_gfx.unpacked_data(entry))
        us_bytes = us_gfx.unpacked_data(entry)
        canvases = [render_full_cell(parse_ncgr(us_bytes), nclr, cells[i]) for i in range(len(cells))]
        selected = set()
        for cell, spec in specs.items():
            donor = render_full_cell(jp_ncgr, jp_nclr, jp_cells[cell])
            live = canvases[cell]
            local = dict(spec)
            source = live if local.pop("use_us_bbox", False) else donor
            bbox = source.getbbox()
            if bbox is None:
                raise ValueError(f"{entry}:{cell} has empty bounds")
            # Draw into the live OAM canvas, but only the original glyph well,
            # so compact 3x5 sits where DIGIFUSION sat instead of recentering
            # on the padded 96x32 cell and clipping a letter.
            local["mode"] = "text"
            local["text_rect"] = bbox
            blank = source.copy()
            blank.paste((0, 0, 0, 0), bbox)
            painted = edit_canvas(blank, local, nclr, None)
            composed = Image.new("RGBA", live.size, (0, 0, 0, 0))
            composed.paste(painted, (0, 0), painted)
            donor.save(qa / f"jp_e{entry:04d}_c{cell:02d}.png")
            live.save(qa / f"before_e{entry:04d}_c{cell:02d}.png")
            composed.save(qa / f"en_e{entry:04d}_c{cell:02d}.png")
            canvases[cell] = composed
            selected.add(cell)
            print(f"sprite {entry}:{cell} {spec['text']} well {bbox} canvas {composed.size}")
        encoded = encode_selected_cells(us_bytes, cells, canvases, nclr, selected)
        if len(encoded) != slot.stored_size:
            raise ValueError(f"{entry} encoded {len(encoded)} != {slot.stored_size}")
        pak[slot.offset : slot.offset + slot.stored_size] = encoded
        patched = parse_ncgr(encoded)
        for cell in selected:
            render_full_cell(patched, nclr, cells[cell]).save(qa / f"rom_e{entry:04d}_c{cell:02d}.png")
    rom[us_item.offset : us_item.offset + us_item.size] = pak


def patch_messages(source: bytes) -> tuple[bytes, list[dict[str, object]]]:
    applied: list[dict[str, object]] = []
    replacements: dict[str, bytes] = {}
    with SRC.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        for pak_i in range(6):
            name = f"MSG/MESPAK{pak_i:02d}.PAK"
            try:
                item = find_nitro_file(files, name)
            except Exception:
                continue
            pak = XrosPak.from_bytes(read_nitro_file(handle, item))
            entries = [pak.unpacked_data(i) for i in range(len(pak.entries))]
            changed = False
            for entry_index, original in enumerate(entries):
                try:
                    _offsets, strings = parse_message_table(original, encoding="shift_jis")
                except Exception:
                    continue
                patched = list(strings)
                for idx, raw in enumerate(patched):
                    before = raw.decode("shift_jis", errors="replace")
                    after = rewrite_fusion(before)
                    if after != before:
                        patched[idx] = after.encode("shift_jis")
                        applied.append(
                            {
                                "key": [pak_i, entry_index, idx],
                                "before": before,
                                "after": after,
                            }
                        )
                if any(a != b for a, b in zip(patched, strings)):
                    entries[entry_index] = build_message_table(original, patched)
                    changed = True
            if changed:
                replacements[name] = build_xros_pak(entries)
    if not replacements:
        return source, applied
    patched_rom = replace_nitrofs_files(source, replacements)
    return patched_rom, applied


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    qa = OUT / "QA"
    qa.mkdir(exist_ok=True)
    rom = bytearray(SRC.read_bytes())
    arm9 = arm9_slice(bytes(rom))
    patch_sprites(rom, qa)
    if arm9 != arm9_slice(bytes(rom)):
        raise AssertionError("ARM9 changed during sprite patch")
    patched, applied = patch_messages(bytes(rom))
    if arm9 != arm9_slice(patched):
        raise AssertionError("ARM9 changed during message patch")
    dest = OUT / "Game" / "Digimon Story Xros Evolution - COMPLETE US v117 DIGIXROS WORDING.nds"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(patched)
    DOWNLOADS.write_bytes(patched)
    leftover = [row for row in applied if "fusion" in row["after"].lower() and "confusion" not in row["after"].lower()]
    manifest = {
        "source": str(SRC),
        "output": str(dest),
        "sha256": hashlib.sha256(patched).hexdigest(),
        "arm9_unchanged": True,
        "message_replacements": len(applied),
        "applied": applied,
        "after_still_has_fusion_word": leftover[:20],
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print("messages", len(applied))
    print("wrote", dest)
    print("wrote", DOWNLOADS)
    print("sample")
    for row in applied[:12]:
        print(" ", row["key"], row["before"][:60], "=>", row["after"][:60])


if __name__ == "__main__":
    main()
