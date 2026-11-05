"""Plot observability using the same telemetry model as ImGui widgets."""
from __future__ import annotations

import inspect
from functools import wraps

from imgui_bundle import implot as native_implot

from src.client.ui.core.instrumented_imgui import _source, _site_id
from src.client.ui.core.testability import Rect, active_telemetry


class ImPlotFacade:
    def __init__(self) -> None:
        self._plot_stack = []

    def __getattr__(self, name):
        target = getattr(native_implot, name)
        if not callable(target) or inspect.isclass(target):
            return target

        @wraps(target)
        def call(*args, **kwargs):
            recorder = active_telemetry()
            if name == "end_plot":
                pending = self._plot_stack.pop() if self._plot_stack else None
                geometry = None
                if pending is not None:
                    plot_recorder, _, _, _ = pending
                    position = native_implot.get_plot_pos()
                    size = native_implot.get_plot_size()
                    geometry = (
                        plot_recorder,
                        Rect(position.x, position.y, size.x, size.y),
                    )
                result = getattr(native_implot, name)(*args, **kwargs)
                if geometry is not None:
                    plot_recorder, rect = geometry
                    plot_recorder.pop_region()
                    _, plot_id, label, source = pending
                    plot_recorder.record_region(
                        plot_id, label, True, rect, kind="plot", source=source
                    )
                return result

            result = getattr(native_implot, name)(*args, **kwargs)
            if recorder is None:
                return result
            if name == "begin_plot" and result:
                source = _source(inspect.currentframe().f_back)
                plot_id = recorder.unique_id(f"plot/{recorder.parent_id}/{_site_id(source, name)}")
                recorder.push_region(plot_id)
                # Geometry queries lock ImPlot setup, so defer them until end_plot.
                self._plot_stack.append((recorder, plot_id, str(args[0]), source))
            elif name.startswith("plot_"):
                source = _source(inspect.currentframe().f_back)
                position, size = native_implot.get_plot_pos(), native_implot.get_plot_size()
                sample_count = next((len(value) for value in args[1:] if hasattr(value, "__len__")), None)
                recorder.record_widget(
                    recorder.unique_id(f"plot-item/{recorder.parent_id}/{_site_id(source, name)}"),
                    str(args[0]) if args else name, name, True, False,
                    Rect(position.x, position.y, size.x, size.y), source=source,
                    interactive=False, value={"sample_count": sample_count},
                )
            return result
        return call


implot = ImPlotFacade()
