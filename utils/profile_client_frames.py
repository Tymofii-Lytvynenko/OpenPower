"""Measure real gameplay frames with a local server, without manual navigation."""
from __future__ import annotations

import cProfile
from pathlib import Path
import pstats
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    import arcade
    from main import configure_multiprocessing, create_local_session
    from src.client.window import MainWindow
    from src.shared.config import GameConfig

    configure_multiprocessing()
    config = GameConfig(ROOT)
    window = MainWindow(config, create_local_session)
    window.set_visible(False)
    session = create_local_session(config, player_tag="ALB")
    window.session = session
    try:
        deadline = time.monotonic() + 90
        while session.state is None and time.monotonic() < deadline:
            session.tick(0)
            time.sleep(0.02)
        if session.state is None:
            raise RuntimeError("Server did not supply initial state")
        window.nav.show_main_menu(session, config)
        window.nav.show_game_view(session, config, "ALB")
        view = window.current_view
        panel_id = sys.argv[2] if len(sys.argv) > 2 else None
        if panel_id:
            view.layout.panel_manager.set_visible(panel_id, True)
            regions = session.state.tables.get("regions")
            if regions is not None and "owner" in regions.columns:
                owned = regions.filter(__import__("polars").col("owner") == "ALB")
                if not owned.is_empty():
                    view.selected_region_id = int(owned["id"][0])
        profile = cProfile.Profile()
        durations = []
        frame_count = int(sys.argv[1]) if len(sys.argv) > 1 else 360
        for index in range(frame_count):
            started = time.perf_counter()
            window.dispatch_events()
            session.tick(1 / 60)
            view.on_update(1 / 60)
            if index == 60:
                profile.enable()
            view.on_draw()
            window.flip()
            durations.append(time.perf_counter() - started)
        profile.disable()
        print(f"panel={panel_id or 'none'} region={view.selected_region_id}")
        for offset in range(0, len(durations) - 59, 300):
            sample = sorted(durations[offset:offset + 60])
            print(f"frames {offset}-{offset+59}: median={sample[30]*1000:.2f}ms p95={sample[57]*1000:.2f}ms")
        pstats.Stats(profile).strip_dirs().sort_stats("cumulative").print_stats(35)
    finally:
        window.close()


if __name__ == "__main__":
    main()
