# Feature Specification: Freeplay Core Loop and System Polish

## User Scenarios & Testing

### Primary User Story

As a single-player, I want to choose a country and enter an open-ended game without choosing a campaign, so I can govern it, react to a changing world, and continue for as long as I want.

### Acceptance Scenarios

1. **Given** the player is on the new-game screen, **When** they choose an available country and start freeplay, **Then** the game opens the map with that country as the player-controlled country without requiring a scenario, objective, or campaign outcome.
2. **Given** a freeplay session is running, **When** the player pauses, resumes, or changes simulation speed, **Then** the displayed date and authoritative world state follow the selected time control.
3. **Given** the player issues an available economic, political, military, or diplomatic order, **When** the simulation accepts or rejects it, **Then** the player can see the resulting state change or a useful reason for rejection.
4. **Given** autonomous countries and world systems are active, **When** the player advances time, **Then** the world continues to evolve and new events, messages, and relevant state changes become visible.
5. **Given** a freeplay save, **When** the player loads it, **Then** the same country, date, state, and ongoing orders continue without requiring campaign setup.
6. **Given** the primary freeplay journeys, **When** the automated UI journey and simulation acceptance flows run, **Then** they report pass/fail outcomes and useful diagnostics without a manual desktop acceptance task.

### Edge Cases

- No country is selected or the selected country becomes unavailable before launch.
- The session fails or is cancelled during startup; the player receives a clear result and no orphaned session remains.
- A command is invalid, unauthorized, stale, or no longer applicable when processed.
- A freeplay save has no campaign metadata or contains legacy campaign metadata.
- Optional campaign content exists but is unavailable; this does not block freeplay.
- The player returns to the menu or loads another save while a session is active.

## Functional Requirements

- **FR-001**: New game MUST offer a direct freeplay path based on selecting a playable country; campaign/scenario selection MUST be optional and MUST NOT gate this path.
- **FR-002**: Starting freeplay MUST create one authoritative simulation session for the selected country and MUST NOT require campaign setup, objectives, or a campaign result to become playable.
- **FR-003**: The player MUST be able to pause, resume, and select each supported simulation speed while seeing the current date and active time state.
- **FR-004**: The in-game interface MUST expose a coherent minimum set of existing economic, political, military, and diplomatic actions, with commands sent through the existing action boundary.
- **FR-005**: Player command outcomes MUST be visible; rejected or failed commands MUST include an actionable reason when the authoritative result provides one.
- **FR-006**: Advancing time MUST continue the existing registered country AI and world simulation systems, including applicable economic, political, demographic, military, diplomatic, and event updates.
- **FR-007**: The player MUST be able to save and resume freeplay while preserving authoritative state and ongoing gameplay orders supported by the existing persistence contract.
- **FR-008**: Freeplay MUST remain open-ended by default and MUST NOT present campaign victory, defeat, or objective completion as a prerequisite for continuing play.
- **FR-009**: The minimum freeplay loop MUST be verifiable through automated simulation and UI journey workflows; no manual desktop usability check is a release task for this feature.
- **FR-010**: Client interaction MUST remain presentation-only and dispatch semantic actions; simulation rules and authoritative state changes MUST remain in their owning module systems.

## Key Entities & Data Model

- **Freeplay Session**: A normal authoritative game session associated with the selected player country and the existing world state; it does not require campaign records.
- **Player Command Result**: The existing authoritative accepted, rejected, or failed result shown to the player with its reason and command identity.
- **Freeplay Save**: The existing save representation containing the authoritative world state and supported ongoing orders, with campaign data optional.

## Success Criteria

- **SC-001**: A player can start a new freeplay session by selecting a country without selecting a campaign or scenario.
- **SC-002**: An automated journey can pause, resume, and change speed, and its report confirms the corresponding date/time state.
- **SC-003**: Automated gameplay flows cover one representative accepted action in each core domain—economy, politics, military, and diplomacy—and confirm an authoritative consequence is visible.
- **SC-004**: Rejected player commands surface a useful reason, while unrelated or AI-owned outcomes do not appear as player errors.
- **SC-005**: A saved freeplay state resumes with the same player country, date, tax policy, and pending unit-movement order.
- **SC-006**: Freeplay can continue across repeated simulation updates without campaign objectives or campaign outcomes being present.
- **SC-007**: All acceptance evidence for this feature is generated by automated commands or tests; the feature task list contains no manual desktop acceptance step.

## Assumptions & Dependencies

- **Assumption**: Freeplay is the default single-player mode; scenarios and campaigns remain optional content outside the core launch path.
- **Assumption**: Existing base gameplay systems and data remain the source of truth; this work closes player-facing integration and reliability gaps before adding new mechanics.
- **Dependency**: Existing session startup, country selection, action dispatch, time controls, feedback, save/load, and UI journey testing infrastructure.
- **Constraint**: Preserve deterministic simulation, persistence compatibility, strict layer boundaries, and composition over inheritance.
