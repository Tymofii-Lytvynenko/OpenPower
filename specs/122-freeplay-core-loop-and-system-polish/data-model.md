# Freeplay Data Model

## Existing Authoritative State

Freeplay should use the current `GameState` and module schemas. No additional table is planned.

| State | Existing owner | Freeplay invariant |
| --- | --- | --- |
| Current date, pause state, and speed | `TimeSystem` and the existing time state | Time controls apply to the authoritative simulation and survive supported persistence paths. |
| Selected player country and political party | Client session/player context and existing government/party tables | The selected country is available to the session; a party is optional and does not create campaign ownership or an outcome. |
| Economy, budget, resources, and trade | Economy and trade systems in `modules/base/systems/` | Domain systems remain the sole writers for their owned tables. |
| Political state and population | Politics and demographics systems | Player actions change state only through their existing action contracts and owning systems. |
| Units, battles, research, and orders | Military systems | Accepted orders and their supported in-progress state remain authoritative and saveable. |
| Relations, treaties, wars, news, and messages | World/diplomacy systems | The world continues to evolve regardless of campaign records. |
| Save metadata and restored state | `src/server/io/` and existing save contracts | Campaign fields may be absent; freeplay load must not require them. |

## Campaign Data

Campaign and objective tables remain valid for optional scenarios. Their absence in a freeplay session is expected and must not block session readiness, command dispatch, simulation advancement, or save/load. Do not manufacture an empty campaign row solely to satisfy the freeplay client.

## Persistence Requirements

- Use existing schema migration, snapshot, IPC, and save/load behavior.
- Preserve the player country, time, tax policy, and a pending unit-movement order.
- Continue to accept legacy saves containing campaign data; campaign data is optional to freeplay.
- Add no schema migration unless automated acceptance identifies a persistent fact that cannot be reconstructed from existing state.
