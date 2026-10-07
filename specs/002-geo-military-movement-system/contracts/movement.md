# Movement Contracts

## ActionMoveUnit

`src/shared/actions.py` defines the semantic movement intent. The client submits an `ActionMoveUnit` with:

- `unit_id`: the force group receiving this order;
- `target_region_id`: required valid destination region;
- optional `target_latitude` and `target_longitude`: custom destination point within the target region;
- optional ordered `via_region_ids`: explicit intermediate waypoints;
- `is_naval_invasion`: requests the separately validated landing policy.

The client may send one action per selected force group. Each group is independently authorized, route-planned, and reported so one invalid group cannot mutate another group's order.

## Route planning result

`MilitaryRoutePlanner.plan(...)` returns an immutable `RoutePlan` containing `region_ids`, `travel_cost`, and `rejection_reason`. A valid plan has a non-empty path and empty rejection reason. A rejected plan has an empty path and a user-presentable reason.

When adjacency is supplied, every consecutive pair must be adjacent. Routes minimize the configured sum of positive finite segment costs; equal-cost candidates use stable lexicographic path ordering. Explicit waypoints are validated in order. Legacy worlds with no adjacency rows retain the existing direct-route compatibility path.

## Access and movement rules

- Transit permits owned/controlled territory, active allied passage rights, explicitly granted military transit, and international waters. Stationing is separately checked at the final destination.
- Domain policy rejects land routes through water and conventional movement for strategic assets; naval routes require valid sea/port regions except eligible invasion coastal endpoints.
- A route must be revalidated before each future segment is entered.
- Movement durations use the baseline `clamp(360 + HaversineKm * 0.45, 360, 10080)` and then the documented bounded scenario modifiers.
- A valid move starts only after readiness authorization. Rejected orders do not alter unit location, ownership, or readiness.

## Naval landing policy

Scenario defaults: an eligible friendly capital ship must be within 750 km of the target; a hostile naval unit must not be within 1,500 km of the invading force. `naval_invasion_escort_km`, `naval_invasion_hostile_fleet_km`, and `naval_capital_ship_types` may override defaults. The checks run both when accepting the order and at the landing boundary. A blocked landing does not transfer control.

## Snapshot/persistence contract

`unit_movement_routes` and `unit_order_feedback` are registered GameState tables. Their schemas and keys are defined in `modules/base/schema.py`; saves, restores, and IPC snapshots must use the existing schema migration path. The client reads these tables and sends actions; it never writes the authoritative state.
