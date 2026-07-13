# Diplomacy and treaty simulation

The authoritative treaty lifecycle is implemented by `TreatyDiplomacySystem`. Client panels only submit actions; every proposal, response, long-term effect, and punctual outcome is calculated on the server state.

## Lifecycle

1. A country submits `ActionCreateTreaty` with members, sides, optional conditions, and whether the treaty remains open.
2. Every invited member submits `ActionRespondTreaty`.
3. Once every response is accepted, a long-term treaty publishes rows in `treaty_effects`; punctual treaties apply their outcome and are retained as completed history.
4. Members of an open treaty may use `ActionJoinTreaty`. Conditions are evaluated again every game day; a failing member becomes suspended until it qualifies again.

## Supported treaty effects

- Alliance expands the defensive side when a war starts and grants member stationing rights.
- Military trespassing grants transit rights for explicitly supplied route regions but never grants a right to station at the final foreign destination.
- Presence removal relocates foreign units to the nearest politically and militarily controlled home region.
- Annexation schedules a six-calendar-month claim. A loss of military control voids that claim and every pending adjacent claim.
- Cultural exchanges, noble cause, human-development collaboration, research partnership, and economic partnership update the corresponding relationship, development, research, and production systems.
- Common markets allocate member supply before constrained world-market flows; economic embargoes block bilateral flows.
- Economic aid and debt assumption use the country budget fields and economic-strength weighting.
- Weapons trade enables members-only unit-market listings; weapons embargoes override that access.

## Conditions and maintenance

Long-term treaties can require minimum diplomatic relation, geographic proximity, comparable military/economic/research strength, government type, and an absence of war between members. Geographic distance uses country centroids derived from owned regions. A generated `region_adjacency` table records shared borders from the authoritative region-colour map.

Maintenance is divided among active members by economic strength and is written to `countries.treaty_maintenance` for the budget system to collect.

## Extending with mods

Treaty definitions live in `src/shared/treaties.py`; all other systems consume the materialized `treaty_effects` table instead of duplicating treaty semantics. Mods can add data layers and use these effects as stable integration points.
