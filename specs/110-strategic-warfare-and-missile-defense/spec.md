# Feature Specification: Strategic Warfare and Missile Defense

## User Scenarios & Testing

### Primary User Story

As a national leader, I want strategic weapons, nuclear research, launch authorization, target effects, and missile defense to be understandable and consequential, so that strategic warfare is a deliberate decision with visible risk rather than an unimplemented inventory.

### Acceptance Scenarios

1. **Research a strategic weapon**: **Given** a country has the required research progress and policy authority, **When** the strategic weapon technology completes, **Then** the country can produce or acquire the permitted weapon class and sees its readiness requirements.
2. **Prepare a launch**: **Given** an owned strategic weapon is operational, **When** the player selects a valid military or civilian target, **Then** the system validates range, readiness, authorization, target status, and launch cost before creating a pending strike.
3. **Resolve defense**: **Given** a target has active missile defense, **When** a strike enters the defense resolution, **Then** the first defense layer can intercept it and a surviving strike can be evaluated by the second layer according to range, coverage, readiness, and deterministic probability.
4. **Apply military damage**: **Given** a strike reaches a military target, **When** it resolves, **Then** affected units, readiness, infrastructure, and communications receive bounded damage according to the weapon and target profile.
5. **Apply civilian consequences**: **Given** a strike reaches a civilian target, **When** it resolves, **Then** population, health, infrastructure, economy, public approval, and environmental consequences are applied within configured bounds and recorded.
6. **Show escalation**: **Given** a strike is launched, intercepted, or detected, **When** the result is known, **Then** the attacker, target, allies, and affected diplomatic systems receive the configured alerts and relation or war signals.
7. **Persist the chain**: **Given** a strike is pending between updates, **When** the game is saved, loaded, or replayed, **Then** authorization, defense, impact, and consequence order remains identical.
8. **Unlock and select a strategic weapon**: **Given** a country completes the strategic program and the required weapon research, **When** it selects a produced or acquired missile, **Then** only weapon classes, payload levels, and targets permitted by its completed research and missile range are available.
9. **Compare configured payload levels**: **Given** the player reviews a missile design, **When** a payload level is selected, **Then** its configured yield and default blast radius are shown before production or launch.
10. **Resolve layered interception**: **Given** a target has researched and fielded operational defense, **When** an incoming missile enters covered space, **Then** long-range and short-range defenses attempt interception in order using the documented default probabilities and configured coverage.

### Edge Cases

- A weapon is out of range, not ready, destroyed, or no longer controlled; launch is rejected without consuming it.
- A target changes owner or becomes invalid while a strike is pending; the strike is cancelled or retargeted only under an explicit policy.
- A defense layer has no coverage, insufficient readiness, or an invalid configuration; the layer contributes zero interception rather than a hidden automatic success.
- Both defense layers engage the same incoming strike; each layer resolves once in a documented order.
- A strike hits an empty military region; infrastructure and strategic effects can apply, but no unit damage is invented.
- A civilian target has no regional population or infrastructure record; the strike applies only effects supported by authoritative data.
- A country attempts to launch without required political authorization; the action is rejected and the attempted escalation is logged.
- A legacy save has strategic weapon inventory but no defense or impact metadata; the inventory remains safe and uses documented defaults.
- A country has weapon technology but has not completed the prerequisite strategic program; weapon research, production, and launch remain unavailable.
- A missile payload level or target distance exceeds completed research or the missile's range; the launch is rejected without consuming the weapon.
- A defense system has been researched but not fielded, or is outside its coverage area; it contributes no interception attempt.

## Functional Requirements

- **FR-001**: Strategic weapon capability MUST be gated by research, production or acquisition, operational status, readiness, range, and political authorization.
- **FR-002**: The system MUST represent intercontinental ballistic and submarine-launched ballistic weapon classes when enabled by scenario data, with class-specific range, payload, readiness, launch time, and defense interaction.
- **FR-003**: A launch request MUST identify the weapon, origin, target country, target region or strategic object, target mode, authorization context, and intended resolution time.
- **FR-004**: Valid launch targets MUST include military and civilian modes. Military mode MUST prefer units, bases, infrastructure, or communications; civilian mode MUST prefer cities, population, or economic centres according to target data.
- **FR-005**: Launch validation MUST reject an invalid owner, target, range, readiness, authorization, destroyed weapon, insufficient cost, or conflicting pending order without mutating the weapon inventory.
- **FR-006**: Missile defense MUST support two ordered defensive layers with independent coverage, range, readiness, interception capability, and failure state. An inactive layer MUST NOT silently intercept.
- **FR-007**: Defense resolution MUST be deterministic for identical weapon, target, defense, time, and ordered actions. An intercepted strike MUST stop downstream impact unless a configured surviving payload exists.
- **FR-008**: A surviving military strike MUST calculate bounded effects on targeted units, unit readiness, regional infrastructure, communications, and military capability using the existing military and infrastructure contracts.
- **FR-009**: A surviving civilian strike MUST calculate bounded effects on population, health, infrastructure, communications, economy, approval, migration pressure, and environment using the existing demographic, health, economic, and political contracts.
- **FR-010**: Collateral damage MUST be represented separately from intended target damage and MUST identify affected regions, categories, severity, and cause.
- **FR-011**: Every launch, interception, miss, impact, collateral effect, and environmental consequence MUST create an auditable event and the appropriate authorized notifications.
- **FR-012**: A detected launch MUST be visible to the target and eligible observers according to detection rules; an unresolved hidden order MUST not reveal impact details before its resolution boundary.
- **FR-013**: Strategic warfare MUST update diplomatic, war, relation, stability, and escalation signals through existing systems and MUST NOT directly rewrite treaty membership or territorial ownership.
- **FR-014**: AI-controlled countries MUST use the same research, authorization, target validation, defense, impact, and escalation rules as human-controlled countries.
- **FR-015**: Strategic weapons, defense status, pending launches, authorization, interception, impact, and consequences MUST survive save/load, snapshot synchronization, and replay.
- **FR-016**: The player MUST be able to inspect each owned weapon’s class, readiness, range, authorization state, pending order, target, defense estimate, and recent outcome.
- **FR-017**: Identical strategic state, time, ordered actions, and deterministic seed MUST produce identical launch, interception, impact, and consequence results.
- **FR-018**: The system MUST process only pending strikes, affected defense layers, target regions, and consequence timers when no strategic state changed elsewhere.
- **FR-019**: Strategic weapon research MUST require completion of the strategic program before weapon-specific research can unlock. Weapon class, payload level, missile range, and target eligibility MUST be derived from completed research and scenario data.
- **FR-020**: Each missile design MUST select one configured payload level. The default ten-level yield and blast-radius profile is:

  | Payload level | Yield (kt) | Default blast radius (km) |
  | --- | ---: | ---: |
  | 1 | 100 | 3.25 |
  | 2 | 200 | 4.25 |
  | 3 | 400 | 6 |
  | 4 | 750 | 7.5 |
  | 5 | 1,500 | 9.5 |
  | 6 | 2,500 | 11.5 |
  | 7 | 5,000 | 14 |
  | 8 | 20,000 | 18 |
  | 9 | 50,000 | 23 |
  | 10 | 100,000 | 30 |

  Scenarios MAY override these values. The resolver MUST use configured aggregate effects and MUST NOT imply precision blast simulation.
