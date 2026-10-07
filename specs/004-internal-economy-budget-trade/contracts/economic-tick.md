# Contract: Economic Tick

## Inputs

- `countries`: unique country `id` plus economic, development, poverty, budget, and trade-modifier fields.
- Population data: nonnegative population by country.
- `domestic_production`: nonnegative finite production by (`country_id`, `game_resource_id`), plus policy metadata when present.
- Optional `resource_ledger`, `stockpiles`, treaty effects, regional production, random-event effects, and political effects.
- A nonnegative elapsed-year fraction derived from the existing time event.

## Outputs

- Demand update writes a `resource_ledger` keyed by country/resource with finite `consumption_usd` values.
- Trade update writes canonical `stockpiles`, `trade_network`, `domestic_production`, and updated country trade-income/expense columns.
- Budget update writes finite treasury/balance values to `countries`.
- Output key uniqueness, sorting, and required column types follow current `GameState` and `DATA_SCHEMA.md` contracts.

## Behavioral invariants

- Wealth index is bounded `[0.05, 10]`; the consumption pool follows the exact formula in `spec.md`.
- Global clearing ratios are bounded `[0, 1]`; zero denominators produce zero corresponding flow, never NaN/inf.
- Imports and exports respect global resource availability and all treaty/regional restrictions.
- Non-storable resources do not accumulate; storable resources decay by `decay_rate * elapsed_fraction` and never create stock.
- Budget calculations use the specified tax, tourism, upkeep, and debt-interest coefficients. Same inputs and elapsed fraction yield reproducible outputs.
- Optimized paths produce the same keys, schema, and formula results as the general path within the explicitly tested floating-point tolerance.

## Failure and fallback contract

- If preconditions for an optimized path fail, route to the compatible general path without dropping policy effects.
- If required data violates invariants, raise/report a concrete validation error; do not silently emit dummy state.
- The <5 ms target is a measured acceptance gate on the fixed 200+ country benchmark and cannot be inferred from unit-test success.
