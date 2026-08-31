from __future__ import annotations

import argparse
from pathlib import Path

from .audio import extract_dusk_sfx


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract locally owned Dusk SDAT samples")
    parser.add_argument("rom", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    catalog = extract_dusk_sfx(args.rom.resolve(), args.output.resolve())
    direct = sum(bool(item["direct_sample"]) for item in catalog["sequences"])
    print(
        f"Extracted {len(catalog['samples'])} Dusk SE samples; "
        f"{direct} sequences map directly to a sample"
    )
    print(args.output.resolve() / "catalog.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
