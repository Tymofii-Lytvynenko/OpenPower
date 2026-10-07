# Client Runtime Ports

This feature does not add a network protocol. It preserves two existing internal contracts.

## LoadingTask

Defined by `src/client/interfaces/loading.py` and consumed by `src/client/views/loading_view.py`:

- A task exposes `progress` in `[0.0, 1.0]` and a user-readable `status_text`.
- `run()` may block and is called on the loading worker, never on the render thread.
- `cancel()` requests cooperative cancellation at safe checkpoints; cancellation must not make a hidden task navigate or retain a process created by that task.
- The return value is passed to the success callback on the UI thread.
- An exception is passed once to the failure callback or surfaced by the loading view.
- A task must not call Arcade/OpenGL/ImGui APIs from its worker.

## SessionPort

Defined by `src/shared/protocols.py` and implemented by local client session adapters:

- `receive_action(GameAction) -> str` submits intent to the authoritative simulation.
- `get_state_snapshot() -> GameState | None` reads the latest snapshot.
- `save_map_changes()` requests editor persistence.
- The client does not write simulation state directly; a session proxy owns process/IPC cleanup.

## SessionFactory

The client-facing factory protocol lives under `src/client/interfaces/`; its implementation is composed by `main.py`:

- The factory receives `GameConfig` plus optional save/player selection and returns a client session protocol.
- `src/client` code does not import `src/server` launcher or process internals.
- The composition root owns bundle construction and must clean up the child process if proxy construction fails.
- The returned session owns its IPC queues/process and provides the boot progress queue consumed by the window or a loading task.

The server boot queue carries `PROGRESS`, `READY`, or `ERROR` messages. `MainWindow` consumes them without blocking the UI event loop; `ServerBootView` only presents the resulting boot state.
