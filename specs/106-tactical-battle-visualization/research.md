# Research: Tactical Battle Visualization

## Decision 1: Reuse the authoritative combat modes

- **Decision**: Treat the existing `positional` mode as a passive engagement and the existing `assault` mode as an active engagement. Keep those values in the authoritative battle table and expose “Passive”/“Active” as presentation labels.
- **Rationale**: `modules/base/systems/military/military_system.py` already creates positional contact when hostile units enter the engagement radius and promotes the contact to assault only after an accepted attack order. `modules/base/systems/military/combat_system.py` already persists the mode and emits the battle lifecycle events. Reusing this contract keeps the client passive and avoids changing combat detection or outcomes.
- **Alternatives considered**:
  - Add a second `visual_mode` field: rejected because it could diverge from the combat mode and introduce a new authoritative state transition.
  - Infer intensity from losses or round number: rejected because those values do not express the player’s assault intent and would make the visual contract nondeterministic across snapshots.

## Decision 2: Store one additive geographic anchor on each battle

- **Decision**: Add `anchor_latitude`, `anchor_longitude`, and `anchor_source` to the existing `battles` table. Compute the anchor when a battle is first created from the participating units’ stopped contact coordinates; preserve it for the lifetime of that battle. Use the region center only when no valid participant coordinate is available. Keep the source vocabulary small: `contact` and `region_center`. Legacy rows are backfilled from the actual referenced region before schema capture; `0,0` is never a missing-value sentinel because it is a valid coordinate.
- **Rationale**: A battle has one map location and already has a stable primary key, region, and lifecycle. Additive columns keep snapshots, saves, and the existing battle panel compatible while making the location independent of visible unit billboards. The movement system already persists the exact first-contact position in each stopped unit, so a deterministic spherical mean of sorted participant positions is a better source than a region center. Preserving the first anchor prevents a moving or filtered unit from moving the effect after the contact has been established. `anchor_source` distinguishes observed contact from the documented fallback and makes legacy rows diagnosable.
- **Alternatives considered**:
  - Create a separate battle-anchor table: rejected because it adds another join, schema, and persistence lifecycle for a one-to-one value.
  - Recalculate the average participant position every frame: rejected because it would move the battle marker and would make filtering/late snapshots affect presentation.
  - Persist a raw contact event only: rejected because old saves and snapshot consumers need a directly available current anchor.

The battle ID is already stable across `positional` → `assault`, so the anchor is copied from the prior row during mode changes rather than recalculated. Snapshot serialization is table-generic; no protocol message or version bump is needed.

## Decision 3: Use a shared globe-anchor projection mechanism

- **Decision**: Extract the minimal geographic-to-screen projection, visible-hemisphere test, silhouette clearance, and bounded marker sizing needed by battle overlays into a reusable client presentation helper. Implement a dedicated `BattleEffectRenderer` that consumes this helper and the battle table; retire the current unit-dependent battle marker from `UnitRenderer`. Do not refactor existing event or unit projection paths as part of this feature.
- **Rationale**: `EventRenderer` and `UnitProjectionService` provide proven reference math, but changing both would expand regression risk without improving battle gameplay. A focused helper plus parity tests prevents back-side/seam regressions, keeps battle effects independent of unit filters, and gives the renderer one bounded loop over battles rather than one animation object per unit.
- **Alternatives considered**:
  - Draw the effect from `UnitRenderer`: rejected because the existing marker requires visible unit billboards and disappears when owners are filtered.
  - Copy the projection math into a new renderer: rejected because duplicated edge and hemisphere rules would drift and regress globe rendering.
  - Use a 3-D particle/projectile system: rejected as outside the MVP and unnecessarily couples presentation to frame rate and object count.

## Decision 4: Drive animation from the client presentation clock

- **Decision**: Derive effect phase from a stable byte-level digest of battle ID, authoritative round/start time, and `ClientGameClock.get_display_total_minutes()`. Never use Python's process-randomized `hash()`, network arrival time, or unseeded randomness. Keep the renderer read-only.
- **Rationale**: `GameView` already supplies a smooth presentation time between snapshots. A pure phase function gives continuous motion at display refresh rate, deterministic replay, and no server-state mutation. A phase can be evaluated per visible battle without allocating persistent animation objects.
- **Alternatives considered**:
  - Advance animation only when a battle snapshot arrives: rejected because it produces the reported stutter.
  - Use wall-clock time: rejected because pause/speed/reconciliation behavior would diverge from the game clock and replay.
  - Seed random effects per frame: rejected because frame-to-frame movement would not be reproducible.

## Decision 5: Represent intensity with aggregate, side-level effects

- **Decision**: Render passive contact with a restrained pulse and paired side halos; render assault with a stronger pulse, directional side exchange, and bounded impact flashes. Use deterministic side colors and ordering, including one color identity per combat side for allied participants.
- **Rationale**: The requested distinction is readability of combat intensity, not a projectile simulation. Side-level identity matches the two-side battle model and avoids implying a third combatant when allies participate. Aggregate primitives keep the cost proportional to battle count.
- **Alternatives considered**:
  - Use country flag colors for every participant: rejected because allies would look like additional combat sides and the effect would become visually noisy.
  - Draw individual soldier or projectile sprites: rejected for scope, performance, and lack of authoritative per-shot data.

## Decision 6: Keep reduced motion as local client preference

