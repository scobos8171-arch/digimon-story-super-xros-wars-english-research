# Xros Blue Battle Overlay Recovery

## Exact-v3 runtime findings (2026-08-09)

Authoritative ROM SHA-256: `90432395bc8aaa67fcc3ef58b90d6ee08732107f4c2323c055d28db8a17fdf87`.

Authoritative captures:

- `work/battle-captures/v3_battle_before.dst`
- `work/battle-captures/v3_battle_after.dst` (two heals and one missed Fire Punch)
- `work/battle-captures/v3_attack_round_before.dst`
- `work/battle-captures/v3_attack_round_after_victory.dst`

The party combatant records begin at `0x0221AFD4` and use a confirmed stride of
`0x1A0` bytes. The live stat fields are:

| Record offset | Meaning | Evidence |
|---|---|---|
| `+0xE0` | Maximum HP | Shoutmon 185; Starmon 211 |
| `+0xE4` | Current HP | Shoutmon `102 -> 185`; Starmon `165 -> 211` |
| `+0xE8` | Maximum SP | Adjacent stable live values |
| `+0xEA` | Current SP | Shoutmon 67; Starmon 79 in the captured records |

Party slot current-HP addresses are `0x0221B0B8`, `0x0221B258`, and
`0x0221B3F8`. Their exact `0x1A0` spacing independently confirms the record
stride seen in Ghidra.

`FUN_021FB678` is a runtime-confirmed HP commit path for one side. It consumes a
three-entry signed delta array, applies each delta at record `+0xE4`, clamps HP
to `0..maxHP`, handles defeat/status bookkeeping, refreshes the HUD through
`FUN_0220CDF8`, and advances battle presentation. `FUN_021FCAB0` is the closely
related commit path for the opposite side. These functions apply results; the
upstream formula producer is still under recovery.

`FUN_021FCB8C` is a static-confirmed SP commit path. It consumes a three-entry
signed delta array, subtracts those deltas from combatant record `+0xEA`, clamps
the result to `0..+0xE8`, and refreshes the HUD through `FUN_0220CDF8`. This
matches the later attack-round captures where slot 1 SP moves from `67 -> 59`
and then `59 -> 43`.

`C:\Users\YOUR_NAME\Downloads\dstate.dst` belongs to an older/different build. Keep
it only for historical comparison; it is not authoritative for exact v3.

### Attack-round capture audit (2026-08-09)

Latest captures inspected:

- `work/battle-captures/v3_attack_round_before.dst`
- `work/battle-captures/v3_attack_round_after_victory.dst`
- `work/battle-captures/v3_attack_round_after_victory 1.dst`
- `work/battle-captures/v3_attack_round_after_victory 2.dst`
- `work/battle-captures/v3_attack_round_after_victory 3.dst`

These are valid live v3 captures, but they are noisy rather than clean formula
fixtures. The round ended in enemy death/victory and included level-up or
post-battle state updates, so enemy HP is already clamped to zero and multiple
records change at once.

Useful recovered facts:

- `v3_attack_round_after_victory.dst` still has the same visible combat records
  as `v3_attack_round_before.dst`, so it was likely saved before action
  settlement reached the record fields we track.
- `v3_attack_round_after_victory 1.dst` shows party slot 1 SP changing
  `67 -> 59`, confirming an 8 SP deduction in the live battle record.
- `v3_attack_round_after_victory 3.dst` shows party slot 1 SP at `43`, giving a
  total observed change of `67 -> 43` across the later captures.
- Slot 0 max HP/SP changes from `162/156` to `168/166`, consistent with
  level-up growth being written back into the same combatant record layout.
- Defeated enemy slots show `hp_cur = 0` and status byte `+0xF1 = 5`, but the
  captures do not preserve the pre-clamp enemy HP delta needed to derive damage.

Focused audit output:
`work/battle-captures/v3_attack_round_focused_summary.json`.

Conclusion: treat these as `[RUNTIME][NOISY]` evidence for SP commit, defeat
state, and growth writeback. Do not use them as damage formula fixtures.

## Current gate

