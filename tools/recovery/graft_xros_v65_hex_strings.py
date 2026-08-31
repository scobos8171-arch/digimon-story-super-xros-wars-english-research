#!/usr/bin/env python3
"""Graft the two verified v65 ARM9 UI strings onto a derivative of v64."""

from __future__ import annotations
import argparse, hashlib, json, struct, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "work" / "DigimonNDSRomEditor-master"))
from rom_research.nds_inventory import read_header  # noqa: E402
from rom_research.nds_code_compression import decompress_blz  # noqa: E402


def crc16(data: bytes | bytearray) -> int:
    value = 0xFFFF
    for byte in data:
        value ^= byte
        for _ in range(8): value = (value >> 1) ^ (0xA001 if value & 1 else 0)
    return value & 0xFFFF


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base", type=Path); parser.add_argument("v65", type=Path); parser.add_argument("output", type=Path); parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    base = bytearray(args.base.read_bytes())
    donor = args.v65.read_bytes()
    with args.base.open("rb") as handle: bh = read_header(handle)
    with args.v65.open("rb") as handle: dh = read_header(handle)
    if bh["arm9_offset"] != dh["arm9_offset"]: raise ValueError("ARM9 offsets differ")
    arm9_offset = int(bh["arm9_offset"]); base_size = int(bh["arm9_size"]); donor_size = int(dh["arm9_size"])
    donor_arm9 = donor[arm9_offset:arm9_offset + donor_size]
    # Verify donor is exactly the documented two-string delta after decompression.
    base_arm9 = decompress_blz(bytes(base[arm9_offset:arm9_offset + base_size])); donor_dec = decompress_blz(donor_arm9)
    diffs = [index for index, (left, right) in enumerate(zip(base_arm9, donor_dec)) if left != right]
    if not diffs or min(diffs) != 0x10BEE4 or max(diffs) != 0x1130A1: raise ValueError("v65 ARM9 is not the expected string-only donor")
    base[arm9_offset:arm9_offset + donor_size] = donor_arm9
    base[arm9_offset + donor_size:arm9_offset + base_size] = b"\xFF" * (base_size - donor_size)
    struct.pack_into("<I", base, 0x2C, donor_size)
    struct.pack_into("<H", base, 0x15E, crc16(base[:0x15E]))
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_bytes(base)
    with args.output.open("rb") as handle:
        header = read_header(handle); handle.seek(int(header["arm9_offset"])); verified = decompress_blz(handle.read(int(header["arm9_size"])))
    if verified[0x10BEE4:0x10BF2F].split(b"\0",1)[0] != b"SELECT WITH THE D-PAD. PRESS A TO CONFIRM.": raise AssertionError("Banner verification failed")
    if verified[0x113098:0x1130A2].split(b"\0",1)[0] != b"FUNDS": raise AssertionError("Funds verification failed")
    report={"base":str(args.base.resolve()),"donor":str(args.v65.resolve()),"output":str(args.output.resolve()),"strings":{"banner":"SELECT WITH THE D-PAD. PRESS A TO CONFIRM.","funds":"FUNDS"},"arm9_compressed_bytes":donor_size,"sha256":hashlib.sha256(base).hexdigest()}
    args.manifest.parent.mkdir(parents=True,exist_ok=True);args.manifest.write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))


if __name__ == '__main__': main()
