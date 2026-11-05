# Feature Specification: UI Journey Test Harness

## User Scenarios & Testing

### User Story 1 — Inspect available UI surfaces (Priority: P1)

As a developer validating the game interface, I want a catalog of registered UI surfaces,
so that I can select an in-game panel or workflow for automated inspection.

**Acceptance Scenarios**

1. **Given** registered UI surfaces, **When** `openpower ui-test list` is invoked,
   **Then** the command returns their IDs and descriptive metadata as JSON.
2. **Given** an unknown surface ID, **When** a run is requested, **Then** the harness
   reports the invalid surface and returns a failing status.

### User Story 2 — Run a reproducible UI journey (Priority: P1)

As a developer, I want to run a UI surface with fixture data and scripted interactions,
so that I can review rendered output and interaction results without starting a campaign
manually.

**Acceptance Scenarios**

1. **Given** a registered surface, fixture, optional journey, and positive viewport size,
   **When** `openpower ui-test run` is invoked, **Then** the harness writes a structured
   report and screenshot to the requested output directory.
2. **Given** a screenshot baseline and a tolerance between zero and one, **When** the
   surface is run, **Then** visual comparison is reported alongside interaction results.
3. **Given** the matrix option, **When** the run is requested, **Then** the surface is
   evaluated at 800×600, 1024×768, 1280×720, and 1920×1080.
4. **Given** an interaction journey, **When** each step is applied, **Then** assertions
   and output artifacts correspond to the named surface and fixture.

### User Story 3 — Run and recover a UI suite (Priority: P2)

As a developer reviewing multiple surfaces, I want a suite command that records every
surface/viewport result and can rerun only failures, so that I can inspect regressions
without losing prior suite evidence.

**Acceptance Scenarios**

1. **Given** the registered surface catalog, **When** `openpower ui-test all` runs,
   **Then** it writes a `suite.json` summary containing each run's surface, viewport,
   result, exit code, report path, and captured log.
2. **Given** an existing suite with failed runs, **When** `--rerun-failed` is selected,
   **Then** only failed surface/viewport pairs are rerun and unrelated prior results are
   retained.
3. **Given** a request for a live smoke check, **When** `openpower ui-test live-smoke` is
   invoked, **Then** the harness exercises the agent input path in the real Arcade runtime
   and writes its artifacts to the requested directory.

## Functional Requirements

- **FR-001**: The harness MUST list registered UI surfaces with stable identifiers.
- **FR-002**: A surface run MUST accept optional fixture and journey JSON, output path,
  viewport dimensions, optional screenshot baseline, and visual tolerance.
- **FR-003**: Fixture and journey files MUST be JSON objects; viewport dimensions MUST be
  positive; visual tolerance MUST be in the inclusive interval from zero to one.
- **FR-004**: A surface run MUST write a machine-readable report and rendered screenshot
  under its output directory.
- **FR-005**: A suite run MUST isolate each surface/viewport run and report its exit status,
  output report path, and captured process log.
- **FR-006**: Suite recovery MUST rerun only previously failed pairs selected for the
  current run and retain results for pairs not rerun.
- **FR-007**: The viewport matrix MUST consist of 800×600, 1024×768, 1280×720, and
  1920×1080.
- **FR-008**: The harness MUST provide a live smoke workflow that uses the real Arcade
  runtime in addition to headless fixture-driven inspection.
- **FR-009**: Invalid arguments, input files, or surface IDs MUST produce an actionable
  failure result rather than a passing report.
- **FR-010**: The harness MUST retain the budget-panel smoke command, validate its viewport,
  and write the panel's report and screenshot to the selected output directory.

## Key Entities & Data Model

- **Surface Definition**: Stable ID, display name, fixture requirements, renderer, and
  interaction driver for one UI inspection target.
- **Journey**: JSON configuration describing ordered interactions and expected outcomes.
- **Fixture**: JSON mapping of state tables, globals, and game time overrides for a
  deterministic surface setup.
- **Surface Report**: Surface ID, viewport, journey result, visual-comparison result,
  diagnostics, and screenshot/report artifact paths.
- **Suite Run**: Surface/viewport pair, pass status, exit code, report path, and captured
  child-process log.

## Success Criteria

- **SC-001**: Every registered UI surface can be listed and invoked by its stable ID.
- **SC-002**: A completed surface run produces both a report and an actual screenshot.
- **SC-003**: A suite report identifies every attempted surface/viewport pair and its
  result, and can be used to select failed pairs for another run.
- **SC-004**: Fixture-driven journeys run without mutating authoritative server state.
- **SC-005**: Live smoke coverage is explicitly distinguishable from headless fixture
  coverage in its output artifacts.
- **SC-006**: The budget-panel command remains available as a named shortcut to its
  registered surface inspection workflow.

## Assumptions & Dependencies

- **Assumption**: Surface definitions and drivers are registered in the UI testing
  catalog; the harness does not infer arbitrary panels from source code.
- **Dependency**: Dear ImGui surface renderers, fixture builders, journey drivers, and the
  Arcade runtime are available in the selected project.
- **Scope**: This feature specifies the validation harness. Gameplay requirements of
  individual panels remain in their owning feature specifications.
