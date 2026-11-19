"""Measure real gameplay frames and optional runtime telemetry."""
from __future__ import annotations

import argparse
import cProfile
import math
import pstats
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("frames", nargs="?", type=int, default=360)
    parser.add_argument("panel", nargs="?", help="Optional game panel to display during the run.")
    parser.add_argument("--profile", action="store_true", help="Run a separate CPU profile after timing.")
    parser.add_argument("--telemetry", action="store_true", help="Collect client/server performance and RSS telemetry.")
    args = parser.parse_args()
    if args.frames < 1:
        parser.error("frames must be a positive integer")
    return args


def _draw_frame(window, session, view):
    window.dispatch_events()
    session.tick(1 / 60)
    view.on_update(1 / 60)
    view.on_draw()
    window.flip()


def _report_frame_times(durations: list[float]) -> None:
    warmup_frames = min(60, max(0, len(durations) - 1))
    measured = durations[warmup_frames:]
    print(f"warmup_frames={warmup_frames} measured_frames={len(measured)}")
    for offset in range(0, len(measured), 60):
        sample = sorted(measured[offset : offset + 60])
        if not sample:
            continue
        median = sample[len(sample) // 2] * 1000
        p95 = sample[max(0, math.ceil(len(sample) * 0.95) - 1)] * 1000
        start_frame = warmup_frames + offset
        end_frame = start_frame + len(sample) - 1
        print(
            f"frames {start_frame}-{end_frame}: median={median:.2f}ms "
            f"p95={p95:.2f}ms max={sample[-1] * 1000:.2f}ms"
        )


def _report_telemetry(session) -> None:
    telemetry = session.telemetry
    telemetry.refresh(force=True)
    client, server = telemetry.client, telemetry.server
    print(f"telemetry.server_status={telemetry.server_status}")
    duration_names = (
        "render.frame_cpu_ms",
        "render.map_ms",
        "ipc.snapshot.apply_ms",
        "ipc.snapshot.decode_ms",
        "ipc.snapshot.prepare_ms",
        "simulation.engine_step_ms",
        "ipc.snapshot.encode_ms",
    )
    for label, snapshot in (("client", client), ("server", server)):
        if snapshot is None:
            continue
        for name in duration_names:
            metric = snapshot.durations.get(name)
            if metric is not None:
                print(
                    f"telemetry.{label}.{name}: n={metric.count} "
                    f"p50={metric.p50:.2f}ms p95={metric.p95:.2f}ms "
                    f"max={metric.maximum:.2f}ms"
                )
        if label == "server":
            system_metrics = sorted(
                (
                    (name, metric)
                    for name, metric in snapshot.durations.items()
                    if name.startswith("simulation.system.") and name.endswith(".update_ms")
                ),
                key=lambda item: item[1].mean,
                reverse=True,
            )
            for name, metric in system_metrics[:10]:
                print(
                    f"telemetry.server.{name}: n={metric.count} "
                    f"mean={metric.mean:.2f}ms p95={metric.p95:.2f}ms "
                    f"max={metric.maximum:.2f}ms"
                )
        for name in ("process.rss_bytes", "process.peak_rss_bytes"):
            metric = snapshot.gauges.get(name)
            if metric is not None:
                print(f"telemetry.{label}.{name}={metric.value / (1024 * 1024):.1f}MiB")
        for name in ("ipc.snapshots.received", "ipc.snapshots.produced", "ipc.snapshots.dropped"):
            metric = snapshot.counters.get(name)
            if metric is not None:
                print(f"telemetry.{label}.{name}={metric.value:.0f}")


def main():
    args = _parse_args()
    import polars as pl

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
        if args.telemetry:
            session.telemetry.reset()
            session.telemetry.set_enabled(True)
        window.nav.show_main_menu(session, config)
        window.nav.show_game_view(session, config, "ALB")
        view = window.current_view
        if args.panel:
            view.layout.panel_manager.set_visible(args.panel, True)
            regions = session.state.tables.get("regions")
            if regions is not None and "owner" in regions.columns:
                owned = regions.filter(pl.col("owner") == "ALB")
                if not owned.is_empty():
                    view.selected_region_id = int(owned["id"][0])

        durations = []
        for _ in range(args.frames):
            started = time.perf_counter()
            _draw_frame(window, session, view)
            durations.append(time.perf_counter() - started)

        print(f"panel={args.panel or 'none'} region={view.selected_region_id}")
        _report_frame_times(durations)
        if args.telemetry:
            _report_telemetry(session)

        if args.profile:
            profile = cProfile.Profile()
            profile.enable()
            for _ in range(args.frames):
                _draw_frame(window, session, view)
            profile.disable()
            print(f"CPU profile: {args.frames} additional frames")
            pstats.Stats(profile).strip_dirs().sort_stats("cumulative").print_stats(35)
    finally:
        window.close()


if __name__ == "__main__":
    main()
