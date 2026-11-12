"""Client-side telemetry aggregation and asynchronous report export."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
import platform
from pathlib import Path
from queue import Empty, Full
from time import monotonic

from src.core.telemetry import PerformanceCollector, TelemetrySnapshot
from src.core.telemetry.memory import sample_memory
from src.shared.telemetry_types import TelemetryControl


class TelemetryService:
    def __init__(self, action_queue, telemetry_queue, output_dir: Path, process=None):
        enabled = os.getenv("OPENPOWER_TELEMETRY", "").lower() in {"1", "true", "yes", "on"}
        self.collector = PerformanceCollector(enabled)
        self.action_queue = action_queue
        self.telemetry_queue = telemetry_queue
        self.process = process
        self.output_dir = Path(output_dir)
        self.started_at = datetime.now(timezone.utc)
        self.server = None
        self.client = self.collector.snapshot()
        self._last_refresh = 0.0
        self._server_received = 0.0
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="telemetry-export")
        self.export_future = None

    def set_enabled(self, enabled: bool):
        self.collector.set_enabled(enabled)
        self.server = None
        self._drain_server()
        self._send(TelemetryControl("enable" if enabled else "disable"))

    def reset(self):
        self.collector.reset()
        self.client = self.collector.snapshot()
        self.server = None
        self._drain_server()
        self._send(TelemetryControl("reset"))

    def _drain_server(self):
        if self.telemetry_queue is None:
            return
        while True:
            try:
                self.telemetry_queue.get_nowait()
            except Empty:
                return

    def _send(self, command):
        try:
            self.action_queue.put_nowait(command)
        except (Full, OSError, ValueError):
            self.collector._log_failure()

    @property
    def server_status(self):
        if not self.collector.enabled:
            return "Disabled"
        if self.process is not None and not self.process.is_alive():
            return "Unavailable"
        return "Available" if self.server is not None and monotonic() - self._server_received < 5 else "Unavailable"

    def refresh(self, force=False):
        now = monotonic()
        if not force and now - self._last_refresh < 1:
            return
        self._last_refresh = now
        if self.collector.enabled:
            sample_memory(self.collector)
            self.client = self.collector.snapshot()
        if self.telemetry_queue is not None:
            while True:
                try:
                    packet = self.telemetry_queue.get_nowait()
                except Empty:
                    break
                if self.collector.enabled:
                    try:
                        self.server = TelemetrySnapshot.from_dict(packet)
                        self._server_received = now
                    except (TypeError, ValueError, KeyError):
                        self.collector._log_failure()

    def export(self):
        if self.export_future is not None and not self.export_future.done():
            return
        self.refresh(force=True)
        report = {
            "schema_version": 1, "application": "OpenPower",
            "started_at": self.started_at.isoformat().replace("+00:00", "Z"),
            "telemetry_mode": "enabled" if self.collector.enabled else "disabled",
            "environment": {"python_version": platform.python_version(), "platform": platform.platform()},
            "processes": {"client": {"metrics": self.client.to_dict()},
                          "server": {"status": self.server_status,
                                     "metrics": self.server.to_dict() if self.server else None}},
        }
        def write():
            self.output_dir.mkdir(parents=True, exist_ok=True)
            path = self.output_dir / ("performance-" + datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%S-%f") + ".json")
            path.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
            return path
        self.export_future = self._executor.submit(write)

    def close(self):
        self._executor.shutdown(wait=False)
