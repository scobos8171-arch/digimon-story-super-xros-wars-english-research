"""Build a conservative Xros Wars UI-sprite English patch.

This script starts from the battle-safe Xros ROM and only ports sprite entries
where the Japanese Lost Evolution asset exactly matches the Xros asset.  That
keeps the patch narrow: if an entry cannot be proven to be the same source
graphic, it is skipped and reported instead of guessed.
"""

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
from rom_research.xros_pak import (  # noqa: E402
    XrosPak,
    build_xros_pak,
    find_nitro_file,
    read_nitro_file,
)


SPRITE_ARCHIVES = {
    "graphics": "SPR_NCGR.PAK",
    "cells": "SPR_NCER.PAK",
}

# Lost JP entry -> Xros entry, identified by exact Japanese graphics matches.
VERIFIED_MATCHES = {
    67: [74],
    68: [75],
    90: [100],
    95: [105],
    96: [106],
    189: [197, 228],
    1689: [1959],
    1690: [1951],
    1692: [1960],
    1693: [1947],
    1694: [1961],
    1695: [1948],
    1698: [1962],
    1699: [1949],
    1715: [1955],
    1716: [1943],
    1717: [1946],
    1718: [1954],
    1719: [1958],
    1722: [1944],
    2889: [2217],
    2892: [2245],
    2893: [2246],
    2985: [111],
    2986: [112],
    2987: [113],
    2988: [114],
    2989: [115],
    2990: [116],
    2991: [117],
    2992: [118],
    2993: [119],
    2994: [120],
    2998: [96],
    2999: [97],
    3001: [98],
    3003: [2224],
}


def _read_archives(rom_path: Path) -> dict[str, XrosPak]:
    with rom_path.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        return {
            kind: XrosPak.from_bytes(
                read_nitro_file(handle, find_nitro_file(files, archive_name))
            )
            for kind, archive_name in SPRITE_ARCHIVES.items()
        }


def _arm9_range(rom_data: bytes) -> tuple[int, int]:
    class Reader:
        def __init__(self, data: bytes):
            self.data = data
            self.pos = 0

        def seek(self, pos: int) -> int:
            self.pos = pos
            return pos

        def read(self, size: int = -1) -> bytes:
            if size < 0:
                size = len(self.data) - self.pos
            result = self.data[self.pos:self.pos + size]
            self.pos += len(result)
            return result

    header = read_header(Reader(rom_data))
    start = int(header["arm9_offset"])
    end = start + int(header["arm9_size"])
    return start, end


def build(
    source: Path,
    lost_japanese: Path,
    lost_english: Path,
    output: Path,
    manifest: Path,
) -> dict[str, object]:
    source_archives = _read_archives(source)
    lost_jp_archives = _read_archives(lost_japanese)
    lost_en_archives = _read_archives(lost_english)

    replacements: dict[str, list[bytes]] = {
        kind: [archive.unpacked_data(index) for index in range(len(archive.entries))]
        for kind, archive in source_archives.items()
    }

    applied: list[dict[str, int | str]] = []
    skipped: list[dict[str, int | str]] = []
    for lost_index, xros_indices in VERIFIED_MATCHES.items():
        for xros_index in xros_indices:
            for kind in SPRITE_ARCHIVES:
                source_raw = source_archives[kind].unpacked_data(xros_index)
                lost_jp_raw = lost_jp_archives[kind].unpacked_data(lost_index)
                lost_en_raw = lost_en_archives[kind].unpacked_data(lost_index)
                if source_raw != lost_jp_raw:
                    skipped.append(
                        {
                            "kind": kind,
                            "lost_index": lost_index,
                            "xros_index": xros_index,
                            "reason": "source no longer matches Lost JP donor",
                        }
                    )
                    continue
                if lost_en_raw == lost_jp_raw:
                    skipped.append(
                        {
                            "kind": kind,
                            "lost_index": lost_index,
                            "xros_index": xros_index,
                            "reason": "Lost English entry is identical",
                        }
                    )
                    continue
                replacements[kind][xros_index] = lost_en_raw
                applied.append(
                    {
                        "kind": kind,
                        "lost_index": lost_index,
                        "xros_index": xros_index,
                    }
                )

    nitro_replacements = {
        archive_name: build_xros_pak(replacements[kind])
        for kind, archive_name in SPRITE_ARCHIVES.items()
        if any(item["kind"] == kind for item in applied)
    }
    if not nitro_replacements:
        raise ValueError("No verified UI sprite replacements were applicable")

    source_data = source.read_bytes()
    patched = replace_nitrofs_files(source_data, nitro_replacements)
    arm9_start, arm9_end = _arm9_range(source_data)
    if patched[arm9_start:arm9_end] != source_data[arm9_start:arm9_end]:
        raise AssertionError("ARM9 changed during a data-only UI sprite patch")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(patched)
    result: dict[str, object] = {
        "source_rom": str(source.resolve()),
        "lost_japanese_donor": str(lost_japanese.resolve()),
        "lost_english_donor": str(lost_english.resolve()),
        "output_rom": str(output.resolve()),
        "source_sha256": hashlib.sha256(source_data).hexdigest(),
        "output_sha256": hashlib.sha256(patched).hexdigest(),
        "patched_archives": sorted(nitro_replacements),
        "applied": applied,
        "skipped": skipped,
        "arm9_unchanged": True,
    }
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("lost_japanese", type=Path)
    parser.add_argument("lost_english", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    result = build(
        args.source,
        args.lost_japanese,
        args.lost_english,
        args.output,
        args.manifest,
    )
    print(
        f"Built {args.output}; applied {len(result['applied'])} sprite edits; "
        f"SHA-256 {result['output_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
