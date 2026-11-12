import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from src.core.telemetry import PerformanceAggregator, PerformanceCollector, TelemetrySnapshot


def test_aggregate_and_dto_roundtrip():
    metric = PerformanceAggregator.duration([1, 2, 3, 4])
    assert (metric.count, metric.mean, metric.p50, metric.p95, metric.maximum, metric.total) == (4, 2.5, 2.5, 4, 4, 10)
    collector = PerformanceCollector(True)
    collector.observe("duration", 2)
    collector.increment("events", 3)
    collector.gauge("memory", 100, "bytes")
    snapshot = collector.snapshot()
    assert TelemetrySnapshot.from_dict(json.loads(json.dumps(snapshot.to_dict()))) == snapshot


def test_measure_exception_disabled_and_reset():
    collector = PerformanceCollector(True)
    with pytest.raises(RuntimeError):
        with collector.measure("failure"):
            raise RuntimeError("original")
    assert collector.snapshot().durations["failure"].maximum > 0
    collector.set_enabled(False)
    with collector.measure("disabled"):
        pass
    collector.increment("disabled")
    assert "disabled" not in collector.snapshot().durations
    collector.reset()
    assert not collector.snapshot().durations


def test_limits_and_independent_collectors():
    a = PerformanceCollector(True, max_metrics=1, max_samples=2)
    b = PerformanceCollector(True)
    for n in range(5):
        a.observe("x", n)
    a.observe("other", 100)
    assert a.snapshot().durations["x"].count == 2
    assert "other" not in a.snapshot().durations
    assert not b.snapshot().durations


def test_concurrent_counters():
    collector = PerformanceCollector(True)
    def work():
        for _ in range(1000):
            collector.increment("count")
    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(lambda _: work(), range(4)))
    assert collector.snapshot().counters["count"].value == 4000


def test_engine_system_metrics_and_rollback():
    from src.engine.simulator import Engine
    from src.shared.state import GameState
    from src.shared.system_interfaces import ISystem, SystemAccess

    class ArbitrarySystem(ISystem):
        access = SystemAccess()
        runtime_state_contract = {}
        id = "mod.arbitrary"
        dependencies = []
        def update(self, state, dt):
            state.globals["temporary"] = True
            raise RuntimeError("expected")

    collector = PerformanceCollector(True)
    engine = Engine(telemetry=collector)
    engine.register_systems([ArbitrarySystem()])
    state = GameState()
    result = engine.step(state, [], 0.1)
    assert not result.success
    assert "temporary" not in state.globals
    snapshot = collector.snapshot()
    assert snapshot.durations["simulation.system.mod.arbitrary.update_ms"].count == 1
    assert snapshot.durations["simulation.rollback_ms"].count == 1
    assert snapshot.counters["simulation.failed_ticks"].value == 1


def test_session_100_ticks_preserves_state(tmp_path):
    from src.engine.simulator import Engine
    from src.server.session import GameSession
    from src.shared.config import GameConfig
    from src.shared.state import GameState
    from src.shared.system_interfaces import ISystem, SystemAccess
    from src.simulation.fingerprint import state_fingerprint

    class ArbitrarySystem(ISystem):
        access = SystemAccess()
        runtime_state_contract = {}
        id = "mod.arbitrary"
        dependencies = []
        def update(self, state, dt):
            state.globals["updates"] = state.globals.get("updates", 0) + 1

    sessions = []
    for enabled in (False, True):
        collector = PerformanceCollector(enabled)
        engine = Engine(telemetry=collector)
        engine.register_systems([ArbitrarySystem()])
        session = GameSession(GameConfig(tmp_path), None, None, engine, None, GameState())
        for _ in range(100):
            session.tick(0.1)
        sessions.append((session, collector))
    assert state_fingerprint(sessions[0][0].state) == state_fingerprint(sessions[1][0].state)
    assert sessions[1][1].snapshot().durations["simulation.system.mod.arbitrary.update_ms"].count == 100
    assert sessions[1][1].snapshot().counters["simulation.ticks"].value == 100


