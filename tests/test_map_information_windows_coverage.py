from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock

from src.client.ui.panels.military import map_information_windows as map_information_module


class _RecordingWidgets:
    instances = []

    def __init__(self, template):
        self.template = template
        self.text_calls = []
        self.meter_calls = []
        self.picture_calls = []
        self.instances.append(self)

    def text(self, *args, **kwargs):
        self.text_calls.append((args, kwargs))

    def meter(self, *args, **kwargs):
        self.meter_calls.append((args, kwargs))

    def path(self, component):
        return f"{self.template}/{component}"

    def picture(self, *args, **kwargs):
        self.picture_calls.append((args, kwargs))


def _install_ui(monkeypatch):
    _RecordingWidgets.instances.clear()
    ui = Mock()
    ui.WindowFlags_ = SimpleNamespace(
        no_decoration=1,
        no_inputs=2,
        no_focus_on_appearing=4,
        no_bring_to_front_on_focus=8,
        no_scrollbar=16,
        no_scroll_with_mouse=32,
        tooltip=64,
    )
    ui.get_style.return_value = SimpleNamespace(font_scale_main=0.5, font_scale_dpi=0.5)
    monkeypatch.setattr(map_information_module, "imgui", ui)
    monkeypatch.setattr(map_information_module, "GMLWidgets", _RecordingWidgets)
    monkeypatch.setattr(map_information_module, "FlagRenderer", Mock(return_value=Mock()))
    window = Mock(side_effect=lambda *_args, **_kwargs: nullcontext())
    monkeypatch.setattr(
        map_information_module,
        "WindowManager",
        SimpleNamespace(window=window),
    )
    return ui, window


def test_selected_unit_window_skips_invalid_contexts_and_renders_all_categories(monkeypatch):
    ui, window = _install_ui(monkeypatch)
    values = SimpleNamespace(
        quantities={"I": 1_000, "G": None, "N": 0, "A": 7},
        fractions={"I": 1.0, "G": 0.0, "N": 0.0, "A": 0.25},
    )
    composition = Mock(return_value=values)
    monkeypatch.setattr(map_information_module, "selected_unit_composition", composition)
    windows = map_information_module.MapInformationWindows("USA")
    state = object()
    projected = SimpleNamespace(screen_x=10, screen_y=20, width=30, height=40)
    project = Mock(return_value=projected)

    windows.render_selected_unit(state, set(), project, 720)
    windows.render_selected_unit(state, {"one", "two"}, project, 720)
    windows.render_selected_unit(state, {"one"}, project, 720, dragging=True)
    project.assert_not_called()

    project.return_value = None
    windows.render_selected_unit(state, {"one"}, project, 720)
    composition.assert_called_once_with(state, "one", "USA")
    window.assert_not_called()

    project.return_value = projected
    composition.return_value = None
    windows.render_selected_unit(state, {"one"}, project, 720)
    window.assert_not_called()

    composition.return_value = values
    windows.render_selected_unit(state, {"one"}, project, 720)

    window.assert_called_once_with(
        "Unit composition",
        x=33.0,
        y=680.0,
        flags=63,
        closable=False,
        gml_template="Small_Unit_Info_Window",
        test_id="unit.map.composition",
        padding=(0, 0),
        follow_position=True,
    )
    ui.push_font.assert_called_once_with(None, 40.0)
    ui.pop_font.assert_called_once_with()
    widgets = _RecordingWidgets.instances[-1]
    assert widgets.template == "Small_Unit_Info_Window"
    assert [args[1] for args, _kwargs in widgets.text_calls] == [
        "I", "1 000", "G", "?", "N", "0", "A", "7"
    ]
    assert [kwargs.get("test_id") for _args, kwargs in widgets.text_calls if "test_id" in kwargs] == [
        "unit.map.quantity.I",
        "unit.map.quantity.G",
        "unit.map.quantity.N",
        "unit.map.quantity.A",
    ]
    assert len(widgets.meter_calls) == 4


def test_region_window_skips_inactive_or_unresolved_controls_and_renders_dynamic_names(monkeypatch):
    ui, window = _install_ui(monkeypatch)
    flag_renderer = Mock()
    monkeypatch.setattr(
        map_information_module,
        "FlagRenderer",
        Mock(return_value=flag_renderer),
    )
    control = Mock(return_value=None)
    monkeypatch.setattr(map_information_module, "region_control", control)
    windows = map_information_module.MapInformationWindows("USA")
    state = object()

    windows.render_region(state, 5, (100, 200))
    windows.render_region(state, 5, (100, 200), active=True)
    assert control.call_count == 1
    window.assert_not_called()
    ui.push_font.assert_not_called()

    values = SimpleNamespace(
        name="Kyiv",
        political_name="Political owner",
        political_tag="POL",
        military_name="Military controller",
        military_tag="UKR",
    )
    control.return_value = values
    ui.calc_text_size.side_effect = lambda text: SimpleNamespace(
        x={"Kyiv": 80.0, "Political owner": 230.0, "Military controller": 175.0}[text]
    )
    session = SimpleNamespace(window_size=(400.0, 56.0), resize_component=Mock())
    monkeypatch.setattr(map_information_module, "active_gml_layout", lambda: session)

    windows.render_region(state, 5, (100, 200), active=True)

    window.assert_called_once_with(
        "Region control",
        x=116,
        y=184,
        flags=127,
        closable=False,
        gml_template="Sphere_Control_Window",
        test_id="map.region_control",
        padding=(0, 0),
        follow_position=True,
        size_override=(356.0, 56),
    )
    assert ui.push_font.call_args.args == (None, 48.0)
    assert ui.pop_font.call_count == 1
    assert ui.calc_text_size.call_count == 3
    assert session.resize_component.call_args_list == [
        (("Sphere_Control_Window/lblRegion",), {"width": 396.0}),
        (("Sphere_Control_Window/frmPoliticCountry",), {"width": 305.0}),
        (("Sphere_Control_Window/frmPoliticCountry/lblCountry",), {"width": 280.0}),
        (("Sphere_Control_Window/frmMilitaryCountry",), {"width": 305.0}),
        (("Sphere_Control_Window/frmMilitaryCountry/lblCountry",), {"width": 280.0}),
    ]

    widgets = _RecordingWidgets.instances[-1]
    assert [args[0] for args, _kwargs in widgets.picture_calls] == [
        "frmPoliticCountry/picFlag",
        "frmMilitaryCountry/picFlag",
    ]
    widgets.picture_calls[0][0][1](24, 12)
    widgets.picture_calls[1][0][1](24, 12)
    assert flag_renderer.draw_flag.call_args_list == [
        (("POL", 24, 12),),
        (("UKR", 24, 12),),
    ]
