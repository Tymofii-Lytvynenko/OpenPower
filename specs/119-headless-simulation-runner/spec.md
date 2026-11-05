# Feature Specification: Headless Simulation Runner and Determinism Comparison

## User Scenarios & Testing

### User Story 1 — Run a reproducible simulation (Priority: P1)

As a developer or scenario author, I want to run a campaign without opening the graphical
client, so that I can inspect gameplay outcomes and reproduce issues from a fixed seed,
module set, and action script.

**Acceptance Scenarios**

1. **Given** a valid project, module list, and duration, **When** `openpower sim run` is
   invoked, **Then** the headless session loads the selected world, advances the configured
   number of days, and writes a run report with a state fingerprint.
2. **Given** a seed and JSON action script, **When** the run reaches each scheduled action,
   **Then** the corresponding supported semantic action is submitted to the session in
   script order.
3. **Given** periodic snapshot and diagnostic intervals, **When** the run advances,
   **Then** timeline records, requested snapshots, diagnostics, and enabled final-table
   exports are written beneath the run output directory.
4. **Given** a system error or a diagnostic failure configured as fatal, **When** the run
   completes, **Then** the report records the failure and the CLI returns a nonzero status.

### User Story 2 — Compare deterministic runs (Priority: P1)

As a developer, I want repeated runs with the same configuration to be compared by their
persistent state, so that divergence is found even when summary metrics happen to match.

**Acceptance Scenarios**

1. **Given** a deterministic configuration, **When** `openpower sim compare` executes the
   requested number of runs, **Then** each run receives the same simulation inputs and
   the result reports whether the complete state fingerprints match.
2. **Given** a difference in persistent state, **When** comparison finishes, **Then** the
   result reports a mismatch and the command exits nonzero.

## Functional Requirements

- **FR-001**: The runner MUST create a headless game session using the selected project,
  modules, optional save, player country, and random seed.
- **FR-002**: The runner MUST accept a duration expressed as years and days, and MUST
  process a validated action script in deterministic order when one is supplied.
- **FR-003**: Each run MUST persist its resolved configuration, timeline, final report,
  state fingerprint, and configured snapshots or table exports under one run directory.
- **FR-004**: Diagnostics MUST report system errors, command failures, schema violations,
  missing required tables, invalid country and region references, and non-finite country
  values when present in the inspected state.
- **FR-005**: A run MUST be marked failed when a configured fatal condition is detected,
  while retaining the diagnostic report for inspection.
- **FR-006**: Repeated-run comparison MUST compare fingerprints of complete persistent
  state and return a failing result when any run diverges.
- **FR-007**: Serialization of run artifacts MUST represent non-finite floating-point
  values as JSON `null` and must emit stable key ordering for deterministic artifacts.

## Key Entities & Data Model

- **SimulationRunConfig**: Immutable inputs for project, modules, save, player, seed,
  duration, action script, output, snapshots, diagnostics, and export policy.
- **SimulationRunReport**: Run identity, artifact paths, snapshot/export paths, failure
  status, issue counts, final fingerprint, and final state summary.
- **DiagnosticIssue**: Severity, stable issue code, message, optional table/column, and
  structured details.
- **ActionScript**: Ordered scheduled actions loaded from JSON and validated against the
  action types handled by the selected runtime.
- **SimulationArtifacts**: Run configuration, JSONL timeline, snapshots, final report,
  and optional final/checkpoint table exports.

## Success Criteria

- **SC-001**: A documented CLI invocation can run a seeded scenario without creating a
  graphical window and produces a final report and fingerprint.
- **SC-002**: Repeated runs with identical inputs produce matching fingerprints; any
  persistent-state difference is reported as a mismatch.
- **SC-003**: Every run artifact can be associated with its run ID and resolved run
  directory, including when the caller selects a custom output directory.
- **SC-004**: Configured fatal diagnostics produce a nonzero CLI result while preserving
  the generated failure report.

## Assumptions & Dependencies

- **Assumption**: The headless runner uses the same `GameSession` and module composition
  as the interactive server, but advances through an explicit deterministic step.
- **Assumption**: The fingerprint includes persistent game state and excludes transient
  presentation state.
- **Dependency**: `GameSession`, the mod runtime, semantic actions, and the schema registry
  are available in the project runtime.
- **Scope**: UI surface automation is specified separately in feature 121; module creation
  and validation commands are specified in feature 120.
