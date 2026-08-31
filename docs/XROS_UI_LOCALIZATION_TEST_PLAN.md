# Xros Evolution v3 UI localization test plan

## Rule

Treat UI localization as a data-only patch. Do not edit ARM9, battle overlays,
or command logic. Each candidate replacement must preserve its NitroFS file
size or be rebuilt through the established PAK repacker; verify the source ROM
and the output ROM have identical ARM9 bytes before testing.

## Reported screens

| Area | Current problem | Correct English target | Patch class | Evidence needed |
|---|---|---|---|---|
| Live Events | Japanese title art and Japanese empty-state line | `LIVE EVENTS`; `No live events are scheduled.` | title sprite + message bank | open screen, save state |
| Shop confirmation | Japanese A/B button art; awkward generated English; clipped headers | `Buy 1 Scale for 500 Bit?`; `Yes`; `No`; `Funds` | button sprite + message bank/layout | buy prompt before confirmation |
| Top message boxes | Text is clipped/overlapping | message must fit with no character overlap | font metrics / line-break table | each affected dialogue/menu state |
| Command ring | Seven Japanese fixed labels | `STATUS`, `SKILLS`, `BATTLE`, `PARTY`, `ITEMS`, `MAP`, `INFO` | fixed UI sprites | screen with command ring visible |
| Quest board | Remaining Japanese tab/footer graphics | `QUEST PROGRESS`, `BACK`; preserve quest-specific text | fixed sprite + message bank | quest list and detail screens |
| Main service menu | Japanese button art | `PLAY`, `QUESTS`, `PARTY`, `DIGIMON ENCYCLOPEDIA` (final wording subject to source meaning) | fixed UI sprites | full service-menu capture |

## Test procedure

1. Load the most recent battle-working v3 ROM.
2. For one menu screen, create a DeSmuME state before opening it and another
   while it is visible.
3. Capture a PNG screenshot and add one row to the issue log: screen, exact
   Japanese text, desired English, whether the text is fixed art or dynamic.
4. Locate only that menu's resource through PAK comparison/load tracing.
5. Make one data-only patch, generate a new versioned ROM, then verify:
   - ARM9/overlay hashes unchanged;
   - the target screen is readable at native 256x192;
   - opening, selecting, cancelling and returning works;
   - one battle still completes.
6. Keep the patch only if all four checks pass. Otherwise revert that one
   resource, not the entire build.

## Why this is a game tester, not a bot

The tester is a reproducible checklist with paired save states, screenshots,
resource IDs, expected text and regression tests. It reports a specific asset
or text-bank failure; it does not wander the game or mutate gameplay.

## Existing safe foundation

`tools/recovery/build_xros_ui_sprite_patch.py` already supports conservative
sprite-only replacements and asserts that ARM9 remains unchanged. Extend that
method per screen after the resource is proven, rather than painting over DS
screenshots at runtime.
