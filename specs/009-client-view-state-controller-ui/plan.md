# Implementation Plan: Client View State Architecture, Navigation & Audio Services

**Branch**: `main` | **Date**: 2026-10-07 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification at `specs/009-client-view-state-controller-ui/spec.md`

## Summary

Complete and verify the existing client composition around `MainWindow`, view navigation, background audio, asynchronous loading, the passive IPC client, and reusable HUD bars. Keep each concern in its existing `src/client` service, task, view, or UI component. View changes continue through Arcade's `Window.show_view`; background work reports progress through task state and never touches OpenGL; `NetworkClient` remains an action/snapshot boundary rather than an authority over game state.

## Technical Context

**Language/Version**: Python 3.10+ (the local test runtime is Python 3.14).

**Primary Dependencies**: Arcade 3.x, `imgui_bundle`, pytest, and the existing `SessionPort` / `ClientSessionProxy` IPC contract.

**Storage**: No new persistent feature state. Per-window service instances, the active Arcade view, task progress/result/error, and one active audio stream are runtime state. Game state remains authoritative in the server process.

**Testing**: Focused pytest tests with mocked windows, views, audio streams, queues, and task workers; run from `.venv\Scripts\python.exe`. Live acceptance additionally needs an interactive desktop client.

**Target Platform**: Existing Windows desktop client plus headless test execution.

**Project Type**: Modular Python desktop application with a server-authoritative simulation process and passive client.

**Performance Goals**: A view transition should finish within one rendered frame (16 ms); server boot progress is polled at 60 Hz; loading work must not block frame rendering. No timing baseline is currently available for live view transitions or sustained rendering.

**Constraints**: Keep window/view/audio/UI policy in `src/client`; do not import client code into shared/core/engine/server/module layers. Keep `src/server` imports out of `src/client`: `main.py` is the composition root and injects a client-facing session factory. Do not mutate authoritative `GameState` from the client. Do not make OpenGL calls from loading workers. Preserve task failures as visible/reportable errors and release prior view/audio resources deterministically. Limit algorithm optimization to three measured iterations per gate; performance work must not delay functional coverage.

**Scale/Scope**: One local desktop window, one active view, one active music stream, a small number of asynchronous loading tasks, and the HUD controls registered by the running client.

## Constitution Check

- **Layer separation and passive client**: PASS. Navigation, audio, loading, and HUD remain in `src/client`; state access and actions go through the existing session/network boundary.
- **Authoritative schemas/data-oriented simulation**: PASS. This feature adds no world-state schema or simulation policy.
- **Modularity/SOLID**: PASS WITH VERIFICATION. Services own focused lifetimes; views compose services and callbacks instead of embedding process or simulation logic.
- **Commenting**: PASS WITH VERIFICATION. New comments must explain lifecycle, threading, or compatibility rationale in English.
- **Empirical verification**: OPEN. Headless service/loading tests are available; live transition timing, audio continuity, and boot progress rendering require desktop acceptance.

## Design Decisions

1. Use `NavigationService` as the single view-construction/transition entry point while leaving old-view teardown to Arcade's view lifecycle. Do not create a second stack or dispose a view before Arcade has delivered its hide lifecycle.
2. Keep one `AudioService` on `MainWindow`, so music survives view changes. Normalize track identity, clamp volume, stop replaced streams, report missing/failed tracks non-fatally, and avoid swallowing unrelated cleanup failures without diagnostics.
3. Keep expensive editor/new-game setup in task workers. Tasks expose bounded progress/status and return a result or exception; `LoadingView` alone performs the next view transition on the UI thread.
4. Keep startup polling in the window scheduler at 60 Hz. Queue polling must be non-blocking, and boot errors must stay visible without a busy loop.
5. Keep process creation in the application composition root (`main.py`) and inject a `SessionFactory` into the client window/tasks. Client modules depend on a client-facing protocol, not `src.server` implementation modules.
6. Keep `NetworkClient` a passive adapter over `SessionPort`; HUD components receive snapshots and callbacks and dispatch semantic actions rather than mutating simulation state.
7. Treat `CentralBar`, `SystemBar`, `ToggleBar`, and `ContextMenu` as reusable composed components with stable action callbacks, not holders of authoritative state.

## Project Structure

```text
main.py
src/client/
├── window.py
├── interfaces/
│   └── session_factory.py
├── services/
│   ├── navigation_service.py
│   ├── audio_service.py
│   ├── imgui_service.py
│   └── network_client_service.py
├── tasks/
│   ├── new_game_task.py
│   ├── load_game_task.py
│   ├── editor_loading_task.py
│   └── session_startup.py
├── views/
│   ├── loading_view.py
│   ├── server_boot_view.py
│   └── base_view.py
└── ui/components/hud/
    ├── central_bar.py
    ├── system_bar.py
    ├── toggle_bar.py
    └── context_menu.py

tests/
├── test_audio_service.py
├── test_navigation_service.py
├── test_loading_view.py
├── test_session_startup.py
├── test_new_game_task.py
├── test_load_game_task.py
├── test_editor_loading_task.py
├── test_window_boot.py
├── test_hud_components.py
└── test_economy_validator.py
```

**Structure Decision**: Extend the existing single desktop project and preserve its service/task/view/component boundaries. No new runtime package, inheritance hierarchy, server API, or persistent table is required.

## Complexity Tracking

No constitution exception is required. Live frame timing and the 60-FPS rendering criterion remain empirical gates; do not perform unmeasured algorithm rewrites to claim they pass. Establish a comparable baseline first, allow at most three measured iterations for any timing gate, and then record and defer a still-failing gate while continuing other features.
