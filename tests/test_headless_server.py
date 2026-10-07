import multiprocessing as mp
import queue
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from src.client.client_session import ClientSessionProxy
from src.engine.simulator import Engine
from src.server.launcher import spawn_local_server
from src.server.server_process import run_server_process
from src.server.session import GameSession
from src.shared.actions import ActionSetPaused
from src.shared.config import GameConfig
from src.shared.state import GameState
from src.server import launcher


class TestHeadlessServer(unittest.TestCase):
    def test_missing_mod_dependency_fails_before_world_data_loading(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            module_dir = project_root / "modules" / "broken"
            module_dir.mkdir(parents=True)
            (module_dir / "mod.toml").write_text(
                '\nid = "broken"\nname = "Broken"\nversion = "0.1.0"\ndependencies = ["missing"]\n',
                encoding="utf-8",
            )
            (project_root / "mods.json").write_text(
                '{"active_mods": ["broken"]}\n',
                encoding="utf-8",
            )
            config = GameConfig(project_root)

            with patch("src.server.session.DataLoader") as data_loader:
                with self.assertRaisesRegex(RuntimeError, "Missing dependency: 'missing'"):
                    GameSession.create_headless(config)

            data_loader.assert_not_called()

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
            ready_deadline = time.monotonic() + 60.0
            ready = False
            while time.monotonic() < ready_deadline and not ready:
                try:
                    status, _, message = proxy.progress_queue.get(timeout=0.5)
                except queue.Empty:
                    continue
                if status == "ERROR":
                    self.fail(message)
                ready = status == "READY"
            self.assertTrue(ready)

            # Slow world bootstrap must not consume the snapshot and command assertion windows.
            state_deadline = time.monotonic() + 30.0
            while time.monotonic() < state_deadline and proxy.state is None:
                proxy.tick(0.0)
                time.sleep(0.05)
            self.assertIsNotNone(proxy.state)

            command_id = proxy.receive_action(ActionSetPaused("launcher-smoke", True))
            command_result = None
            command_deadline = time.monotonic() + 30.0
            while time.monotonic() < command_deadline and command_result is None:
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

            self.assertIsNotNone(
                command_result,
                msg=(
                    f"Server process alive={bundle.process.is_alive()}, "
                    f"exitcode={bundle.process.exitcode}, "
                    f"tick={proxy.state.globals.get('tick') if proxy.state else None}, "
                    f"results={proxy.state.journal.command_results[-3:] if proxy.state else None}"
                ),
            )
            self.assertEqual(command_result["status"], "executed")
            self.assertTrue(proxy.state.time.is_paused)
        finally:
            proxy.shutdown()
            if bundle.process.is_alive():
                bundle.process.terminate()
                bundle.process.join(timeout=5.0)
            self.assertFalse(bundle.process.is_alive())

    def test_launcher_reaps_server_when_client_map_loading_fails(self):
        process = Mock()
        process.is_alive.return_value = True
        config = Mock()
        config.get_data_dirs.return_value = []
        config.get_asset_path.return_value = Path("missing-map.png")

        with (
            patch.object(launcher.mp, "Queue", return_value=Mock()),
            patch.object(launcher.mp, "Process", return_value=process),
            patch.object(
                launcher,
                "RegionMapData",
                side_effect=MemoryError("map allocation failed"),
            ),
        ):
            with self.assertRaisesRegex(MemoryError, "map allocation failed"):
                launcher.spawn_local_server(config)

        process.start.assert_called_once_with()
        process.terminate.assert_called_once_with()
        process.join.assert_called_once_with(timeout=5.0)

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
