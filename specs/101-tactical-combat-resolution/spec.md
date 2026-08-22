# Feature Specification: Tactical Combat Resolution MVP

## Clarifications

### Session 2026-08-22

- **Layer ownership**: `src/shared` contains passive actions, events, and view contracts only. Save migration/defaulting belongs to `src/server`; readiness, order, combat, alliance, and occupation policy belongs to `modules/base`.
- **Pending-order policy**: the latest valid movement or attack command replaces the existing pending order. An invalid command is rejected without deleting a valid pending order. An explicit readiness command cancels a pending movement/attack order, and hostile contact cancels both the transition and pending order.
- **Same-tick precedence**: when hostile contact and transition completion occur at the same simulation minute, contact interruption is processed first and combat uses the last completed readiness status. Other due transitions finalize afterward.
- **Combat outcome scope**: the MVP removes units whose strength reaches zero; it does not simulate routing. If both sides reach zero in one deterministic round, the battle is a draw with no victor and no occupation/controller transfer.
- **Alliance eligibility**: only a direct active military/defensive alliance with a country already on a battle side can add an ally. Alliances are not transitive. An ambiguous ally assignment is omitted for that tick and produces a diagnostic event; it never creates a third side.
- **Occupation resistance**: occupation exposes `resistance=0.0` as a deterministic MVP value. No separate resistance simulation is included.

## User Scenarios & Testing

### User Story 1 - Manage Unit Readiness (Priority: P1)

As a national military commander, I want to place units into parked, ready, or fortified status and see the preparation progress, so that I can prepare forces before committing them to movement or combat.

**Why this priority**: Readiness is the foundation for predictable military orders and defensive preparation.

**Independent Test**: Select a unit, request each supported status transition, and verify that the status, completion time, progress indicator, and command availability change as specified.

**Acceptance Scenarios**:

1. **Given** a newly deployed unit, **When** no readiness order is issued, **Then** the unit remains `PARKED`.
2. **Given** a `PARKED` unit, **When** the commander requests `READY`, **Then** the unit remains parked while a four-day transition progresses and becomes ready only when the transition completes.
3. **Given** a `READY` unit, **When** the commander requests `PARKED`, **Then** a two-day transition is shown and the unit becomes parked at completion.
4. **Given** a `READY` unit, **When** the commander requests `FORTIFIED`, **Then** a two-day transition is shown and the unit becomes fortified at completion.
5. **Given** a `FORTIFIED` unit, **When** the commander requests `READY`, **Then** the status changes immediately.
6. **Given** a `PARKED` unit, **When** the commander requests `FORTIFIED`, **Then** the unit first completes the transition to `READY` and then completes the fortification transition before becoming fortified.
7. **Given** a unit with an active status transition, **When** the commander views the unit on the map or in the unit details view, **Then** the current status, target status, progress, and estimated remaining time are visible.

---

### User Story 2 - Issue Orders Around Readiness (Priority: P1)

As a commander, I want movement and attack orders to respect unit readiness, so that units cannot bypass preparation time and the resulting behavior remains understandable.

**Why this priority**: Orders must remain authoritative and predictable while readiness changes are in progress.

**Independent Test**: Issue movement and attack orders to parked, ready, fortified, and transitioning units and verify the resulting order queue and status transitions.

**Acceptance Scenarios**:

1. **Given** a `READY` unit, **When** it receives a valid movement order, **Then** movement starts without a readiness transition.
2. **Given** a `FORTIFIED` unit, **When** it receives a movement or attack order, **Then** fortification is cancelled, the unit becomes ready immediately, and the requested order proceeds.
3. **Given** a `PARKED` unit, **When** it receives a movement or attack order, **Then** the order waits behind the required transition to `READY` and does not execute early.
4. **Given** a unit with an active status transition, **When** a conflicting status, movement, or attack order is issued, **Then** the command is rejected or replaces the pending order according to the displayed command policy, without silently bypassing the transition.
5. **Given** a unit is attacked while changing status, **When** engagement begins, **Then** the transition is cancelled and the unit enters combat using its last completed readiness status.

---

### User Story 3 - Resolve Two-Sided Battles With Allied Support (Priority: P1)

As a player, I want hostile forces to form a battle and allied forces to reinforce one of the two sides, so that engagements reflect military alliances without creating ambiguous multi-sided combat.

**Why this priority**: The battle loop must support coalition warfare while retaining a clear attacker-versus-defender model.

**Independent Test**: Create a hostile engagement with one or more allied countries present, advance the simulation through combat rounds, and verify side membership, losses, and conclusion.

**Acceptance Scenarios**:

