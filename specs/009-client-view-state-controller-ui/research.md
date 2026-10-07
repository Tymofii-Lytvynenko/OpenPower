# Research: Client View State Architecture, Navigation & Audio Services

## Decision: Keep navigation on the existing Arcade view lifecycle

- **Decision**: Route menu, loading, game, load-game, and editor transitions through the window-owned `NavigationService`; delegate resource hide/show semantics to `arcade.Window.show_view`.
- **Rationale**: `MainWindow` owns the stable service lifetime and views already reach navigation through the window. A parallel stack would create duplicate lifecycle authority and risks stale input handlers.
- **Alternatives considered**: Add a second client-side view stack; rejected because Arcade already owns the active view and dispatch lifecycle.

## Decision: Keep background work behind the LoadingTask protocol

- **Decision**: Run blocking initialization away from the render loop, communicate only bounded progress/status and a result/error, and make view replacement/cancellation explicit.
- **Rationale**: `LoadingView` already separates task execution from UI-thread view transitions. OpenGL and ImGui work must stay on the window thread.
- **Alternatives considered**: Run map parsing or process startup inside a view callback; rejected because it freezes rendering and input.

## Decision: Keep one window-owned audio stream manager

- **Decision**: Reuse `AudioService` for the whole `MainWindow` lifetime; identify tracks consistently, clamp volume, preserve an already-playing same track, and log recoverable missing/load/stop failures.
- **Rationale**: The service is not view-owned, so it naturally preserves audio through `show_view` transitions. Stream lifetime needs one authority.
- **Alternatives considered**: Load music from each view; rejected because it restarts tracks and complicates cleanup.

## Decision: Keep session access passive and boot polling scheduled

- **Decision**: Retain `NetworkClient` as the `SessionPort` adapter and poll the server progress queue from the Arcade scheduler at 60 Hz using non-blocking reads.
- **Rationale**: The server process remains authoritative; a scheduled non-blocking poll preserves a responsive boot screen.
- **Alternatives considered**: Let a view access server internals or block on a queue read; rejected because the former violates layer boundaries and the latter stalls the UI thread.

## Decision: Inject server session creation from the application composition root

- **Decision**: Keep `src/server` launcher imports in `main.py`; pass a `SessionFactory` callable through `MainWindow` to new/load-game tasks. Client modules depend only on the client session protocol.
- **Rationale**: The governing constitution restricts client imports from `src/server`, while the current window and load/new-game paths import `spawn_local_server` directly. Injection preserves the requested local-process boot flow without leaking server implementation into the client layer.
- **Alternatives considered**: Keep the launcher import in each client view/task; rejected because it contradicts the strict layer rule and duplicates process construction.

## Decision: Treat timing as an unmeasured gate until live sampling

- **Decision**: Keep the 16 ms transition and continuous-render criteria open until measured in a running desktop client. Do not change algorithms without a comparable baseline; cap any future optimization sequence at three measured iterations.
- **Rationale**: Existing unit tests can prove lifecycle calls and state invariants but cannot measure GPU presentation, audible continuity, or actual frame scheduling.
- **Alternatives considered**: Treat mocks or headless tests as proof of live timing; rejected because they do not include the event loop, graphics driver, or audio backend.

## Audit evidence

- The repository already contains `NavigationService`, `AudioService`, `ImGuiService`, `NetworkClient`, `LoadingView`, `NewGameTask`, `EditorLoadingTask`, and the specified HUD bars. The plan therefore targets behavior/coverage gaps and lifecycle correctness rather than introducing a parallel architecture.
- `tests/test_client_services.py` currently covers active-track reuse, volume clamping, missing files, and one navigation route. `tests/test_loading_view.py` covers one-shot failure/success notification and worker start idempotence.
- Baseline on 2026-10-07: `.venv\Scripts\python.exe -m pytest -q tests/test_client_services.py tests/test_loading_view.py` → **6 passed** in 1.52s; pytest reported 116 `DeprecationWarning`s from the installed Pyglet Win32 COM shim (`ctypes._pointer_type_cache`).
- The current client imports the server launcher from `src/client/window.py`, `src/client/tasks/new_game_task.py`, and `src/client/views/load_game_view.py`. Route these imports through an injected factory from `main.py` to comply with the constitution's stricter client/server boundary.
- Desktop timing, audio continuity, window boot progress rendering, and rapid switch cleanup remain unverified by a live client. Headless tests will be reported separately.
- No performance baseline or optimization iteration has been run for this feature; current timing-gate budget is 0/3.
- Implementation headless quickstart on 2026-10-07: **56 passed** (116 third-party Pyglet Win32 COM deprecation warnings). The nearby display-settings/IPC/geo-name/globe-projection regression group also passed (**25 passed**).
- A full-repository run did not complete: it was manually stopped around 39% after several minutes in a CPU-bound test; the first quiet run showed one failure without identifying its test, and the bounded `-x` rerun was also stopped before surfacing an outcome. This remains an unisolated full-suite/performance gate, not a feature-specific failure; no optimization attempts were made.
