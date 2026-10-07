# Research: Geo-Coordinated Military Movement & Pathfinding

## Decisions

### Geographic distance and projection

- **Decision**: Reuse `EquirectangularProjection.geo_distance_km` for the Haversine calculation and coordinate normalization.
- **Rationale**: The core module already owns shared map geometry, uses the specified 6,371 km radius, clamps latitude, and normalizes longitude. Duplicating this logic in gameplay policies risks divergent distance and date-line behavior.
- **Alternatives considered**: A new movement-only Haversine helper (rejected as duplicate mechanism); a planar distance (rejected because it violates spherical distance requirements).

### Route selection

- **Decision**: Keep least-cost routing in the composable `MilitaryRoutePlanner`, backed by region adjacency and segment-cost callbacks. Use complete route tuples as the deterministic equal-cost tie-break.
- **Rationale**: This keeps legal access/domain policy injectable and the search reusable by movement-related systems. It also makes equal-cost paths stable across process and save/load boundaries.
- **Alternatives considered**: Embedding route search inside `MilitarySystem` (rejected due to mixed responsibilities); relying on table iteration order (rejected as nondeterministic).

### Permissions and state transitions

- **Decision**: Query the existing war/treaty state through `MovementAccessPolicy` and keep readiness transitions in `ReadinessSystem`; revalidate only the next route boundary before continuing movement.
- **Rationale**: These are established sources of truth in the engine. Reimplementing treaty or readiness state locally would create conflicting policy.
- **Alternatives considered**: Copying treaty/readiness rules into movement (rejected); validating a route once and never again (rejected because external state changes can invalidate it).

### Persistence and user feedback

- **Decision**: Store route legs and feedback in schema-backed GameState tables, and transport them through existing snapshots and save/IPC migration paths.
- **Rationale**: It preserves deterministic simulation ownership, client passivity, and save compatibility.
- **Alternatives considered**: Client-only route state (rejected because it cannot be authoritative or survive reload); a new persistence service (rejected as unnecessary).

### Legacy scenarios without adjacency

- **Decision**: Retain the existing direct-route compatibility mode only when the scenario has no adjacency edges; once adjacency is supplied, route legs must follow it.
- **Rationale**: Some existing maps/tests predate the adjacency table, while current data supports explicit legal routing. This narrow fallback preserves old scenarios without weakening validation when route data exists.
- **Alternatives considered**: Reject all orders on maps without adjacency (rejected as a backwards-incompatible gameplay regression); treating all regions as adjacent when some adjacency exists (rejected as an authorization bypass).

## Validation Evidence to Gather

- Compare spherical distances against known geographic benchmarks within the spec tolerance.
- Verify deterministic route selection, treaty/war changes, domain checks, readiness behavior, and route-leg arrival using integration tests.
- Record the 10,000-unit movement/manpower benchmark separately from rendering and IPC measurements.
- Keep human-visible map-color and route-inspection checks distinct from headless policy tests.
