# Quickstart & Verification Guide: Multi-Process IPC Architecture

## Prerequisites & Launching

To verify the multi-process architecture end-to-end:

```bash
# Launch the application (starts MainWindow and spawns server process)
python main.py
```

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
