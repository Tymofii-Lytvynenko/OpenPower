# Feature Specification: Military Capability Matrix and Training

## User Scenarios & Testing

### Primary User Story

As a military commander, I want unit roles, capabilities, counter-capabilities, research, design, experience, and training to be explicit, so that military composition and preparation matter beyond unit count and generic strength.

### Acceptance Scenarios

1. **Inspect a unit type**: **Given** a player selects a unit type or design, **When** its details open, **Then** the player sees its role, speed, manoeuvrability, sensors, range, precision, damage, payload, stealth, countermeasures, armour, and training requirements.
2. **Research a capability**: **Given** a research track is available, **When** progress reaches a capability threshold, **Then** the relevant unit design, role, counter, or characteristic becomes available according to its prerequisites.
3. **Create a design**: **Given** a country has unlocked components, **When** it creates a unit design, **Then** the design records its selected capabilities, costs, production requirements, role, and battlefield constraints.
4. **Train a formation**: **Given** a unit has access to a training location and funding, **When** training is scheduled, **Then** it advances through Recruit, Regular, Veteran, and Elite levels only after the required time and training conditions are met.
5. **Use a counter**: **Given** an attacking capability meets a defending capability’s counter condition, **When** the existing battle resolver evaluates the engagement, **Then** it receives the documented modifier without changing battle identity, side membership, or occupation lifecycle.
6. **Estimate an unknown force**: **Given** a commander lacks complete intelligence or telecom coverage, **When** the unit overview is generated, **Then** hidden capabilities and strength are shown as an estimate with confidence and freshness rather than false precision.
7. **Persist readiness and experience**: **Given** a unit is training, deployed, or engaged, **When** the game is saved and loaded, **Then** capability, experience, training progress, and derived modifiers remain consistent.
8. **Compare force composition**: **Given** the player opens a force or design, **When** unit types are compared, **Then** each type's fixed role and target interactions are distinguishable from the design's researched, adjustable characteristics.
9. **Use allied intelligence**: **Given** an ally has a more accurate current estimate of a foreign force, **When** the player inspects that force, **Then** the best eligible shared estimate is shown with its source, confidence, and freshness.

### Edge Cases

- A design references a locked or retired capability; production is blocked and the reason is visible.
- A unit has no training location, funding, or eligible instructor; training pauses without losing completed progress.
- A unit reaches Elite and receives no further experience benefit from duplicate training.
- A unit type has no configured counter; it uses the neutral interaction result rather than an invented weakness.
- A unit has a capability inappropriate to its domain; design validation rejects it before production.
- A battle contains an allied unit with a different country’s training state; each unit retains its own state while the battle resolver receives a side-level projection.
- Telecom or intelligence data becomes stale during battle; the commander’s estimate degrades without changing authoritative unit state.
- A legacy unit lacks capability or experience fields; it receives documented defaults and remains compatible with existing strength and readiness.

## Functional Requirements

- **FR-001**: The system MUST define canonical unit roles and domains for land, air, naval, and strategic forces, with data-driven extension points for scenario or mod content. The default catalog MUST cover infantry and infantry vehicles, air-defence units, mobile launchers, tanks and artillery; transport and attack helicopters, anti-submarine helicopters, attack aircraft, fighters and bombers; patrol craft, corvettes, frigates, destroyers, attack submarines, ballistic-missile submarines and aircraft carriers; and strategic missiles and missile-defence systems.
- **FR-002**: Each unit type or design MUST expose role-relevant characteristics including speed, manoeuvrability, sensors, gun or strike range, precision, damage, missile payload, missile range, missile precision, missile damage, stealth, countermeasures, and armour where applicable.
- **FR-003**: Every unit type MUST distinguish fixed characteristics that define its role and valid target interactions from variable characteristics that a national design may improve. Capability values MUST have documented units, bounds, prerequisites, production implications, and interaction meaning. A missing characteristic MUST use an explicit not-applicable or neutral value.
- **FR-004**: Research MUST be funded by force domain or configured research group. Research completion MUST advance the shared capability level for eligible unit types in that group and unlock capabilities, components, counters, or design constraints through existing research progression without duplicating research queues or progress rules.
- **FR-005**: Unit designs MUST validate role, domain, capability prerequisites, production cost, maintenance, and deployment constraints before becoming producible.
- **FR-006**: Units MUST track Recruit, Regular, Veteran, and Elite training levels, experience progress, training state, training location, training cost, and last training event. A new production order MAY select Recruit or Regular as its automatic initial training level; Veteran and Elite training MUST require a completed-unit training order.
- **FR-007**: Training MUST consume configured time and resources, MUST preserve completed progress when paused, and MUST be unavailable when the unit is in an incompatible movement, battle, or loss state.
- **FR-008**: The system MUST publish a capability projection to the existing battle resolver. It MUST provide role, counter, range, damage, defence, training, and intelligence modifiers without reimplementing battle rounds, readiness transitions, occupation, or annexation.
- **FR-009**: Capability interactions MUST support explicit counter relationships and neutral outcomes. A counter MUST be attributable to the involved capabilities and remain bounded.
- **FR-010**: Intelligence views MUST distinguish authoritative owned-unit data from estimated foreign-unit data and MUST include confidence, freshness, and source factors. Foreign force-composition accuracy MUST account for the observer's telecommunications capability and active intelligence assigned to the force owner's country. Eligible allied countries MUST share the most accurate available estimate without exposing data beyond the receiving country's intelligence authority.
- **FR-011**: AI-controlled countries MUST use the same research, design, training, capability, counter, and intelligence rules as human-controlled countries.
- **FR-012**: The player MUST be able to compare unit roles, capabilities, counters, training level, production implications, and estimated enemy information from the military interface.
- **FR-013**: Capability, design, training, experience, and intelligence state MUST survive save/load, snapshot synchronization, and replay.
- **FR-014**: Identical capability state, training inputs, research state, and ordered actions MUST produce identical design availability, training progress, intelligence estimates, and battle projections.
- **FR-015**: The system MUST process only changed designs, active training, affected research unlocks, and stale intelligence records when no other military state changed.
- **FR-016**: Training MUST improve only the configured characteristics for a unit role, including speed and manoeuvrability, sensors, weapon precision, stealth, and countermeasures where applicable. Training MUST move the force to a training state, remove it from active map presence and battle eligibility for the training period, and return it to deployment availability when training completes or is explicitly aborted.
- **FR-017**: The default combat-efficiency factors MUST be 0.25 for parked, 1.0 for ready, and 1.5 for fortified units. Readiness transition timing MUST remain governed by the existing tactical-combat contract. Readiness-dependent upkeep MUST use explicit, bounded scenario values; changing readiness MUST emit a mobilization signal that eligible foreign observers can detect under the intelligence rules.
- **FR-018**: The unit catalog MUST document each role's intended strengths, weaknesses, valid attack targets, target vulnerabilities, and deployment domain. A unit MUST not damage a target outside its configured interaction matrix.
- **FR-019**: A missing or stale foreign-unit observation MUST be displayed as unknown or estimated rather than as a zero-strength authoritative force.

