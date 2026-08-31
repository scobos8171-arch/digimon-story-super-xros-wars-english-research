# Xros Evolution Tester Build Status

## Run this build

`outputs/Xros Evolution Complete US v3 UI+NAMES TEST/Game/Digimon Story Xros Evolution - COMPLETE US v3 UI+NAMES TEST.nds`

This is the current **battle-working** tester build. Its gameplay data and
ARM9 battle code must remain untouched during UI work.

## What a tester can reliably test now

- Story progression, field movement, encounters, battles, guarding, fleeing,
  healing, leveling, and DigiXros eligibility.
- English dialogue, character names, and the bulk of roster names.
- Runtime telemetry and automatic save-state evidence through
  `START_XROS_GAME_TESTER.cmd`.

## Known visual defects (not gameplay blockers)

| Screen | Defect | Correct repair type |
|---|---|---|
| Command ring | Seven labels remain Japanese | Replace fixed sprite labels |
| Live Events | Japanese title/empty-state art | Replace title sprite and text-bank string |
| Shop confirmation | Japanese button glyphs; clipped wording | Replace button sprites; reflow message string |
| Quest/service screens | Some title/footer buttons remain Japanese | Replace fixed sprite labels |
| A few white dialogue boxes | English can overlap or crop | Reflow only the affected message strings |

## Safety rule

Do not patch battle overlays, ARM9 code, save data, or emulator settings for
these UI repairs. Each UI batch is data-only, versioned, and must pass a full
battle regression before it replaces this tester build.
