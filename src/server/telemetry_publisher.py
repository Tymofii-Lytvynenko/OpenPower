"""Non-blocking server telemetry publication."""
from queue import Full
from time import monotonic
from src.core.telemetry.memory import sample_memory


class TelemetryPublisher:
    def __init__(self, collector, queue):
        self.collector = collector
        self.queue = queue
        self._last = monotonic()

    def publish_if_due(self):
        if not self.collector.enabled or self.queue is None:
            return
        now = monotonic()
        if now - self._last < 1.0:
            return
        self._last = now
        try:
            sample_memory(self.collector)
            self.queue.put_nowait(self.collector.snapshot().to_dict())
        except Full:
            pass
        except Exception:
            self.collector._log_failure()