Overlay 0 (`021f3d20`–`0221ae9f`) is verified as the active battle/effect overlay. Static analysis has produced useful candidates, but exact HP/SP fields and formulas require a controlled before/after battle state pair. Archived localization and validation states are not such a pair; their extracted WRAM is identical.

### Existing-state audit (2026-08-09)

The three archived localization states under
`C:\Users\YOUR_NAME\Documents\Codex\2026-07-24\can\work\runtime_qa\Saves\StateSlots\Digimon Story Xros Evolution - COMPLETE US LOCALIZATION (backups)`
were extracted and compared. State `125183079.dst` has battle overlay 0 and
overlay 2 loaded at their expected RAM addresses, but each comparison to its
neighboring state changes about 99,500 separate RAM runs. These are different
execution contexts, not a single action resolving, so they must not be used to
infer combat fields or formulas.

Audit output: `work/decomp/runtime_states/recovered_xros_candidates/`.

`C:\Users\YOUR_NAME\Downloads\dstate.dst` is a separate valid Xros battle-screen
candidate: it loads battle overlay 0 and overlay 3 exactly. It is retained as
the preferred baseline state. A second state saved immediately after one
ordinary attack from this same loaded state is still required before the
runtime differential can identify HP/SP fields.

## Static candidates (not yet production facts)

| Address | Candidate behavior | Static evidence | Confidence |
|---|---|---|---|
| `021f3d20` | Percentage/chance test | Calls the RNG and reduces the result to an apparent 0–100 range before comparing it with the argument. | Probable generic helper |
| `021f3d60` | Build/sort combatant action order | Iterates nine `0x1a0`-byte combatant records, builds ten 8-byte entries, applies modifiers, then sorts them. | Probable |
| `021f4008` | Apply effect opcode list | Fetches a record, dispatches on byte-sized opcodes, and mutates many signed 16-bit fields in the destination structure. | Probable |
| `021f4840` | Move accuracy check | Rolls 1–100, resolves the active move/species record, and compares against record byte `+0x17`. | Candidate |
| `021f48a4` | Modified accuracy/status chance | Rolls 1–100 and compares against record byte `+0x18` plus a combatant modifier. | Candidate |

Do not rename these as verified gameplay functions until runtime watchpoints confirm their callers and written fields.

## Capture protocol

1. Load the localized Xros Blue ROM in DeSmuME.
2. Enter a normal battle and stop at the command menu.
3. Record the target's visible current HP and the attacker's current SP.
4. Save `work/battle-captures/battle_before.dst`.
5. Use one ordinary single-target damaging skill. Avoid critical hits, misses, counters, healing, poison, or multi-hit moves for the first sample.
6. Wait until HP/SP values settle and the next command state is stable.
7. Record the new HP/SP values and save `work/battle-captures/battle_after.dst`.
8. Run `ANALYZE_BATTLE_STATES.ps1` with the four visible values.

## Verification ladder

1. **Field location:** exact visible HP/SP transitions identify candidate RAM addresses.
2. **Structure confirmation:** repeat from a reloaded before-state with a second skill; addresses must remain stable and surrounding `0x1a0` record layout must agree.
3. **Writer confirmation:** place emulator write breakpoints on the confirmed addresses and record the program counters.
4. **Function confirmation:** inspect those PCs, callers, constants, and record accesses in Ghidra overlay 0.
5. **Formula fixtures:** record attacker stats, defender stats, move ID/power, random outcome, multipliers, and final damage for repeated trials.
6. **PC implementation:** replace only the corresponding placeholder mechanic and require the fixture suite to match.

## Recovery sequence after the first pair

1. HP subtraction and SP deduction
2. Move targeting and target masks
3. Accuracy/evasion and critical checks
4. Damage and elemental/attribute multipliers
5. Healing, buffs, debuffs, and status opcodes
6. Turn ordering and guard/change behavior
7. Enemy AI selection and full turn resolution
## Clean non-lethal full-round fixture (2026-08-09)

The pair `work_battle_captures_clean_before_hit.dst` -> `clean_after_hit.dst`
is the first clean v3 capture covering a complete non-lethal round without victory,
reward, or level-up contamination.

