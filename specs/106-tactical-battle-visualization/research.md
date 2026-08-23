# Research: Tactical Battle Visualization

## Decision 1: Reuse the authoritative combat modes

- **Decision**: Treat the existing `positional` mode as a passive engagement and the existing `assault` mode as an active engagement. Keep those values in the authoritative battle table and expose “Passive”/“Active” as presentation labels.
- **Rationale**: `modules/base/systems/military/military_system.py` already creates positional contact when hostile units enter the engagement radius and promotes the contact to assault only after an accepted attack order. `modules/base/systems/military/combat_system.py` already persists the mode and emits the battle lifecycle events. Reusing this contract keeps the client passive and avoids changing combat detection or outcomes.
- **Alternatives considered**:
  - Add a second `visual_mode` field: rejected because it could diverge from the combat mode and introduce a new authoritative state transition.
  - Infer intensity from losses or round number: rejected because those values do not express the player’s assault intent and would make the visual contract nondeterministic across snapshots.

## Decision 2: Store one additive geographic anchor on each battle

- **Decision**: Add `anchor_latitude`, `anchor_longitude`, and `anchor_source` to the existing `battles` table. Compute the anchor when a battle is first created from the participating units’ stopped contact coordinates; preserve it for the lifetime of that battle. Use the region center only when no valid participant coordinate is available. Keep the source vocabulary small: `contact` and `region_center`.
- **Rationale**: A battle has one map location and already has a stable primary key, region, and lifecycle. Additive columns keep snapshots, saves, and the existing battle panel compatible while making the location independent of visible unit billboards. The movement system already persists the exact first-contact position in each stopped unit, so a deterministic spherical mean of sorted participant positions is a better source than a region center. Preserving the first anchor prevents a moving or filtered unit from moving the effect after the contact has been established. `anchor_source` distinguishes observed contact from the documented fallback and makes legacy rows diagnosable.
- **Alternatives considered**:
  - Create a separate battle-anchor table: rejected because it adds another join, schema, and persistence lifecycle for a one-to-one value.
  - Recalculate the average participant position every frame: rejected because it would move the battle marker and would make filtering/late snapshots affect presentation.
  - Persist a raw contact event only: rejected because old saves and snapshot consumers need a directly available current anchor.

The battle ID is already stable across `positional` → `assault`, so the anchor is copied from the prior row during mode changes rather than recalculated. Snapshot serialization is table-generic; no protocol message or version bump is needed.

## Decision 3: Use a shared globe-anchor projection mechanism

- **Decision**: Extract the common geographic-to-screen projection and visible-hemisphere/edge handling used by map overlays into a reusable client presentation helper. Implement a dedicated `BattleEffectRenderer` that consumes this helper and the battle table; retire the current unit-dependent battle marker from `UnitRenderer`.
- **Rationale**: `EventRenderer` and `UnitProjectionService` currently contain related camera, globe-facing, and clipping calculations. A shared projection mechanism prevents the new effect from reintroducing the back-side/seam bugs already addressed elsewhere. A dedicated renderer keeps battle effects independent of unit filters and gives the renderer a single bounded loop over battles rather than one animation object per unit.
- **Alternatives considered**:
  - Draw the effect from `UnitRenderer`: rejected because the existing marker requires visible unit billboards and disappears when owners are filtered.
  - Copy the projection math into a new renderer: rejected because duplicated edge and hemisphere rules would drift and regress globe rendering.
  - Use a 3-D particle/projectile system: rejected as outside the MVP and unnecessarily couples presentation to frame rate and object count.

## Decision 4: Drive animation from the client presentation clock

- **Decision**: Derive effect phase from the stable battle ID, authoritative round/start time, and `ClientGameClock.get_display_total_minutes()`. Never use network arrival time or unseeded randomness. Keep the renderer read-only.
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

- **Decision**: Add unit tests for anchor computation and projection, renderer tests for lifecycle/mode/reduced-motion/filter behavior, integration coverage for passive-to-active escalation, and a 100-battle performance gate using the existing client performance harness.
- **Rationale**: The critical risks are geographic correctness, stale snapshot smoothing, globe occlusion, and frame cost. Focused tests make each risk observable without requiring a full interactive session; the existing performance test provides a comparable baseline.
- **Alternatives considered**:
  - Rely only on manual visual checks: rejected because deterministic anchor and lifecycle regressions are easy to miss.
  - Benchmark per-unit effects: rejected because the design intentionally removes per-unit work from the battle renderer.

The renderer will not depend exclusively on transient battle events. A concluded row may exist for only one authoritative tick, so the client keeps a short-lived last-visual cache keyed by battle ID to show the bounded conclusion cue and then expires it. Lifecycle tests also cover stalemate idempotency so a status marker cannot cause a duplicate start effect.

## Resolved Technical Unknowns

- The project uses Python 3.10+, Polars/Arrow table schemas, Arcade/OpenGL/ImGui client rendering, and pytest-based tests.
- The existing client presentation clock is suitable for smooth effect timing.
- Existing battle modes and lifecycle statuses are sufficient; no terrain, supply, combat-formula, or third-side data is required.
- No extension hooks are registered in `.specify/extensions.yml`; no pre-plan or post-plan command is required.
