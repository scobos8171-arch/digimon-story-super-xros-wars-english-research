from __future__ import annotations

import argparse
import json
from pathlib import Path

from .nds import NdsRom


def main() -> int:
    parser = argparse.ArgumentParser(description="Export the SDAT from a locally owned ROM")
    parser.add_argument("rom", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    rom = NdsRom(args.rom.resolve())
    item = next((entry for entry in rom.files if entry.path.casefold().endswith(".sdat")), None)
    if item is None:
        raise ValueError(f"No SDAT archive found in {args.rom}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(rom.read(item))
    manifest = {
        "source_rom": args.rom.name,
        "game_code": rom.header.game_code,
        "source_path": item.path,
        "output": args.output.name,
    }
    args.output.with_suffix(".json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
