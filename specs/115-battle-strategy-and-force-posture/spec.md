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
9. **Review a battle at a glance**: **Given** a battle has participating countries and forces, **When** the player opens its overview, **Then** it shows both sides, participating force types and counts, relative positions, and a current aggregate balance indicator.
10. **Command force types**: **Given** the player selects a force type in a battle, **When** the player chooses attack or back off or applies an attack/defend preset, **Then** only authorized forces of the affected types receive the order and the resulting command state is visible.
11. **Withdraw a force**: **Given** a force is ordered to retreat, **When** it withdraws to the rear of its side's battle position and completes regrouping, **Then** it exits the battle and follows a valid route back to its capital.
12. **Occupy a cleared country**: **Given** no surviving hostile force remains in the target country, **When** an authorized commander orders occupation, **Then** eligible forces spread across valid regions and establish military control without changing political ownership; annexation remains a separate action.
13. **Review a battle result**: **Given** a battle concludes, **When** the player opens its summary, **Then** the summary identifies participants, outcome, and losses by force type and country where information is authorized.

### Edge Cases

- A commander submits an order for a unit or battle it does not control; the action is rejected without changing posture.
- A force is destroyed, captured, or removed before its order becomes effective; the order is cancelled with a reason.
- A battle concludes while a retreat order is pending; the order becomes a no-op and does not resurrect combat.
- A force has no valid retreat route or safe destination; it remains in the battle state and receives the configured risk or surrender outcome.
- A posture conflicts with a mandatory scenario order; the scenario rule wins and the player sees the conflict.
- A preset contains an unavailable posture for one unit domain; available orders apply and the unavailable entry is marked rather than silently ignored.
- Two authorized orders arrive at the same boundary; deterministic order precedence resolves the conflict.
- A legacy battle has no explicit posture; it uses the documented neutral posture without changing battle identity.
- A retreating force cannot reach the battle's rear or its capital because its route becomes invalid; movement reports the block and the existing battle and movement rules decide its safe fallback.
- An occupation order is submitted while hostile forces remain or by an unauthorized country; it is rejected without changing political ownership or force location.
- A battle summary includes force types or participants hidden from a viewer; the viewer sees only information permitted by existing intelligence rules.

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
- **FR-016**: The battle overview MUST show participating countries on each existing side, counts by force type, relative force positions, and a derived aggregate balance indicator. It MUST identify the indicator as an estimate rather than an outcome guarantee.
- **FR-017**: Commanders MUST be able to issue attack or back-off orders to an authorized force type and apply data-driven attack/defend presets. Presets MUST resolve into visible per-force orders and MUST NOT override a more specific valid order.
- **FR-018**: A retreat MUST move the affected force toward the rear of its current battle position; after the configured regrouping condition is met, the force MUST leave the battle and return toward its capital using the military movement route and access contract. It MUST NOT change the existing readiness timing or create a new combat side.
- **FR-019**: After hostile forces in a target country are cleared, an authorized occupation order MUST distribute eligible forces over valid target regions and establish military control only. It MUST NOT change sovereign or political ownership; formal annexation MUST remain a separate political or diplomatic action.
- **FR-020**: A completed battle MUST expose an authorized summary of outcome, participating sides and countries, and casualties by force type. Unavailable enemy details MUST remain subject to intelligence confidence and disclosure rules.

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
- **SC-008**: A battle overview displays the participating forces by type, side, and relative position, and labels the aggregate balance as an estimate.
- **SC-009**: Attack/back-off orders and attack/defend presets affect only authorized force types and produce inspectable command records.
- **SC-010**: A successfully regrouped retreat exits the battle and follows a valid route toward the capital without changing the battle's side model or readiness contract.
- **SC-011**: An occupation order is accepted only after hostile forces are cleared, establishes regional military control, and leaves political ownership unchanged.
- **SC-012**: Completed battle summaries report authorized participants, outcomes, and force-type losses without disclosing unknown information.

## Assumptions & Dependencies

- **Assumption**: Existing battle IDs, two-side participant rules, readiness, movement, and occupation remain authoritative.
- **Assumption**: Battle balance indicators are approximate summaries from available force and intelligence data; the authoritative battle resolver alone determines outcomes.
- **Assumption**: The initial release uses aggregate command projections and does not model individual soldiers, terrain supply networks, or projectile paths.
- **Assumption**: Presets are scenario data and may be extended without changing the battle lifecycle contract.
- **Dependency**: Existing military movement, readiness, battle, visualization, diplomacy, snapshot, and persistence contracts remain available.
- **Dependency**: Movement to the rear, withdrawal, and return to capital use the military movement route and access rules; occupation and annexation use existing military-control and political-ownership contracts.
