# Feature Specification: Tactical Battle Visualization

## User Scenarios & Testing

### Primary User Story

As a military commander, I want battles to be visibly located on the map and to look different when forces are merely in contact versus when one side has ordered an assault, so that I can understand combat intensity without opening raw battle data.

### Acceptance Scenarios

1. **Show a passive engagement**: **Given** hostile armies enter one another's engagement zone without an explicit assault order, **When** the battle becomes active, **Then** the map shows a restrained passive-contact animation at the battle location and labels the battle as passive or positional.
2. **Show an active assault**: **Given** a passive battle exists, **When** a valid attack or assault order is executed by a participating unit, **Then** the map changes to a visibly stronger active-assault animation and labels the battle as active or assault.
3. **Anchor the animation**: **Given** a battle is created during stationary contact or movement contact, **When** the player rotates, pans, or zooms the globe, **Then** the animation remains attached to the authoritative contact location rather than to a screen coordinate.
4. **Use the actual contact point**: **Given** the armies meet inside an engagement zone rather than at a region center, **When** the battle effect is displayed, **Then** it appears at the contact point or at the deterministic battle anchor recorded for that engagement, with a documented region-center fallback only when no contact coordinate exists.
5. **Keep animation smooth between snapshots**: **Given** the server sends battle updates less frequently than the display refreshes, **When** the battle effect is rendered, **Then** its pulse and exchange phases continue smoothly from the presentation clock without waiting for another server update or jumping between snapshots.
6. **Represent two sides and allies**: **Given** a battle contains multiple countries on two sides, **When** the animation is displayed, **Then** all effects use the side's visual identity, allied units are grouped with their side, and no third visual side is created.
7. **Change intensity without changing the battle**: **Given** a passive battle escalates to an assault or an assault returns to positional contact, **When** the next authoritative battle state arrives, **Then** only the visual intensity and effect pattern change while the battle identity and location remain stable.
8. **Respect the globe**: **Given** a battle anchor rotates behind the globe or approaches the visible edge, **When** the map is rendered, **Then** the effect is hidden or clipped with the globe's visible hemisphere and never draws across the back side or map seam.
9. **Handle lifecycle changes**: **Given** a battle is stalemated or concluded, **When** the corresponding state arrives, **Then** the passive or active combat animation stops or changes to a short conclusion indicator and does not continue indefinitely.
10. **Show battles when units are filtered**: **Given** the player hides one or more unit owners, **When** a battle remains in the selected world area, **Then** its battle marker and effect remain visible if authoritative battle data contains a valid anchor.
11. **Handle multiple simultaneous battles**: **Given** several battles are visible at once, **When** their effects overlap or share a region, **Then** each remains identifiable through deterministic spacing, layering, or marker treatment without random frame-to-frame movement.
12. **Avoid gameplay coupling**: **Given** an animation is displayed, **When** the player changes camera position or the client drops a frame, **Then** no unit strength, battle round, ownership, or outcome changes as a result.

### Edge Cases

- A passive battle has no explicit attack order and must not display active assault effects.
- A battle starts from a moving-unit contact where the units stop between region centers.
- A battle has no valid participant coordinate because units are hidden or a legacy row is incomplete; the region anchor is used as a fallback.
- Two battles share a region but have different wars or battle IDs; their effects remain visually distinguishable.
- One side contains several allied countries with different flag colors; side identity remains clear without implying a third side.
- The battle mode changes in the same snapshot as a round update; the new visual mode applies without duplicating the battle marker.
- A battle concludes during a frame; no later frame continues the combat loop indefinitely.
- A battle anchor is on the back hemisphere, near the globe silhouette, or near the longitude seam.
- The globe is zoomed far in or far out; the effect remains map-anchored and its screen footprint remains bounded.
- The client receives a stale battle row while a newer state is already available; the newest state wins and no old effect is resurrected.
- A battle is visible while the battle overview, unit details, or selection rectangle is open; overlays do not block required controls.
- Reduced or disabled animation settings are enabled; a persistent battle marker and state label remain available even when motion effects are suppressed.

