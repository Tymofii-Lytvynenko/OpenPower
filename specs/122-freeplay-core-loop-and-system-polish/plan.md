# Implementation Plan: Freeplay Core Loop and System Polish

**Branch**: Not created; planning on the existing `main` branch | **Date**: 2026-11-09 | **Spec**: [spec.md](spec.md)

**Input**: [Freeplay Core Loop and System Polish specification](spec.md)

## Summary

Make freeplay the direct single-player entry point and close the player-facing gaps in the loop that already exists: select a country, enter an authoritative session, control time, issue consequential domain actions, understand command outcomes, and save/resume. Keep campaigns optional. Reuse the 34 registered base systems, current actions, HUD panels, and persistence pipeline; add no parallel simulation rules or new authoritative schema unless implementation evidence requires one.

## Technical Context

**Language/Version**: Python 3.10+  
**Primary Dependencies**: Arcade, Dear ImGui, Polars, Apache Arrow, existing OpenPower modules  
**Storage**: Existing authoritative `GameState` tables and save/IPC contracts  
**Testing**: Existing pytest coverage, simulation session tests, and the `openpower ui-test` harness; all planned acceptance is automated  
**Target Platform**: OpenPower desktop client, single-player local session  
**Project Type**: Python desktop strategy game with an authoritative simulation process  
**Performance Goals**: Preserve existing simulation-step and rendering budgets; add no new workload or performance target without evidence of a current bottleneck  
**Constraints**: Determinism, save compatibility, passive-client/layer boundaries, no required campaign records, no manual desktop acceptance task  
**Scale/Scope**: Freeplay launch and the minimum economy, politics, military, diplomacy, time-control, feedback, and save/resume paths over existing systems

## Constitution Check

- **Layer separation**: PASS. The client selects a country and dispatches semantic actions; module systems own simulation policy; server/session code owns state integrity and persistence.
- **Composition over inheritance / SOLID**: PASS. Reuse session-startup collaborators and injected navigation/action boundaries. Do not create a parallel freeplay simulation or subclass a campaign task to bypass its workflow.
- **Data-oriented state**: PASS. Existing Polars tables remain authoritative. Add no table or migration unless the implementation demonstrates a missing persistent contract.
- **Empirical verification**: PASS for the plan. The planned implementation must add/run automated acceptance evidence before it is declared complete. No test or UI command was run while preparing this plan.
- **Campaign scope**: PASS. Campaigns and scenarios remain optional content; their setup, objectives, and outcome lifecycle do not gate or terminate freeplay.

## Current-State Findings

See [research.md](research.md) for the system inventory and evidence. The key integration gap is that `NewGameView` opens on scenario selection and requires a selected scenario, while `NewGameTask` sends `ActionStartCampaign` and waits for a campaign row before reporting the session ready. `open_sandbox` therefore uses campaign setup even though the desired default is open-ended freeplay. Time controls, domain systems, player-facing panels, command feedback, and persistence already exist and should be polished at their current ownership boundaries.

## Project Structure

### Documentation (this feature)

```text
specs/122-freeplay-core-loop-and-system-polish/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── contracts/freeplay-start-and-playability.md
├── quickstart.md
├── checklists/requirements.md
└── tasks.md
```

### Source Code and Automated Acceptance

```text
src/client/views/new_game_view.py
src/client/tasks/session_startup.py
src/client/tasks/freeplay_start_task.py
src/client/ui/components/shared/freeplay_setup_window.py
src/client/ui/layouts/game_layout.py
src/client/ui/layouts/game_panel_registry.py
src/client/ui/components/hud/central_bar.py
src/client/ui/components/shared/command_feedback.py
src/client/ui/components/shared/unit_order_feedback.py
src/client/ui/testing/
src/shared/actions.py
modules/base/registration.py
modules/base/systems/{economy,politics,military,world,demographics}/
src/server/io/{save_writer.py,data_load_manager.py}
tests/test_new_game_view_coverage.py
tests/test_freeplay_start_task.py
tests/test_freeplay_core_loop.py
tests/test_freeplay_save_load.py
tests/ui/{fixtures,journeys}/
```

**Structure Decision**: Keep gameplay policy in its existing registered module systems, use the current action and persistence contracts, and extend the existing UI test harness. Extract a small freeplay startup coordinator only if it gives `NewGameView` and session startup a clear single responsibility; keep it composed from existing startup, session, and navigation ports.

## Complexity Tracking

No constitution exception or new architectural layer is planned. Any schema change or additional orchestration layer requires a demonstrated gap and a documented owner.
