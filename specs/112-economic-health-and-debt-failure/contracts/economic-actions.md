# Economic Policy and Debt Action Contract

All commands are server-validated semantic `GameAction` values. A rejected command changes no authoritative table and emits a readable command result. `player_id` must be authorized for every country named in the command; a creditor approval additionally requires authority over the creditor.

## Policy changes

- `ActionChangeEconomicPolicy(country_tag, policy_name, target_value)` supports `minimum_wage`, `interest_rate`, and each bounded existing `budget_*_ratio` allocation. `ActionSetTax` schedules the existing income-tax rate through this transition path. The established `ActionUpdateBudget` remains available for its original immediate allocation workflow.
- The server validates finite scenario-bounded values, current authority, affordability of any one-time transition cost, and the configured cooldown.
- Accepted changes append a `scheduled` row with prior value, target value, cost, effective minute, cooldown boundary, and reason. Effects begin only when the simulation reaches the effective minute.
- Invalid, unauthorized, unaffordable, or cooldown-blocked changes are rejected without changing policy or reserves.

## Foreign financing

- `ActionRequestDebtContract` names debtor and existing creditor, principal, annual interest rate, payment frequency, principal installment, maturity, currency/settlement basis, and conditions.
- A request creates a pending contract only. It does not create or transfer money.
- `ActionResolveDebtContract` requires creditor authority. Acceptance validates the creditor's available reserves and transfers the principal exactly once; rejection leaves both treasuries unchanged.
- Domestic overdraft exposure remains the legacy negative-reserve budget path and is reported separately from creditor-backed foreign contracts.

## Service, restructuring, and distress

- Only contracts due at or before the current simulation minute are settled. Interest and principal due are calculated from persisted terms; payment is capped by debtor reserves and is transferred to the recorded creditor. The unpaid amount remains arrears.
- A shortfall creates or updates a single active distress case for the debtor. Repeated processing of the same due boundary is idempotent. Calendar-month terms use the game calendar and clamp the day when a target month is shorter.
- `ActionRequestDebtRestructuring` must be authorized, identify an eligible active contract/case, and supply bounded revised terms. Acceptance updates future schedule terms and keeps unpaid arrears visible; it never forgives principal implicitly.
- Default/recovery transitions are deterministic, threshold-configurable, journaled facts. Restrictions are bounded modifiers consumed by existing systems and are removed only when their persisted recovery conditions hold.

## Events and read model

Accepted or rejected commands and material lifecycle transitions publish readable domain events containing affected country/contract IDs, changed amounts or indicators, game minute, and reason. Client panels are passive snapshot presenters and dispatch only these actions; they do not compute eligibility, costs, or outcomes.