## Functional Requirements

- **FR-001**: The visualization MUST treat `positional` contact as a passive battle and `assault` contact as an active battle. Passive contact is created when hostile armies are within the configured engagement zone without a valid explicit assault order; active contact requires an executed attack or assault order from a participating side.
- **FR-002**: Passive and active battles MUST remain the same authoritative battle entity when only the engagement mode changes. The visualization MUST change intensity and effect pattern without creating duplicate battles or resetting the battle location.
- **FR-003**: Every visualized battle MUST have a stable map anchor associated with its authoritative contact location. The anchor MUST support a latitude/longitude contact point and a region reference, with the region center used only as a deterministic fallback when no contact coordinate is available.
- **FR-004**: The battle anchor MUST be persisted or deterministically reconstructable so that replay, save/load, and snapshot replacement do not move an existing effect to a different location.
- **FR-005**: Passive battle animation MUST use low-intensity, non-directional feedback such as a restrained pulse, paired side halos, or a subtle clash marker. It MUST NOT imply a committed advance, projectile exchange, or an explicit assault.
- **FR-006**: Active battle animation MUST use a higher-intensity visual language such as directional exchanges, impact flashes, or stronger pulses that clearly communicate an ordered assault. It MUST remain a presentation effect and MUST NOT simulate individual projectiles or alter combat calculations.
- **FR-007**: Visual identity MUST distinguish the two battle sides using side-level colors or symbols. Allied countries MUST inherit the visual identity of their assigned side, and neutral or rejected participants MUST NOT produce combat effects.
- **FR-008**: Animation timing MUST be driven by the client presentation clock and a deterministic battle/round phase. It MUST continue smoothly between authoritative snapshots and MUST NOT depend on per-frame server updates, random unseeded values, or network arrival timing.
- **FR-009**: The animation MUST remain attached to the globe surface during camera rotation, zoom, and pan. Its screen-space footprint MUST remain bounded so zooming does not cause the effect to grow with the globe instead of remaining a readable map marker.
- **FR-010**: The renderer MUST apply the same visible-hemisphere and globe-edge rules as other map overlays. Back-facing effects MUST be hidden, edge-crossing effects MUST be clipped or split, and no effect may draw across the globe's hidden side or longitude seam.
- **FR-011**: A battle marker and its state label MUST remain available when unit billboards are filtered, occluded, or absent, provided the battle row has a valid anchor. Unit visibility MUST NOT determine whether authoritative battle state is shown.
- **FR-012**: Passive, active, stalemated, and concluded states MUST have distinct visual lifecycle behavior. Combat animation MUST stop when a battle is concluded; any conclusion pulse MUST be short-lived, bounded, and non-interactive.
- **FR-013**: Multiple visible battles MUST use deterministic ordering and spacing when their effects overlap. Identical state and camera inputs MUST produce identical effect positions, phases, colors, and draw ordering.
- **FR-014**: Battle animation MUST not change simulation state, issue commands, alter selection, intercept input, or affect unit movement, readiness, strength, occupation, ownership, or battle outcomes.
- **FR-015**: The visual layer MUST degrade gracefully when a battle row lacks a contact coordinate, a participant list, or a recognized side color. It MUST use the documented fallback and retain a visible state marker rather than failing the entire map overlay.
- **FR-016**: The battle status interface and map marker MUST expose the same passive/active terminology and the underlying positional/assault state so that the visual effect and battle panel cannot contradict one another.
- **FR-017**: A player-controlled reduced-motion or disabled-animation setting MUST suppress motion and flashing while retaining a static battle marker, side identity, lifecycle state, and map focus behavior.
- **FR-018**: The feature MUST cover passive contact, active escalation, anchor projection, camera rotation/zoom, globe occlusion, snapshot interpolation, lifecycle stop behavior, multiple battles, filtered units, reduced motion, and deterministic replay with focused tests.
- **FR-019**: Rendering battle effects MUST remain bounded independently of the number of units in each battle. The renderer MUST draw from the battle projection rather than creating one animated object per soldier or per combat calculation.

