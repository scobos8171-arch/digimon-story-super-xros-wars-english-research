from __future__ import annotations

import re
import shutil
import hashlib
from pathlib import Path


UI_ROOT = Path(r"C:\Users\YOUR_NAME\pixelforge\xros_ui_localization_pack\07_MANUAL_EDIT_ALL_REMAINING_V2\EDIT_THESE_NATIVE_PNGS")
COMPLETED_ROOT = Path(r"C:\Users\YOUR_NAME\pixelforge\xros_ui_localization_pack\01_WORK_COMPLETED_PAIRED")
ORIGINAL_ROOT = Path(r"C:\Users\YOUR_NAME\pixelforge\xros_ui_localization_pack\02_NEEDS_LOCALIZATION")
TITLE_ROOT = Path(r"C:\Users\YOUR_NAME\pixelforge\xros_ui_localization_pack\08_TITLE_SCREEN_MANUAL_EDIT")
STAGE = Path(r"C:\Users\YOUR_NAME\Documents\Codex\2026-07-24\c-users-scobo-downloads-download-digimon\work\xros_ui_v35_user_edits")
CELL_RE = re.compile(r"cell_(\d+)", re.IGNORECASE)
ENTRY_RE = re.compile(r"entry_(\d+)", re.IGNORECASE)


def stage(source: Path) -> tuple[int, int, Path]:
    entry_match = next((ENTRY_RE.fullmatch(part) for part in source.parts if ENTRY_RE.fullmatch(part)), None)
    cell_match = CELL_RE.search(source.stem)
    if not cell_match:
        cell_match = next((CELL_RE.fullmatch(part) for part in source.parts if CELL_RE.fullmatch(part)), None)
    if not entry_match or not cell_match:
        raise ValueError(f"Cannot identify entry/cell from {source}")
    entry, cell = int(entry_match.group(1)), int(cell_match.group(1))
    folder = STAGE / f"entry_{entry:04d}" / f"cell_{cell:02d}"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / "english_completed.png"
    shutil.copy2(source, target)
    return entry, cell, target


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ids(path: Path) -> tuple[int, int]:
    entry_match = next((ENTRY_RE.fullmatch(part) for part in path.parts if ENTRY_RE.fullmatch(part)), None)
    cell_match = CELL_RE.search(path.stem)
    if not cell_match:
        cell_match = next((CELL_RE.fullmatch(part) for part in path.parts if CELL_RE.fullmatch(part)), None)
    if not entry_match or not cell_match:
        raise ValueError(f"Cannot identify entry/cell from {path}")
    return int(entry_match.group(1)), int(cell_match.group(1))


def main() -> None:
    if STAGE.exists():
        shutil.rmtree(STAGE)
    selected: list[Path] = []
    # Completed replacements are authoritative regardless of their timestamp.
    # The old timestamp-only staging silently omitted valid hand-edited artwork.
    # Older approved Aseprite pairs store the finished bitmap under this name.
    # The parent folder and metadata mark these as completed work.
    selected.extend(COMPLETED_ROOT.rglob("source_or_predecessor.png"))
    # A dedicated English output takes precedence when both conventions exist.
    selected.extend(COMPLETED_ROOT.rglob("english_completed.png"))
    for path in UI_ROOT.rglob("*.png"):
        entry, cell = ids(path)
        original = ORIGINAL_ROOT / f"entry_{entry:04d}" / f"cell_{cell:02d}_source_japanese.png"
        # Include every hand-edited cell. An unchanged source is deliberately
        # omitted because rebuilding it adds risk without changing the game.
        if not original.exists() or digest(path) != digest(original):
            selected.append(path)
    selected.extend(TITLE_ROOT.glob("entry_*/cell_*_source.png"))

    seen: set[tuple[int, int]] = set()
    records = []
    for source in selected:
        entry, cell, target = stage(source)
        if (entry, cell) in seen:
            # A later manual-edit file supersedes an older completed-library file.
            records.append(f"{entry:04d}:{cell:02d} superseded by {source} -> {target}")
            continue
        seen.add((entry, cell))
        records.append(f"{entry:04d}:{cell:02d} <- {source} -> {target}")
    (STAGE / "STAGED_FILES.txt").write_text("\n".join(records) + "\n", encoding="utf-8")
    print(f"Staged {len(records)} user-edited cells in {STAGE}")


if __name__ == "__main__":
    main()
