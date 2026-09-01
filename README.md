# Digimon Story: Super Xros Wars — English Research Project

Community tooling, documentation, and reproducible research for translating and
reverse-engineering the Nintendo DS game **Digimon Story: Super Xros Wars Blue**.

This repository exists so the localization and decompilation work can continue
in public. It contains source code, formats, offsets, workflows, build metadata,
and research notes. It does **not** contain a game ROM, save state, BIOS, firmware,
or extracted copyrighted game assets.

## Current milestone

The current private test build is **v147**. It combines the stable v142 base,
boot-safe moving menu text, both localized Taiki cut-ins, the corrected SKIP
button, artist-updated command buttons, and the artist-redrawn Battle Results
header.

Reproducibility hashes:

- Required clean Blue ROM SHA-256: `73A5C90ED2D507A337152D73620C235D8331B4ACC0E8AA6E2CB99D62E81F49FB`
- Expected v145 SHA-256: `A1E41504B6EBCD483EACEA36C0E035AA105B80BBB19668F4FF3E4D57BE14D97F`
- v147 is a private test build based on v145. Its source graphic is documented
  in [the v147 Battle Results contribution](assets/contributions/SoraLeon/battle-results-header/README.md).

The distributable binary patch and cross-platform patch instructions will live
under `release/v145/`. The complete ROM is intentionally excluded.

New contributors should start with the [v145 final-layer build guide](docs/V145_FINAL_LAYER_BUILD.md)
and the [screen-by-screen localization status map](research/LOCALIZATION_STATUS.md).

## How to help

Pick a workstream:

1. **Localization QA** — capture untranslated text with a screenshot, location,
   reproduction steps, and—when useful—a DeSmuME state kept off GitHub.
2. **Runtime research** — identify text buffers, VRAM loads, overlays, archive
   entries, and code paths; submit reproducible evidence rather than guesses.
3. **Graphics** — edit native-size RGBA exports without resizing, flattening,
   palette expansion, or canvas changes.
4. **Decompilation** — name functions and structures, document calling
   conventions, and convert verified behavior into readable source.
5. **Tooling** — make the extraction, matching, validation, and patch workflows
   portable and easier to run.

Read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting work.

## Repository map

- `docs/` — technical findings and localization notes.
- `rom_research/` — NitroFS, Xros PAK, sprite, message, and ROM patch primitives.
- `tools/nds_decompiler/` — save-state extraction and runtime analysis.
- `tools/rom_importer/` — Nitro format and archive inspection tools.
- `tools/recovery/` — Xros-specific localization, graphics, and recovery scripts.
- `research/` — community-maintained evidence tables and progress tracking.
- `release/` — patch metadata and legal binary-patch releases; never full ROMs.

## Research standard

Every technical claim should identify its evidence:

- ROM version and SHA-256;
- file/archive and entry index;
- address or file offset;
- capture/state context;
- exact reproduction command;
- confidence level: confirmed, strong inference, or hypothesis.

This prevents unverified guesses from becoming permanent project lore.

## Legal and project status

This is an unofficial, non-commercial fan research project. Digimon and all
related game content belong to their respective owners. Contributors must use
their own legally obtained copy of the game. Do not upload ROMs, save states,
BIOS/firmware, decrypted proprietary binaries, or bulk extracted game assets.

## Credits

Project direction and localization: **scobos8171-arch** and contributors.

Art/localization contribution credit: **SoraLeon**, for collaboration,
localization assistance, and the v147 Battle Results header artwork.
