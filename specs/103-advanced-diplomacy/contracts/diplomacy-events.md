# Contract: Diplomatic Proposals and Balance Events

## Peace package input

- A proposal identifies an active war and is submitted by a player authorized to control a war-side leader.
- Each clause must be a normalized supported type: reparations, territory transfer, treaty annulment, or demilitarization.
- Proposal count and expiry are bounded; every affected country/region/treaty must exist and obey war-side membership constraints.
- All required independent participants on the responding side must accept. A rejection, expiry, ended war, or failed final validation prevents clause application.

## Ratification outputs

- On submission, emit `EventPeaceDealProposed` and store pending status.
- On terminal response, emit `EventPeaceDealResolved` with status/reason and simulation minute.
- On territory mutation, commit region owner/controller first, then emit `EventTerritoryOwnershipChanged` with previous/new owner and source.
- On accepted package, apply the full package, close the war through existing peace actions, and refresh treaty/war projections within the simulation tick.

## Balance outputs

- Offensive occupation/annexation and unprovoked war changes update `aggressive_expansion_events`/scores, emit `EventAggressiveExpansionUpdated`, and may form/revise/dissolve mutual-defense `coalition_pacts`.
- Both `side_a` and `side_b` are valid offensive actors when capturing a region owned by the opposite active-war side.
- Battle casualties, enemy-held home regions, active blockades, and conflict duration contribute to each participant's war-exhaustion row; emit `EventWarExhaustionUpdated` when the score meaningfully changes.
- Coalition and exhaustion projections update the country/unit state consumed by map overlays, politics, combat, and the war panel.

## Determinism and failure behavior

- Process participants, clauses, and generated events in stable order; identical state plus identical inputs must yield identical ids, rows, and event order.
- Malformed clauses and unauthorized actions are rejected without partial state changes.
- Missing optional tables use schema-backed empty/default tables; invalid numeric values are bounded or rejected by the existing policy rather than converted to arbitrary gameplay state.

## Bilateral trade commands and events

- `ActionCreateTradeDeal`: authorized source country, target country, offered/requested asset arrays, and expiry duration in days (default 30, accepted range 1–365).
- `ActionRespondTradeDeal`: pending deal ID, controlled recipient country, and accept/reject choice.
- `ActionCounterTradeDeal`: incoming deal ID, controlled countering country, replacement packages, and a new bounded deadline. The original resolves as `countered`; the new deal stores reciprocal links.
- `ActionWithdrawTradeDeal`: pending deal ID and controlled source country. Only its proposer may withdraw.
- `EventDiplomaticTradeChanged`: deal ID, source/target IDs, lifecycle status, reason, and simulation minute. Territory-transfer settlement also emits `EventTerritoryOwnershipChanged` after state commit.

The system rechecks authority, active-war exclusion, available cash, region ownership/occupation/minimum retained territory, and current research levels at creation and before acceptance. It validates the complete exchange before changing country reserves, region owners, capital fallback, or research tracks. Invalid or stale assets resolve with a reason and do not partially settle.
