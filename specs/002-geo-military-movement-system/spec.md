# Feature Specification: Geo-Coordinated Military Movement & Pathfinding System

## User Scenarios & Testing

### Primary User Story
As a military commander player, I want to order military units across spherical global coordinates with accurate geographic pathing, distance formulas, and smooth movement interpolation, so that troop deployments reflect realistic global distances and travel times.

### Acceptance Scenarios
1. **Issuing Movement Orders**: **Given** a military unit, **When** an `ActionMoveUnit` is issued specifying target region or coordinates (`target_latitude`, `target_longitude`), **Then** the military system updates unit target geolocations and calculates arrival duration in total simulation minutes.
2. **Geographic Distance Calculation**: **Given** source `GeoCoordinate(lat1, lon1)` and target `GeoCoordinate(lat2, lon2)`, **When** computing distance, **Then** Haversine formula on a 6371.0 km radius Earth sphere determines exact `distance_km`.
3. **Movement Progress & Interpolation**: **Given** a moving unit (`is_moving = True`), **When** simulation time advances, **Then** `movement_progress` advances as `(current_minute - departed_at_minute) / duration_minutes` until reaching 1.0 (arrival).
4. **Unit Recruitment & Costing**: **Given** an `ActionBuildUnit`, **When** processed, **Then** unit cost (`1,000,000 * count`) is deducted from country `money_reserves`, `military_count` is incremented, and a new unit record (`{country_tag}-{unit_type}-{index:03d}`) is generated in the home region.
5. **Manpower Aggregation**: **Given** active regions, **When** every 7th simulation tick runs, **Then** `pop_15_64` (working age population) is aggregated per country owner and updated as `total_core_manpower` in the countries table.
6. **Plan a permitted route**: **Given** a unit and a destination, **When** a movement order is accepted, **Then** the game finds and displays a deterministic route through eligible political regions and international waters, including the reason if no legal route exists.
7. **Move a selected force**: **Given** one or more selected unit groups, **When** the commander issues Move or Move and Attack, **Then** each group receives an independently validated route and retains its own status, owner, and travel estimate.
8. **Attempt a naval landing**: **Given** a force is invading a coastal region from the sea, **When** the landing is evaluated, **Then** the route is allowed only when the configured capital-ship escort and hostile-fleet distance conditions are satisfied.

### Edge Cases
- Moving to invalid target region IDs: Movement request ignored if `target_region_id` is not present in the valid regions set.
- Target geolocation resolution: If explicit `target_latitude`/`target_longitude` are omitted in action, system automatically looks up region center coordinates.
- Backfill geo coordinates: Units table missing `latitude`/`longitude` columns automatically backfills coordinates from region center points.
- A route crosses a country without transit rights; the movement is rejected before departure and reports the blocked region and missing permission.
- A previously legal route becomes unavailable while units are in transit; the group stops at its last legal waypoint and receives a route-recalculation or cancellation result.
- An invasion route loses its capital-ship escort or becomes blocked by a hostile fleet before arrival; the landing is blocked without transferring control.

## Route, Access, and Domain Rules

- **FR-001**: A destination order MUST resolve to a deterministic sequence of adjacent political regions and, when applicable, international-water segments. The route MUST minimize configured travel cost among legal routes; equal-cost routes MUST use a stable tie-breaker.
- **FR-002**: A route MUST allow movement through territory owned or militarily controlled by the unit's country, territory covered by an active allied passage right, and international waters. Other foreign territory MUST require an active military-transit permission. A treaty or war change MUST trigger revalidation of affected future route segments.
- **FR-003**: The route planner MUST report a specific rejection reason when the destination is invalid, unreachable, outside the force's domain, or blocked by territorial access. Rejected movement MUST not change the unit's coordinates, readiness, or ownership.
- **FR-004**: The client MUST display the chosen route and intended action. Route and unit colors MUST distinguish own, allied, hostile, and neutral affiliation using the existing map color conventions.
- **FR-005**: Travel duration MUST use the existing OpenPower geographic-duration contract as its baseline and apply configured modifiers for force size, domestic infrastructure, destination territory, and unit domain. Each route segment MUST retain its geographic distance and authoritative departure and arrival times.
- **FR-006**: Only a ready unit may begin movement. A parked unit MUST follow the readiness transition and pending-order rules in the tactical combat specification; a fortified unit MUST leave fortification before moving. No local movement rule may bypass those transitions.
- **FR-007**: Movement and Move and Attack MUST support multiple selected groups while validating ownership, readiness, route access, target, and domain separately for each group. Failure for one group MUST not mutate another group's order.
- **FR-008**: A sea invasion MUST require an eligible capital ship within 750 km of the target region and MUST be blocked while a hostile fleet is within 1,500 km of the invading fleet. These are scenario-configurable defaults and MUST be evaluated again when the invasion reaches its landing boundary.
- **FR-009**: Land, air, and naval movement MUST use domain-compatible routes and destinations. Ground and air deployment destinations MUST be controlled by the owner or explicitly authorized; naval movement may use valid sea zones and ports permitted by the scenario.

