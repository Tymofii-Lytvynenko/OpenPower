from __future__ import annotations

import sys
import os
import multiprocessing as mp
from pathlib import Path
from typing import Any, Sequence

# 1. Setup Python Path
ROOT_DIR = Path(__file__).parent.resolve()
sys.path.append(str(ROOT_DIR))


def profiling_enabled(environment: dict[str, str] | None = None) -> bool:
    values = os.environ if environment is None else environment
    return str(values.get("OPENPOWER_PROFILE", "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def configure_multiprocessing() -> None:
    """Prepare the process model required by frozen Windows application builds."""
    mp.freeze_support()
    mp.set_start_method("spawn", force=True)


def export_profile_html(profiler: Any, output_path: Path) -> Path | None:
    if profiler is None or not profiler.last_session:
        return None
    output_path.write_text(profiler.output_html(), encoding="utf-8")
    return output_path


def create_local_session(config, *, save_name=None, player_tag=None):
    """Compose server process and client proxy at the application boundary."""
    from src.client.client_session import ClientSessionProxy
    from src.server.launcher import spawn_local_server

    bundle = spawn_local_server(config, save_name=save_name, player_tag=player_tag)
    try:
        return ClientSessionProxy(
            map_data=bundle.map_data,
            action_queue=bundle.action_queue,
            state_queue=bundle.state_queue,
            progress_queue=bundle.progress_queue,
            snapshot_ack_queue=bundle.snapshot_ack_queue,
            process=bundle.process,
        )
    except BaseException:
        process = bundle.process
        if process.is_alive():
            process.terminate()
        process.join(timeout=5.0)
        for channel in (
            bundle.action_queue,
            bundle.state_queue,
            bundle.progress_queue,
            bundle.snapshot_ack_queue,
        ):
            channel.close()
        raise


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments:
        from src.cli import main as cli_main
        return cli_main(arguments)

    import arcade
    from src.shared.config import GameConfig
    from src.client.window import MainWindow

    profiler = None
    if profiling_enabled():
        try:
            from pyinstrument import Profiler
        except ImportError:
            pass
        else:
            profiler = Profiler()
            profiler.start()

    print("--- OpenPower Engine Initializing ---")
    print(f"Process ID (PID): {os.getpid()}")

    # 3. Initialize Configuration
    config = GameConfig(ROOT_DIR)
    print(f"[Main] Project Root: {config.project_root}")
    print(f"[Main] Active Mods: {config.active_mods}")

    # 4. Start the Window
    # The Window now owns the NavigationService
    window = MainWindow(config, session_factory=create_local_session)

    # 5. Kickoff
    # window.setup() uses NavigationService to show the LoadingView
    window.setup()

    print("--- Window Created. Handing off to Application Loop. ---")
    try:
        arcade.run()
    finally:
        if profiler is not None:
            profiler.stop()
            output_path = export_profile_html(profiler, ROOT_DIR / "profile_results.html")
            if output_path is not None:
                print(f"Saved {output_path}")
    return 0


if __name__ == "__main__":
    configure_multiprocessing()
    raise SystemExit(main())
