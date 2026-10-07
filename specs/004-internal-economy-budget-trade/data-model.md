# Data Model: Internal Economy, Budget & Trade

The simulation mutates existing `GameState.tables`; this feature adds no independent database or persistence subsystem. Table keys and schemas are governed by `DATA_SCHEMA.md` and the runtime schemas.

## Entities and projections

| Table / projection | Key | Relevant fields | Ownership and invariants |
|---|---|---|---|
| `countries` | `id` | `gdp`, `gdp_per_capita`, `money_reserves`, `human_dev`, `poverty_rate`, `personal_income_tax_rate`, economic modifiers, `trade_income`, `trade_expense` | Country-level macro and treasury state. Country identifiers are unique. Fiscal values are finite; missing optional policy fields use established defaults. |
| `population` or regional population aggregation | country identifier | `population` | Demand input. Aggregate exactly once per country for the formulaic demand path; population must be nonnegative. |
| `domestic_production` | (`country_id`, `game_resource_id`) | `domestic_production`, legality/control flags, `tax_rate` | Production and market policy. Keys are unique for the fast aligned path; general path handles supported compatibility schemas. |
| `resource_ledger` | (`country_id`, `game_resource_id`) | `consumption_usd` | Internal demand projection. Nonnegative finite demand; complete catalog/country coverage is required only where the selected path declares aligned keys. |
| `stockpiles` | (`country_id`, `game_resource_id`) | `stock_amount` | Persisted physical carry-over. Non-storable resources are zero after clearing; storable goods apply annual decay scaled by elapsed-year fraction. |
| `trade_network` | (`exporter_id`, `importer_id`, `game_resource_id`) | `trade_value_usd` | Cleared flow projection. Totals must not exceed available supply/demand under the global ratios and any bilateral/regional constraints. |
| Resource catalog | `game_resource_id` | category, unit, storage status, annual decay | Shared metadata; the 36 identifiers and storage behavior must match `RESOURCE_MAPPING` and `TradeSystem.RESOURCE_PHYSICS`. |

## Formula pipeline

1. Aggregate population and derive country GDP per capita and the world anchor.
2. Clip the wealth index to `[0.05, 10.0]`; derive solvent population and propensity-to-consume pool.
3. Evaluate resource demand formulas in dependency order, then normalize country demand to its consumption pool.
4. Combine domestic output and opening stockpiles; clear global supply/demand by resource, subject to treaty/regional policies.
5. Apply non-storable evaporation, annual physical decay, excess-stockpile production penalties, trade taxes, and government-control expenses.
6. Project closing production, stockpiles, trade network, and treasury inputs.
7. On the budget tick, credit income-tax and tourism revenues and debit military upkeep/debt interest according to the feature formulas.

## State transitions

- **Demand cycle**: `countries + population + resource formula catalog -> resource_ledger`.
- **Market cycle**: `domestic_production + resource_ledger + opening stockpiles + trade policy -> updated domestic_production + closing stockpiles + trade_network + trade budget columns`.
- **Budget cycle**: `countries + production/trade/tourism + military count -> updated country reserves and fiscal projections`.
- Transitions are event-driven by the existing real-second/year-fraction system. Elapsed fraction must be nonnegative; repeated same-input transitions must be deterministic.

## Data integrity

- Every join must preserve intended key cardinality; duplicate keys are rejected from optimized aligned paths or handled by a deliberate general-path policy.
- Null and absent optional columns must follow documented defaults; invalid/non-finite required numeric values must not silently become arbitrary values.
- Stable aggregation and canonical sorting are required at state-write boundaries.
- All state writes remain Polars frames so existing IPC save/load behavior remains compatible.
