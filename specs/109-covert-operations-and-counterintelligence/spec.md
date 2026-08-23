# Feature Specification: Covert Operations and Counterintelligence

## User Scenarios & Testing

### Primary User Story

As a national leader, I want to recruit, train, deploy, and defend covert cells, so that intelligence, sabotage, assassination, terrorism, coup attempts, and counterintelligence create a hidden but auditable strategic layer.

### Acceptance Scenarios

1. **Create a cell**: **Given** a country has available covert capacity and funding, **When** the player creates a cell, **Then** the cell has an origin, current assignment, readiness, skill level, upkeep, and lifecycle state.
2. **Train a cell**: **Given** a cell is eligible for training, **When** the player starts training, **Then** the cell consumes time and funding and advances through Recruit, Regular, Veteran, or Elite levels only when the training completes.
3. **Run espionage**: **Given** a trained cell has a valid target and assignment, **When** the mission executes, **Then** it can reveal civilian, military, economic, or strategic intelligence with an accuracy determined by cell skill, preparation, target security, and communications.
4. **Run sabotage**: **Given** a cell has a valid civilian or military sabotage target, **When** the mission executes, **Then** it applies bounded damage or disruption, publishes a result, and can trigger detection or retaliation.
5. **Attempt a high-risk mission**: **Given** a cell is assigned assassination, terrorism, coup, or framing, **When** the preparation and execution conditions are met, **Then** the system resolves success, failure, capture, detection, and diplomatic consequences using the mission’s configured risk.
6. **Defend against a cell**: **Given** a target country has domestic security and counterintelligence capacity, **When** an incoming mission is prepared or executed, **Then** detection and interception probability reflects the defender’s capacity and the attacker’s concealment.
7. **Track covert activity**: **Given** a cell or mission changes state, **When** the player opens the covert overview, **Then** the player sees known cells, assignments, preparation, upkeep, confidence, detection, and the latest outcome without exposing information that the target has not discovered.
8. **Persist hidden state**: **Given** cells, missions, and detection information exist, **When** the game is saved, loaded, or replayed, **Then** hidden information and pending mission outcomes remain consistent.

### Edge Cases

- A cell is created in a country without a valid owner or target; it remains unassigned and cannot execute a mission.
- A cell is captured during preparation; the mission is cancelled or exposed according to its configured capture rule.
- A target changes owner, government, or war status before execution; target validity and diplomatic consequences are reevaluated at the execution boundary.
- A cell lacks communications or transit access; it cannot advance beyond the corresponding lifecycle state.
- A mission is submitted twice; only one active mission may consume the cell and the second action is rejected.
- A failed mission must not reveal secret information to the target unless the configured detection result says it was exposed.
- A legacy save contains no covert-cell records; the system starts with no cells and does not invent intelligence.
- A cell reaches the maximum skill level; additional training consumes no time or funding unless an explicit maintenance rule applies.

## Functional Requirements