Runtime-confirmed changes:

- Enemy slot 7: HP `250 -> 166` (`-84` total from three player actions).
- Party slot 0: HP `113 -> 83` (`-30`).
- Party slot 1: HP `174 -> 146` (`-28`), SP `43 -> 35` (`-8`).
- Party slot 2: HP `210 -> 202` (`-8`), SP `79 -> 71` (`-8`).
- Party slot 3: SP `111 -> 103` (`-8`), with no HP change.

This fixture validates the HP/SP record offsets and commit behavior under a live
non-lethal round. It does not isolate the three outgoing damage amounts. The next
controlled fixture can either snapshot between actions or assign **Guard** to the
other active Digimon. Guard is available through the per-Digimon command ring;
it was initially overlooked because it is not shown as a persistent main-screen
button.

The player reported the resolved action order as:

1. Spadamon — Fire Punch
2. Shoutmon — Petit Fire RV
3. Starmon — Petite Divine RV
4. Ballistamon — signature move (exact displayed name still to be recorded)

The three observed `-8` SP changes are consistent with the first three selected
moves, but exact slot-to-species attribution remains pending a mid-round snapshot.
## Isolated move fixture: Spadamon Fire Punch (2026-08-09)

The pair `single_attack_before.dst` -> `single_attack_after.dst` landed between
Spadamon's first action and Shoutmon's second action. Only one combatant-field
change occurred:

- Enemy slot 7 current HP: `112 -> 81`.
- Runtime-confirmed damage: **31**.
- No party HP, enemy status, maximum-stat, or other combatant-record fields changed.

The SP value did not change inside this narrow pair because the command had already
been selected before `single_attack_before.dst`. The adjacent full-round fixture
shows an `-8` SP deduction for each of the three selected player moves, supporting
an 8 SP cost for Fire Punch. A command-selection pair is still required to mark
that cost independently runtime-confirmed for this specific move.
## Isolated move fixture: Shoutmon Petit Fire RV (2026-08-09)

The pair `single_attack_after.dst` -> `shoutmon_petit_fire_after.dst` isolated
Shoutmon's second action. Exactly two combatant fields changed:

- Shoutmon/actor slot 1 SP: `27 -> 19` (**8 SP cost**).
- Minotarumon/target slot 7 HP: `81 -> 55` (**26 damage**).

This is the first v3 fixture that independently runtime-confirms both the move's
damage result and its SP cost within the same isolated action window.
## Isolated move fixture: Starmon Petite Divine RV (2026-08-09)

The pair `shoutmon_petit_fire_after.dst` -> `starmon_petite_divine_after.dst`
isolated Starmon's third action. Exactly two combatant fields changed:

- Starmon/actor slot 2 SP: `63 -> 55` (**8 SP cost**).
- Minotarumon/target slot 7 HP: `55 -> 29` (**26 damage**).

This independently runtime-confirms both damage and SP cost for Petite Divine RV.
The state is intentionally paused before Ballistamon's fourth action; allowing it
to resolve against the remaining 29 HP would likely yield clamped lethal damage
and introduce defeat-state transitions.
## Isolated resisted fixture: Ballistamon Heavy Speaker (2026-08-09)

The pair `starmon_petite_divine_after.dst` ->
`Ballistamon_signature_move__after.dst` isolated Ballistamon's fourth action. The
user observed `Resist` and 2 displayed damage. Exactly two combatant fields changed:

- Ballistamon/actor slot 3 SP: `95 -> 87` (**8 SP cost**).
- Minotarumon/target slot 7 HP: `29 -> 27` (**2 resisted damage**).

Combatant status offset `+0xF1` did not change. This indicates that the displayed
`Resist` classification is probably held in the transient action-result structure
processed by the resolver/presentation path rather than persisted on the target's
combatant record. The recovered move table and localized message block identify
this action as move ID 0, **Heavy Speaker**.
## All-Guard round fixture (2026-08-09)

The pair `all_guard_before.dst` -> `all_guard_after.dst` captured a round with
Guard assigned to all three active Digimon. Only party slot 1 took damage:

