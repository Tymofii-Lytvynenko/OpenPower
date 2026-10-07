# Production and Transfer Action Contract

## Domestic production

The client submits queue, pause/resume, reprioritize, cancel, split, and dispatch intents through existing `GameAction` records. The authoritative military systems revalidate country authority, design ownership/research, quantity, capacity, funds, destination domain, territorial control, and route access. UI code reads presenter projections only.

Each queue projection exposes priority, status, capacity, progress, remaining work/funding, ETA, and blocking reason. Completion is idempotent and preserves production provenance and the unit readiness contract.

## Foreign production

The buyer may request only an eligible seller-owned design under treaty/scenario permission and seller standing acceptance. The seller independently accepts or rejects. Acceptance captures configured pricing; delivery revalidates legality, design, funds, access, deployment destination, and demilitarization constraints before a single payment and ownership transfer. Cancellation settles only documented incurred cost and records the configured relation penalty.

## Used-unit market

The owner may list and withdraw eligible stationary inventory. A buyer must be authorized, treaty-eligible, non-embargoed, and able to fund the requested amount. Purchase is single-commit, may split a stack, and routes transferred units through shared movement/readiness state. Ineligible countries cannot inspect foreign designs or purchase the listing.

## Determinism and persistence

Identical ordered actions, world inputs, and time yield identical queue allocations, contract prices, due deliveries, routes, and ownership. All persistent pipeline records use the existing GameState snapshot and save APIs; no separate market or deployment persistence is introduced.
