# Recovery Library Workflow

The authoritative reusable output for future game-engine work is generated at:

`work/reusable_asset_library/`

It consolidates decoded assets and data from Dusk, Lost Evolution, Xros Blue and
Xros Red without copying ROM containers. Every copied or hard-linked file retains
its original workspace path, byte size and SHA-256 hash in `library_manifest.json`.

## Verification policy

The library deliberately uses three roster states:

- `active_candidate`: currently playable after redirect filtering.
- `redirected_alias_review`: retained possible duplicate or alias.
- `unidentified_source_slot`: extracted slot without normalized mechanics.

None of these states means the graphics have been human-approved. Mechanics use a
separate provenance field: `rom_verified`, `compatibility_estimate`, or `missing`.

## Commands

```powershell
python tools\recovery\build_library.py
python tools\recovery\build_library.py --verify-only
```

The first command materializes the reusable library. The second checks file sizes,
forbidden container types, active metadata, and duplicate active display names.

## Field-sprite recovery

`data/recovery/field_candidate_analysis.json` validates all anonymous walking
sheets and compares padding-independent pixel hashes against linked field sprites.
It also derives source-specific entry offsets only when supported by at least 20
exact anchors and a majority of all anchor pairs.

Current recovered relationships are:

- Lost Evolution: `walk entry = internal species ID + 474` (122 exact anchors).
- Xros Blue: `walk entry = internal species ID + 266` (25/25 exact anchors).
- Dusk: no inference is needed; its ARM9 species table already stores walk entries.

These relationships initially produced 84 missing-walk proposals. Three entries
were proven duplicates by identical battle and walk pixels and were redirected.
Of the remaining proposals, 62 passed side-by-side visual review, 16 were rejected
as mismatches/placeholders, and three field-only identity conflicts remain blocked.

The 62 accepted sets are materialized under
`assets/digimon/provisional_field_walk/`. They are exposed in the roster catalog as
`effective_field_walk_available`, but remain provisional until exercised in-engine.
This reduces the active roster without an effective walk set from 103 to 41.

## Continuing recovery

Work through `work/reusable_asset_library/recovery_queue.json` in this order:

1. Resolve redirects and identity/attribute review.
2. Resolve open visual and animation reports.
3. Review the inferred field links and identity conflicts.
4. Decode Lost Evolution mechanics into source-provenance tables.
5. Decode Xros mechanics and DigiXros recipes.
6. Recover semantic map names and traversal/event metadata.
7. Identify character sheets and connect NPC placement/dialogue.
8. Map audio samples and sequences to gameplay events.

Corrections should be stored in upstream normalized/QA files and the library should
then be regenerated. This prevents one-off edits from being lost or silently mixed
with unverified extraction output.
