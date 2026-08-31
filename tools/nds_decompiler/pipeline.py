from __future__ import annotations

import hashlib
import json
import re
import struct
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from tools.rom_importer.nds import NdsRom, decompress_blz


def _u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _slug(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip()).strip("._")
    return value or "nds_game"


@dataclass(frozen=True)
class ArmHeader:
    kind: str
    rom_offset: int
    entry_address: int
    ram_address: int
    stored_size: int


@dataclass(frozen=True)
class OverlayRecord:
    processor: str
    overlay_id: int
    ram_address: int
    ram_size: int
    bss_size: int
    static_init_start: int
    static_init_end: int
    file_id: int
    compressed_size: int
    flags: int
    output_file: str
    sha256: str


def parse_arm_headers(header: bytes) -> tuple[ArmHeader, ArmHeader]:
    if len(header) < 0x200:
        raise ValueError("Nintendo DS header is truncated")
    return (
        ArmHeader("arm9", _u32(header, 0x20), _u32(header, 0x24), _u32(header, 0x28), _u32(header, 0x2C)),
        ArmHeader("arm7", _u32(header, 0x30), _u32(header, 0x34), _u32(header, 0x38), _u32(header, 0x3C)),
    )


def _try_decompress_arm9(data: bytes) -> tuple[bytes, bool]:
    try:
        decoded = decompress_blz(data)
    except ValueError:
        return data, False
    return (decoded, True) if len(decoded) > len(data) else (data, False)


def _extract_overlay_table(
    rom: NdsRom,
    rom_bytes: bytes,
    *,
    processor: str,
    table_offset: int,
    table_size: int,
    output: Path,
) -> list[OverlayRecord]:
    if table_size == 0:
        return []
    if table_size % 0x20 or table_offset + table_size > len(rom_bytes):
        raise ValueError(f"{processor.upper()} overlay table is malformed")
    files_by_id = {item.file_id: item for item in rom.files}
    records: list[OverlayRecord] = []
    overlay_dir = output / "binaries" / "overlays" / processor
    overlay_dir.mkdir(parents=True, exist_ok=True)
    for cursor in range(table_offset, table_offset + table_size, 0x20):
        values = struct.unpack_from("<8I", rom_bytes, cursor)
        overlay_id, ram_address, ram_size, bss_size, init_start, init_end, file_id, packed = values
        nitro_file = files_by_id.get(file_id)
        if nitro_file is None:
            raise ValueError(f"{processor} overlay {overlay_id} references missing file {file_id}")
        stored = rom.read(nitro_file)
        compressed_size = packed & 0xFFFFFF
        flags = packed >> 24
        decoded = decompress_blz(stored) if flags & 1 else stored
        if len(decoded) != ram_size:
            raise ValueError(
                f"{processor} overlay {overlay_id} decoded to 0x{len(decoded):X}; expected 0x{ram_size:X}"
            )
        filename = f"overlay_{overlay_id:04d}_0x{ram_address:08X}.bin"
        target = overlay_dir / filename
        target.write_bytes(decoded)
        records.append(
            OverlayRecord(
                processor=processor,
                overlay_id=overlay_id,
                ram_address=ram_address,
                ram_size=ram_size,
                bss_size=bss_size,
                static_init_start=init_start,
                static_init_end=init_end,
                file_id=file_id,
                compressed_size=compressed_size,
                flags=flags,
                output_file=target.relative_to(output).as_posix(),
                sha256=hashlib.sha256(decoded).hexdigest(),
            )
        )
    return records


def _analysis_programs(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for executable in manifest["executables"]:
        result.append(
            {
                "name": executable["kind"],
                "processor": executable["kind"],
                "language": "ARM:LE:32:v5t" if executable["kind"] == "arm9" else "ARM:LE:32:v4t",
                "base_address": executable["ram_address"],
                "entry_address": executable["entry_address"],
                "static_init_start": 0,
                "static_init_end": 0,
                "file": executable["output_file"],
            }
        )
    for overlay in manifest["overlays"]:
        result.append(
            {
                "name": f"{overlay['processor']}_overlay_{overlay['overlay_id']:04d}",
                "processor": overlay["processor"],
                "language": "ARM:LE:32:v5t" if overlay["processor"] == "arm9" else "ARM:LE:32:v4t",
                "base_address": overlay["ram_address"],
                "entry_address": 0,
                "static_init_start": overlay["static_init_start"],
                "static_init_end": overlay["static_init_end"],
                "file": overlay["output_file"],
            }
        )
    return result


def extract_rom(rom_path: Path, output: Path, *, extract_nitrofs: bool = True) -> dict[str, Any]:
    rom_path = Path(rom_path).resolve()
    output = Path(output).resolve()
    if not rom_path.is_file():
        raise FileNotFoundError(rom_path)
    output.mkdir(parents=True, exist_ok=True)
    rom_bytes = rom_path.read_bytes()
    rom = NdsRom(rom_path)
    arm_headers = parse_arm_headers(rom_bytes[:0x200])

    binaries = output / "binaries"
    binaries.mkdir(parents=True, exist_ok=True)
    executables: list[dict[str, Any]] = []
    for arm in arm_headers:
        stored = rom.read_range(arm.rom_offset, arm.stored_size)
        decoded, compressed = _try_decompress_arm9(stored) if arm.kind == "arm9" else (stored, False)
        target = binaries / f"{arm.kind}_0x{arm.ram_address:08X}.bin"
        target.write_bytes(decoded)
        record = asdict(arm)
        record.update(
            {
                "decoded_size": len(decoded),
                "blz_decompressed": compressed,
                "output_file": target.relative_to(output).as_posix(),
                "sha256": hashlib.sha256(decoded).hexdigest(),
            }
        )
        executables.append(record)

    overlays: list[OverlayRecord] = []
    overlays.extend(
        _extract_overlay_table(
            rom,
            rom_bytes,
            processor="arm9",
            table_offset=_u32(rom_bytes, 0x50),
            table_size=_u32(rom_bytes, 0x54),
            output=output,
        )
    )
    overlays.extend(
        _extract_overlay_table(
            rom,
            rom_bytes,
            processor="arm7",
            table_offset=_u32(rom_bytes, 0x58),
            table_size=_u32(rom_bytes, 0x5C),
            output=output,
        )
    )

    nitrofs_count = 0
    if extract_nitrofs:
        nitrofs_count = rom.extract(output / "nitrofs")

    manifest: dict[str, Any] = {
        "schema_version": 1,
        "source": {
            "filename": rom_path.name,
            "sha256": _sha256(rom_path),
            "size": rom_path.stat().st_size,
            "title": rom.header.title,
            "game_code": rom.header.game_code,
            "maker_code": rom.header.maker_code,
        },
        "executables": executables,
        "overlays": [asdict(record) for record in overlays],
        "nitrofs_file_count": nitrofs_count,
        "notes": [
            "Raw ARM programs and overlays are separate because DS overlays may share RAM addresses.",
            "Generated data is for local analysis of a user-supplied cartridge dump.",
        ],
    }
    manifest["analysis_programs"] = _analysis_programs(manifest)
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def default_output_for(rom_path: Path, root: Path) -> Path:
    return Path(root) / _slug(Path(rom_path).stem)
