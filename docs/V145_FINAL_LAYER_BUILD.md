# v145 final-layer build guide

This guide reproduces the **final v145 visual layer** from the verified v142
base. It is deliberately narrow: it does not claim to rebuild every earlier
localization pass from a clean ROM in one command yet.

## Required private inputs

Keep these files outside the repository:

- a legally dumped Super Xros Wars Blue ROM;
- the verified v142 base built by a maintainer;
- artist-created, native-size RGBA button PNGs.

Never commit any of them. The expected v142 source SHA-256 is recorded in
`release/v145/skip_fix_manifest.json`.

## Python environment

Use Python 3.11+ and install Pillow. The scripts also require the local
`rom_research` package in this repository and a local copy of the companion
Nitro helpers described in `docs/DIGIPAK_XROS_GRAPHICS_WORKFLOW.md`.

## Build order

1. Start with the verified v142 ROM.
2. Apply the SKIP-button patch, which edits only `SPR_NCGR.PAK`, entry `2002`,
   cell `2`.
3. Apply the final command-button patch, which edits only `SPR_NCGR.PAK`,
   entry `1971`, cells `21` through `34`.
4. Compare the generated manifests and decoded QA PNGs before distributing a
   test build.

Example commands, with private paths substituted for the placeholders:

```powershell
py tools/recovery/patch_xros_skip_button_png.py `
  PRIVATE_V142.nds PRIVATE_ASSETS/SKIP_RED.png PRIVATE_V144.nds QA/v144

py tools/recovery/patch_xros_command_button_pngs.py `
  PRIVATE_V144.nds PRIVATE_ASSETS PRIVATE_V145.nds QA/v145
```

The command-button directory must contain:

`ORDERS_A/B`, `SPECIAL_A/B`, `DIGIXROS_A/B`, `ITEMS_A/B`, `TACTICS_A/B`,
`FORMATION_A/B`, and `WAIT_A/B`, all as transparent PNGs with the original
native dimensions. The patcher rejects scaling and validates the decoded ROM
cells against the supplied art. `WAIT_A` is a documented shared-tile exception.

## Required verification

- Confirm the output SHA-256 against `release/v145/build_manifest.json`.
- Confirm that the manifests report `arm9_unchanged: true`.
- Confirm the changed archive is only `SPR_NCGR.PAK`.
- Cold boot the ROM, then open the command menu and SKIP prompt.
- Save/load using a fresh test save; do not test by overwriting a valued save.

## Related independently reproducible patches

| Feature | Script | Native target |
| --- | --- | --- |
| Both Taiki callouts | `patch_xros_taiki_digixros_cutin.py` | `SPR_NCGR.PAK` entry 1993 OBJ lettering strips |
| Menu tutorial image | `patch_xros_menu_tutorial_image.py` | `data/BG_NCGR.PAK` entry 87 + `data/BG_NSCR.PAK` entry 84 |
| Moving command banner | `patch_xros_hex_instruction_banner.py` | ARM9 CP932 slot at RAM `0x0210BEE4` |

Each patch has a different loader/format contract. Do not combine them by
blindly copying bytes between ROM builds; apply them in a documented lineage
and keep the produced manifest with the build.
