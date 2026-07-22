# Feature Specification: Mod Data Chaining Engine

## User Scenarios & Testing

### Primary User Story
As a player or mod developer, I want to activate multiple game mods concurrently with declarative dependency ordering, configuration inheritance, and data table overlaying (`mods.json`), so that custom content, historical scenarios, and gameplay tweaks can be combined seamlessly without manual file editing or mod conflicts.

### Acceptance Scenarios
1. **Mod Dependency Resolution**: **Given** a `mods.json` file specifying multiple active mods with explicit dependencies, **When** the mod manager initializes on startup, **Then** it computes a topological load order, verifying all required parent mods are present and free of circular references.
2. **Data Table Merging**: **Given** a secondary mod providing updated region parameters or new country attributes, **When** game datasets are loaded, **Then** the secondary mod's records overlay cleanly onto the base dataset without overwriting unreferenced rows or violating schemas.
3. **Conflict Detection & Reporting**: **Given** missing mod dependencies or conflicting table schemas, **When** the startup loader runs, **Then** initialization halts safely, displaying a detailed diagnostic report identifying the failing mod IDs and missing prerequisites.

### Edge Cases
- Circular dependencies between two or more community mods (e.g., Mod A requires Mod B, Mod B requires Mod A).
- Deeply nested mod chains (10+ levels of dependency hierarchy) altering identical data tables.
- Mods targeting different schema versions or deprecated game data structures.

## Functional Requirements

- **FR-001**: Topological Dependency Ordering: The mod loader MUST scan `mods.json` manifests, construct a dependency graph, and determine valid load ordering prior to dataset instantiation.
- **FR-002**: Data Table Overlaying: The loading pipeline MUST support non-destructive DataFrame merging, allowing child mods to append, update, or patch specific rows/columns in Polars game tables.
- **FR-003**: Cascading Asset Resolution: Texture atlas definitions, sound files, and localization strings MUST resolve hierarchically down the active mod chain with base game fallbacks.
- **FR-004**: Schema & Version Validation: The loader MUST validate mod metadata against minimum engine version requirements and reject incompatible mod configurations before state initialization.
- **FR-005**: Dynamic System Registration: ECS systems provided by active mods MUST be registered into the simulation tick pipeline in validated dependency order.

## Key Entities & Data Model

- **ModManifest**: Represents mod identifier, human-readable name, author, version, engine compatibility range, dependencies list, and asset paths.
- **ModLoadChain**: Ordered sequence of validated active mods ready for table merging and system registration.

## Success Criteria

- **SC-001**: Fast Initialization: Resolving dependency trees and merging tables for up to 25 active mods completes in under 1.5 seconds on startup.
- **SC-002**: Topological Determinism: 100% of valid mod configurations yield identical load sequences across Linux and Windows platforms.
- **SC-003**: Robust Error Handling: 100% of circular or missing dependencies are trapped with descriptive error messages before `GameState` allocation.

## Assumptions & Dependencies

- **Assumption**: `mods.json` manifest file structure and `modules/` directory conventions exist.
- **Dependency**: Polars DataFrame concats and joins support non-destructive dataset merging in `src/server`.
