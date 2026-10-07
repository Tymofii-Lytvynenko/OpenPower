# Regional Infrastructure Action and Read-Model Contract

## Investment command

`ActionInvestRegionalInfrastructure` carries:

- `player_id: str` — actor used by existing session/command authority rules.
- `country_tag: str` — funding country; it must currently own the target region.
- `region_id: int` — existing authoritative region.
- `category: str` — a configured infrastructure category.
- `target_level: float` — finite target. A value above the profile's current `level` is an upgrade level. A value at or below current `level` is interpreted as a repair-capacity target and must be above current capacity without exceeding the recorded/natural restoration ceiling.

The server resolves cost and duration from the configured policy and regional area scale; clients cannot set cost, duration, or project type. Funding is currently treasury-only. The server rejects invalid ownership, authority, category, target, budget allocation, active-project conflicts, or insufficient reserves without a partial debit or capacity change. Acceptance debits the full quote once and records an `in_progress` project with its actor, funding country, type, target, progress, and reason.

## Cancellation and project lifecycle

`ActionCancelInfrastructureProject` carries `player_id` and `project_id`. Only the actor recorded on an active project may cancel it. The server refunds the uncompleted share of the original cost. Completed and already-cancelled projects are not cancellable.

Project states are `in_progress`, `paused`, `completed`, and `cancelled`. State, game-time timestamps, and the last transition reason are persisted on the project row. A project pauses if its funding country no longer controls the region and resumes only after control returns. A project cannot transfer to a different country or actor.

## Damage and recovery

Strategic impacts and random disaster events create source-attributed damage rows. Stable source/region/category IDs make repeated delivery idempotent. Category-level `damage_response` policy overrides can tune specific event or strategic multipliers. A repair is server-quoted and cannot restore capacity beyond the effective recorded/natural restoration ceiling. Damage rows remain as history and mark `recovered` once the associated ceiling is reached.

## Materialized infrastructure read model

Authoritative profiles are in `regional_infrastructure`. Existing systems and client presenters may read bounded normalized outputs on `regions`:

| Output | Meaning |
|---|---|
| `transport_access` | Transport capacity used by military transit. |
| `utilities_capacity` | Utilities/public-service capacity. |
| `industrial_access` | Industrial-access modifier; never creates output on its own. |
| `telecom_capacity` | Regional telecom capacity available to authorized information systems. |
| `infrastructure` | Backward-compatible transport alias. |
| `infrastructure_health` | Mean condition across configured profiles. |
| `communications` | Backward-compatible telecom alias. |
| `health_capacity` | Backward-compatible utilities/service alias. |

Country read models are weighted aggregates, not authoritative regional inputs. The system writes only regional/country rows whose projected outputs changed.

## Compatibility

Missing support tables are initialized by the base module schema registry. Configured legacy region columns seed initial category profiles; absent legacy values use policy baselines. Initialization does not debit funds or alter country aggregates except to materialize their derived infrastructure indices. Arrow snapshots and generic save/load carry the support tables without custom serializers.
