# Feature Specification: Campaign Scenarios, Objectives, and Advisor

## User Scenarios & Testing

### Primary User Story

As a player, I want a campaign to define my country, political sphere, objectives, deadlines, and success state, with an advisor that explains urgent opportunities and risks, so that the simulation has a clear strategic direction without limiting sandbox play.

### Acceptance Scenarios

1. **Start a scenario**: **Given** a scenario defines selectable countries, starting conditions, sphere or party control, and objectives, **When** the player starts it, **Then** all setup values are applied once and shown before the first actionable update.
2. **Track an objective**: **Given** an objective requires a control, diplomatic, economic, resource, research, or strategic condition, **When** the relevant state changes, **Then** progress, remaining requirement, deadline, and status update visibly.
3. **Complete a control objective**: **Given** a player must control a region or conquer a country, **When** the condition is met for the required duration, **Then** the objective completes and records the qualifying state.
4. **Complete a development objective**: **Given** an objective requires GDP per capita, resource share, or a population or development threshold, **When** the metric reaches the requirement, **Then** progress reflects the authoritative metric and does not use a stale snapshot.
5. **Complete a treaty or strategic objective**: **Given** an objective requires joining a treaty, building a nuclear capability, or using a strategic weapon, **When** the existing diplomacy or strategic system resolves that action, **Then** the objective receives the event and updates without duplicating the underlying mechanic.
6. **Delegate a sphere**: **Given** the player controls a sphere or party scope that can be delegated, **When** the player assigns it to AI control, **Then** the assignment, authority, priorities, and return-to-player action are visible and persistent.
7. **Use the advisor**: **Given** a country has a new crisis, opportunity, deadline, or objective change, **When** the advisor evaluates it, **Then** it creates a prioritized recommendation with context, confidence, affected system, and optional focus action.
8. **Resolve victory or defeat**: **Given** all required objectives complete, a deadline expires, or a loss condition is met, **When** the scenario evaluates, **Then** it enters a visible win, loss, draw, or sandbox-continuation state according to scenario rules.
9. **Persist campaign state**: **Given** scenario progress, delegation, recommendations, and deadlines exist, **When** the game is saved and loaded, **Then** the same objective and campaign outcome follows.

### Edge Cases

- A scenario has no objectives; it remains a valid sandbox campaign with no forced victory screen.
- Two objectives depend on the same event; each evaluates independently and records its own completion.
- A control objective is briefly met and then lost before its hold duration; progress follows the configured reset or decay rule.
- A metric is unavailable because a region or resource has no source record; the objective remains pending with a visible missing-data reason.
- The player changes country or delegation authority mid-campaign; existing progress remains attached to the scenario actor.
- A deadline expires in the same update as an objective completes; deterministic evaluation order decides the result and records both conditions.
- An advisor recommendation becomes invalid before selection; it is marked stale rather than issuing an invalid action.
- A legacy save contains static objective rows but no progress; progress starts from the current authoritative state.

## Functional Requirements

- **FR-001**: A campaign scenario MUST define selectable actors, starting setup, political or sphere scope, objective set, deadlines, win conditions, loss conditions, and sandbox policy.
- **FR-002**: Scenario setup MUST apply country, party or sphere control, initial relations, starting military or economic state, and enabled rules exactly once at campaign start.
- **FR-003**: Objectives MUST support control of regions, conquest of countries, treaty or alliance membership, resource requirements, GDP-per-capita thresholds, strategic-weapon construction or use, and resource-share thresholds.
- **FR-004**: Every objective MUST define actor, condition, target, quantity or threshold, hold duration where needed, deadline, progress rule, completion status, failure status, and evidence.
- **FR-005**: Objective evaluation MUST consume authoritative outputs from territory, diplomacy, economy, resources, research, military, strategic, demographics, and politics systems and MUST NOT reimplement their calculations.
- **FR-006**: Objective progress MUST show current value, target value, remaining amount, time held, deadline, and the event or state that last changed it.
- **FR-007**: The system MUST support objective states pending, active, completed, failed, expired, cancelled, and blocked, with explicit transition reasons.
- **FR-008**: Campaign outcome MUST evaluate required and optional objectives, win conditions, loss conditions, deadlines, draw rules, and sandbox continuation at a deterministic boundary.
- **FR-009**: Sphere or party delegation MUST identify owner, delegate, scope, authority, priorities, start time, return condition, and current AI or human controller.
- **FR-010**: Delegation MUST never grant authority beyond its declared scope and MUST remain compatible with existing country ownership, command, diplomacy, and multiplayer authority rules.
- **FR-011**: The advisor MUST consume existing messages, news, objectives, and system signals to generate prioritized recommendations for crises, opportunities, deadlines, and unresolved actions.
- **FR-012**: Advisor recommendations MUST include reason, source signal, affected country or region, confidence or urgency, expiry, and optional authorized action. A recommendation MUST not silently issue commands.
- **FR-013**: AI-controlled countries and delegated spheres MUST use the same objective, authority, and campaign rules as human-controlled actors.
- **FR-014**: Campaign state, objective progress, setup provenance, delegation, recommendations, deadlines, and outcome MUST survive save/load, snapshot synchronization, and replay.
- **FR-015**: Identical scenario state, time, events, and ordered actions MUST produce identical progress, recommendations, and campaign outcome.
- **FR-016**: The player MUST be able to see all active objectives, progress, deadlines, delegation, recent evidence, and advisor priorities from the campaign overview.

## Key Entities & Data Model

- **Campaign Scenario**: Starting setup, actor scope, rules, objective set, deadlines, and outcome policy.
- **Campaign Objective**: A measurable condition with actor, target, threshold, duration, progress, status, evidence, and deadline.
- **Sphere Delegation**: A bounded transfer of control over a country, party, or sphere to a human or AI authority.
- **Advisor Recommendation**: A prioritized explanation of an opportunity, risk, deadline, or recommended authorized action.
- **Campaign Outcome**: The current win, loss, draw, sandbox, or ongoing state with qualifying evidence.

## Scope Boundaries

This feature activates scenario setup, objective evaluation, delegation, and advisor guidance around existing systems. It does not replace diplomacy, economy, military combat, strategic warfare, political lifecycle, messages, news, or thematic maps. It does not force sandbox campaigns to use objectives.

## Success Criteria

- **SC-001**: 100% of scenario starts apply setup once and expose the selected actor, scope, rules, objectives, and deadlines before the first action.
- **SC-002**: In controlled scenarios, each supported objective type updates within one relevant state update and records evidence for completion or failure.
- **SC-003**: An objective completed and then lost before its hold duration never reports a false permanent completion.
- **SC-004**: Advisor recommendations identify the affected system, reason, urgency, and expiry for 100% of configured high-priority signals.
- **SC-005**: Repeated seeded runs and save/load reproduce identical objective progress, delegations, recommendations, and campaign outcomes.
- **SC-006**: A player can identify the next required objective action and its deadline within 30 seconds from the campaign overview.
- **SC-007**: Evaluating 10,000 objectives and 5,000 advisor signals completes within 500 milliseconds in a controlled benchmark when only affected conditions changed.

## Assumptions & Dependencies

- **Assumption**: Existing objective, message, news, diplomacy, economy, military, research, resource, and strategic records are extended as the authoritative event sources.
- **Assumption**: Objective definitions are scenario data and can be added without changing the simulation runner.
- **Assumption**: Advisor guidance is informative by default; all state-changing actions still require explicit authorized commands.
- **Dependency**: Existing territory, diplomacy, economy, research, resources, military, politics, message, news, snapshot, and persistence contracts remain available.
