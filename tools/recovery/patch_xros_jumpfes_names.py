"""Patch battle-demo name strings stored outside the normal message packs."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
ROM_RESEARCH = REPO_ROOT / "work" / "DigimonNDSRomEditor-master"
if str(ROM_RESEARCH) not in sys.path:
    sys.path.insert(0, str(ROM_RESEARCH))

from rom_research.nds_inventory import read_header, read_nitrofs  # noqa: E402
from rom_research.nitrofs_patch import replace_nitrofs_files  # noqa: E402
from rom_research.xros_pak import find_nitro_file, read_nitro_file  # noqa: E402


TARGET_FILE = "BLUE_JUMPFES2010.BIN"
PATCHES = {
    "\u30b7\u30e3\u30a6\u30c8\u30e2\u30f3": "Shoutmon",
    "\u30d0\u30ea\u30b9\u30bf\u30e2\u30f3": "Ballistamon",
    "\u30c9\u30eb\u30eb\u30e2\u30f3": "Dorulumon",
}


class BytesReader:
    def __init__(self, data: bytes | bytearray):
        self.data = data
        self.pos = 0

    def seek(self, pos: int) -> int:
        self.pos = pos
        return pos

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = len(self.data) - self.pos
        result = bytes(self.data[self.pos:self.pos + size])
        self.pos += len(result)
        return result


def _arm9_range(rom_data: bytes) -> tuple[int, int]:
    header = read_header(BytesReader(rom_data))
    start = int(header["arm9_offset"])
    return start, start + int(header["arm9_size"])


def build(source: Path, output: Path, manifest: Path) -> dict[str, object]:
    with source.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        target = find_nitro_file(files, TARGET_FILE)
        original = read_nitro_file(handle, target)

    patched = bytearray(original)
    applied: list[dict[str, int | str]] = []
    for japanese, english in PATCHES.items():
        needle = japanese.encode("shift_jis")
        replacement = english.encode("shift_jis")
        if len(replacement) > len(needle):
            raise ValueError(f"{english!r} is longer than {japanese!r}")
        replacement = replacement + b" " * (len(needle) - len(replacement))
        start = 0
        while True:
            offset = original.find(needle, start)
            if offset < 0:
                break
            patched[offset:offset + len(needle)] = replacement
            applied.append(
                {
                    "file": TARGET_FILE,
                    "offset": f"0x{offset:X}",
                    "japanese": japanese,
                    "english": english,
                    "bytes": len(needle),
                }
            )
            start = offset + len(needle)

    if not applied:
        raise ValueError("No JUMPFES battle names were found to patch")

    source_data = source.read_bytes()
    rom = replace_nitrofs_files(source_data, {TARGET_FILE: bytes(patched)})
    arm9_start, arm9_end = _arm9_range(source_data)
    if rom[arm9_start:arm9_end] != source_data[arm9_start:arm9_end]:
        raise AssertionError("ARM9 changed during JUMPFES name patch")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(rom)
    result: dict[str, object] = {
        "source_rom": str(source.resolve()),
        "output_rom": str(output.resolve()),
        "source_sha256": hashlib.sha256(source_data).hexdigest(),
        "output_sha256": hashlib.sha256(rom).hexdigest(),
        "target_file": TARGET_FILE,
        "applied": applied,
        "arm9_unchanged": True,
    }
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    result = build(args.source, args.output, args.manifest)
    print(
        f"Built {args.output}; patched {len(result['applied'])} names; "
        f"SHA-256 {result['output_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
