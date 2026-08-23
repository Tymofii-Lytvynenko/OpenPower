# Feature Specification: Economic Health and Debt Failure

## User Scenarios & Testing

### Primary User Story

As a national leader, I want wages, employment, inflation, interest, poverty, economic health, and debt distress to interact, so that fiscal choices can create both growth and credible failure states.

### Acceptance Scenarios

1. **Inspect economic health**: **Given** a country is selected, **When** the economic overview opens, **Then** it shows economic health, minimum wage, interest rate, inflation, unemployment, poverty, treasury, deficit, and debt exposure with recent causes.
2. **Change a policy lever**: **Given** the player has authority over economic policy, **When** a valid minimum-wage, interest, tax, or spending change is submitted, **Then** it enters the configured transition and affects future economic updates without retroactively rewriting history.
3. **Create inflation pressure**: **Given** demand, money supply, budget deficit, or resource costs rise beyond configured limits, **When** the economy updates, **Then** inflation increases with a visible cause and reduces real purchasing power or demand according to the policy model.
4. **Resolve unemployment and poverty**: **Given** production, wages, migration, and labour demand change, **When** the labour update runs, **Then** unemployment and poverty respond and feed approval, migration, health, and economic health.
5. **Borrow externally**: **Given** a country cannot fund its deficit, **When** it requests or receives foreign financing, **Then** principal, interest, maturity, creditor, and conditions are recorded and future budget updates include debt service.
6. **Enter debt distress**: **Given** debt service, reserves, and economic health cross configured failure thresholds, **When** the distress process resolves, **Then** the country enters a visible default, restructuring, or external-control state with bounded policy consequences.
7. **Recover**: **Given** a country reduces its deficit, improves economic health, or completes restructuring, **When** recovery conditions are met, **Then** debt distress is reduced or exited and the previous failure restrictions are removed only as specified.
8. **Persist economic state**: **Given** policies, debt, and distress timers are active, **When** the game is saved and loaded, **Then** the same values, schedules, and next outcome continue.

### Edge Cases

- A country has no external creditors; it cannot create a foreign debt record from an unsupported lender.
- Interest is negative, inflation is below zero, or a policy would exceed allowed bounds; the system applies configured floors and records the clamp.
- Debt service exceeds current reserves; the country enters the defined arrears or default path rather than receiving unlimited money.
- A country’s GDP or economic-health source is missing; it uses the documented initialization rule and flags the missing input.
- A wage change affects no employed population; it does not invent household income or employment.
- A restructuring is already active; a second rescue or default action is rejected or merged according to the configured rule.
- A legacy save has national budget values but no economic-health fields; new fields start from documented derived baselines.

## Functional Requirements

- **FR-001**: Each country MUST have bounded economic-health indicators for economic health, minimum wage, interest rate, inflation, unemployment, poverty, and real or nominal income context.
- **FR-002**: The system MUST distinguish treasury reserves, current deficit or surplus, domestic debt, foreign debt, debt service, arrears, restructuring, and default state.
- **FR-003**: Policy actions MUST support configurable changes to minimum wage, interest rate, tax pressure, public spending, borrowing, and debt restructuring, with authority, cost, effective time, and cooldown.
- **FR-004**: Economic updates MUST calculate feedback among production, demand, wages, employment, inflation, poverty, reserves, approval, migration, and economic health using documented bounded relationships.
- **FR-005**: Inflation MUST have attributable causes, a visible rate and trend, and a defined effect on real income, demand, budget costs, or savings. It MUST NOT silently change nominal values without an explanation.
- **FR-006**: Employment updates MUST distinguish labour supply, employed population, unemployment, underemployment where configured, wage pressure, and poverty pressure.
- **FR-007**: Foreign debt MUST record creditor, principal, interest, maturity, repayment schedule, currency or settlement basis, conditions, and current status.
- **FR-008**: Debt service MUST reduce the country’s available fiscal capacity according to the schedule. Insufficient funds MUST produce arrears, restructuring eligibility, or default according to configured thresholds.
- **FR-009**: Debt distress MUST support at least arrears, restructuring, and default or external-control states with visible entry conditions, restrictions, recovery conditions, and consequences.
- **FR-010**: Failure consequences MUST be bounded and MUST use existing budget, trade, diplomacy, politics, migration, health, and production contracts rather than deleting unrelated state.
- **FR-011**: AI-controlled countries MUST use the same policy, borrowing, debt-service, distress, and recovery rules as human-controlled countries.
- **FR-012**: The player MUST be able to inspect each indicator’s current value, direction, threshold, top causes, policy setting, and debt obligations from the economic overview.
- **FR-013**: Every policy, borrowing, repayment, restructuring, distress, and recovery transition MUST publish a readable event with affected values and reason.
- **FR-014**: Identical economic state, time, policy actions, and deterministic seed MUST produce identical indicators, debt schedules, and failure transitions.
- **FR-015**: Economic-health indicators, policy transitions, debt records, distress state, and timers MUST survive save/load, snapshot synchronization, and replay.
- **FR-016**: Processing MUST update countries with changed policies, debt schedules, or external conditions and MUST not recompute unaffected debt contracts on every tick.

## Key Entities & Data Model

- **Economic Health Profile**: Country-level indicators for health, wages, interest, inflation, employment, poverty, income, and recent causes.
- **Fiscal Position**: Treasury, revenue, spending, deficit or surplus, reserves, liquidity, and available fiscal capacity.
- **Debt Contract**: A domestic or foreign obligation with creditor, principal, interest, maturity, service schedule, conditions, and status.
- **Debt Distress Case**: A tracked arrears, restructuring, default, or external-control lifecycle with triggers, restrictions, and recovery.
- **Economic Policy**: A time-bounded policy choice affecting wages, rates, taxes, spending, borrowing, or restructuring.

## Scope Boundaries

This feature adds missing economic-health, labour, inflation, interest, and debt-failure dynamics. It does not replace the existing resource market, trade, tourism, budget categories, GDP model, treaty effects, or regional infrastructure; it consumes and extends their outputs.

## Success Criteria

- **SC-001**: 100% of economic policy actions show an effective date, cost, and resulting indicator changes; invalid actions change no state.
- **SC-002**: In controlled scenarios, a sustained deficit increases debt or reduces reserves, and debt service can reach arrears or default without unlimited-fund fallback.
- **SC-003**: Wage, employment, inflation, poverty, and economic-health changes propagate to declared dependent systems within one economic update.
- **SC-004**: Each debt contract produces the documented service amount and status at its scheduled dates, including save/load boundaries.
- **SC-005**: Repeated seeded runs reproduce identical economic indicators and distress outcomes from identical initial conditions and actions.
- **SC-006**: A player can identify the largest economic risk, next debt obligation, and current recovery condition within 30 seconds.
- **SC-007**: Updating 10,000 country profiles and 100,000 debt obligations completes within 1 second in a controlled benchmark when only scheduled obligations are due.

## Assumptions & Dependencies

- **Assumption**: Existing national GDP, budget, reserves, trade, and resource outputs remain authoritative inputs; this feature adds missing feedback and failure state.
- **Assumption**: Initial distress thresholds are configurable scenario values, with no requirement to model a real-world institution or currency union.
- **Assumption**: Economic health is a composite indicator with inspectable component values, not a hidden replacement for GDP.
- **Dependency**: Existing budget, economy, resource, trade, production, migration, politics, diplomacy, regional-infrastructure, notification, and persistence contracts remain available.
