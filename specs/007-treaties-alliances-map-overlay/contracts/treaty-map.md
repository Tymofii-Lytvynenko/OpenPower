# Treaty and Map Overlay Contracts

## Static-data contract

The root collection key in each world TOML file matches its filename stem. The loader exposes a `countries_treaties` and `countries_wars` DataFrame when corresponding base datasets contain rows.

## Diplomacy read contract

- Treaty rows with no status are treated as active legacy rows; explicit statuses other than `active` are ignored for alliance coloring.
- A positive `expires_at_minute` at or before the current minute is expired; zero is non-expiring.
- `suspended_members` are excluded from active military-alignment membership.
- War rows with no status are legacy-active; explicit non-active rows are not enemies.

## Client rendering contract

- `EmpireMapMode.calculate_colors` is a deterministic, read-only projection from region ownership/control and current diplomacy tables.
- `ViewportController` refreshes only when the selected perspective or a relevant source table revision changes.
- Lookup updates use a previous and target palette; shader interpolation is bounded to `[0, 1]` and does not mutate simulation state.
- Region picking resolves IDs through existing map data and focuses/selects through the client controller.