## Exact Mathematical Formulas & Algorithms

### Haversine Distance Formula (`src/core/map/geo.py`)
\[ d = 2 \cdot R \cdot \arcsin\left(\min\left(1.0, \sqrt{\sin^2\left(\frac{\Delta \text{lat}}{2}\right) + \cos(\text{lat}_1) \cdot \cos(\text{lat}_2) \cdot \sin^2\left(\frac{\Delta \text{lon}}{2}\right)}\right)\right) \]
*Where \( R = 6371.0 \) km.*

### Movement Duration Formula (`MovementDurationPolicy`)
\[ \text{duration\_minutes} = \text{int}\left(\max\left(360, \min\left(10080, 360 + \text{distance\_km} \times 0.45\right)\right)\right) \]
*Minimum duration is 6 hours (360 min); maximum duration is 7 days (10,080 min).*

## Key Data Model & Table Schema (`units`)

| Field Name | Type | Description |
| :--- | :--- | :--- |
| `id` | `Utf8` | Unique unit identifier (e.g. `USA-army-001`) |
| `owner` | `Utf8` | Country tag owning the unit |
| `unit_type` | `Utf8` | Unit classification (default: `"army"`) |
| `strength` | `Int64` | Unit troop headcount / strength |
| `current_region_id` | `Int32` | Region ID where unit currently resides |
| `latitude` / `longitude` | `Float64` | Current geographic coordinates |
| `source_region_id` / `lat` / `lon` | `Int32` / `Float64` | Waypoint origin coordinates |
| `target_region_id` / `lat` / `lon` | `Int32` / `Float64` | Waypoint destination coordinates |
| `departed_at_minute` | `Int64` | Minute timestamp when march began |
| `arrival_at_minute` | `Int64` | Minute timestamp of estimated arrival |
| `movement_progress` | `Float64` | Normalized progress from `0.0` to `1.0` |
| `is_moving` | `Boolean` | True if currently marching towards target |

## Success Criteria

- **SC-001**: Distance Precision: Haversine distance matches standard geographic spherical benchmarks within 0.01% tolerance.
- **SC-002**: Stable Tick Execution: Processing movement and manpower updates for 10,000 units completes under 2ms per tick.
- **SC-003**: Deterministic Progress: Unit arrival occurs on the exact calculated `arrival_at_minute` timestamp.
- **SC-004**: Legal routing: 100% of movement attempts either produce a valid route through permitted regions or a visible rejection reason, with zero unauthorized border crossings.
- **SC-005**: Route stability: identical map, access rights, unit attributes, and ordered commands produce the same route and arrival times across repeated runs and save/load.
- **SC-006**: Naval invasion validation: all controlled cases at the escort and hostile-fleet distance boundaries produce the documented allow/block result without premature landing or control transfer.

## Assumptions & Dependencies

- **Assumption**: Equirectangular projection maps map pixels to latitude `[-90, 90]` and longitude `[-180, 180]`.
- **Assumption**: The existing geographic-duration formula remains the baseline; size, infrastructure, destination, and domain adjustments are explicit, bounded scenario data.
- **Assumption**: The 750 km escort radius and 1,500 km hostile-fleet exclusion radius are default scenario values, not constants that mods cannot override.
- **Dependency**: `ISystem` interface handles system registration under `base.military`.
- **Dependency**: Readiness transitions and pending orders remain governed by `specs/101-tactical-combat-resolution/spec.md`; route permissions consume existing treaty and war state.
