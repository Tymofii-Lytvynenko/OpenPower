import multiprocessing as mp
import queue
import time
import unittest
from pathlib import Path

from src.client.client_session import ClientSessionProxy
from src.engine.simulator import Engine
from src.server.launcher import spawn_local_server
from src.server.server_process import run_server_process
from src.server.session import GameSession
from src.shared.actions import ActionSetPaused
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

    def test_launcher_client_proxy_executes_command_over_delta_ipc(self):
        config = GameConfig(Path(__file__).resolve().parent.parent)
        bundle = spawn_local_server(config)
        proxy = ClientSessionProxy(
            map_data=bundle.map_data,
            action_queue=bundle.action_queue,
            state_queue=bundle.state_queue,
            progress_queue=bundle.progress_queue,
            snapshot_ack_queue=bundle.snapshot_ack_queue,
            process=bundle.process,
        )

        try:
            deadline = time.monotonic() + 60.0
            ready = False
            while time.monotonic() < deadline and not ready:
                try:
                    status, _, message = proxy.progress_queue.get(timeout=0.5)
                except queue.Empty:
                    continue
                if status == "ERROR":
                    self.fail(message)
                ready = status == "READY"
            self.assertTrue(ready)

            while time.monotonic() < deadline and proxy.state is None:
                proxy.tick(0.0)
                time.sleep(0.05)
            self.assertIsNotNone(proxy.state)

            command_id = proxy.receive_action(ActionSetPaused("launcher-smoke", True))
            command_result = None
            while time.monotonic() < deadline and command_result is None:
                proxy.tick(0.0)
                if proxy.state is not None:
                    command_result = next(
                        (
                            result
                            for result in proxy.state.journal.command_results
                            if result.get("command_id") == command_id
                        ),
                        None,
                    )
                time.sleep(0.05)

            self.assertIsNotNone(command_result)
            self.assertEqual(command_result["status"], "executed")
            self.assertTrue(proxy.state.time.is_paused)
        finally:
            proxy.shutdown()
            if bundle.process.is_alive():
                bundle.process.terminate()
                bundle.process.join(timeout=5.0)

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