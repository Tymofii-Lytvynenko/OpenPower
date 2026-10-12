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

## Developer UI test contracts

- `UIRunTelemetry.frame()` is opt-in and scopes widget/region recording to one rendered frame. Outside that context, the instrumented ImGui/ImPlot facades preserve native calls.
- A widget exposes semantic ID, native ID, type/label/value/options, visibility/enabled state, logical rectangle, parent region, and source location. Explicit IDs are recommended for repeated rows and controls that must remain addressable across source edits.
- Journey selectors match exact IDs or declared label/type/source/region criteria. Multiple matches are an error. Journey assertions may check visibility, enabled/value/geometry and action type/count/fields.
- Deterministic journey runs use supplied tables/globals, in-memory settings, and a recording client. They verify rendered controls and dispatched commands only; server resolution, campaign state, and OpenGL performance require separate evidence.
- Geometry diagnostics fail on invalid/non-positive rectangles, off-screen windows, and duplicate native IDs; clipping and sibling overlap are warnings because scroll regions and overlays may be intentional.
- The live bridge is disabled by default. When explicitly enabled, it accepts local commands only for visible, enabled interactive controls, deduplicates unique request IDs, and reports delivered versus interrupted input.
- Test outputs are local artifacts: `report.json`, `actual.png`, optional `overlay.png`/`diff.png`, and `receipts.json`. Baselines are never updated automatically. Full operator instructions are in `docs/UI_TESTING.md`.