1. **Given** hostile units enter the same region or engagement zone, **When** the simulation processes the contact, **Then** exactly one active battle is created for the region and conflict.
2. **Given** an active battle with two primary belligerents, **When** an eligible military ally enters the engagement, **Then** the ally joins one existing side and contributes units and strength to that side.
3. **Given** an allied country is present but has no active military alliance with either side, **When** the battle is resolved, **Then** it remains neutral and does not join either side automatically.
4. **Given** a battle contains multiple countries on each side, **When** the battle state is displayed, **Then** the battle still has exactly two sides and each country's contribution is separately visible.
5. **Given** an active battle, **When** a combat round is processed, **Then** casualties and readiness effects are deterministic from the initial state, unit strength, and unit readiness status.
6. **Given** one side reaches the configured defeat threshold, **When** the battle concludes, **Then** units whose strength reaches zero are removed, the battle emits one conclusion event, and no routing simulation is performed.

---

### User Story 4 - Monitor Battle Status (Priority: P1)

As a player, I want a clear battle status interface and map feedback, so that I can understand who is fighting, how the battle is progressing, and which allied forces are involved.

**Why this priority**: Combat decisions require current information without inspecting raw simulation data.

**Independent Test**: Open an active battle and verify that all required participants, readiness states, balance values, round information, losses, and lifecycle status are visible and update after a simulation round.

**Acceptance Scenarios**:

1. **Given** at least one active battle, **When** the player opens the battle overview, **Then** the interface lists the region, lifecycle status, both sides, participating countries, allied contributions, current balance, and cumulative losses.
2. **Given** an active battle, **When** a combat round updates the state, **Then** the battle interface refreshes the round, strength, losses, and status distribution without requiring a restart.
3. **Given** a unit is changing readiness, **When** it is shown in the unit overlay or details view, **Then** its progress bar and remaining time are visible.
4. **Given** a battle starts or concludes, **When** the client receives the updated state, **Then** the map displays the engagement or updated political control within one state update.
5. **Given** the player selects a battle entry, **When** the focus action is used, **Then** the map centers on the battle region.

---

### User Story 5 - Establish Military Occupation (Priority: P2)

As a victorious commander, I want the conquered region to retain its political owner while recording military control and occupation details, so that battlefield victory is distinct from permanent annexation.

**Why this priority**: Occupation is the necessary consequence of a concluded land battle but does not require a full diplomacy or annexation system for this MVP.

**Independent Test**: Resolve a battle in a region controlled by the defeated side and verify controller transfer, owner preservation, occupation state creation, and garrison tracking.

**Acceptance Scenarios**:

1. **Given** a battle concludes with a victor, **When** no hostile force remains in the region, **Then** military control changes to the victor while political ownership remains unchanged.
2. **Given** a region becomes occupied, **When** the player opens its details, **Then** the occupying country, garrison strength, resistance value, and occupation start time are visible.
3. **Given** a new hostile force enters an occupied region, **When** the simulation processes the contact, **Then** the occupation remains contested and is not silently finalized.

---

## Edge Cases

- A `PARKED → FORTIFIED` request is represented as two ordered transition stages.
- A readiness transition is interrupted by combat, save/load, pause, or a replacement command.
- A valid pending movement or attack order is replaced by the latest valid order, while an invalid replacement leaves the existing pending order intact.
- A hostile contact at the exact transition completion minute interrupts the transition before completion and uses the last completed readiness status.
- A fortified unit is ordered to move and must lose its fortified status before movement begins.
- Multiple allied countries join either side of one battle.
- The same ally is eligible for both sides due to inconsistent diplomatic data; the ally is omitted for that tick and a diagnostic event explains the rejection.
- Both sides reach the defeat threshold during the same round; the configured draw policy prevents arbitrary occupation.
- Units reaching zero strength are removed; no routing state is created in this MVP.
- A battle ends while a battle status view is open.
- A region has occupation state but no surviving garrison.
- A transition or battle update is serialized and restored without changing its completion result.

## Functional Requirements

