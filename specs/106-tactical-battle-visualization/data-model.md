# Data Model: Tactical Battle Visualization

## Authoritative `battles` table

The feature extends the existing battle row; it does not create a second combat entity. Existing fields such as `id`, `war_id`, `region_id`, `attacker_side`, `defender_side`, `mode`, `balance`, strengths, losses, `round`, timing, `victor_side`, and `status` retain their current meaning.

| Field | Type | Required | Default | Meaning and validation |
|---|---|---:|---|---|
| `id` | `Utf8` | yes | — | Stable battle identity and deterministic animation seed. |
| `war_id` | `Utf8` | yes | — | Authoritative war relationship. |
| `region_id` | `Int32` | yes | — | Region containing the engagement and fallback anchor source. |
| `mode` | `Utf8` | yes | `positional` | `positional` is passive; `assault` is active. Unknown values are rejected at server validation. |
| `anchor_latitude` | `Float64` | yes | `0.0` | Geographic anchor in degrees, inclusive range `[-90, 90]`. |
| `anchor_longitude` | `Float64` | yes | `0.0` | Geographic anchor in degrees, normalized to `[-180, 180]`. |
| `anchor_source` | `Utf8` | yes | `region_center` | `contact` when created from valid participant contact coordinates; `region_center` when the deterministic region fallback is used. |
| `status` | `Utf8` | yes | `active` | Existing lifecycle values `active`, `stalemate`, and `concluded`. |

The remaining existing columns are carried unchanged through `BATTLE_SCHEMA`, `SUPPORT_TABLE_SPECS["battles"]`, snapshots, and save/load normalization. The anchor columns are additive so old rows receive the documented fallback defaults.

## Anchor construction and immutability

1. On first battle creation, the military system asks a small anchor policy for the participating units’ current geographic positions, ordered by stable unit ID.
2. Valid coordinates are combined using a spherical mean (unit-vector average), then converted back to latitude/longitude. This avoids a longitude-seam jump when contacts straddle `+180`/`-180` and gives a stable midpoint if the two sides stop a few meters apart.
3. If no valid participant coordinate exists, the policy reads the region’s canonical latitude/longitude and marks the source `region_center`.
4. On subsequent updates, the original anchor fields are copied forward unchanged, even when units move, are filtered, or arrive in a later snapshot.
5. A legacy row with default or missing anchor columns is rendered from its region center and remains compatible with the additive schema.

The server owns anchor creation and persistence. The client must never recalculate an existing battle’s anchor from visible units.

## Presentation-only entities

### `BattleVisualPhase`

Not persisted. For a battle row and a presentation time, the renderer derives:

- a stable phase seed from `battle.id`;
- a cadence offset from `started_at_minute` and `round`;
- a normalized phase from `ClientGameClock.get_display_total_minutes()`;
- a lifecycle-specific conclusion age when a concluded row is first observed.

The function is pure for identical inputs. It has no random or network-time input and does not mutate `GameState`.

For a concluded row that is present for only one authoritative tick, the client may keep a short-lived visual cache keyed by `battle.id` solely to bound the conclusion cue. The cache is presentation state and is discarded after the configured conclusion duration; it cannot resurrect the combat loop.

### `BattleSideVisual`

Not persisted. The renderer resolves one deterministic color/symbol per authoritative side (`attacker_side` and `defender_side`). Allied countries listed under the same side inherit that side’s identity; they do not create additional visual sides. Missing colors use the existing deterministic political-color helper.

### `GameSettings.reduce_motion`

Local client preference only. It is loaded and saved by the existing settings service and is not part of world tables, snapshots, actions, or server events. When true, the renderer evaluates a static phase and disables movement/flashes while retaining marker, side identity, label, and focus behavior.

## Lifecycle and mode transitions

The authoritative combat system remains the source of transitions:

| Previous state | Event/condition | Next state | Visual behavior |
|---|---|---|---|
| no row | hostile units contact without assault order | `active` + `positional` | Start passive marker/effect at the persisted anchor. |
| `active` + `positional` | accepted attack/assault order from a participant | `active` + `assault` | Keep `id` and anchor; switch to active effect pattern on the next snapshot. |
| `active` + `assault` | authoritative mode returns to positional | `active` + `positional` | Keep `id` and anchor; reduce intensity without restarting identity. |
| `active` | combat resolution reaches stalemate | `stalemate` | Stop combat loop; retain a restrained state marker. Lifecycle bookkeeping must remain idempotent for this status. |
| `active`/`stalemate` | combat resolution concludes | `concluded` | Stop combat effect and optionally show one bounded conclusion indicator. |

The renderer must not manufacture transitions. A stale row is replaced by the newest state revision, and a concluded row cannot resurrect a prior combat loop.

## Relationships

- `battles.region_id -> regions.id` provides the fallback geographic anchor.
- `battle_units.battle_id -> battles.id` and the unit table provide creation-time contact coordinates only; they are not a live render dependency.
- `countries_wars` provides the war and side membership used to resolve the two visual sides.
- Snapshot revisions determine newest authoritative state; the presentation clock determines only local animation phase.

## Compatibility and validation

- Register the three columns in both the canonical battle schema and the server support-table specification in the same order/types expected by Polars/Arrow normalization.
- Validate latitude/longitude ranges and the finite-value requirement at server state-load/update boundaries. Validate `anchor_source` against `contact` and `region_center`.
- Normalize old saved rows with the region fallback; do not reject a save solely because it predates battle anchors.
- If a row is malformed after normalization, the client skips only its moving effect and draws a deterministic region marker where possible; one bad row must not suppress all battle overlays.
