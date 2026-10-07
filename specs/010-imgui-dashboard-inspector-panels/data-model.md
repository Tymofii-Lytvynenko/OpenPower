# Data Model: Dashboard & Inspector Panels

This feature does not add persistent tables or change authoritative schemas.

## Existing inputs and outputs

| Surface | Input | Output |
| --- | --- | --- |
| Budget panel | `countries` tax and `budget_*_ratio` columns; `resource_ledger` demand totals | `ActionUpdateBudget(country_tag, allocations)` |
| Resource panel | `resource_ledger`, `trade_network`, `domestic_production`, `countries` | `ActionUpdateResourcePolicy` for selected-resource policy controls |
| Data inspector | immutable Polars frames exposed by `GameState.tables` | Filtered/sorted view; no state mutation |
| Politics system | `countries`, political effect tables, game-time day events | Updated `countries.gvt_stability` on seven-day boundaries |

## Budget allocation shape

`ActionUpdateBudget.allocations` remains a mapping of country column name to ratio. It contains `personal_income_tax_rate` and each configured sector ratio (`budget_health_ratio`, `budget_edu_ratio`, `budget_social_ratio`, `budget_gov_ratio`, `budget_env_ratio`, `budget_research_ratio`, `budget_infra_ratio`, `budget_telecom_ratio`, `budget_imf_ratio`, `budget_propaganda_ratio`, and `budget_tourism_promo_ratio`). Values are finite floats clamped to `[0.0, 1.0]` before dispatch.

## Resource plot model

The plot is a projection of `trade_network`, not a new stored model:

- Filter exports where `exporter_id == selected_country` and group by `game_resource_id`.
- Filter imports where `importer_id == selected_country` and group by `game_resource_id`.
- Full-join the aggregates, use zero for absent flows, and calculate `net = exports - imports`.
- Sort by absolute net flow and show at most eight rows so the plot remains legible.

## Political stability model

For a weekly update, baseline target is `clip(0.7 * approval + 0.3 * HDI - corruption, 0, 100)`. Null/missing/invalid values use approval `50.0`, HDI `0.5`, corruption `0.1`, and stability `50.0`. The baseline then passes through existing explicit political modifiers before stability moves by 5%, cast to integer to preserve the established game-state type.