- **FR-001**: Every military unit MUST have one stable readiness status: `PARKED`, `READY`, or `FORTIFIED`.
- **FR-002**: Readiness changes MUST be asynchronous and MUST expose current status, target status, progress from 0 to 1, and estimated remaining game time.
- **FR-003**: The default readiness durations MUST be four game days for `PARKED → READY`, two game days for `READY → PARKED`, two game days for `READY → FORTIFIED`, and zero time for `FORTIFIED → READY`.
- **FR-004**: `PARKED → FORTIFIED` MUST execute as two ordered transitions, first to `READY` and then to `FORTIFIED`.
- **FR-005**: Movement and attack orders MUST not bypass an active readiness transition. The latest valid order MUST replace the existing pending order, an invalid order MUST leave the existing pending order unchanged, and a valid pending order MUST execute only after the transition completes.
- **FR-006**: Movement or attack MUST cancel `FORTIFIED`; a fortified unit MUST become `READY` before the order executes.
- **FR-007**: A unit attacked during a readiness transition MUST cancel that transition and enter combat with its last completed readiness status. If contact and transition completion share a simulation minute, contact interruption MUST take precedence.
- **FR-008**: The engine MUST automatically create one tracked battle when hostile forces contact each other in the same region or engagement zone. For an engagement-zone contact, the battle region MUST be the lowest positive current region ID among the contact units, with unit ID as the tie-breaker, and only stationary units in that region contribute to the first round.
- **FR-009**: Each battle MUST contain exactly two sides, and each side MAY contain multiple countries, including eligible military allies.
- **FR-010**: Allied participation MUST require a direct active military or defensive alliance with a country already on the side and a valid stationary presence in the engagement; alliance chains MUST NOT be transitive, neutral countries MUST not join automatically, and ambiguous assignments MUST be omitted with a diagnostic event.
- **FR-011**: Combat rounds MUST apply deterministic outcomes based on unit strength and readiness status. Units whose strength reaches zero MUST be removed; simultaneous zero strength MUST produce a draw without occupation. Terrain type, regional fortification data, supply factor, and full logistics MUST be outside this MVP.
- **FR-012**: Battle lifecycle state MUST distinguish at least `ACTIVE`, `STALEMATE`, and `CONCLUDED`.
- **FR-013**: Battle state changes MUST emit semantic start, update, and conclusion events that are available to the client through the existing state synchronization path.
- **FR-014**: The battle status interface MUST display both sides, country membership, allied contributions, strength balance, cumulative losses, readiness distribution, round information, lifecycle status, and battle region.
- **FR-015**: Readiness progress MUST be visible in the unit overlay and unit details interface, including a remaining-time estimate.
- **FR-016**: A concluded victory MUST update military control of the region without changing political ownership and MUST create or update an occupation record.
- **FR-017**: Readiness transitions, pending orders, battle state, and occupation state MUST survive save/load without changing a deterministic outcome.
- **FR-018**: Combat resolution MUST execute in the simulation process and MUST not block client rendering or input handling. Snapshot consumption MUST remain bounded independently of graphics or network I/O.

## Key Entities & Data Model

- **UnitReadiness**: Stable status of a unit (`PARKED`, `READY`, or `FORTIFIED`) and the combat readiness modifier associated with that status.
- **StatusTransition**: The requested target status, transition stage, start time, completion time, progress, and optional pending movement or attack order.
- **CombatEngagement**: Battle identifier, region, conflict identifier, lifecycle status, round number, start time, last update time, side membership, current balance, and cumulative losses.
- **CombatParticipant**: Unit and country membership within one of the two battle sides, including ally role, current strength, readiness status, and contribution.
- **OccupationStatus**: Region, military controller, garrison strength, resistance value, occupation start time, and contested state.
- **BattleStatusView**: Player-facing summary of both sides, participants, readiness distribution, losses, balance, round, lifecycle state, and map focus target.

## Scope Boundaries

The MVP does not add terrain classification, regional fortification levels, supply networks, organization simulation, naval or air combat, pathfinding, permanent annexation, or more than two opposing sides. Allied countries are represented as additional participants within one of the two sides.

## Success Criteria

- **SC-001**: 100% of repeated simulations with the same initial state, commands, and game time produce the same readiness transitions, battle updates, and outcomes.
- **SC-002**: A readiness progress indicator reaches completion at the configured transition time with no more than one simulation update of visible timing error.
- **SC-003**: No movement or attack order bypasses the required readiness transition, and every valid order either executes after readiness or reports a clear rejection.
- **SC-004**: Every hostile contact produces exactly one battle start event, zero or more update events, and no more than one conclusion event.
- **SC-005**: Allied participants are displayed on the correct side in 100% of valid alliance scenarios, while neutral participants remain outside the battle sides.
- **SC-006**: Players can identify both sides, allied contributions, current balance, losses, readiness states, and lifecycle status from the battle interface without opening raw state data.
- **SC-007**: A concluded victory updates visible military control within one client state update while preserving political ownership.
- **SC-008**: Validation covers at least 100 simultaneous active engagements without blocking the simulation step or client update loop, including a bounded headless snapshot-consumption check independent of graphics and network I/O; a 500-engagement performance target remains a post-MVP benchmark.

## Assumptions & Dependencies

- Existing unit movement, war records, treaty records, state snapshots, and map interaction systems remain available.
- Readiness durations are measured in game days and are configuration values, with the defaults defined in FR-003.
- The stable readiness status remains separate from transient movement and engagement state.
- The two-side battle model is authoritative; allied countries are participants inside one side rather than independent combatants.
- Occupation records represent military control, expose a deterministic `resistance=0.0` value, and do not perform permanent annexation, routing, or economic extraction in this MVP.
- Existing state synchronization delivers events and updated tables to the client.
