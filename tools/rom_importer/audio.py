from __future__ import annotations

import json
import struct
import wave
from pathlib import Path
from typing import Any

from .nds import NdsRom


_IMA_STEPS = (
    7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31,
    34, 37, 41, 45, 50, 55, 60, 66, 73, 80, 88, 97, 107, 118, 130,
    143, 157, 173, 190, 209, 230, 253, 279, 307, 337, 371, 408, 449,
    494, 544, 598, 658, 724, 796, 876, 963, 1060, 1166, 1282, 1411,
    1552, 1707, 1878, 2066, 2272, 2499, 2749, 3024, 3327, 3660, 4026,
    4428, 4871, 5358, 5894, 6484, 7132, 7845, 8630, 9493, 10442,
    11487, 12635, 13899, 15289, 16818, 18500, 20350, 22385, 24623,
    27086, 29794, 32767,
)
_IMA_INDEX = (-1, -1, -1, -1, 2, 4, 6, 8)


def _clamp(value: int, low: int, high: int) -> int:
    return min(high, max(low, value))


def decode_wave_samples(wave_object: Any) -> list[int]:
    """Decode an ndspy SWAV's PCM8, PCM16, or Nintendo DS IMA-ADPCM data."""
    wave_type = int(wave_object.waveType)
    data = bytes(wave_object.data)
    if wave_type == 0:
        return [struct.unpack("b", bytes((value,)))[0] << 8 for value in data]
    if wave_type == 1:
        usable = len(data) - len(data) % 2
        return list(struct.unpack(f"<{usable // 2}h", data[:usable]))
    if wave_type != 2 or len(data) < 4:
        raise ValueError(f"Unsupported or truncated SWAV type {wave_type}")

    predictor, index = struct.unpack_from("<hB", data, 0)
    index = _clamp(index, 0, 88)
    samples = [predictor]
    # Nintendo DS ADPCM stores the low nibble before the high nibble.
    for byte in data[4:]:
        for nibble in (byte & 0x0F, byte >> 4):
            step = _IMA_STEPS[index]
            difference = step >> 3
            if nibble & 1:
                difference += step >> 2
            if nibble & 2:
                difference += step >> 1
            if nibble & 4:
                difference += step
            predictor += -difference if nibble & 8 else difference
            predictor = _clamp(predictor, -32768, 32767)
            index = _clamp(index + _IMA_INDEX[nibble & 7], 0, 88)
            samples.append(predictor)
    return samples


def write_wav(path: Path, sample_rate: int, samples: list[int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(struct.pack(f"<{len(samples)}h", *samples))


def extract_dusk_sfx(rom_path: Path, output: Path) -> dict[str, Any]:
    """Extract Dusk's SWAV samples and direct one-sample SE sequence mappings."""
    try:
        from ndspy.soundArchive import SDAT
    except ImportError as exc:  # pragma: no cover - local dependency diagnostic
        raise RuntimeError("ndspy is required to inspect Nintendo DS SDAT files") from exc

    rom = NdsRom(rom_path)
    sdat_file = next(
        (item for item in rom.files if item.path.casefold().endswith(".sdat")), None
    )
    if sdat_file is None:
        raise ValueError(f"No SDAT archive was found in {rom_path}")
    archive = SDAT(rom.read(sdat_file))
    output.mkdir(parents=True, exist_ok=True)
    samples_dir = output / "samples"
    catalog: dict[str, Any] = {
        "source_rom": rom_path.name,
        "source_game_code": rom.header.game_code,
        "source_sdat": sdat_file.path,
        "sequences": [],
        "samples": [],
    }

    sample_paths: dict[tuple[int, int], str] = {}
    for archive_id, (archive_name, wave_archive) in enumerate(archive.waveArchives):
        if wave_archive is None or not str(archive_name or "").startswith("WAVE_SE"):
            continue
        for wave_id, swav in enumerate(wave_archive.waves):
            samples = decode_wave_samples(swav)
            safe_name = str(archive_name or f"swar_{archive_id:03d}").lower()
            relative = Path("samples") / f"{archive_id:03d}_{safe_name}_{wave_id:03d}.wav"
            write_wav(output / relative, int(swav.sampleRate), samples)
            duration_ms = round(len(samples) * 1000 / max(1, int(swav.sampleRate)))
            sample_paths[(archive_id, wave_id)] = relative.as_posix()
            catalog["samples"].append(
                {
                    "wave_archive_id": archive_id,
                    "wave_archive": archive_name,
                    "wave_id": wave_id,
                    "path": relative.as_posix(),
                    "sample_rate": int(swav.sampleRate),
                    "duration_ms": duration_ms,
                    "encoding": int(swav.waveType),
                    "looped": bool(swav.isLooped),
                }
            )

    if archive.sequenceArchives and archive.sequenceArchives[0][1] is not None:
        for sequence_id, (sequence_name, sequence) in enumerate(
            archive.sequenceArchives[0][1].sequences
        ):
            bank_id = int(sequence.bankID)
            bank_name, bank = archive.banks[bank_id]
            wave_archive_ids = list(bank.waveArchiveIDs) if bank is not None else []
            direct_path = None
            if len(wave_archive_ids) == 1 and wave_archive_ids[0] is not None:
                wave_archive_id = int(wave_archive_ids[0])
                _, selected_archive = archive.waveArchives[wave_archive_id]
                if selected_archive is not None and len(selected_archive.waves) == 1:
                    direct_path = sample_paths.get((wave_archive_id, 0))
            catalog["sequences"].append(
                {
                    "id": sequence_id,
                    "name": sequence_name,
                    "bank_id": bank_id,
                    "bank": bank_name,
                    "wave_archive_ids": wave_archive_ids,
                    "direct_sample": direct_path,
                    "volume": int(sequence.volume),
                }
            )

    (output / "catalog.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return catalog
