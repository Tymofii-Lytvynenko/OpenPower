# Feature Specification: Tactical Combat Resolution

## User Scenarios & Testing

### Primary User Story
As a player controlling a sovereign nation, I want my military units to engage opposing forces in real-time tactical combat when invading or defending territory, so that wars are resolved through strategic unit positioning, terrain advantage, supply lines, and force composition rather than instant arbitrary outcomes.

### Acceptance Scenarios
1. **Initiating Engagement**: **Given** hostile military forces enter the same region or overlapping geographic coordinates, **When** the simulation tick processes, **Then** an active battle engagement is created and battle start events are broadcast to the map UI.
2. **Combat Calculation**: **Given** an ongoing battle engagement, **When** simulation ticks execute, **Then** casualties, morale depletion, and organization loss are computed deterministically based on unit stats, terrain defensive bonuses, and supply status.
3. **Battle Conclusion & Territory Occupation**: **Given** one side's morale or force count falls below surrender thresholds, **When** the combat state updates, **Then** the defeated force retreats or is destroyed, and the region's control transitions to the victor with an occupation state applied.

### Edge Cases
- Multi-faction engagements involving three or more warring powers in a single region.
- Armies retreating into non-allied, neutral, or impassable terrain.
- Simultaneous morale collapse of both attacking and defending armies.

## Functional Requirements

- **FR-001**: Combat Initiation: The engine MUST automatically detect hostile unit collisions/co-location and establish a tracked `CombatEngagement`.
- **FR-002**: Asynchronous Resolution: Combat calculations MUST run within the simulation process without blocking the main UI rendering thread.
- **FR-003**: Terrain & Fortification Modifiers: Combat calculations MUST apply defensive modifiers based on terrain type (mountains, forest, urban) and regional fortification structures.
- **FR-004**: Morale & Attrition System: Forces MUST suffer morale degradation and supply attrition, driving unit retreats prior to total annihilation.
- **FR-005**: Occupation Transfer: Victorious forces MUST establish an occupation state on contested regions, updating political control and economic extraction capabilities.
- **FR-006**: Telemetry & Event Signaling: Combat state changes MUST emit semantic events (`EventBattleStarted`, `EventBattleUpdated`, `EventBattleConcluded`) across IPC for visual and audio rendering.

## Key Entities & Data Model

- **CombatEngagement**: Tracks active battle identifier, region location, participating force IDs, battle duration, cumulative casualties, and morale status.
- **OccupationStatus**: Represents regional occupation state, controlling country ID, garrison strength, and civilian resistance index.

## Success Criteria

- **SC-001**: Seamless Performance: Combat resolution for 500+ simultaneous global engagements completes without dropping main UI rendering frame rates below 60 FPS.
- **SC-002**: Determinism: 100% of combat engagements yield identical outcomes across matching random seeds and initial force configurations.
- **SC-003**: Real-Time Map Feedback: Political map overlays and unit health indicators update within 1 simulation tick of combat state changes.

## Assumptions & Dependencies

- **Assumption**: Existing unit movement vectors and spherical/equirectangular projection systems are operational.
- **Dependency**: IPC event dispatch pipeline is available for broadcasting combat events to the client.
