# Quickstart & Verification Guide: Multi-Process IPC Architecture

## Prerequisites & Launching

Run from the repository root in PowerShell with the project virtual environment.

To verify the multi-process architecture end-to-end:

```powershell
# Launch the application (starts MainWindow and spawns server process)
.venv\Scripts\python.exe main.py
```

## Automated verification

```powershell
.venv\Scripts\python.exe -m pytest `
  tests/test_game_state_ipc.py `
  tests/test_client_snapshot_performance.py `
  tests/test_command_pipeline.py `
  tests/test_runtime_architecture.py `
  tests/test_layer_boundaries.py `
  tests/test_headless_server.py::TestHeadlessServer::test_game_session_starts_headlessly_and_serializes_state `
  tests/test_headless_server.py::TestHeadlessServer::test_launcher_client_proxy_executes_command_over_delta_ipc `
  tests/test_headless_server.py::TestHeadlessServer::test_run_server_process_boots_in_a_separate_process -q -p no:cacheprovider
```

Recorded result on the current Windows/Python 3.14 workspace: `18 passed in 30.33s`. This covers full/delta snapshot IPC, command dispatch, spawn startup, server/client interaction, and process teardown. Snapshot bounds are asserted in `tests/test_client_snapshot_performance.py`: 2,000 tactical rows under 2 MB and under 1.5 seconds; 100 engagement summaries under 100 ms for headless decode/presentation.

## Validation Scenarios

### Scenario 1: Multi-Core Process Decoupling
1. Launch the application.
2. Open Task Manager (Windows) or process monitor.
3. Observe two distinct `python.exe` processes running:
   - Client Window Process (GUI rendering, Arcade/OpenGL context).
   - Server Background Process (`run_server_process`, daemon=True).

### Scenario 2: 10 TPS Pace & 60+ FPS Rendering
1. Enter the game screen.
2. Verify that UI interaction (camera dragging, ImGui panel inspection) runs smoothly at 60+ FPS.
3. Verify simulation tick progression advances deterministically at 10 TPS in the Central Bar HUD.

### Scenario 3: Clean Process Teardown
1. Close the application window via `X` or exit menu.
2. Check Task Manager to confirm both processes exit cleanly without zombie `python.exe` background tasks remaining.

**Manual status (2026-10-06):** Launched `.venv\Scripts\python.exe -u main.py`, reached the main menu, and started a single-player session at speed 1. The HUD advanced from `2001-01-01 02:12` to `2001-01-02 00:31` while the client stayed interactive; country selection, speed controls, and a map drag responded. Windows process inspection showed the client and a distinct child server process. The live FPS overlay samples were `60, 60, 59, 60, 59, 60`; this confirms the decoupled UI kept rendering during simulation, but does not pass the sustained 60+ FPS criterion because sub-60 samples occurred. Closing the window stopped both processes. Keep T012 open until a sustained in-client 60+ FPS measurement is recorded.
