# Data Model: Battle Strategy and Force Posture

## Authoritative records

### Force posture — `battle_force_postures`

One current command projection per force, keyed by `unit_id` and associated with `battle_id` and `country_id`.

- `strategy`: attack, defend, hold, back_off, retreat, or reorganize.
- `issuer_player_id`, `effective_at_minute`, `expires_at_minute`, and `reason`: command provenance and timing.
- `attack_modifier`, `defense_modifier`, `casualty_modifier`, `attack_risk_modifier`, `readiness_modifier`, `holding_modifier`, and `counterattack_modifier`: bounded projection values consumed by the battle resolver.
- `status`: active, retreating, reorganizing, returning, blocked, completed, or cancelled.

### Battle command order — `battle_command_orders`

Append-oriented command history keyed by `id`, with battle/country/force-type scope, strategy, issuer, creation/effective times, lifecycle status, affected unit IDs, and reason.

### Unit combat projection — `units`

`combat_posture`, `combat_strength_modifier`, `combat_defense_modifier`, `combat_casualty_modifier`, `engagement_mode`, `unit_lifecycle`, `cohesion`, and `reorganization_until_minute` affect combat eligibility and continuation. Unit identity and ownership remain authoritative in the existing unit row.

### Retreat/return route — `unit_movement_routes`

Existing shared route rows identify source, destination, route regions/index, status, rejection reason, and update time. Retreat uses an off-map rear target within the battle region, then the route/access contract for return to capital.

### Military occupation — `regions` and `occupations`

Occupation orders update `regions.controller` and create/refresh occupation records. They do not update `regions.owner`; formal sovereignty changes remain in political/diplomatic systems.

### Scenario configuration

- `battle_strategy_presets`: named default and per-unit-type strategy mapping.
- `battle_posture_projections`: scenario overrides for all seven posture projections, clamped to supported bounds.
- `battle_strategy_constraints`: optional list of battle/country/unit-type rules with `allowed_strategies` or `required_strategy`; a matching rule rejects the whole command before authoritative state changes.
- Retreat/reorganization settings configure rear distance, regroup duration, and cost per unit strength.

## Relationships and invariants

- A command can affect only units owned by the authorized issuer country and participating in the requested active battle; force-type filters narrow the selection.
- A specific valid force-type order overrides a later broad preset for that force.
- Same-boundary occupation commands are ordered by region/controller/issuer; posture commands are ordered by battle/country, then broad scope before force-specific scope, with issuer and strategy name as stable tie-breakers. Thus force-specific commands win over broad commands, and an overlapping same-scope tie resolves to the last lexical issuer/strategy key.
- A retreat never creates a new side. Completed/cancelled battles cannot be resumed by stale retreat rows.
- Retreat may leave the battle only after reaching the rear, completing regrouping, and selecting a valid capital route; blocked route states remain visible.
- Occupation requires an active hostile conflict, no surviving stationary hostile force in the target country, and an eligible force stationed in the requested target region. It changes military controller only.
- Battle summary detail is exposed only to authorized viewers; unknown or unauthorized detail is not inferred from current simulation rows.

## State transitions

```text
active posture ──retreat order──> retreating ──rear reached──> reorganizing
      │                                                       │
      │                                                       └──regroup complete──> returning ──capital reached──> completed
      ├──reorganize order──> reorganizing ──deadline──> completed/hold
      └──route invalid / battle concluded / unit removed──> blocked or cancelled
```
