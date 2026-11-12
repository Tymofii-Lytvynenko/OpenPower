"""Best-effort process RSS, including native allocations."""

def sample_memory(collector):
    if not collector.enabled:
        return
    try:
        import psutil
    except ImportError:
        return
    try:
        rss = psutil.Process().memory_info().rss
        collector._rss_peak = max(getattr(collector, "_rss_peak", 0), rss)
        collector.gauge("process.rss_bytes", rss, "bytes")
        collector.gauge("process.peak_rss_bytes", collector._rss_peak, "bytes")
    except Exception:
        collector._log_failure()