def test_publisher_full_queue_and_service_export(tmp_path, monkeypatch):
    from queue import Queue
    from src.client.services.telemetry_service import TelemetryService
    from src.server.telemetry_publisher import TelemetryPublisher
    from src.shared.telemetry_types import TelemetryControl

    monkeypatch.setenv("OPENPOWER_TELEMETRY", "1")
    actions, packets = Queue(), Queue(maxsize=1)
    collector = PerformanceCollector(True)
    collector.observe("simulation.tick.total_ms", 4.0)
    publisher = TelemetryPublisher(collector, packets)
    publisher._last = 0
    publisher.publish_if_due()
    publisher._last = 0
    publisher.publish_if_due()  # A full queue must not block the simulation.
    service = TelemetryService(actions, packets, tmp_path)
    service.refresh(force=True)
    assert service.server.durations["simulation.tick.total_ms"].p95 == 4.0
    service.set_enabled(False)
    assert actions.get_nowait() == TelemetryControl("disable")
    service.export()
    data = json.loads(service.export_future.result(timeout=5).read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert data["processes"]["client"]["metrics"] == service.client.to_dict()
    service.close()


def test_optional_memory_dependency(monkeypatch):
    import sys
    from src.core.telemetry.memory import sample_memory
    collector = PerformanceCollector(True)
    monkeypatch.setitem(sys.modules, "psutil", None)
    sample_memory(collector)
    assert not collector.snapshot().gauges


def test_server_process_publishes_and_survives_full_telemetry_queue(monkeypatch):
    import multiprocessing as mp
    import queue
    import time
    from pathlib import Path
    from src.server.server_process import run_server_process
    from src.shared.telemetry_types import TelemetryControl

    monkeypatch.setenv("OPENPOWER_TELEMETRY", "1")
    ctx = mp.get_context("spawn")
    actions, states, progress = ctx.Queue(), ctx.Queue(maxsize=2), ctx.Queue()
    packets = ctx.Queue(maxsize=1)
    process = ctx.Process(target=run_server_process,
                          args=(str(Path.cwd()), actions, states, progress),
                          kwargs={"telemetry_queue": packets})
    process.start()
    try:
        deadline = time.monotonic() + 60
        while True:
            status, _, message = progress.get(timeout=max(0.1, deadline-time.monotonic()))
            if status == "ERROR":
                pytest.fail(message)
            if status == "READY":
                break
        first = packets.get(timeout=30)
        assert first["durations"]["simulation.tick.total_ms"]["count"] > 0
        # Leave telemetry unconsumed until its bounded queue fills.
        time.sleep(2.5)
        assert process.is_alive()
        actions.put(TelemetryControl("disable"))
        actions.put("SHUTDOWN")
        process.join(timeout=30)
        assert not process.is_alive()
        assert process.exitcode == 0
    finally:
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)
        for q in (actions, states, progress, packets):
            q.close()
            q.cancel_join_thread()


def test_performance_panel_opens_and_closes_in_real_imgui(tmp_path, caplog):
    from queue import Queue
    from imgui_bundle import imgui
    from src.client.services.telemetry_service import TelemetryService
    from src.client.ui.components.hud.panel_manager import PanelManager
    from src.client.ui.panels.service.performance_panel import PerformancePanel

    service = TelemetryService(Queue(), Queue(), tmp_path)
    manager = PanelManager()
    manager.register("PERFORMANCE", PerformancePanel(service))
    context = imgui.create_context()
    try:
        io = imgui.get_io()
        io.display_size = (1024, 768)
        io.delta_time = 1 / 60
        io.backend_flags |= imgui.BackendFlags_.renderer_has_textures
        io.set_ini_filename(str(tmp_path / "imgui.ini"))
        manager.set_visible("PERFORMANCE", True)
        imgui.new_frame()
        manager.render_all(None, None)
        imgui.end_frame()
        assert manager.is_visible("PERFORMANCE")
        assert not [record for record in caplog.records if record.levelname == "ERROR"]
        manager.set_visible("PERFORMANCE", False)
        assert not manager.is_visible("PERFORMANCE")
    finally:
        imgui.destroy_context(context)
        service.close()


def test_telemetry_failure_does_not_hide_original_exception(monkeypatch, caplog):
    collector = PerformanceCollector(True)
    def fail(*args, **kwargs):
        raise RuntimeError("telemetry failure")
    monkeypatch.setattr(collector, "observe", fail)
    with pytest.raises(ValueError, match="original"):
        with collector.measure("failure"):
            raise ValueError("original")
    assert "Performance telemetry failed" in caplog.text
