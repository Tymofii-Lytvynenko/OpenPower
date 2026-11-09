from types import SimpleNamespace

from src.client.ui.core import instrumented_implot


class _TelemetryRecorder:
    def __init__(self):
        self.parent_id = "panel.root"
        self.unique_ids = []
        self.pushed_regions = []
        self.popped_regions = 0
        self.widgets = []
        self.regions = []

    def unique_id(self, value):
        self.unique_ids.append(value)
        return value

    def push_region(self, region_id):
        self.pushed_regions.append(region_id)

    def pop_region(self):
        self.popped_regions += 1

    def record_widget(self, *args, **kwargs):
        self.widgets.append((args, kwargs))

    def record_region(self, *args, **kwargs):
        self.regions.append((args, kwargs))


def test_plot_calls_record_regions_and_data_samples_after_deferred_layout(monkeypatch):
    native_calls = []

    def begin_plot(label):
        native_calls.append(("begin_plot", label))
        return True

    def plot_bars(label, values):
        native_calls.append(("plot_bars", label, values))
        return "bars-result"

    def end_plot():
        native_calls.append(("end_plot",))
        return "end-result"

    native = SimpleNamespace(
        begin_plot=begin_plot,
        plot_bars=plot_bars,
        end_plot=end_plot,
        get_plot_pos=lambda: SimpleNamespace(x=10.0, y=20.0),
        get_plot_size=lambda: SimpleNamespace(x=300.0, y=180.0),
    )
    recorder = _TelemetryRecorder()
    source = object()
    monkeypatch.setattr(instrumented_implot, "native_implot", native)
    monkeypatch.setattr(instrumented_implot, "active_telemetry", lambda: recorder)
    monkeypatch.setattr(instrumented_implot, "_source", lambda _frame: source)
    monkeypatch.setattr(instrumented_implot, "_site_id", lambda _source, _name: "site-1")
    facade = instrumented_implot.ImPlotFacade()

    assert facade.begin_plot("GDP") is True
    assert facade.plot_bars("GDP", [2, 4, 6]) == "bars-result"
    assert facade.end_plot() == "end-result"

    plot_id = "plot/panel.root/site-1"
    assert recorder.pushed_regions == [plot_id]
    assert recorder.popped_regions == 1
    assert recorder.widgets == [
        (
            (
                "plot-item/panel.root/site-1",
                "GDP",
                "plot_bars",
                True,
                False,
                instrumented_implot.Rect(10.0, 20.0, 300.0, 180.0),
            ),
            {"source": source, "interactive": False, "value": {"sample_count": 3}},
        )
    ]
    assert recorder.regions == [
        (
            (plot_id, "GDP", True, instrumented_implot.Rect(10.0, 20.0, 300.0, 180.0)),
            {"kind": "plot", "source": source},
        )
    ]
    assert native_calls == [
        ("begin_plot", "GDP"),
        ("plot_bars", "GDP", [2, 4, 6]),
        ("end_plot",),
    ]
    assert facade._plot_stack == []


def test_facade_returns_unwrapped_values_without_telemetry_and_handles_empty_plot_stack(monkeypatch):
    def begin_plot(_label):
        return False

    def plot_line(*_args):
        return "line-result"

    def end_plot():
        return "end-result"

    class PlotStyle:
        pass

    native = SimpleNamespace(
        begin_plot=begin_plot,
        plot_line=plot_line,
        end_plot=end_plot,
        max_items=4,
        PlotStyle=PlotStyle,
    )
    monkeypatch.setattr(instrumented_implot, "native_implot", native)
    monkeypatch.setattr(instrumented_implot, "active_telemetry", lambda: None)
    facade = instrumented_implot.ImPlotFacade()

    assert facade.max_items == 4
    assert facade.PlotStyle is PlotStyle
    assert facade.begin_plot("hidden") is False
    assert facade.plot_line([1, 2]) == "line-result"
    assert facade.end_plot() == "end-result"
    assert facade._plot_stack == []
