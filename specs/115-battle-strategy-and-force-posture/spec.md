# Feature Specification: Battle Strategy and Force Posture

## User Scenarios & Testing

### Primary User Story

As a commander, I want to choose attack, defence, disengagement, and retreat postures for participating forces, so that battles respond to operational intent rather than using one generic resolution behaviour.

### Acceptance Scenarios

1. **Set a battle posture**: **Given** a country controls a participating force, **When** the commander selects an allowed posture, **Then** the authoritative battle state records the order, effective time, issuer, and affected force.
2. **Use an attack strategy**: **Given** a force has an active attack posture and valid targets, **When** the next battle round resolves, **Then** the existing resolver receives the documented attack, risk, readiness, and casualty modifiers.
3. **Use a defensive strategy**: **Given** a force has a defensive posture, **When** the next battle round resolves, **Then** it receives the documented protection, holding, readiness, and counterattack behaviour without automatically changing ownership.
4. **Disengage**: **Given** a commander orders a force to back off, **When** the order is valid, **Then** the force stops initiating new assaults and follows the configured disengagement or withdrawal path.
5. **Retreat and reorganize**: **Given** a force has retreated or reached a safe location, **When** reorganization is scheduled, **Then** it restores readiness or cohesion according to time, location, infrastructure, and supply assumptions before returning to active combat.
6. **Use a preset**: **Given** the player selects a configured strategy preset, **When** it is applied to an eligible battle or force, **Then** every affected posture is shown and can be overridden by a more specific valid order.
7. **Handle allies**: **Given** several countries fight on one side, **When** one commander changes its posture, **Then** the order affects only authorized forces and does not create a third side or silently command an ally’s units.
8. **Persist command intent**: **Given** a posture, retreat, or reorganization order is pending, **When** the game is saved and loaded, **Then** the same order, deadline, and next battle projection remain active.

### Edge Cases

- A commander submits an order for a unit or battle it does not control; the action is rejected without changing posture.
- A force is destroyed, captured, or removed before its order becomes effective; the order is cancelled with a reason.
- A battle concludes while a retreat order is pending; the order becomes a no-op and does not resurrect combat.
- A force has no valid retreat route or safe destination; it remains in the battle state and receives the configured risk or surrender outcome.
- A posture conflicts with a mandatory scenario order; the scenario rule wins and the player sees the conflict.
- A preset contains an unavailable posture for one unit domain; available orders apply and the unavailable entry is marked rather than silently ignored.
- Two authorized orders arrive at the same boundary; deterministic order precedence resolves the conflict.
- A legacy battle has no explicit posture; it uses the documented neutral posture without changing battle identity.

## Functional Requirements

- **FR-001**: A battle or participating force MUST expose an explicit posture state with issuer, effective time, duration or expiry, and reason.
- **FR-002**: The initial posture set MUST include attack, defend, hold, back off, retreat, and reorganize. Scenario data MAY add domain-specific postures.
- **FR-003**: An attack posture MUST control whether a force may initiate or sustain an assault and MUST supply bounded attack-risk, readiness, and casualty modifiers to the existing resolver.
- **FR-004**: A defensive or hold posture MUST control assault participation and MUST supply bounded protection, readiness, holding, and counterattack modifiers to the existing resolver.
- **FR-005**: A back-off posture MUST stop new assault initiation and MUST calculate a valid disengagement or withdrawal action using the existing movement and battle contracts.
- **FR-006**: A retreat order MUST identify a valid destination or fallback route, timing, risk, interruption rule, and resulting battle participation state.
- **FR-007**: A reorganize order MUST identify duration, eligible location, readiness or cohesion recovery, resource cost, and the condition required before renewed combat participation.
- **FR-008**: Strategy presets MUST be data-driven, inspectable, assignable to eligible forces, and overridable by a more specific authorized order.
- **FR-009**: Command authority MUST be checked per country, force, battle, ally, and scenario rule. An order MUST NOT mutate another country’s units without an explicit shared-command permission.
- **FR-010**: The existing battle resolver MUST remain responsible for battle identity, rounds, readiness transitions, side membership, occupation, and outcome. This feature supplies command intent and bounded projections only.
- **FR-011**: Posture changes MUST be reflected in the battle overview and command history with effective time, affected forces, and expected effect.
- **FR-012**: AI-controlled countries MUST use the same posture, retreat, reorganization, authority, and conflict rules as human-controlled countries.
- **FR-013**: Identical battle state, posture orders, time, and deterministic seed MUST produce identical command projections, retreat paths, and next outcomes.
- **FR-014**: Postures, orders, presets, deadlines, route decisions, and reorganization progress MUST survive save/load, snapshot synchronization, and replay.
- **FR-015**: The system MUST process only battles and forces whose posture, route, readiness, or lifecycle changed when no global command rule changed.

## Key Entities & Data Model

- **Force Posture**: A command state controlling a force’s participation, risk, protection, and engagement intent.
- **Battle Command Order**: An authorized attack, defence, back-off, retreat, or reorganization order with issuer, timing, target, route, and lifecycle.
- **Strategy Preset**: A named set of posture defaults and priorities applicable to eligible forces or battles.
- **Retreat Route**: A validated path and risk profile for disengagement or withdrawal.
- **Command Projection**: The bounded attack, defence, readiness, casualty, and participation modifiers consumed by the existing battle resolver.

## Scope Boundaries

This feature adds command intent and force posture around the existing tactical battle lifecycle. It does not replace battle resolution, readiness state, movement, occupation, annexation, unit capability, supply simulation, or battle visualization. It does not create a third combat side.

## Success Criteria

- **SC-001**: 100% of posture and retreat orders are either applied to an authorized force or rejected without state mutation and with a visible reason.
- **SC-002**: In controlled battles, attack, defence, back-off, retreat, and reorganize postures produce distinct documented projections and lifecycle states.
- **SC-003**: An ally’s posture order changes only the issuer’s authorized forces in 100% of multi-country battle tests.
- **SC-004**: A concluded battle never resumes because of a stale posture or retreat order.
- **SC-005**: Repeated seeded runs and save/load reproduce identical command projections, retreat paths, and battle continuation decisions.
- **SC-006**: A player can identify every participating force’s current posture, issuer, effective time, and next action within 30 seconds.
- **SC-007**: Updating 10,000 active force postures and 2,000 battles completes within 500 milliseconds in a controlled benchmark when only due orders advance.

## Assumptions & Dependencies

- **Assumption**: Existing battle IDs, two-side participant rules, readiness, movement, and occupation remain authoritative.
- **Assumption**: The initial release uses aggregate command projections and does not model individual soldiers, terrain supply networks, or projectile paths.
- **Assumption**: Presets are scenario data and may be extended without changing the battle lifecycle contract.
- **Dependency**: Existing military movement, readiness, battle, visualization, diplomacy, snapshot, and persistence contracts remain available.
