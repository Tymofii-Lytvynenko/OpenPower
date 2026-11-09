from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import src.client.ui.panels.politics.relations_panel as relations_module
from src.client.ui.panels.politics.relations_panel import RelationsPanel
from src.client.ui.panels.politics.relations_presenter import RelationCountryOption, RelationPairView


def countries():
    return (RelationCountryOption("CAN", "Canada"), RelationCountryOption("USA", "United States"))


def pair(current_value=10.0, history=()):
    return RelationPairView(countries()[1], countries()[0], current_value, tuple(history))


def make_imgui(monkeypatch, *, combos=(), hovered=False, begin_plot=True):
    imgui = Mock()
    imgui.StyleVar_.frame_padding = 1
    imgui.ImVec2.side_effect = lambda x, y: SimpleNamespace(x=x, y=y)
    imgui.is_item_hovered.return_value = hovered
    imgui.combo.side_effect = iter(combos) if combos else lambda *_args, **_kwargs: (False, 0)
    imgui.begin_plot.return_value = begin_plot
    imgui.get_window_pos.return_value = SimpleNamespace(x=20.0, y=30.0)
    monkeypatch.setattr(relations_module, "imgui", imgui)
    return imgui


def panel_for(countries_rows=None, relation_pair=None):
    presenter = Mock()
    presenter.countries.return_value = countries_rows if countries_rows is not None else countries()
    presenter.build_pair.return_value = relation_pair
    return RelationsPanel(presenter), presenter


def test_render_returns_window_state_and_registers_native_close_anchor(monkeypatch):
    is_open = False
    positions = []

    @contextmanager
    def window(*args, **kwargs):
        positions.append((args, kwargs))
        yield is_open

    monkeypatch.setattr(relations_module.WindowManager, "window", window)
    imgui = make_imgui(monkeypatch)
    imgui.get_window_pos.return_value = SimpleNamespace(x=10.0, y=20.0)
    imgui.get_window_size.return_value = SimpleNamespace(x=300.0, y=150.0)
    imgui.get_frame_height.return_value = 25.0
    anchor = Mock(return_value=False)
    monkeypatch.setattr(relations_module.UIAnchorRegistry, "is_target", anchor)
    record = Mock()
    monkeypatch.setattr(relations_module.UIAnchorRegistry, "record", record)
    panel, _presenter = panel_for()
    panel._render_content = Mock()
    state = SimpleNamespace()
    context = SimpleNamespace(target_tag="USA")

    assert panel.render(state, context) is False
    anchor.return_value = True
    is_open = True
    assert panel.render(state, context) is True

    record.assert_called_once_with("relations.panel.close", 285.0, 20.0, 25.0, 25.0)
    panel._render_content.assert_called_once_with(state, context)
    assert positions[0][1]["test_id"] == "relations.panel"


def test_content_requires_two_countries_and_prevents_selecting_the_same_pair(monkeypatch):
    imgui = make_imgui(monkeypatch, combos=[(True, 1), (False, 0)])
    panel, presenter = panel_for(countries_rows=(RelationCountryOption("CAN", "Canada"),))
    panel._render_content(SimpleNamespace(), SimpleNamespace(target_tag="MEX"))
    imgui.text_disabled.assert_called_once_with("At least two country records are required to compare relations.")
    presenter.build_pair.assert_not_called()

    imgui = make_imgui(monkeypatch, combos=[(True, 1), (False, 0)])
    panel, presenter = panel_for(relation_pair=pair())
    panel._render_content(SimpleNamespace(), SimpleNamespace(target_tag="CAN"))
    assert panel._country_a == "USA"
    assert panel._country_b == "USA"
    imgui.text_disabled.assert_called_once_with("Choose two different countries.")
    presenter.build_pair.assert_not_called()


