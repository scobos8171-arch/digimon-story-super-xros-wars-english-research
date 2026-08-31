from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .extractor import extract_batch, extract_proof, verify_extraction
from .encounters import extract_dusk_encounters
from .mechanics import extract_mechanics
from .nds import NdsRom
from .nitro import (
    parse_ncgr,
    parse_nclr,
    parse_nscr,
    render_palette_preview,
    render_screen,
    render_tileset,
)
from .profiles import detect_profile, discover_roms, species_for_rom
from .canonical import enrich as enrich_canonical
from .decomp_bridge import extract_decomp_project
from .editor_bridge import export_editor_data


def _path(value: str) -> Path:
    return Path(value).expanduser()


def _print_json(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def command_info(args: argparse.Namespace) -> int:
    rom = NdsRom(args.rom)
    profile = detect_profile(rom)
    species = species_for_rom(rom)
    _print_json(
        {
            "path": str(rom.path.resolve()),
            "title": rom.header.title,
            "game_code": rom.header.game_code,
            "profile": profile,
            "nitrofs_files": len(rom.files),
            "species": len(species),
            "first_species": [item.to_dict() for item in species[:5]],
        }
    )
    return 0


def command_unpack(args: argparse.Namespace) -> int:
    rom = NdsRom(args.rom)
    count = rom.extract(args.output, prefix=args.prefix)
    _print_json({"files_extracted": count, "output": str(args.output.resolve())})
    return 0


def command_overlays(args: argparse.Namespace) -> int:
    rom = NdsRom(args.rom)
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = []
    for overlay in rom.arm9_overlays():
        filename = f"overlay_{overlay.overlay_id:03d}_0x{overlay.ram_address:08x}.bin"
        (args.output / filename).write_bytes(overlay.data)
        manifest.append(
            {
                "overlay_id": overlay.overlay_id,
                "file": filename,
                "file_id": overlay.file_id,
                "ram_address": overlay.ram_address,
                "ram_size": overlay.ram_size,
                "bss_size": overlay.bss_size,
                "compressed_size": overlay.compressed_size,
                "flags": overlay.flags,
            }
        )
    (args.output / "overlays.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    _print_json({"overlays": len(manifest), "output": str(args.output.resolve())})
    return 0


def _load_component(path: Path) -> bytes:
    if not path.is_file():
        raise FileNotFoundError(path)
    return path.read_bytes()


def command_inspect(args: argparse.Namespace) -> int:
    args.output.mkdir(parents=True, exist_ok=True)
    ncgr = parse_ncgr(_load_component(args.ncgr))
    palette = parse_nclr(_load_component(args.nclr))
    render_tileset(ncgr, palette, columns=args.columns).save(
        args.output / "tileset.png"
    )
    render_palette_preview(palette).save(args.output / "palette.png")
    result = {
        "bpp": ncgr.bpp,
        "tiles": len(ncgr.tiles),
        "colors": len(palette),
        "tileset": "tileset.png",
        "palette": "palette.png",
    }
    if args.nscr:
        nscr = parse_nscr(_load_component(args.nscr))
        render_screen(ncgr, palette, nscr).save(args.output / "screen.png")
        result.update(
            {
                "screen": "screen.png",
                "screen_size": [nscr.width, nscr.height],
                "map_entries": len(nscr.entries),
            }
        )
    (args.output / "inspection.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    _print_json(result)
    return 0


def command_proof(args: argparse.Namespace) -> int:
    result = extract_proof(args.rom, args.name, args.output)
    _print_json(
        {
            "display_name": result["display_name"],
            "source_game": result["source_game"],
            "battle_animations": sorted(result["animations"]),
            "has_walk_animation": result["has_walk_animation"],
            "output": str(args.output.resolve()),
        }
    )
    return 0


def command_batch(args: argparse.Namespace) -> int:
    paths = list(args.rom or [])
    if args.rom_dir:
        paths.extend(discover_roms(args.rom_dir))
    unique_paths = list(dict.fromkeys(path.resolve() for path in paths))
    if not unique_paths:
        raise ValueError("No .nds files supplied; use --rom or --rom-dir")
    report = extract_batch(
        unique_paths,
        args.output,
        clean=args.clean,
        raw_components=args.raw_components,
        characters=args.characters,
    )
    _print_json(report)
    return 0


def command_verify(args: argparse.Namespace) -> int:
    result = verify_extraction(args.output)
    _print_json(result)
    return 0 if result["ok"] else 1


def command_mechanics(args: argparse.Namespace) -> int:
    paths = list(args.rom or [])
    if args.rom_dir:
        paths.extend(discover_roms(args.rom_dir))
    unique_paths = list(dict.fromkeys(path.resolve() for path in paths))
    if not unique_paths:
        raise ValueError("No .nds files supplied; use --rom or --rom-dir")
    _print_json(extract_mechanics(unique_paths, args.output))
    return 0


def command_encounters(args: argparse.Namespace) -> int:
    roster_path = args.output / "roster.json"
    if not roster_path.is_file():
        raise FileNotFoundError(roster_path)
    _print_json(
        extract_dusk_encounters(
            args.rom, args.output / "encounters" / "dusk.json", roster_path
        )
    )
    return 0


def command_canonical(args: argparse.Namespace) -> int:
    _print_json(enrich_canonical(args.output, workers=args.workers))
    return 0


def command_editor_data(args: argparse.Namespace) -> int:
    _print_json(
        export_editor_data(
            args.rom,
            args.editor_root,
            args.output,
            include_strings=args.strings,
        )
    )
    return 0


def command_decomp_extract(args: argparse.Namespace) -> int:
    _print_json(extract_decomp_project(args.rom, args.dsd, args.output))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rom-importer",
        description=(
            "Extract normalized, local-only assets from user-supplied Digimon DS ROM dumps."
        ),
    )
    commands = parser.add_subparsers(dest="command", required=True)

    info = commands.add_parser("info", help="identify a ROM and summarize its roster")
    info.add_argument("rom", type=_path)
    info.set_defaults(handler=command_info)

    unpack = commands.add_parser("unpack", help="unpack the ROM's NitroFS")
    unpack.add_argument("rom", type=_path)
    unpack.add_argument("output", type=_path)
    unpack.add_argument("--prefix", default="", help="optional NitroFS subtree")
    unpack.set_defaults(handler=command_unpack)

    overlays = commands.add_parser(
        "overlays", help="decode ARM9 code overlays for format research"
    )
    overlays.add_argument("rom", type=_path)
    overlays.add_argument("output", type=_path)
    overlays.set_defaults(handler=command_overlays)

    inspect = commands.add_parser("inspect", help="preview NCGR/NCLR/NSCR files")
    inspect.add_argument("--ncgr", type=_path, required=True)
    inspect.add_argument("--nclr", type=_path, required=True)
    inspect.add_argument("--nscr", type=_path)
    inspect.add_argument("--columns", type=int)
    inspect.add_argument("--output", "-o", type=_path, required=True)
    inspect.set_defaults(handler=command_inspect)

    proof = commands.add_parser("proof", help="extract one named Digimon")
    proof.add_argument("rom", type=_path)
    proof.add_argument("--name", required=True)
    proof.add_argument("--output", "-o", type=_path, required=True)
    proof.set_defaults(handler=command_proof)

    batch = commands.add_parser("batch", help="extract and dedupe the full union roster")
    batch.add_argument("--rom", action="append", type=_path)
    batch.add_argument("--rom-dir", type=_path)
    batch.add_argument("--output", "-o", type=_path, default=Path("work/extracted"))
    batch.add_argument("--clean", action="store_true")
    batch.add_argument("--raw-components", action="store_true")
    batch.add_argument("--characters", action="store_true")
    batch.set_defaults(handler=command_batch)

    mechanics = commands.add_parser(
        "mechanics", help="extract normalized stats, skills, growth, and evolution routes"
    )
    mechanics.add_argument("--rom", action="append", type=_path)
    mechanics.add_argument("--rom-dir", type=_path)
    mechanics.add_argument(
        "--output", "-o", type=_path, default=Path("work/extracted")
    )
    mechanics.set_defaults(handler=command_mechanics)

    encounters = commands.add_parser(
        "encounters", help="extract Dusk area encounter rates and weighted groups"
    )
    encounters.add_argument("rom", type=_path)
    encounters.add_argument(
        "--output", "-o", type=_path, default=Path("work/extracted")
    )
    encounters.set_defaults(handler=command_encounters)

    canonical = commands.add_parser(
        "canonical", help="enrich species attributes from a cached public reference"
    )
    canonical.add_argument(
        "--output", "-o", type=_path, default=Path("work/extracted")
    )
    canonical.add_argument("--workers", type=int, default=12)
    canonical.set_defaults(handler=command_canonical)

    editor_data = commands.add_parser(
        "editor-data",
        help="cross-check Dusk mechanics and export supplemental editor tables",
    )
    editor_data.add_argument("rom", type=_path)
    editor_data.add_argument("--editor-root", type=_path, required=True)
    editor_data.add_argument(
        "--output", "-o", type=_path, default=Path("work/extracted")
    )
    editor_data.add_argument(
        "--strings", action="store_true", help="also export every decoded string region"
    )
    editor_data.set_defaults(handler=command_editor_data)

    decomp = commands.add_parser(
        "decomp-extract",
        help="run ds-decomp against an owned ROM for ARM9/overlay research",
    )
    decomp.add_argument("rom", type=_path)
    decomp.add_argument("--dsd", type=_path, required=True)
    decomp.add_argument("--output", "-o", type=_path, required=True)
    decomp.set_defaults(handler=command_decomp_extract)

    verify = commands.add_parser("verify", help="verify an extracted asset tree")
    verify.add_argument("output", type=_path, nargs="?", default=Path("work/extracted"))
    verify.set_defaults(handler=command_verify)
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except (FileNotFoundError, ValueError, RuntimeError, IndexError) as exc:
        parser.error(str(exc))
        return 2


if __name__ == "__main__":
    sys.exit(main())