- HP `196 -> 189` (**7 damage**).
- SP remained `147 -> 147`; Guard consumed no SP.

The completed-round state does not retain an obvious Guard marker in the standard
combatant fields. A future snapshot immediately after Guard assignment but before
round execution is needed to identify the temporary command/flag and connect it
to the resolver's damage-reduction branch.

## Flee outcome fixture (2026-08-09)

The runtime captures `FLEE_MISSED.dst`, `flee_failed_after.dst`, and
`flee_success_after.dst` confirm both sides of the escape mechanic. The first
attempt failed with the game's miss feedback and battle continued; the next
attempt succeeded and returned to the field. Flee is therefore a fallible check,
not a guaranteed command in this encounter.

These states do not have one common clean pre-attempt snapshot. The successful
state also includes battle teardown, resource cleanup, and field restoration, so
its broad memory diff cannot safely identify an escape-rate field by itself. The
high-confidence next step is static tracing from the flee command handler to its
RNG comparison; a later controlled pair can validate the resulting formula.

## Shoutmon X2 DigiXros fixture (2026-08-09)

The pair `digixros_ready_before.dst` -> `digixros_after.dst` captured a successful
in-battle DigiXros initiated by Ballistamon with Shoutmon available as its
component. Other party members were assigned Guard. The user visually confirmed
that the DigiXros animation and attack executed.

The focused combatant-record differential found:

- Shoutmon (slot 1): SP `146 -> 138` (`-8`).
- Ballistamon (slot 2): SP `142 -> 50` (`-92`) and HP `234 -> 205` (`-29`).
- Enemy slot 6: HP `41 -> 0` (at least 41 damage).
- Enemy slot 8: HP `36 -> 0` (at least 36 damage), defeat status `+0xF1 = 5`.
- Spadamon, Starmon, Agumon, and Tentomon did not lose HP or SP.

The resolved round therefore consumed **100 total party SP** across Shoutmon and
Ballistamon. The observed `8 + 92` split is runtime-confirmed, but its semantic
interpretation as component-versus-initiator cost remains provisional until a
snapshot taken immediately after command confirmation exposes the queued
DigiXros command fields. Both enemy damage results are clamped and are lower
bounds rather than exact raw damage.

The machine-readable fixture is
`work/battle-captures/shoutmon_x2_digixros_fixture.json`.

### Generic DigiXros requirement recovery

Static analysis establishes that `FUN_0209CFE0` is the generic special-move
availability gate. For type-1 move records it resolves the initiating formation
member, rejects the forbidden formation coordinate, follows the move's `+0x1C`
pointer, and checks every required species through `FUN_02048A84`. That helper
scans the 3x3 party formation and compares a live entity's zero-based species ID
at entity offset `+0x1E`. The gate finally verifies the actor has the required
resource/SP. `FUN_020CBC14` calls this gate when building the usable command list.

The linked requirement table begins at ARM9 address `0x020E092C`; records are 14
bytes: an unresolved first short, component count at `+2`, then up to five signed
16-bit component species IDs at `+4`. Recipe record 200, referenced by special
move record 1205, contains component IDs `356, 357`. The extracted roster maps
those zero-based IDs to Shoutmon and Ballistamon. Combined with the successful
runtime fixture, this verifies that record as the Shoutmon X2 requirement.

The ready-state also resolves the queued-command side of the join. Ballistamon's
combatant record starts at `0x0221B314`; its eligible special list begins at
`+0x10A` and contains `1205, 1217, 1208, 1215`. Selected special ID `1205` is
stored at both `+0x14C` and `+0x150`. Those values persist after resolution, so
they are configuration/selection fields rather than transient animation noise.

`tools/nds_decompiler/xros_digixros_table.py` now exports all 219 referenced
requirement records to
`work/extracted/xros_evolution_us_v3/digixros_recipes.json`. The first short is
kept explicitly unresolved: it is not the resulting species ID. Other DigiXros
result names should be joined only after their result lookup path is recovered or
verified in a runtime fixture.
