# Feature Specification: Mod Authoring and Runtime Validation CLI

## User Scenarios & Testing

### User Story 1 — Create a module scaffold (Priority: P1)

As a mod author, I want a command to create a minimal module with a manifest,
registration entry point, starter system, and README, so that I can begin from a module
structure the engine can discover.

**Acceptance Scenarios**

1. **Given** a valid lower-snake-case module ID that does not already exist, **When**
   `openpower mod create` is invoked, **Then** the command creates the module under the
   selected project's `modules/` directory and reports how to validate it.
2. **Given** a module ID with invalid characters or an existing target directory, **When**
   the command is invoked, **Then** it fails with a clear error and does not overwrite the
   existing module.
3. **Given** explicit display name and dependency options, **When** the scaffold is
   created, **Then** those values are represented in the generated manifest.

### User Story 2 — Validate a module through the real runtime (Priority: P1)

As a mod author, I want to validate a module through the actual load and startup path, so
that manifest, dependency, registration, schema, system, and action errors are found
before I enable the module in a campaign.

**Acceptance Scenarios**

1. **Given** a valid module, **When** `openpower mod validate` is invoked, **Then** the
   runtime loads its dependency set, builds a headless session, executes a startup tick,
   and reports the resolved systems, schemas, tables, and handled actions.
2. **Given** a missing module, invalid dependency declaration, import failure, or invalid
   system graph, **When** validation runs, **Then** it fails with the originating runtime
   error rather than reporting the module as valid.
3. **Given** a project root supplied with `--project-root`, **When** either command runs,
   **Then** all module discovery and generated paths are rooted in that project.

## Functional Requirements

- **FR-001**: The create command MUST accept a module ID, optional display name, one or
  more dependencies, and an optional project root.
- **FR-002**: Module IDs and dependencies MUST use the supported lower-snake-case form
  and begin with a letter.
- **FR-003**: The scaffold MUST include a module manifest, package initializer, registration
  function, starter system, and author README.
- **FR-004**: The create command MUST refuse to overwrite an existing module directory.
- **FR-005**: Validation MUST load the requested module through the production discovery,
  contribution composition, schema, and session startup path and execute one startup tick.
- **FR-006**: A successful validation report MUST identify the resolved module order,
  system IDs, table schemas, state tables, and handled action types.
- **FR-007**: Validation failures MUST remain visible as command failures with useful
  diagnostics; the CLI MUST NOT mark a failed load as valid.

## Key Entities & Data Model

- **Mod manifest**: Module ID, display name, version, API version, minimum engine version,
  and declared dependencies.
- **ModScaffoldResult**: Normalized module ID, generated module path, and files created.
- **ModValidationReport**: Module ID, resolved load order, system IDs, schema names, state
  table names, and handled action types.

## Success Criteria

- **SC-001**: A new module created by the CLI is discoverable by the runtime without
  manually adding it to a central registration list.
- **SC-002**: A valid module passes validation only after the runtime completes a startup
  tick and reports its composed contracts.
- **SC-003**: Invalid IDs and existing directories never produce a partial overwrite.
- **SC-004**: Every validation failure returns a failing status and preserves the specific
  failure context for the author.

## Assumptions & Dependencies

- **Assumption**: New gameplay policy is implemented inside modules and composed through
  the mod API described in features 008 and 104.
- **Dependency**: `src/shared/mods.py`, `src/shared/mod_api.py`, `GameSession`, and the
  CLI entry point are available in the selected project.
- **Scope**: This feature covers module scaffolding and validation. Running scripted
  simulations and comparing deterministic runs are described in feature 119.
