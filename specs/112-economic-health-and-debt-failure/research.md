# Research: Economic Health and Debt Failure

## Decision: Add explicit debt contracts instead of treating negative reserves as all debt

**Decision**: Keep `money_reserves` as liquid treasury and add typed, keyed domestic/foreign debt contracts plus arrears and distress records. Continue calculating the current negative-reserve overdraft interest as a bounded emergency path for compatibility, but never convert an overdraft into an unlimited lender or positive treasury.

**Rationale**: `BudgetSystem` currently charges a fixed interest expense only when `money_reserves < 0`; there is no creditor, principal schedule, maturity, debt-service record, or failure lifecycle. Existing diplomacy can transfer reserves when assuming foreign debt, but does not create contractual obligations.

**Alternatives considered**: Store all debt as a negative `money_reserves` value. Rejected because it cannot identify creditor, principal, maturity, repayment, arrears, or restructuring. Replace the existing budget model. Rejected because this feature must extend rather than replace GDP, trade, and budget ledgers.

## Decision: Keep indicator definitions at country scope and derive them from current authoritative inputs

**Decision**: Store bounded economic-health fields in the existing country table, with a pure policy module deriving health, real-income, inflation pressure, employment, and poverty updates from current GDP, production, reserves, fiscal position, population, and configured policy. Add explicit labor-supply/employment source fields only when an authoritative value exists; missing optional sources follow documented neutral initialization.

**Rationale**: The country schema already includes `economic_health`, `human_dev`, GDP, reserves, taxes, poverty, and annual revenue/expense; `InternalEconomySystem` owns GDP, production, and demand. Existing systems such as research and military production already consume `economic_health`. There is no current minimum-wage, interest-policy, inflation, unemployment, or employment model.

**Alternatives considered**: Hide economic health in globals or duplicate production/population ledgers. Rejected because the values must be typed, saveable, inspectable, and feed existing consumers. Treat GDP as a complete health measure. Rejected because the specification explicitly distinguishes GDP from health and requires poverty/labor/inflation feedback.

## Decision: Apply policy at deterministic game-time boundaries

**Decision**: Represent policy changes with an authorized semantic action and a persisted effective-dated transition. Apply the latest accepted values at its game-time minute, record a readable cause, and avoid rewriting previous nominal values.

**Rationale**: The repository uses deterministic game-time state and shared `GameAction` commands; real-second events drive existing annual budget/economy fractions. Effective-dated changes make action order replayable and prevent retroactive ledger edits.

**Alternatives considered**: Apply client-side slider changes immediately to snapshot state. Rejected because clients are passive observers. Use wall-clock time. Rejected because it diverges across clients and replays.

## Decision: Use scheduled contracts and due-work filtering for debt service

**Decision**: Persist next-payment and maturity timestamps, contractual rate, schedule, and remaining principal. Budget projections aggregate annualized service, while only contracts whose next obligation is due enter the payment/arrears lifecycle. Use stable keyed tables and deterministic ordering.

**Rationale**: This supports creditor visibility and the 100,000-contract controlled benchmark without recomputing or mutating every loan on each tick. The existing `BudgetSystem` already uses Polars LazyFrames and stable numeric reductions.

**Alternatives considered**: Scan and rewrite every contract each real-second update. Rejected because service is date-bound and the benchmark explicitly requires scheduled incremental work. Recalculate interest only from total debt. Rejected because it hides creditor-specific schedules and status.

## Decision: Distress modifies existing systems through bounded modifiers

**Decision**: Model arrears, restructuring, default, and recovery as explicit distress states with recorded trigger, restrictions, and eligibility time. Feed bounded production/trade/budget/policy modifiers into existing economic and diplomacy contracts; do not delete units, production, treaty, or population state.

**Rationale**: `BudgetSystem`, `InternalEconomySystem`, `TradeSystem`, `DiplomacySystem`, and `PoliticsSystem` already provide integration points. A separate state machine preserves current ledgers while making failure visible and reversible.

**Alternatives considered**: Set GDP or reserves to zero on default. Rejected because it destroys unrelated authoritative state and bypasses the configured recovery path. Invent rescue money automatically. Rejected because failed debt service must create arrears/restructuring/default rather than unlimited funds.

## Decision: Make causes first-class persisted records and present them read-only

**Decision**: Record a stable cause row for policy application, inflation/labor/health updates, loan origination/payment, arrears, restructuring, default, and recovery. A client presenter reads country and debt snapshots and sends semantic actions only.

**Rationale**: The current overview must expose the largest risks, next obligation, thresholds, and causes. Generic Polars tables already persist through Arrow snapshot and save/load contracts.

**Alternatives considered**: Infer causes later from current values. Rejected because transitions and source evidence would be lost. Let the client compute policy eligibility. Rejected because costs, bounds, and authority are server policy.