## Key Entities & Data Model

- **Unit Role Definition**: A canonical domain and role with required, optional, and countered capabilities.
- **Default Role Catalog**: The scenario-level roster of land, air, naval, and strategic unit roles, including each role's fixed characteristics, valid targets, vulnerabilities, and deployment domain.
- **Unit Capability Profile**: Characteristics, bounds, prerequisites, production impact, and interaction rules for a unit type or design.
- **Unit Design**: A country-owned configuration assembled from unlocked capabilities with cost, maintenance, role, and deployment constraints.
- **Training Record**: A unit’s level, experience, progress, location, cost, eligibility, and lifecycle.
- **Capability Projection**: The bounded battle-facing role, counter, training, range, damage, and defence modifiers consumed by the existing resolver.
- **Intelligence Estimate**: A confidence-scored view of another country’s capabilities, strength, readiness, or design information.

## Scope Boundaries

This feature adds capability and training depth around existing research, design, units, readiness, and tactical resolution. It does not replace battle lifecycle, two-side rules, movement, production queue scheduling, occupation, annexation, strategic strike resolution, or thematic maps.

## Success Criteria

- **SC-001**: 100% of producible unit designs show their role, applicable capabilities, prerequisites, costs, and counters before production is authorized.
- **SC-002**: In controlled tests, each training level changes the documented projection and cannot be reached without completing its configured training requirement.
- **SC-003**: Capability and counter modifiers change only the documented battle projection; battle identity, sides, readiness lifecycle, occupation, and ownership remain unchanged.
- **SC-004**: Foreign capability views show confidence and freshness in 100% of cases where the information is incomplete or stale.
- **SC-005**: Repeated seeded runs and save/load reproduce identical research unlocks, design validation, training progress, and capability projections.
- **SC-006**: A player can select a design and identify its role, strongest counter, training level, and production constraint within 30 seconds.
- **SC-007**: Updating 50,000 units and 10,000 designs completes within 1 second in a controlled benchmark when only 5% of records changed.
- **SC-008**: Every default unit type has a documented role, domain, fixed characteristics, variable characteristics, valid target set, and counter relationship before it can be produced.
- **SC-009**: In controlled cases, Recruit, Regular, Veteran, and Elite training applies only its documented characteristic changes and the unit cannot participate in movement or combat while training.
- **SC-010**: Identical telecom, intelligence assignments, alliance sharing, and observation time produce the same foreign-force estimate, confidence, and freshness across repeated runs.

## Assumptions & Dependencies

- **Assumption**: Existing research tracks, unit designs, unit readiness, and battle resolution remain authoritative; this feature supplies richer capability and experience data.
- **Assumption**: The initial capability matrix is data-driven and can be extended by content modules without changing the simulation runner.
- **Assumption**: Aggregate capability projections are sufficient for the first release; individual projectile or soldier simulation is out of scope.
- **Assumption**: The default role catalog is data-driven. Scenario and mod content may add types without changing the established unit, movement, or battle identities.
- **Assumption**: Training levels affect unit capability through bounded projections; the existing OpenPower readiness durations and transition rules remain authoritative.
- **Dependency**: Existing research, military unit, readiness, production, infrastructure, intelligence, battle, snapshot, and persistence contracts consume the new projections.
