"""Build a diagnostic Xros ROM by copying named NitroFS files from a donor."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from build_xros_custom_ui_rom import (
    arm9_slice,
    find_nitro_file,
    read_header,
    read_nitro_file,
    read_nitrofs,
    replace_nitrofs_files,
)


def files_from(rom: Path, names: list[str]) -> dict[str, bytes]:
    with rom.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        return {name: read_nitro_file(handle, find_nitro_file(files, name)) for name in names}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("donor", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("--file", action="append", required=True)
    args = parser.parse_args()

    base = args.base.read_bytes()
    donor_files = files_from(args.donor, args.file)
    patched = replace_nitrofs_files(base, donor_files)
    if arm9_slice(base) != arm9_slice(patched):
        raise AssertionError("ARM9 changed during archive mix")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(patched)
    report = {
        "base": str(args.base.resolve()),
        "donor": str(args.donor.resolve()),
        "output": str(args.output.resolve()),
        "base_sha256": hashlib.sha256(base).hexdigest(),
        "output_sha256": hashlib.sha256(patched).hexdigest(),
        "copied_files": args.file,
        "arm9_unchanged": True,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
