from __future__ import annotations

import argparse
from pathlib import Path

from .environments import extract_backgrounds


def main() -> int:
    parser = argparse.ArgumentParser(description="Render Nitro background triplets")
    parser.add_argument("rom", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    manifest = extract_backgrounds(args.rom.resolve(), args.output.resolve())
    print(f"Rendered {manifest['rendered']} backgrounds; {manifest['failed']} failed")
    print(args.output.resolve() / "manifest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
