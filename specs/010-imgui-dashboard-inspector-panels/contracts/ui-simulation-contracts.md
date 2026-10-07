# UI and Simulation Contracts

## Budget action

- The client creates `ActionUpdateBudget` only when the local player applies a draft for their own country.
- `country_tag` is the currently selected country and `player_id` is the authenticated client ID.
- `allocations` carries all configured sector ratios and `personal_income_tax_rate` as finite values in `[0.0, 1.0]`.
- The client dispatches through `net_client.send_action`; it never mutates a `GameState` DataFrame.
- `BudgetSystem` remains the authority that validates and applies the action.

## Resource chart

- The view is read-only and uses the existing trade-network flow definitions: exports minus imports is net exports.
- Required input columns are `exporter_id`, `importer_id`, `game_resource_id`, and `trade_value_usd`.
- If required columns are absent, render an explicit diagnostic naming them; do not suppress the error or display fabricated values.
- ImPlot calls are made only within an active ImGui frame and with the plot context paired to the active ImGui context.

## Weekly political drift

- Updates require an `EventNewDay`, an unpaused game, and an elapsed whole-game-day count divisible by seven.
- The engine simulation-step tick is not a calendar source.
- Metric null/invalid fallbacks are `50.0`, `0.5`, `0.1`, and `50.0` for approval, HDI, corruption, and stability respectively.
- Existing rights, stability, economic, migration, event, and war-exhaustion mechanics remain in force around the new baseline.