def test_content_reports_unavailable_pair_and_empty_history(monkeypatch):
    imgui = make_imgui(monkeypatch, combos=[(False, 0), (True, 0)], hovered=True)
    panel, presenter = panel_for(relation_pair=None)
    panel._country_a = "USA"
    panel._country_b = "CAN"
    panel._render_content(SimpleNamespace(), SimpleNamespace(target_tag="USA"))
    presenter.build_pair.assert_called_once()
    imgui.text_disabled.assert_called_once_with("Relation data is unavailable for this pair.")

    imgui = make_imgui(monkeypatch, hovered=True)
    monkeypatch.setattr(relations_module, "active_gml_layout", lambda: None)
    panel, _presenter = panel_for(relation_pair=pair(current_value=None, history=()))
    widgets = SimpleNamespace(text_at=Mock())
    monkeypatch.setattr(relations_module, "GMLWidgets", lambda _root: widgets)

    panel._render_content(SimpleNamespace(), SimpleNamespace(target_tag="MEX"))

    imgui.set_tooltip.assert_called_once_with("United States → Canada: unavailable")
    widgets.text_at.assert_called_once()
    assert widgets.text_at.call_args.args[:2] == ("UIGraph", "No relation history recorded.")
    assert widgets.text_at.call_args.kwargs["max_width"] == 240.0


def test_content_plots_history_with_and_without_a_mapped_graph_rectangle(monkeypatch):
    rect = SimpleNamespace(x=5.0, y=7.0, width=250.0, height=80.0)
    monkeypatch.setattr(relations_module, "active_gml_layout", lambda: None)
    imgui = make_imgui(monkeypatch, hovered=False, begin_plot=True)
    panel, _presenter = panel_for(relation_pair=pair(history=((1440, -20.0), (2880, 30.0))))
    panel._country_a, panel._country_b = "USA", "CAN"
    panel._graph_rect = lambda: rect
    implot = Mock()
    implot.Flags_.canvas_only = 1
    implot.AxisFlags_.no_decorations = 2
    implot.ImAxis_.y1 = 3
    implot.begin_plot.return_value = True
    monkeypatch.setattr(relations_module, "implot", implot)
    panel._render_content(SimpleNamespace(), SimpleNamespace(target_tag="USA"))

    assert imgui.ImVec2.call_args.args == (250.0, 80.0)
    imgui.set_cursor_screen_pos.assert_called_once_with((25.0, 37.0))
    implot.setup_axis_limits.assert_called_once_with(3, -100.0, 100.0)
    x_values, y_values = implot.plot_line.call_args.args[1:]
    assert x_values.tolist() == [1.0, 2.0]
    assert y_values.tolist() == [-20.0, 30.0]
    implot.end_plot.assert_called_once()

    imgui = make_imgui(monkeypatch, begin_plot=False)
    monkeypatch.setattr(relations_module, "imgui", imgui)
    panel._graph_rect = lambda: None
    implot.begin_plot.return_value = False
    panel._render_content(SimpleNamespace(), SimpleNamespace(target_tag="USA"))
    assert imgui.ImVec2.call_args.args == (-1.0, 39.0)
    implot.end_plot.assert_called_once()


def test_country_selectors_and_graph_rect_resolution_use_gml_mappings(monkeypatch):
    imgui = make_imgui(monkeypatch, combos=[(False, 0)])
    panel, _presenter = panel_for()
    result = panel._country_selector(
        "Country A", 0, ["Canada (CAN)"], label_component="lblCountryA",
        combo_component="cboCountryA", test_id="relations.country_a",
    )
    assert result == (False, 0)
    imgui.push_style_var.assert_called_once_with(1, (4.0, 0.5))
    imgui.pop_style_var.assert_called_once()
    assert panel._component_path("cboCountryA") == "Relations_Window/frmInner/frmRelations/cboCountryA"

    monkeypatch.setattr(relations_module, "active_gml_layout", lambda: None)
    assert panel._graph_rect() is None
    layout = SimpleNamespace(
        layout=SimpleNamespace(component=lambda _component: "graph-component"),
        rect_for=lambda component: (component, 1),
    )
    monkeypatch.setattr(relations_module, "active_gml_layout", lambda: layout)
    assert panel._graph_rect() == ("graph-component", 1)
