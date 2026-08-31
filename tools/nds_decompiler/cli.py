from __future__ import annotations

import argparse
import json
from pathlib import Path

from .annotator import annotate_with_ollama, gpu_status
from .ghidra import analyze_manifest
from .pipeline import default_output_for, extract_rom


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract and analyze user-supplied Nintendo DS cartridge dumps.")
    commands = parser.add_subparsers(dest="command", required=True)

    extract = commands.add_parser("extract", help="Extract NitroFS, ARM binaries, overlays, and a memory manifest.")
    extract.add_argument("rom", type=Path)
    extract.add_argument("--output", type=Path)
    extract.add_argument("--output-root", type=Path, default=Path("work/decomp"))
    extract.add_argument("--no-nitrofs", action="store_true")

    analyze = commands.add_parser("analyze", help="Import every extracted executable into Ghidra headlessly.")
    analyze.add_argument("manifest", type=Path)
    analyze.add_argument("--ghidra", type=Path)
    analyze.add_argument("--program", action="append", help="Analyze only this named program; repeat as needed.")
    analyze.add_argument("--force", action="store_true", help="Re-analyze programs that already have exports.")

    gpu = commands.add_parser("gpu-status", help="Report whether a local NVIDIA GPU is available for AI annotation.")

    annotate = commands.add_parser("annotate", help="Ask a local Ollama coding model to annotate one pseudocode file.")
    annotate.add_argument("pseudocode", type=Path)
    annotate.add_argument("--output", type=Path, required=True)
    annotate.add_argument("--model", default="qwen2.5-coder:14b")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "extract":
        output = args.output or default_output_for(args.rom, args.output_root)
        manifest = extract_rom(args.rom, output, extract_nitrofs=not args.no_nitrofs)
        print(json.dumps({"output": str(output.resolve()), "title": manifest["source"]["title"], "overlays": len(manifest["overlays"]), "nitrofs_files": manifest["nitrofs_file_count"]}, indent=2))
        return 0
    if args.command == "analyze":
        selected = set(args.program) if args.program else None
        print(json.dumps(analyze_manifest(args.manifest, ghidra=args.ghidra, programs=selected, force=args.force), indent=2))
        return 0
    if args.command == "gpu-status":
        print(json.dumps(gpu_status(), indent=2))
        return 0
    if args.command == "annotate":
        print(json.dumps(annotate_with_ollama(args.pseudocode, args.output, model=args.model), indent=2))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
