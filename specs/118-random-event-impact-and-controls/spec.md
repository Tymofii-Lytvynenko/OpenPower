# Feature Specification: Random Event Impact and Controls

## User Scenarios & Testing

### Primary User Story

As a player or scenario administrator, I want random events to have concrete, bounded effects and clear controls, so that disasters, health crises, strikes, booms, and environmental shocks change the simulation without becoming opaque or uncontrollable.

### Acceptance Scenarios

1. **Trigger an eligible event**: **Given** an event is enabled and its conditions, location, cooldown, and probability are valid, **When** the event roll resolves, **Then** one event instance is created with a cause, affected scope, severity, duration, and seed.
2. **Apply a disaster**: **Given** an earthquake, flood, wildfire, tornado, volcanic event, drought, or tsunami affects a region, **When** it resolves, **Then** population, health, infrastructure, economy, migration, and budget effects use the event’s configured bounded profile.
3. **Apply a health crisis**: **Given** an epidemic affects eligible regions, **When** the event progresses, **Then** health, mortality pressure, labour, migration, public approval, and response cost change through existing system contracts.
4. **Apply an economic event**: **Given** an economic boom or strike affects an eligible country or region, **When** it progresses, **Then** production, employment, demand, budget, approval, and political pressure receive the configured effects.
5. **Respond to an event**: **Given** an event offers response choices, **When** the player or AI selects a valid response, **Then** the response cost, mitigation, delay, and secondary effects are recorded and applied once.
6. **Disable events**: **Given** the scenario or administrator disables a category or all random events, **When** the next roll boundary occurs, **Then** no new disabled event is created while active instances follow their explicit completion rule.
7. **Inspect event history**: **Given** an event is active or resolved, **When** the player opens the event view, **Then** it sees trigger, location, severity, effects, response, remaining duration, and recovery state.
8. **Persist deterministic events**: **Given** an event is pending, active, or resolved, **When** the game is saved, loaded, or replayed, **Then** the same instance, timing, effects, and response result continue.

### Edge Cases

- An event’s target no longer exists or changes owner; the instance follows its scope policy and does not affect an invalid record.
- Several events hit one region in the same update; severity stacking and order are deterministic and bounded.
- An event is disabled after triggering; its active effects follow the configured finish, cancellation, or conversion rule.
- An event has no valid response option or the player lacks funds; the default response is visible and does not invent resources.
- An event rolls at a boundary with a cooldown or global disable change; the documented boundary order decides eligibility.
- An event would reduce a value below its minimum or raise it above its maximum; the result is clamped with remaining pressure recorded.
- A legacy save contains active-event identifiers but no effect state; the system reconstructs only documented defaults and marks uncertainty.
- A no-op event has no applicable target; it is recorded as skipped rather than repeatedly retriggered.

## Functional Requirements

- **FR-001**: The existing random-event catalog MUST support enabled state, category, eligible scope, trigger conditions, probability, cooldown, severity range, duration, response options, and effect profile.
- **FR-002**: Event instances MUST record event type, seed, trigger time, target, affected scope, severity, duration, status, response, effects applied, and recovery state.
- **FR-003**: Event eligibility MUST evaluate scenario settings, category enablement, target conditions, ownership, cooldown, active-instance limits, and deterministic probability.
- **FR-004**: Disaster profiles MUST support bounded effects for infrastructure, health, population pressure, migration, economy, public approval, budget, and recovery according to configured event type.
- **FR-005**: Health-crisis profiles MUST use existing demographic and health contracts for mortality, health, labour, migration, and public-service effects and MUST NOT create a parallel population model.
- **FR-006**: Economic-event profiles MUST use existing economy, budget, production, labour, politics, and resource contracts for booms, strikes, and related effects.
- **FR-007**: Every event effect MUST identify category, magnitude, start, duration or expiry, source event, affected subject, and whether it is immediate, recurring, or recoverable.
- **FR-008**: Response choices MUST define authority, cost, timing, mitigation, risk, and secondary effects. An invalid response MUST be rejected without partial cost.
- **FR-009**: Event stacking MUST use explicit category caps, precedence, and aggregation rules. It MUST never bypass minimum or maximum value bounds.
- **FR-010**: Scenario or administrative controls MUST support enabling or disabling all events and individual categories, configuring frequency, and setting deterministic seeds or scenario defaults.
- **FR-011**: AI-controlled countries MUST use the same eligibility, response, cost, mitigation, and consequence rules as human-controlled countries.
- **FR-012**: The player MUST be able to inspect active and recent events, affected subjects, severity, remaining duration, response, effects, and recovery progress.
- **FR-013**: Every triggered, skipped, rejected, resolved, cancelled, and disabled event MUST publish a readable event-history record and authorized notification.
- **FR-014**: Identical event state, time, settings, and deterministic seed MUST produce identical triggers, severity, stacking, responses, and effects.
- **FR-015**: Event catalog settings, active instances, effects, responses, cooldowns, and recovery timers MUST survive save/load, snapshot synchronization, and replay.
- **FR-016**: Processing MUST evaluate only due rolls, active instances, affected subjects, and recovery timers when no global event setting changed.

## Key Entities & Data Model

- **Event Definition**: A configurable event category with eligibility, probability, cooldown, severity, duration, responses, and effects.
- **Event Instance**: A triggered event with target, seed, lifecycle, severity, response, effect records, and recovery.
- **Event Effect**: A bounded immediate, recurring, or recoverable change attributed to one event and subject.
- **Event Response**: An authorized player or AI choice with cost, timing, mitigation, risk, and secondary effects.
- **Event Control Profile**: Scenario or administrative enablement, frequency, category, and deterministic-seed settings.

## Scope Boundaries

This feature extends the existing random-event trigger and catalog concepts with real consequences, responses, controls, and lifecycle records. It does not create a second event generator, replace the economy, demographics, health, infrastructure, politics, budget, strategic, or history systems, or add thematic-map rendering.

## Success Criteria

- **SC-001**: 100% of triggered events create one inspectable instance with target, severity, timing, seed, and effect profile.
- **SC-002**: In controlled scenarios, each supported event category changes its declared downstream indicators within one relevant update and never exceeds configured bounds.
- **SC-003**: Disabled event categories create zero new instances after the next eligibility boundary while active instances follow their documented completion rule.
- **SC-004**: Invalid responses consume zero cost and create no partial effect in 100% of tested cases.
- **SC-005**: Repeated seeded runs and save/load reproduce identical event instances, responses, stacking, and recovery.
- **SC-006**: A player can determine why an event occurred, what it affects, how long it lasts, and which response is available within 30 seconds.
- **SC-007**: Updating 10,000 active events and 100,000 effect records completes within 1 second in a controlled benchmark when only due records advance.

## Assumptions & Dependencies

- **Assumption**: The existing active-event catalog and deterministic roll pipeline remain the starting trigger contract; this feature adds effect and control semantics.
- **Assumption**: Event effects are bounded and data-driven, with no requirement for unbounded cascading catastrophe simulation in the first release.
- **Assumption**: Disabling an event prevents new instances but does not silently erase active effects.
- **Dependency**: Existing economy, demographics, health, infrastructure, migration, politics, budget, strategic, history, notification, snapshot, and persistence contracts consume event effects.
