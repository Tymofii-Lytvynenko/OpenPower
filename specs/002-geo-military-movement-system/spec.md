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

### Edge Cases
- Moving to invalid target region IDs: Movement request ignored if `target_region_id` is not present in the valid regions set.
- Target geolocation resolution: If explicit `target_latitude`/`target_longitude` are omitted in action, system automatically looks up region center coordinates.
- Backfill geo coordinates: Units table missing `latitude`/`longitude` columns automatically backfills coordinates from region center points.

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

## Assumptions & Dependencies

- **Assumption**: Equirectangular projection maps map pixels to latitude `[-90, 90]` and longitude `[-180, 180]`.
- **Dependency**: `ISystem` interface handles system registration under `base.military`.