- **Decision**: Add a local `reduce_motion` setting to the existing game settings model and settings UI. When enabled, suppress pulse movement and flashing while retaining a static marker, side colors, state label, and focus behavior.
- **Rationale**: Motion preference is presentation state, not simulation state, so it must not enter `GameState` or server snapshots. The existing settings service is the natural persistence boundary.
- **Alternatives considered**:
  - Put the preference in the world state: rejected because it would be shared between players and violate passive-client boundaries.
  - Hide all battle overlays: rejected because the specification requires state identification to remain available.

## Decision 7: Validate compatibility through additive schema normalization

- **Decision**: Extend the canonical battle schema and support-table defaults with the anchor columns, validate coordinate ranges and source values at state-load boundaries, and allow old rows to normalize to the region fallback. No event or snapshot protocol version bump is required because snapshots serialize table columns generically.
- **Rationale**: `src/shared/snapshots.py` and `GameState.update_table` already carry schema-defined table columns. Additive defaults preserve old saves and clients while keeping malformed coordinates from reaching the renderer. The server remains responsible for data integrity; the client only degrades to a visible fallback marker.
- **Alternatives considered**:
  - Reject all old battle rows without anchors: rejected because it would make existing saves unloadable.
  - Add a bespoke protocol message for battle visuals: rejected because the feature is fully represented by the existing authoritative battle table and would duplicate transport logic.

## Decision 8: Verify with focused deterministic and performance tests

- **Decision**: Add unit tests for anchor computation and projection, renderer tests for lifecycle/mode/reduced-motion/filter behavior, integration coverage for passive-to-active escalation, and a dedicated 100-battle render benchmark. Preserve the existing snapshot/presenter performance test, but do not treat it as evidence for frame-time overhead because it measures serialization and presentation-model consumption rather than drawing.
- **Rationale**: The critical risks are geographic correctness, stale snapshot smoothing, globe occlusion, and frame cost. Focused tests make each risk observable without requiring a full interactive session. The render benchmark uses warm-up plus repeated baseline/feature samples and compares medians to reduce timing noise.
- **Alternatives considered**:
  - Rely only on manual visual checks: rejected because deterministic anchor and lifecycle regressions are easy to miss.
  - Benchmark per-unit effects: rejected because the design intentionally removes per-unit work from the battle renderer.

The renderer will not depend exclusively on transient battle events. A concluded row may exist for only one authoritative tick, so the client keeps a short-lived last-visual cache keyed by battle ID to show the bounded conclusion cue and then expires it. Lifecycle tests also cover stalemate idempotency so a status marker cannot cause a duplicate start effect.

## Decision 9: Resolve overlaps without moving the authoritative anchor

- **Decision**: Cache stable battle-ID order by battle revision. Insert visible bounded footprints into a screen-space grid whose cell size is at least the maximum bounded footprint diameter, test only the same and neighboring cells, and assign the first available offset from a fixed ordered candidate set to labels and decorative effects. Retain a small anchor mark and leader at the exact projected coordinate.
- **Rationale**: Two battles can share a region or nearly identical coordinates. Stable offsets keep both identifiable while the anchor mark preserves the meaning of the authoritative contact point and prevents frame-to-frame jitter.
- **Alternatives considered**:
  - Random jitter: rejected because repeated frames and replays would diverge.
  - Move the stored anchor: rejected because collision handling is a presentation concern and must not rewrite authoritative geography.
  - Hide all but one battle: rejected because the specification requires simultaneous battles to remain identifiable.

## Decision 10: Preserve the marker and cull decorative limb effects

- **Decision**: Reject back-facing anchors. For a front-facing anchor, always retain the bounded static marker, but draw a halo, flash, or exchange segment only when its complete footprint fits within the projected silhouette clearance.
- **Rationale**: This preserves the authoritative battle location while avoiding CPU-side circular clipping or additional stencil work for presentation-only decoration. It guarantees no hidden-hemisphere bleed and reduces work near the limb without changing simulation or map capabilities.
- **Alternatives considered**:
  - Suppress the entire battle near the silhouette: rejected because a valid front-facing battle would disappear prematurely.
  - Clip every decorative primitive: rejected because the extra geometry work provides little readability benefit over retaining the marker and omitting decoration.
  - Draw the full screen-space effect: rejected because it would visibly cross the globe boundary.

## Decision 11: Cache snapshot-derived presentation inputs

- **Decision**: Cache normalized battle rows, stable ordering, region lookup, and side palettes by relevant table revisions. Recompute camera projection, visibility, collision grid, and phase only for visible battle anchors on each frame. Submit all primitives through one no-input overlay draw list.
- **Rationale**: Snapshot-derived data changes far less often than the display refresh. Revision-keyed caches remove repeated Polars row conversion, sorting, and palette resolution while preserving smooth camera and clock-driven presentation.
- **Alternatives considered**:
  - Rebuild every input every frame: rejected because it creates avoidable allocations and scales poorly.
  - Retain a mutable animation object per unit: rejected because cost would depend on participant count and couple presentation to units.

## Resolved Technical Unknowns

- The project uses Python 3.10+, Polars/Arrow table schemas, Arcade/OpenGL/ImGui client rendering, and pytest-based tests.
- The existing client presentation clock is suitable for smooth effect timing.
- Existing battle modes and lifecycle statuses are sufficient; no terrain, supply, combat-formula, or third-side data is required.
- No extension hooks are registered in `.specify/extensions.yml`; no pre-plan or post-plan command is required.