- **FR-021**: Strategic launches MUST distinguish military and civilian target modes, select only missiles with sufficient researched range, and record the selected payload. Collateral effects MUST remain possible in either mode and be resolved separately from intended effects.
- **FR-022**: Missile defense MUST require both completed defense research and a fielded operational system. The default long-range layer MUST make a first interception attempt at 60% and, only after failure, a second attempt at 50%; its combined default probability is 80%. The default short-range layer MUST attempt interception at 50%. Scenarios MAY override these probabilities and layer order.
- **FR-023**: Missile defense MUST resolve automatically for covered incoming strikes. Defense maintenance MUST scale with configured covered area, and an inactive, unfielded, unresearched, or out-of-coverage system MUST contribute no attempt.

## Key Entities & Data Model

- **Strategic Weapon**: An owned weapon asset with class, payload, range, readiness, operational state, origin, and authorization requirements.
- **Strategic Launch Order**: A validated or pending order with origin, target, mode, timing, authorization, cost, and lifecycle status.
- **Missile Defense Layer**: An independent defensive capability with coverage, range, readiness, interception capacity, and result.
- **Strategic Impact**: The resolved intended and collateral effects of a strike across military, civilian, infrastructure, communications, economic, political, and environmental categories.
- **Payload Profile**: A researched missile payload level with configured yield, default blast radius, and bounded impact parameters.
- **Defense Profile**: A researched and fielded missile-defense system with layer, coverage area, range, interception attempts, maintenance, and operational state.
- **Escalation Event**: The visible diplomatic and political record generated by detection, launch, interception, or impact.

## Scope Boundaries

This feature adds strategic weapon resolution around the existing inventory and panel concepts. It does not replace conventional combat, unit movement, production capacity, diplomacy, demographic simulation, health, economy, or political lifecycle. It does not add a separate world map renderer or a second ownership model.

## Success Criteria

- **SC-001**: 100% of invalid launch attempts leave weapon inventory, target state, and readiness unchanged and show a reason.
- **SC-002**: In controlled tests, each active defense layer resolves once in order and an intercepted strike produces no downstream impact unless a documented surviving payload exists.
- **SC-003**: Military and civilian strikes produce distinct, inspectable impact categories and never apply effects outside configured bounds.
- **SC-004**: Every strategic lifecycle transition creates an auditable event and the required authorized notifications within one state update.
- **SC-005**: Identical state and ordered actions reproduce the same launch, defense, impact, and escalation results across three repeated runs and after save/load.
- **SC-006**: A player can determine weapon readiness, target validity, authorization, defense estimate, and pending outcome from the strategic overview within 30 seconds.
- **SC-007**: Resolving 1,000 pending strikes and 2,000 defense-layer evaluations completes within 500 milliseconds in a controlled benchmark when unrelated regions are unchanged.
- **SC-008**: A country cannot research a weapon class before the strategic-program gate, and 100% of rejected out-of-range or unreached payload launches preserve weapon inventory.
- **SC-009**: For each default defense profile, controlled deterministic runs apply only its documented attempts in order and reproduce the configured interception outcome.
- **SC-010**: The strategic overview displays each available payload's yield/radius and each defense layer's coverage and interception estimate before launch resolution.

## Assumptions & Dependencies

- **Assumption**: Existing strategic-weapon inventory and launch-action concepts are the starting domain contract; this feature adds validation and resolution behaviour around them.
- **Assumption**: The initial release uses two defense layers, deterministic seeded interception, and bounded aggregate consequences rather than detailed blast physics.
- **Assumption**: The listed payload yields, blast radii, and interception probabilities are data defaults; scenario data may tune them without changing validation or lifecycle contracts.
- **Assumption**: Strategic launch authorization is scenario-configurable and may require a war, crisis, government authority, or explicit policy.
- **Dependency**: Existing research, production, military, infrastructure, demographics, health, economy, politics, diplomacy, notification, snapshot, and persistence contracts remain authoritative.
