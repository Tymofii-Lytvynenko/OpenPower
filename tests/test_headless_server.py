import multiprocessing as mp
import queue
import time
import unittest
from pathlib import Path

from src.engine.simulator import Engine
from src.server.server_process import run_server_process
from src.server.session import GameSession
from src.shared.config import GameConfig
from src.shared.state import GameState


class TestHeadlessServer(unittest.TestCase):
    def test_game_session_starts_headlessly_and_serializes_state(self):
        project_root = Path(__file__).resolve().parent.parent
        config = GameConfig(project_root)
        progress_messages: list[tuple[float, str]] = []

        session = GameSession.create_headless(
            config,
            progress_cb=lambda progress, text: progress_messages.append((progress, text)),
        )

        self.assertIsNone(session.map_data)
        self.assertIsInstance(session.engine, Engine)
        self.assertTrue(progress_messages)
        self.assertEqual(progress_messages[-1], (1.0, "Server: Ready."))

        session.tick(0.1)
        ipc_payload = session.state.to_ipc()
        round_tripped_state = GameState.from_ipc(ipc_payload)

        self.assertIn("regions", round_tripped_state.tables)
        self.assertIn("countries", round_tripped_state.tables)
        self.assertFalse(round_tripped_state.get_table("regions").is_empty())
        self.assertFalse(round_tripped_state.get_table("countries").is_empty())
        self.assertIn("base.time", round_tripped_state.system_state)

    def test_run_server_process_boots_in_a_separate_process(self):
        project_root = Path(__file__).resolve().parent.parent
        ctx = mp.get_context("spawn")
        action_queue = ctx.Queue()
        state_queue = ctx.Queue()
        progress_queue = ctx.Queue()
        shutdown_event = ctx.Event()
        process = ctx.Process(
            target=run_server_process,
            args=(str(project_root), action_queue, state_queue, progress_queue, None, shutdown_event),
            daemon=True,
        )

        process.start()
        try:
            ready_event: tuple[float, str] | None = None
            deadline = time.monotonic() + 60.0
            while time.monotonic() < deadline:
                try:
                    status, progress, text = progress_queue.get(timeout=1.0)
                except queue.Empty:
                    continue
                if status == "ERROR":
                    self.fail(text)
                if status == "READY":
                    ready_event = (progress, text)
                    break

            self.assertEqual(ready_event, (1.0, "Engine Started"))

            snapshot_deadline = time.monotonic() + 30.0
            snapshot_payload = None
            while time.monotonic() < snapshot_deadline and snapshot_payload is None:
                try:
                    snapshot_payload = state_queue.get(timeout=1.0)
                except queue.Empty:
                    continue

            self.assertIsNotNone(snapshot_payload)
            snapshot = GameState.from_ipc(snapshot_payload)
            self.assertIn("countries", snapshot.tables)
            self.assertIn("regions", snapshot.tables)
            self.assertFalse(snapshot.get_table("countries").is_empty())

            shutdown_event.set()
            process.terminate()
            process.join(timeout=10.0)
            self.assertFalse(process.is_alive())
        finally:
            if process.is_alive():
                shutdown_event.set()
                process.terminate()
                process.join(timeout=5.0)
            if process.is_alive():
                process.kill() if hasattr(process, "kill") else process.terminate()
                process.join(timeout=5.0)


if __name__ == "__main__":
    unittest.main()