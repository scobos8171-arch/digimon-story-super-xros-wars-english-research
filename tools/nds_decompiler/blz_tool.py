from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

# Support both documented invocations:
#
#   python -m tools.nds_decompiler.blz_tool ...
#   python tools/nds_decompiler/blz_tool.py ...
#
# The latter previously failed because Python placed only this script's folder
# on sys.path.  Add the repository root before importing the shared decoder.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.rom_importer.nds import decompress_blz


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def decompress_file(source: Path, output: Path, *, keep_arm9_prefix: bool) -> dict[str, object]:
    raw = source.read_bytes()
    decoded = decompress_blz(raw)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(decoded)
    return {
        "source": str(source.resolve()),
        "output": str(output.resolve()),
        "source_size": len(raw),
        "output_size": len(decoded),
        "source_sha256": _sha256(raw),
        "output_sha256": _sha256(decoded),
        "arm9_mode": keep_arm9_prefix,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Decompress Nintendo DS BLZ ARM9/overlay files used by Digimon Story games."
    )
    parser.add_argument("source", type=Path, help="Compressed arm9.bin or overlay9_*.bin file.")
    parser.add_argument("output", type=Path, help="Where to write the decompressed binary.")
    parser.add_argument(
        "--arm9",
        action="store_true",
        help="Mark the input as ARM9 in the JSON report. Output bytes use the verified DS BLZ decode.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    print(json.dumps(decompress_file(args.source, args.output, keep_arm9_prefix=args.arm9), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