- **FR-001**: The system MUST represent covert cells with owner, origin, current location or assignment, lifecycle state, skill level, readiness, concealment, upkeep, and last-known status.
- **FR-002**: Cell lifecycle MUST support creation, recruitment, transit, training, active assignment, dormant status, capture, retirement, and loss.
- **FR-003**: Skill levels MUST include Recruit, Regular, Veteran, and Elite. Each level MUST define mission capability, preparation quality, concealment, and maintenance cost.
- **FR-004**: A cell MUST be assigned at most one active mission and MUST meet the mission’s target, location, skill, readiness, and communications requirements before preparation begins.
- **FR-005**: Missions MUST support civilian espionage, military espionage, civilian sabotage, military sabotage, assassination, terrorism, coup attempt, and framing as distinct mission types with distinct risks and outputs.
- **FR-006**: Every mission MUST have preparation, execution, resolution, and cleanup states. Preparation MUST consume configured time and resources before execution becomes valid.
- **FR-007**: Mission resolution MUST calculate success, partial success, failure, capture, detection, and attribution using the cell, target security, preparation, relevant relations, and configured randomness seeded by authoritative state.
- **FR-008**: Civilian espionage MUST be able to reveal bounded information about government, economy, demographics, laws, or relations. Military espionage MUST be able to reveal bounded information about units, readiness, research, production, or strategic weapons.
- **FR-009**: Civilian and military sabotage MUST apply bounded, target-specific disruption and MUST never directly delete authoritative country, region, unit, or treaty records.
- **FR-010**: Assassination, terrorism, coup, and framing missions MUST use separate consequence profiles and MUST publish their result, attribution state, and political or diplomatic effects.
- **FR-011**: Defender counterintelligence MUST be able to detect, disrupt, capture, or misattribute an incoming mission. The target MUST receive secret details only when the resolution includes discovery.
- **FR-012**: Cells and missions MUST consume upkeep, preparation cost, or execution cost from the owning country through the existing budget contract, and insufficient funds MUST block or pause the action.
- **FR-013**: A detected or attributed operation MUST create readable messages, relation changes, diplomatic pressure, war or crisis signals, or domestic security effects according to its mission profile.
- **FR-014**: AI-controlled countries MUST use the same cell, mission, resource, target-validity, and detection rules as human-controlled countries.
- **FR-015**: The player MUST see only information authorized by the cell’s owner, target discovery state, and intelligence confidence. The interface MUST distinguish confirmed, estimated, outdated, and unknown information.
- **FR-016**: Covert actions MUST be validated by country authority, target validity, cell availability, deadlines, and current diplomatic or war rules. The client MUST not mutate cell or mission state directly.
- **FR-017**: Identical covert state, time, ordered actions, and deterministic seed MUST produce identical preparation, detection, and mission outcomes.
- **FR-018**: Cells, missions, hidden discoveries, capture results, and pending deadlines MUST survive save/load, snapshot synchronization, and replay.
- **FR-019**: The system MUST process only active cells, pending missions, and affected counterintelligence links when no covert state changed elsewhere.

## Key Entities & Data Model

- **Covert Cell**: A persistent intelligence asset with owner, skill, lifecycle, concealment, readiness, assignment, and upkeep.
- **Covert Mission**: A time-bounded operation with type, target, preparation, cost, risk, execution time, result, and attribution.
- **Counterintelligence Posture**: A country-level defensive capacity covering domestic security, communications monitoring, foreign penetration, and response authority.
- **Intelligence Finding**: A target-specific piece of information with confidence, freshness, discovery authority, and expiration or invalidation conditions.
- **Covert Incident**: A visible or hidden record of detection, capture, attribution, retaliation, or political consequence.

## Scope Boundaries

This feature activates the existing covert-cell and covert-mission concepts. It does not replace diplomacy, war resolution, political lifecycle, military combat, strategic weapon resolution, or the existing notification and save systems. It does not expose secret data merely because an operation exists.

## Success Criteria

- **SC-001**: 100% of invalid covert actions fail without consuming a cell, budget, or target state and provide a reason.
- **SC-002**: In controlled scenarios, each skill level changes the documented preparation, success, concealment, or cost outcome and reaches the next level only after its training completes.
- **SC-003**: Target countries receive secret mission details in 100% of detected cases and in 0% of undiscovered cases.
- **SC-004**: Repeated runs with identical state, actions, and seed produce identical mission outcomes, discoveries, and diplomatic consequences.
- **SC-005**: A player can inspect all owned cells, pending missions, upkeep, target, preparation status, and known results from the covert overview within 30 seconds.
- **SC-006**: Save/load during recruitment, training, preparation, and execution preserves the same next outcome and hidden-information boundaries.
- **SC-007**: Processing 5,000 active cells and 1,000 pending missions completes within 500 milliseconds in a controlled benchmark when unrelated countries are unchanged.

## Assumptions & Dependencies

- **Assumption**: Existing covert-cell records and action names are the starting domain contract; this feature adds authoritative lifecycle and resolution behaviour around them.
- **Assumption**: Mission outcomes use deterministic seeded variation, not untracked randomness.
- **Assumption**: The first release models aggregate covert capability rather than individual agents, travel animations, or real-world operational procedures.
- **Dependency**: Existing country authority, budget, relations, war, politics, strategic-weapon, notification, snapshot, and persistence contracts remain authoritative.
- **Dependency**: Military, economic, political, and diplomatic effects are emitted to their existing systems rather than recalculated inside covert operations.
