# Implementation Plan: ImGui Dashboard & Data Inspector Panels

**Branch**: `010-imgui-dashboard-inspector-panels` | **Date**: 2026-10-07 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/010-imgui-dashboard-inspector-panels/spec.md`

## Summary

Complete the existing ImGui dashboards and inspectors on the current client/server architecture. Add the missing personal-income-tax budget control and dispatch it through `ActionUpdateBudget`, show resource trade balances with ImPlot, make resource-ledger schema failures visible, and align political weekly drift with the specified baseline formula and metric fallbacks while retaining OpenPower's active political modifiers. Keep `GameState` server-authoritative and the client limited to action dispatch and snapshot display.

## Technical Context

**Language/Version**: Python 3.12 (project `.venv`)
**Primary Dependencies**: Polars, imgui_bundle (Dear ImGui + ImPlot), Arcade
**Storage**: Existing in-memory Polars `GameState.tables`; persistence contracts unchanged
**Testing**: pytest; headless panel/system tests plus manual rendered-window checks
**Target Platform**: Windows desktop, OpenGL-backed Arcade client; headless server remains supported
**Project Type**: Desktop grand-strategy game with client/server process boundary
**Performance Goals**: 10,000-row Data Inspector gate <4 ms/frame; interactive dashboard target 60+ FPS
**Constraints**: No direct client mutation of `GameState`; no layer-boundary changes; preserve existing budget, political-effect, war-exhaustion, and policy behavior; performance tuning limited to three measured optimization iterations per algorithm
**Scale/Scope**: Eight existing dashboard/inspector panels; this change closes specification gaps without replacing their architecture

## Constitution Check

- **Layer separation/passive client**: Pass. UI emits `ActionUpdateBudget`; simulation continues to own political state changes.
- **Polars data model**: Pass. Existing `GameState` DataFrames remain the source for dashboards and inspectors.
- **Composition/SOLID**: Pass. ImPlot context remains owned by the existing `ImGuiService`; resource plotting stays in `ResourcesPanel`.
- **Commenting**: Pass. Code comments will explain rationale only and remain in English.
- **Empirical verification/anti-masking**: Pass after implementing explicit missing-column messages, focused tests, and recording the performance gates separately from functional tests.

## Project Structure

```text
modules/base/systems/politics/politics_system.py
src/client/services/imgui_service.py
src/client/ui/panels/budget_panel.py
src/client/ui/panels/resources_panel.py
src/client/window.py
src/client/views/editor_view.py
tests/test_budget_panel.py
tests/test_data_inspector_panel.py
tests/test_politics_stability_drift.py
tests/test_resources_panel.py
specs/010-imgui-dashboard-inspector-panels/
```

**Structure Decision**: Modify the existing game client service and panels, the existing base politics system, and their focused pytest modules. No new runtime package or cross-layer interface is introduced. Feature evidence and pending empirical gates are recorded alongside this plan.

## Design Decisions

1. Treat the user's `tick % 7 == 0` as a weekly game-time boundary, not `GameState.globals["tick"]`: the engine tick advances every simulation step and is not a day counter. Use elapsed game days derived from `TimeData.total_minutes`, and only process on `EventNewDay`.
2. Compute the baseline target from the specified approval/HDI/corruption equation with finite null/missing fallbacks. Apply existing rights, stability, economic-health, and war-exhaustion modifiers afterward so the new baseline does not silently remove OpenPower gameplay.
3. Use the installed ImPlot bindings directly (`create_context`, `set_current_context`, `destroy_context`, `begin_plot`, `setup_axis_ticks`, `plot_bars`, `end_plot`). Keep the context paired with its owning ImGui context.
4. Keep data-inspector filtering/sorting caching and ImGui `ListClipper` virtualization. First measure the 10k-row scenario; change the algorithm only if evidence fails the gate, with at most three recorded attempts.

## Complexity Tracking

No constitution violations are introduced. Empirical UI timing depends on the rendered desktop/OpenGL path and is not established by headless tests; the measurement method and current status are tracked in `performance-log.md`.
