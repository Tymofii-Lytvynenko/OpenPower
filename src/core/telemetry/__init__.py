"""Bounded, process-local performance measurements.

Durations are inclusive: nested measurements must not be added together.
Snapshots summarize the retained rolling window, not lifetime totals.
"""
from __future__ import annotations

from collections import deque
from contextlib import AbstractContextManager, nullcontext
from dataclasses import asdict, dataclass
import logging
from math import ceil, isfinite
from functools import wraps
from threading import Lock
from time import perf_counter_ns
from typing import Literal

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class DurationMetric:
    unit: Literal["ms"]
    count: int
    mean: float
    p50: float
    p95: float
    maximum: float
    total: float


@dataclass(frozen=True)
class ValueMetric:
    unit: str
    value: float


@dataclass(frozen=True)
class TelemetrySnapshot:
    durations: dict[str, DurationMetric]
    counters: dict[str, ValueMetric]
    gauges: dict[str, ValueMetric]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> TelemetrySnapshot:
        return cls(
            {k: DurationMetric(**v) for k, v in data["durations"].items()},
            {k: ValueMetric(**v) for k, v in data["counters"].items()},
            {k: ValueMetric(**v) for k, v in data["gauges"].items()},
        )


class PerformanceAggregator:
    @staticmethod
    def duration(values: list[float]) -> DurationMetric:
        ordered = sorted(values)
        count = len(ordered)
        if not count:
            raise ValueError("Cannot aggregate an empty sample")
        middle = count // 2
        median = ordered[middle] if count % 2 else (ordered[middle - 1] + ordered[middle]) / 2
        return DurationMetric("ms", count, sum(ordered) / count, median,
                              ordered[ceil(count * 0.95) - 1], ordered[-1], sum(ordered))


class _Measurement(AbstractContextManager):
    def __init__(self, collector: PerformanceCollector, name: str):
        self.collector = collector
        self.name = name
        self.started = 0

    def __enter__(self):
        self.started = perf_counter_ns()
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            self.collector.observe(self.name, (perf_counter_ns() - self.started) / 1_000_000)
        except Exception:
            self.collector._log_failure()
        return False


def _safe_record(method):
    @wraps(method)
    def guarded(self, *args, **kwargs):
        try:
            return method(self, *args, **kwargs)
        except Exception:
            self._log_failure()
    return guarded


class PerformanceCollector:
    def __init__(self, enabled: bool = False, *, max_metrics: int = 512,
                 max_samples: int = 4096, window_seconds: float = 60.0):
        if max_metrics < 1 or max_samples < 1 or window_seconds <= 0:
            raise ValueError("Telemetry limits must be positive")
        self.enabled = enabled
        self._max_metrics = max_metrics
        self._max_samples = max_samples
        self._window_ns = int(window_seconds * 1_000_000_000)
        self._durations: dict[str, deque[tuple[int, float]]] = {}
        self._counters: dict[str, ValueMetric] = {}
        self._gauges: dict[str, ValueMetric] = {}
        self._lock = Lock()
        self._last_failure_log_ns = 0

    def _log_failure(self) -> None:
        now = perf_counter_ns()
        if now - self._last_failure_log_ns >= 60_000_000_000:
            self._last_failure_log_ns = now
            LOGGER.exception("Performance telemetry failed; measurements may be incomplete")

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled

    def measure(self, name: str) -> AbstractContextManager:
        return _Measurement(self, name) if self.enabled else nullcontext()

    def _has_room(self, name: str) -> bool:
        return len(name) <= 256 and (name in self._durations or name in self._counters or name in self._gauges
                or len(self._durations) + len(self._counters) + len(self._gauges) < self._max_metrics)

    @_safe_record
    def observe(self, name: str, duration_ms: float) -> None:
        if not self.enabled or not isfinite(duration_ms) or duration_ms < 0:
            return
        now = perf_counter_ns()
        with self._lock:
            if name not in self._durations:
                if not self._has_room(name):
                    return
                self._durations[name] = deque(maxlen=self._max_samples)
            samples = self._durations[name]
            samples.append((now, duration_ms))
            while samples and samples[0][0] < now - self._window_ns:
                samples.popleft()

    @_safe_record
    def increment(self, name: str, amount: int = 1) -> None:
        if not self.enabled:
            return
        with self._lock:
            if name not in self._counters and not self._has_room(name):
                return
            previous = self._counters.get(name, ValueMetric("count", 0))
            self._counters[name] = ValueMetric("count", previous.value + amount)

    @_safe_record
    def gauge(self, name: str, value: float, unit: str = "count") -> None:
        if not self.enabled or not isfinite(value):
            return
        with self._lock:
            if name not in self._gauges and not self._has_room(name):
                return
            self._gauges[name] = ValueMetric(unit, value)

    def reset(self) -> None:
        with self._lock:
            self._durations.clear()
            self._counters.clear()
            self._gauges.clear()
            self._rss_peak = 0

    def snapshot(self) -> TelemetrySnapshot:
        cutoff = perf_counter_ns() - self._window_ns
        with self._lock:
            samples = {name: [v for t, v in values if t >= cutoff]
                       for name, values in self._durations.items()}
            counters, gauges = self._counters.copy(), self._gauges.copy()
        return TelemetrySnapshot(
            {name: PerformanceAggregator.duration(values) for name, values in samples.items() if values},
            counters, gauges,
        )
