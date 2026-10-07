# Data Model: Production, Deployment, and Foreign Orders

Concrete Polars schemas in `modules/base/schema.py` and `modules/base/systems/military/military_system.py` are authoritative.

## Production order (`production_orders`)

An owner/design/quantity request with priority, lifecycle, progress, work remaining, assigned capacity, per-unit cost, ETA, requested training level, source/provenance, and a visible blocking reason. Queue allocation is ordered by priority and stable ID. Pausing or cancellation does not roll completed work back.

## Deployment order (`unit_deployment_orders`)

A completed production unit group awaiting a destination or dispatch. Records owning country, originating production order, unit and quantity, source/destination region, route, progress index, arrival estimate, status, and blocking reason. Split groups are separate unit/deployment records, not duplicate active forces.

## Movement route (`unit_movement_routes`)

One current route per unit, including owner, origin/destination, region path, current leg, custom destination and naval-invasion flags, status, and last rejection reason. Existing military movement access and domain compatibility determine whether the next leg remains legal.

## Foreign order (`foreign_unit_orders`)

A buyer request accepted by a seller, with design/quantity, new-production cost, price, incurred cancellation cost, status, timestamps, delivered unit IDs, payment status, ownership transfer time, route/destination, and reason. Buyer and seller ownership remain explicit until the contract commits at delivery.

## Seller profile (`seller_acceptance_profiles`)

Per-country standing foreign-order permission plus configured price multiplier and cancellation penalty. Standing permission is necessary but does not replace per-contract seller acceptance.

## Used-unit listing (`unit_market_listings`)

An eligible existing unit/group listed by its current owner with quantity, condition/price basis, buyer eligibility, and transaction status. A purchase reduces or transfers the listed quantity exactly once and enters the same unit ownership/transit/readiness path as other transfers.

## Invariants

- Capacity defaults to `national output × economic health × configured coefficient`.
- Priority allocation fills earlier work first and gives any residual capacity to only the first partially served order.
- A completed order creates one deployment-queued unit exactly once; units in transit are not map/combat/order eligible.
- Foreign-order requests create no unit or debit before seller acceptance and legal delivery commitment.
- Invalid or duplicate transactions do not change funds, inventory, or ownership.
- Market sales and foreign production reuse shared unit and movement records; no duplicate inventory exists.
- All queue, payment, ownership, and transit state is save/snapshot/replay persistent; absent legacy fields use documented defaults.
