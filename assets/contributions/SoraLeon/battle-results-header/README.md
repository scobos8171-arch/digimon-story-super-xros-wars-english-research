# Battle Results Header — SoraLeon contribution

Credit: **SoraLeon** — localization collaboration and header-art contribution.

This folder contains the editable source and PNG preview for the v147 English
`BATTLE RESULTS` header. The files are native **168×32 RGBA** canvases; do not
resize or flatten them before re-importing.

## Safe import target

| Field | Value |
| --- | --- |
| Base build | v145 (`A1E41504…BE14D97F`) |
| ROM file | `BG_NCGR.PAK` |
| Archive entry | `307` |
| Runtime layer | Main-engine BG2 |
| Title tile rectangle | x=6..20, y=1..3 |
| Unchanged | BG map, palette, all other entries, ARM9, battle values |

## Rebuild

From a legally obtained private v145 ROM and a private captured Battle Results
state, export the Aseprite file then run:

```powershell
python tools/recovery/aseprite_to_png.py assets/contributions/SoraLeon/battle-results-header/Sprite-0003.aseprite work/header.png
python tools/recovery/patch_xros_battle_results_header.py <v145.nds> <battle-results-state-dir> <v147.nds> <qa-dir> --art work/header.png
```

The tool rejects a canvas other than 168×32 and verifies its source tiles
against the captured state before writing the replacement. No ROM, state, or
bulk-extracted game archive is stored in this repository.
