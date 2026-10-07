# Data Model: Economic Health and Debt Failure

## Country economic-health and fiscal profile

The existing `countries` row remains the current-state source. GDP, population, reserves, revenue, expense, budget ratios, and human development are not duplicated. Existing `poverty_rate` and `economic_health` remain authoritative country indicators. Add bounded columns for minimum wage, policy interest rate, inflation, labor supply, employment, unemployment, underemployment, nominal/real income indices, domestic overdraft exposure, foreign contractual debt, annual debt service, arrears, distress status/modifiers, and the last processed economic-health minute. Annual fiscal balance is derived as revenue minus expense. Domestic debt is the existing negative-reserve overdraft exposure; it is not assigned a fabricated lender. Foreign debt and arrears are materialized incrementally from explicit contract rows.

Indicator rules:

- Rates (`economic_health`, `inflation_rate`, `unemployment_rate`, `employment_rate`, `underemployment_rate`, and `poverty_rate`) and income indices are finite and clamped to documented scenario bounds. Inflation may represent bounded deflation down to -0.10.
- Nominal GDP, revenue, expense, reserves, minimum wage, and debt principal remain non-negative inputs except that the existing treasury may be negative while implicit overdraft handling resolves.
- Missing legacy indicators seed from explicit policy baselines or compatible existing values; they never change nominal GDP or treasury during schema migration.

## Economic policy transition

Stored in `economic_policy_transitions`, keyed by `id`.

| Field | Type | Meaning |
|---|---|---|
| `id` | Utf8 | Stable transition identifier. |
| `country_id` | Utf8 | Country whose policy is changing. |
| `player_id` | Utf8 | Actor that submitted the policy command. |
| `policy_name` | Utf8 | Minimum wage, interest rate, tax, or supported budget allocation. |
| `previous_value` | Float64 | Value at acceptance; prior economic observations are not rewritten. |
| `target_value` | Float64 | Server-validated bounded target. |
| `transition_cost` | Float64 | Server-calculated fiscal cost, reserved only when accepted. |
| `created_at_minute` | Int64 | Game-time request timestamp. |
| `effective_at_minute` | Int64 | Deterministic time when the policy takes effect. |
| `cooldown_until_minute` | Int64 | Earliest permitted next change. |
| `status` | Utf8 | `scheduled`, `applied`, `cancelled`, or `rejected`. |
| `reason` | Utf8 | Human-readable transition/result rationale. |

## Foreign debt contract

Stored in `debt_contracts`, keyed by `id`.

| Field | Type | Meaning |
|---|---|---|
| `id` | Utf8 | Stable financing/obligation identifier. |
| `debtor_country_id` | Utf8 | Country responsible for payment. |
| `creditor_country_id` | Utf8 | Existing sovereign creditor. |
| `debt_type` | Utf8 | `foreign`; domestic overdraft is the legacy negative-reserve ledger. |
| `principal_original` | Float64 | Financed principal at approval. |
| `principal_remaining` | Float64 | Outstanding principal. |
| `annual_interest_rate` | Float64 | Bounded nominal annual rate. |
| `payment_frequency_months` | Int32 | Positive number of game months per payment period. |
| `principal_payment` | Float64 | Scheduled principal installment before maturity. |
| `currency_code` | Utf8 | Settlement basis (scenario code, not an exchange-rate engine). |
| `conditions` | Utf8 | Persisted financing conditions. |
| `created_at_minute` | Int64 | Request or approval game minute. |
| `next_payment_at_minute` | Int64 | Next scheduled service boundary. |
| `maturity_at_minute` | Int64 | Contract maturity boundary. |
| `maturity_months` | Int32 | Original or restructured duration in calendar months. |
| `arrears_amount` | Float64 | Past-due amount not covered by treasury. |
| `status` | Utf8 | `pending`, `current`, `arrears`, `restructured`, `paid`, `rejected`, or `defaulted`. |
| `reason` | Utf8 | Last transition rationale. |

A pending foreign loan creates no funds. Approval verifies both countries and creditor capacity, transfers principal from creditor reserves to debtor reserves once, then activates the contract. Scheduled payments debit only available debtor reserves and transfer only the amount actually paid; unpaid amounts remain arrears. Negative national reserves continue to be reported as domestic overdraft debt through the legacy budget ledger. The foreign contract is never silently forgiven.

Payment-frequency and maturity months follow the simulation calendar and clamp the day when a target month is shorter. If the game advances across multiple payment dates in one update, each missed boundary is settled in chronological game-minute order, with contract ID as the deterministic tie-breaker; no installment is deferred to a later simulation tick merely because time advanced across it.

## Debt distress case

Stored in `debt_distress_cases`, keyed by `id`; at most one active case exists per country.

| Field | Type | Meaning |
|---|---|---|
| `id` | Utf8 | Stable case identifier. |
| `country_id` | Utf8 | Affected country. |
| `status` | Utf8 | `arrears`, `restructuring`, `default`, `recovery_pending`, or `closed`. |
| `trigger` | Utf8 | Recorded threshold or action that opened the case. |
| `entered_at_minute` | Int64 | Game-time entry boundary. |
| `updated_at_minute` | Int64 | Last transition boundary. |
| `arrears_at_entry` | Float64 | Past-due debt when the case opened. |
| `restriction_json` | Utf8 | Bounded policy/trade restrictions active during the case. |
| `recovery_condition` | Utf8 | Condition that must hold before restrictions are removed. |
| `reason` | Utf8 | Readable lifecycle rationale. |

Distress stores bounded production, trade, policy, health, political-stability, and creditworthiness modifiers on the country profile for existing consumers. Budget, trade, and production consume the first three. Economic-health updates apply the health factor to the recomputed index; weekly politics scales the stability target so recovery occurs naturally after the case closes. AI creditor approval utility is reduced by the debtor's creditworthiness factor but remains subject to the normal creditor-capacity and server-validation rules. Creditor transfers remain explicit contract settlements. It does not delete unrelated state or create treasury funds. A closed case clears only the modifiers owned by this lifecycle.

## Economic cause record

Stored in `economic_cause_records`, keyed by `id`.

Each record contains country, source type and source ID, indicator, previous/new values, unit, game minute, reason, and completeness/confidence. Causes are append-oriented evidence: unknown causes are represented as unknown rather than inferred from a later snapshot.

## Persistence and processing

All support tables are registered in the base Polars schema registry with stable keys. New/partial legacy state receives deterministic defaults. Effective policy changes, contracts, distress timers, and cause records survive generic Arrow snapshots and save/load. Systems query due policy/debt rows and changed country profiles rather than rewriting every contract on every tick.