## Key Entities & Data Model

- **BattleVisualAnchor**: The stable geographic point and region fallback used to place a battle marker and its effects on the globe.
- **PassiveBattleVisual**: The low-intensity representation of a `positional` engagement created by proximity contact.
- **ActiveBattleVisual**: The high-intensity representation of an `assault` engagement created by an explicit attack order.
- **BattleVisualPhase**: A deterministic presentation-only phase derived from battle identity, round, lifecycle state, and the client presentation clock.
- **BattleSideVisual**: The side-level color, symbol, or intensity identity shared by principal countries and eligible allies.
- **BattleConclusionIndicator**: A bounded, non-interactive visual acknowledgement that a battle has ended.

## Scope Boundaries

This feature adds map visualization only. It does not change engagement detection, combat formulas, readiness timing, alliance eligibility, unit strength, occupation rules, or battle outcomes. It does not add individual soldier models, projectile physics, terrain-specific effects, sound, camera shake, or a third combat side.

## Success Criteria

- **SC-001**: In user acceptance testing, players correctly identify passive versus active battle intensity in at least 95% of displayed scenarios without opening raw battle data.
- **SC-002**: In 100% of tested contacts, the effect is anchored to the authoritative contact point or documented region fallback and remains attached during camera rotation, pan, and zoom.
- **SC-003**: Between two authoritative snapshots, the effect phase advances continuously with the presentation clock; no snapshot boundary produces a visible positional jump or phase reset.
- **SC-004**: Back-facing or seam-crossing effects are hidden or clipped correctly in 100% of globe-orbit test positions, with no combat effect rendered on the hidden interior or opposite globe surface.
- **SC-005**: Passive effects produce no active-assault visual pattern, and active effects are visibly stronger in 100% of mode comparison tests.
- **SC-006**: A concluded battle stops its combat animation within one state update; any conclusion indicator disappears within one second of its presentation start.
- **SC-007**: With 100 simultaneous visible battles, the battle visualization adds no more than 5% overhead to the baseline frame time and does not reduce the existing client performance gate.
- **SC-008**: Identical snapshots, camera inputs, and presentation time produce identical effect phases, positions, colors, and ordering across repeated runs.
- **SC-009**: Battle markers and lifecycle labels remain visible for 100% of valid battles when unit billboards are filtered or temporarily absent.
- **SC-010**: Reduced-motion mode removes animated movement and flashing while preserving battle identification, side identity, state label, and focus behavior in 100% of tested cases.

## Assumptions & Dependencies

- **Assumption**: The existing battle modes `positional` and `assault` are the authoritative equivalents of passive and active battles. The user-facing labels may say passive and active while the underlying state remains stable.
- **Assumption**: A passive battle begins from hostile units entering the existing engagement radius; no additional terrain or supply data is required for the visual distinction.
- **Assumption**: An active battle begins only after an explicit attack or assault order has been accepted for a participating unit. Merely being in the same engagement zone does not make a battle active.
- **Assumption**: Stylized aggregate effects are sufficient for the MVP; individual shot, projectile, soldier, and physics simulation are intentionally excluded.
- **Assumption**: The client presentation clock is the source for smooth visual timing, while the server remains authoritative for battle mode, anchor, lifecycle, strength, and outcome.
- **Dependency**: The tactical combat state provides a stable battle ID, region, mode, lifecycle, participants, round, and authoritative state revisions.
- **Dependency**: Unit or battle state provides a contact coordinate for movement contacts, or the region table provides a deterministic geographic fallback.
- **Dependency**: Existing globe projection and visible-hemisphere handling are reused so visual effects follow the same camera and clipping rules as other overlays.
- **Dependency**: Existing battle overview, unit overlay, snapshot, and reduced-motion settings remain available for presentation integration.
