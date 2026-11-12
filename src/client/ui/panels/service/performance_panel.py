"""In-game view of the process-local performance snapshots."""
from src.client.ui.core.containers import WindowManager
from src.client.ui.core.instrumented_imgui import imgui


class PerformancePanel:
    def __init__(self, service):
        self.service = service
        self.sort_p95 = False

    @staticmethod
    def _metric(snapshot, name):
        if snapshot is None:
            return "N/A"
        duration = snapshot.durations.get(name)
        if duration is not None:
            return f"p50 {duration.p50:.2f} / p95 {duration.p95:.2f} ms"
        value = snapshot.gauges.get(name) or snapshot.counters.get(name)
        return f"{value.value:.2f} {value.unit}" if value else "N/A"

    def render(self, state, context):
        service = self.service
        service.refresh()
        with WindowManager.window("Performance Monitor", x=100, y=100, w=650, h=600,
                                  test_id="performance.panel") as opened:
            if not opened:
                return False
            if imgui.button("Disable collection" if service.collector.enabled else "Enable collection"):
                service.set_enabled(not service.collector.enabled)
            imgui.same_line()
            if imgui.button("Reset statistics"):
                service.reset()
            imgui.same_line()
            if imgui.button("Export JSON"):
                service.export()
            if service.export_future and service.export_future.done():
                try:
                    imgui.text(f"Exported: {service.export_future.result()}")
                except Exception as exc:
                    imgui.text_wrapped(f"Export failed: {exc}")
            client, server = service.client, service.server if service.server_status == "Available" else None
            imgui.separator_text("Overview")
            imgui.text(f"Server: {service.server_status}")
            imgui.text(f"FPS: {self._metric(client, 'render.fps')}")
            imgui.text(f"Frame interval: {self._metric(client, 'render.frame_interval_ms')}")
            imgui.text(f"Simulation tick: {self._metric(server, 'simulation.tick.total_ms')}")
            imgui.text(f"Client RAM: {self._metric(client, 'process.rss_bytes')}")
            imgui.text(f"Server RAM: {self._metric(server, 'process.rss_bytes')}")
            imgui.separator_text("Simulation (inclusive times)")
            if imgui.button("Sort by p95" if not self.sort_p95 else "Sort by total"):
                self.sort_p95 = not self.sort_p95
            if server:
                rows = [(name, metric) for name, metric in server.durations.items()
                        if name.startswith("simulation.system.") and name.endswith(".update_ms")]
                rows.sort(key=lambda row: row[1].p95 if self.sort_p95 else row[1].total, reverse=True)
                imgui.text("System | Avg ms | P95 ms | Max ms | Total ms")
                for name, metric in rows:
                    imgui.text(f"{name[18:-10]} | {metric.mean:.2f} | {metric.p95:.2f} | {metric.maximum:.2f} | {metric.total:.2f}")
            imgui.separator_text("Rendering (CPU submission)")
            for name in ("frame_cpu", "map", "units", "effects", "ui", "imgui"):
                imgui.text(f"{name}: {self._metric(client, 'render.' + name + '_ms')}")
            imgui.separator_text("IPC")
            for label, snap, name in (("Encode", server, "ipc.snapshot.encode_ms"),
                                      ("Decode", client, "ipc.snapshot.decode_ms"),
                                      ("Payload (serialized tables)", server, "ipc.snapshot.payload_bytes"),
                                      ("Produced", server, "ipc.snapshots.produced"),
                                      ("Received", client, "ipc.snapshots.received"),
                                      ("Dropped", server, "ipc.snapshots.dropped")):
                imgui.text(f"{label}: {self._metric(snap, name)}")
        return True
