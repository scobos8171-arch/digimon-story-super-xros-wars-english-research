#!/usr/bin/env python3
"""Build a clean, ROM-free handoff for Xros UI localization work."""

from __future__ import annotations

import csv
import importlib.util
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "outputs" / "Xros UI Localization PixelForge Pack"
PIXELFORGE = Path("C:/Users/scobo/pixelforge")
PIXELFORGE_PACK = PIXELFORGE / "xros_ui_localization_pack"
ZIP_OUTPUT = ROOT / "outputs" / "Xros UI Localization PixelForge Pack.zip"
DONORS = ROOT / "work" / "xros-custom-ui-donors"
REMAINING = ROOT / "work" / "xros-remaining-ui-cells"
DUSK_UI = ROOT / "work" / "map_builder_kit" / "battle_ui" / "dusk"
ROM_RESEARCH = ROOT / "work" / "DigimonNDSRomEditor-master"
PATCHER = ROOT / "tools" / "recovery" / "build_xros_custom_ui_rom.py"

if str(ROM_RESEARCH) not in sys.path:
    sys.path.insert(0, str(ROM_RESEARCH))

from rom_research.xros_sprite import XrosSpriteSet  # noqa: E402


def reset_folder(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def copy_file(source: Path, destination: Path) -> None:
    if not source.is_file():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def png_info(path: Path) -> tuple[int, int, int]:
    with Image.open(path) as image:
        rgba = image.convert("RGBA")
        return rgba.width, rgba.height, len(set(rgba.getdata()))


def load_patch_specs() -> dict[int, dict[int, dict[str, object]]]:
    spec = importlib.util.spec_from_file_location("xros_ui_patcher", PATCHER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {PATCHER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.SPECS


def find_build_rom(prefix: str) -> Path:
    folders = sorted((ROOT / "outputs").glob(prefix))
    if not folders:
        raise FileNotFoundError(f"build not found: {prefix}")
    roms = sorted(folders[0].rglob("*.nds"))
    if not roms:
        raise FileNotFoundError(f"ROM not found under {folders[0]}")
    return roms[0]


def save_pair(
    approved_root: Path,
    entry: int,
    cell: int,
    text: str,
    source_image: Image.Image,
    english_image: Image.Image,
    source_kind: str,
    target_build: str,
) -> dict:
    pair_dir = approved_root / f"entry_{entry:04d}" / f"cell_{cell:02d}"
    pair_dir.mkdir(parents=True, exist_ok=True)
    source_path = pair_dir / "source_or_predecessor.png"
    english_path = pair_dir / "english_completed.png"
    source_image.save(source_path)
    english_image.save(english_path)
    width, height, colors = png_info(source_path)
    ew, eh, ecolors = png_info(english_path)
    metadata = {
        "entry": entry,
        "cell": cell,
        "english_text": text,
        "source_kind": source_kind,
        "target_build": target_build,
        "source_dimensions": [width, height],
        "english_dimensions": [ew, eh],
        "dimensions_match": (width, height) == (ew, eh),
        "source_color_count": colors,
        "english_color_count": ecolors,
        "status": "completed_work_reference",
        "note": "Curated reference pair. Visual approval and cold-boot ROM testing are still required before release.",
    }
    (pair_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def build_pair_contact_sheet(approved_root: Path, output: Path) -> None:
    pairs = sorted(approved_root.glob("entry_*/cell_*"))
    if not pairs:
        return
    tiles: list[Image.Image] = []
    for pair in pairs:
        source = Image.open(pair / "source_or_predecessor.png").convert("RGBA")
        english = Image.open(pair / "english_completed.png").convert("RGBA")
        scale = max(1, min(4, 240 // max(source.width, english.width, 1)))
        width = max(source.width, english.width) * scale
        tile = Image.new("RGBA", (width, (source.height + english.height) * scale + 18), "#202733")
        tile.alpha_composite(source.resize((source.width * scale, source.height * scale), Image.Resampling.NEAREST), (0, 0))
        tile.alpha_composite(english.resize((english.width * scale, english.height * scale), Image.Resampling.NEAREST), (0, source.height * scale))
        tiles.append(tile)
    columns = 5
    cell_w = max(tile.width for tile in tiles)
    cell_h = max(tile.height for tile in tiles)
    rows = (len(tiles) + columns - 1) // columns
    sheet = Image.new("RGBA", (columns * cell_w, rows * cell_h), "#10151d")
    for index, tile in enumerate(tiles):
        sheet.alpha_composite(tile, ((index % columns) * cell_w, (index // columns) * cell_h))
    sheet.save(output)


def main() -> int:
    reset_folder(OUTPUT)

    approved_root = OUTPUT / "01_WORK_COMPLETED_PAIRED"
    queue_root = OUTPUT / "02_NEEDS_LOCALIZATION"
    refs_root = OUTPUT / "03_ENGLISH_DS_UI_REFERENCES" / "Dusk_USA"
    qa_root = OUTPUT / "04_BEST_QA_AND_REFINED_WORK"
    tools_root = OUTPUT / "05_SAFE_TOOLS"

    donor_manifest = json.loads((DONORS / "manifest.json").read_text(encoding="utf-8"))
    approved_keys: set[tuple[int, int]] = set()
    approved_by_key: dict[tuple[int, int], dict] = {}
    for item in donor_manifest["entries"]:
        entry = int(item["entry"])
        cell = int(item["cell"])
        approved_keys.add((entry, cell))
        source = Path(item["source"])
        english = Path(item["donor"])
        approved_by_key[(entry, cell)] = save_pair(
            approved_root,
            entry,
            cell,
            item["text"],
            Image.open(source).convert("RGBA"),
            Image.open(english).convert("RGBA"),
            "original_extracted_japanese",
            "deterministic_donor_work",
        )

    # Recover approved work that lived only inside historical ROM builds.
    # v31 contains the refined command ring and bank; v20 is the last matching
    # predecessor envelope for command cells whose NCER height was corrected.
    patch_specs = load_patch_specs()
    source_rom = find_build_rom("Xros Evolution Complete US v4 UI TEXT CLEANUP")
    predecessor_rom = find_build_rom("Xros Evolution Complete US v20 NATIVE UI CLEAN CANDIDATE")
    refined_rom = find_build_rom("Xros Evolution Complete US v31 NATIVE UI CLEAN REFINED")
    source_sprites = XrosSpriteSet.from_rom(source_rom)
    predecessor_sprites = XrosSpriteSet.from_rom(predecessor_rom)
    refined_sprites = XrosSpriteSet.from_rom(refined_rom)
    recovered_keys = {
        (196, 8),
        *{(1987, cell) for cell in range(9)},
        *{(221, cell) for cell in range(16, 32)},
        *{(2249, cell) for cell in range(4)},
        *{(2250, cell) for cell in range(4)},
    }
    for entry, cell in sorted(recovered_keys):
        detail = patch_specs[entry][cell]
        source_image = source_sprites.render(entry, cell).convert("RGBA")
        english_image = refined_sprites.render(entry, cell).convert("RGBA")
        if source_image.size != english_image.size:
            raise RuntimeError(f"unsafe recovered pair {entry}:{cell}: {source_image.size} != {english_image.size}")
        approved_by_key[(entry, cell)] = save_pair(
            approved_root, entry, cell, str(detail["text"]), source_image, english_image,
            "localized_build_before_native_sprite_edit", "v31_native_ui_clean_refined",
        )

    for cell in range(1, 8):
        detail = patch_specs[196][cell]
        source_image = predecessor_sprites.render(196, cell).convert("RGBA")
        english_image = refined_sprites.render(196, cell).convert("RGBA")
        if source_image.size != english_image.size:
            raise RuntimeError(f"unsafe refined pair 196:{cell}: {source_image.size} != {english_image.size}")
        approved_by_key[(196, cell)] = save_pair(
            approved_root, 196, cell, str(detail["text"]), source_image, english_image,
            "previous_command_ring_edit", "v31_native_ui_clean_refined",
        )

    approved_keys = set(approved_by_key)
    approved_rows = [approved_by_key[key] for key in sorted(approved_by_key)]

    remaining_rows: list[dict] = []
    cell_pattern = re.compile(r"(?P<entry>\d{4})_cell(?P<cell>\d{2})\.png$", re.IGNORECASE)
    for source in sorted(REMAINING.glob("*_cell*.png")):
        match = cell_pattern.match(source.name)
        if not match:
            continue
        entry = int(match.group("entry"))
        cell = int(match.group("cell"))
        if (entry, cell) in approved_keys:
            continue
        width, height, colors = png_info(source)
        destination = queue_root / f"entry_{entry:04d}" / f"cell_{cell:02d}_source_japanese.png"
        copy_file(source, destination)
        remaining_rows.append(
            {
                "priority": "unreviewed",
                "entry": entry,
                "cell": cell,
                "width": width,
                "height": height,
                "source_colors": colors,
                "japanese_meaning": "",
                "recommended_english": "",
                "status": "needs_translation_and_visual_review",
                "source_png": str(destination.relative_to(OUTPUT)),
            }
        )

    for source in sorted(DUSK_UI.glob("*.png")):
        copy_file(source, refs_root / source.name)

    qa_sources = {
        "command_ring_refined_full_sheet.png": ROOT / "outputs" / "Xros Evolution Complete US v30 NATIVE UI COMMAND RING REFINED" / "QA" / "render" / "0196_all_cells.png",
        "bank_refined_full_sheet.png": ROOT / "outputs" / "Xros Evolution Complete US v31 NATIVE UI CLEAN REFINED" / "QA" / "render" / "2250_all_cells.png",
        "result_button_best_preview.png": ROOT / "work" / "ui-qa-result-button-one-cell" / "preview-cleanfont2.png",
        "command_ring_best_preview.png": ROOT / "work" / "ui-qa-command-ring-one-cell" / "preview-clean.png",
        "bank_best_preview.png": ROOT / "work" / "ui-qa-bank-refined" / "preview.png",
        "completed_donor_contact_sheet.png": DONORS / "contact-sheet.png",
    }
    for name, source in qa_sources.items():
        copy_file(source, qa_root / name)
    build_pair_contact_sheet(approved_root, qa_root / "all_curated_pairs.png")

    tool_sources = (
        ROOT / "tools" / "pixelforge_studio" / "scripts" / "ui_localizer.py",
        ROOT / "tools" / "recovery" / "build_xros_custom_ui_rom.py",
        ROOT / "tools" / "recovery" / "build_xros_custom_ui_donors.py",
        ROOT / "tools" / "recovery" / "render_xros_entry_cells.py",
        ROOT / "tools" / "recovery" / "audit_xros_text_sprites.py",
    )
    for source in tool_sources:
        copy_file(source, tools_root / source.name)

    with (OUTPUT / "completed_work.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(approved_rows[0].keys()))
        writer.writeheader()
        writer.writerows(approved_rows)

    with (OUTPUT / "localization_queue.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        fields = list(remaining_rows[0].keys()) if remaining_rows else ["entry", "cell", "status"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(remaining_rows)

    manifest = {
        "purpose": "ROM-free Xros UI localization handoff for PixelForge",
        "completed_reference_pairs": len(approved_rows),
        "remaining_extracted_cells": len(remaining_rows),
        "english_dusk_reference_images": len(list(refs_root.glob("*.png"))),
        "constraints": {
            "dimensions_must_match_source": True,
            "nearest_neighbor_only": True,
            "anti_aliasing": False,
        "source_entry_palette_only": True,
            "raw_ai_output_is_rom_safe": False,
        },
        "recommended_pipeline": [
            "Translate wording with an LLM or human review.",
            "Optionally use Qwen-Image-Edit for a visual draft only.",
            "Finish the cell in PixelForge DS UI Localizer; it restricts edits to the loaded source-cell palette.",
            "Require its validation JSON before ROM injection.",
            "Patch a copied ROM and cold-boot test it; never overwrite the source ROM.",
        ],
    }
    (OUTPUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    readme = f"""XROS UI LOCALIZATION - PIXELFORGE HANDOFF

WHAT IS INCLUDED
- 01_WORK_COMPLETED_PAIRED: {len(approved_rows)} Japanese/English reference pairs from work already completed.
- 02_NEEDS_LOCALIZATION: {len(remaining_rows)} extracted cells that still require translation and/or visual identification.
- 03_ENGLISH_DS_UI_REFERENCES: English Digimon World Dusk UI assets for typography and spacing reference.
- 04_BEST_QA_AND_REFINED_WORK: selected final/refined sheets and previews; discarded giant-white-block experiments are excluded.
- 05_SAFE_TOOLS: extraction, rendering, deterministic patching, and validation scripts. No ROM is included.

BEST WORKFLOW
1. Finish the current PixelForge LoRA training before changing its dataset.
2. Restart PixelForge Studio after training. Open the new DS UI Localizer tab.
3. Load a source cell from 02_NEEDS_LOCALIZATION.
4. Translate the label naturally and keep it short.
5. Select only the Japanese glyph region, apply English, and Save + Validate.
6. Keep the source PNG, English PNG, and validation JSON together.
7. Only inject validated cells into a COPY of your ROM, then cold-boot test menus and battles.

AI MODEL GUIDANCE
- Best local draft model: Qwen-Image-Edit (20B), because it is specifically designed for text edits while preserving appearance.
- On a 4060, the full model may be impractical without aggressive quantization/offload. It is optional.
- Do NOT use a normal SDXL LoRA to spell final UI labels. It may hallucinate letters or disturb borders.
- The deterministic PixelForge localizer is the authority for exact English spelling, original dimensions, transparency, and palette.
- Historical completed pairs may use another color from that NCGR entry's shared palette even when that color is absent from the one rendered frame. The final encoder/ROM audit is authoritative for those recovered pairs.

TRAINING GUIDANCE
- Do not mix Japanese source cells into an English style LoRA target set.
- Train on completed English cells plus English Dusk references if the objective is English DS UI style.
- Keep paired source/English images separately for future image-to-image research.
- Tiny UI images should be enlarged only with nearest-neighbor for training; originals remain untouched.
"""
    (OUTPUT / "00_READ_ME_FIRST.txt").write_text(readme, encoding="utf-8")

    launcher = f'''@echo off
"{PIXELFORGE / '.venv' / 'Scripts' / 'pythonw.exe'}" "{PIXELFORGE / 'scripts' / 'ui_localizer.py'}"
'''
    (OUTPUT / "OPEN DS UI LOCALIZER.cmd").write_text(launcher, encoding="utf-8")

    # Keep the training handoff isolated from 00_library_raw so a currently
    # running job cannot see new files. The user can copy refs after it ends.
    if PIXELFORGE.exists():
        reset_folder(PIXELFORGE_PACK)
        for source in OUTPUT.rglob("*"):
            if source.is_file():
                target = PIXELFORGE_PACK / source.relative_to(OUTPUT)
                copy_file(source, target)

    with zipfile.ZipFile(ZIP_OUTPUT, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for source in sorted(OUTPUT.rglob("*")):
            if source.is_file():
                archive.write(source, Path(OUTPUT.name) / source.relative_to(OUTPUT))

    print(json.dumps({"output": str(OUTPUT), "zip": str(ZIP_OUTPUT), "pixelforge_copy": str(PIXELFORGE_PACK), **manifest}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
