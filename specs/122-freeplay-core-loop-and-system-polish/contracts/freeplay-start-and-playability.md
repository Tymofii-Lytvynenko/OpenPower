# Freeplay Start and Playability Contract

## Start Request

- Required input: a selected playable country.
- Optional input: a selected political party when the country supports one.
- Scenario/campaign id: absent for default freeplay; present only for an explicitly selected scenario.

## Ready Session

A freeplay session is ready when the existing session startup reports an initial authoritative world snapshot and the selected player-country context is valid. A campaign row, campaign objective, or campaign-start command is not a freeplay readiness condition.

Startup failure or cancellation must use the existing session cleanup path and return an actionable result to the client.

## Player Actions

- The client dispatches existing typed `GameAction` values through `NetworkClient`.
- Only the authoritative system that owns a gameplay domain accepts, rejects, and applies its action.
- Rejected/failed player commands surface their authoritative reason where one is available.
- The client renders state and results; it does not update `GameState` directly.

## Save and Resume

- Freeplay uses the existing save/load pipeline.
- Campaign metadata is optional and is not required to reconstruct player country, simulation time, world state, or supported pending orders.
- Loading another save or returning to the menu releases the previous session through existing lifecycle cleanup.

## Automated Acceptance Evidence

The implementation must produce machine-readable outcomes for:

1. Freeplay start with no campaign/scenario input.
2. Pause/resume and speed changes reflected in authoritative time state.
3. Representative actions in economy, politics, military, and diplomacy, including an invalid action with a visible rejection reason.
4. Save/load continuation with campaign metadata absent, preserving the player country, date, tax policy, and a pending unit-movement order.
5. Continued world simulation with no campaign victory/defeat condition.

Use existing pytest/session coverage and extend `src/client/ui/testing/` journeys where it provides the needed view-level evidence. These workflows are automated; no human desktop acceptance is required by this contract.
