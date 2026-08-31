# Tooling guide

## `rom_research/`

Core reusable readers and writers for Nintendo DS NitroFS, Xros PAK archives,
sprites, messages, overlays, compression, and ROM rebuilding.

## `tools/nds_decompiler/`

Runtime research utilities. `state_memory.py` extracts named memory blocks from
a locally supplied DeSmuME state. Never commit those extracted blocks.

## `tools/rom_importer/`

Archive/Nitro-format parsers and import helpers used for offline inspection.

## `tools/recovery/`

Historical and current Xros localization experiments. Many `patch_vNNN_*`
scripts capture one verified step in the build history. Treat hard-coded build
paths as examples and migrate reusable behavior into argument-driven tools.

The current artist-PNG injectors are:

- `patch_xros_skip_button_png.py`
- `patch_xros_command_button_pngs.py`
- `patch_xros_menu_tutorial_image.py` (experimental; do not use for releases
  until its runtime tile mapping is replaced by the in-place workflow)

## Environment

Python 3.11+ and Pillow are the primary requirements. Some inventory/reporting
tools use the packages listed in `tools/rom_importer/requirements.txt`.

Always work on a copy of a legally obtained ROM and verify hashes before and
after every build.

