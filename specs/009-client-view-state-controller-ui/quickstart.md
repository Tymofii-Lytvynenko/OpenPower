# Quickstart: Client View State Architecture, Navigation & Audio Services

## Automated validation

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_audio_service.py tests/test_navigation_service.py tests/test_loading_view.py tests/test_client_service_contracts.py tests/test_session_startup.py tests/test_new_game_task.py tests/test_load_game_task.py tests/test_editor_loading_task.py tests/test_window_boot.py tests/test_session_factory_composition.py tests/test_hud_components.py tests/test_economy_validator.py tests/test_client_services.py tests/test_layer_boundaries.py
```

Headless result on 2026-10-07: **56 passed**. The run emitted 116 third-party Pyglet `ctypes._pointer_type_cache` deprecation warnings; no project test failed. Boot tests also verify that each queued progress update is surfaced in order before the terminal `READY` message; actual on-screen rendering remains part of interactive acceptance.

## Interactive acceptance

1. Start the desktop client and confirm the boot screen paints before the local server starts. Observe progress updates and verify the main menu appears after `READY`; force a startup error and verify it remains visible without a frozen window.
2. Navigate through main menu, new game, loading, game, load game, and editor routes. Verify each transition reaches the requested view and the previous view no longer receives input or scheduled updates.
3. Start editor loading, switch away while work is running, then confirm its worker cannot unexpectedly replace the newly selected view or retain session/process resources.
4. Play a music track, navigate between views, and confirm it remains continuous. Select another track, stop playback, adjust volume below/within/above range, and try a missing file; confirm the application remains usable.
5. Resize the window repeatedly and verify viewport/scissor bounds and current-view resize handling stay synchronized.
6. Verify CentralBar, SystemBar, ToggleBar, and ContextMenu actions route through their callbacks and do not mutate authoritative simulation state in the client.

Record mocked/headless test results separately from live observations. The 16 ms transition and continuous audio/rendering criteria remain open until a live desktop run is measured.

## Interactive acceptance status

Not run in this implementation pass. A live desktop run is still required to verify the boot screen/progress rendering, one-frame navigation timing, continuous audio, rapid view replacement, and resize behavior. No frame-time or audio-continuity result is inferred from headless tests.

The full repository suite was stopped manually at roughly 39% after several minutes in a CPU-bound test. The initial quiet run showed one failure without printing its test name; a `-x` rerun was also stopped at the same slow section before it surfaced a result. The nearby display-settings, IPC, geo-name, and globe-projection group passed separately (**25 passed**), so the original failure remains unisolated. This is recorded as an incomplete suite/performance gate, not as evidence of a failed 009 acceptance scenario; no optimization iteration has been spent.
