from contextlib import contextmanager, nullcontext
from types import SimpleNamespace
from unittest.mock import Mock

import src.client.ui.components.hud.central_bar as central_bar_module
from src.client.ui.components.hud.central_bar import CentralBar
from src.client.ui.components.hud.country_selector import CountryOption, CountryStatus
from src.client.ui.layouts.gml_layout import GMLRect


def _imgui_mock(monkeypatch, *, expanded=False):
    imgui = Mock()
    imgui.WindowFlags_.no_decoration = 1
    imgui.WindowFlags_.no_move = 2
    imgui.WindowFlags_.no_scroll_with_mouse = 4
    imgui.WindowFlags_.no_background = 8
    imgui.WindowFlags_.no_saved_settings = 16
    imgui.StyleVar_.window_padding = 1
    imgui.Col_.button = 1
    imgui.WindowFlags_.no_mouse_inputs = 32
    imgui.begin.return_value = (expanded, None)
    imgui.get_main_viewport.return_value = SimpleNamespace(
        pos=SimpleNamespace(x=10.0, y=20.0),
        size=SimpleNamespace(x=1280.0, y=720.0),
    )
    monkeypatch.setattr(central_bar_module, "imgui", imgui)
    return imgui


def test_constructor_composes_flag_renderer_and_country_selector(monkeypatch):
    renderer, selector = Mock(), Mock()
    monkeypatch.setattr(central_bar_module, "FlagRenderer", Mock(return_value=renderer))
    selector_factory = Mock(return_value=selector)
    monkeypatch.setattr(central_bar_module, "CountrySelector", selector_factory)
    callbacks = [Mock() for _ in range(9)]

    bar = CentralBar(*callbacks)

    selector_factory.assert_called_once_with(renderer)
    assert bar.flag_renderer is renderer
    assert bar.country_selector is selector
    assert bar._open_ai_cb is callbacks[0]
    assert bar._focus_country_cb is callbacks[-1]
    assert bar.show_speed_controls is False
    assert bar.active_tag == ""
    assert bar.country_status is CountryStatus.NEUTRAL
    assert bar.is_own is False


def test_render_handles_collapsed_and_expanded_window(monkeypatch):
    imgui = _imgui_mock(monkeypatch)
    imgui.begin.side_effect = [(False, None), (True, None)]
    imgui.get_window_pos.return_value = SimpleNamespace(x=20.0, y=30.0)
    imgui.get_window_size.return_value = SimpleNamespace(x=900.0, y=80.0)
    monkeypatch.setattr(central_bar_module, "gml_style", nullcontext)
    session = object()
    monkeypatch.setattr(central_bar_module, "get_gml_layout", lambda _name: SimpleNamespace(width=1000.0))
    create_session = Mock(return_value=session)
    monkeypatch.setattr(central_bar_module, "create_gml_layout_session", create_session)
    monkeypatch.setattr(central_bar_module, "use_gml_layout", lambda _session: nullcontext())
    monkeypatch.setattr(central_bar_module, "GMLWidgets", Mock())
    bar = object.__new__(CentralBar)
    bar.country_selector = Mock()
    for name in (
        "_render_background", "_render_sphere_meters", "_render_country_section",
        "_render_quick_actions", "_render_time_section", "_render_ticker",
    ):
        setattr(bar, name, Mock())

    assert bar.render(None, None, "USA", CountryStatus.PLAYER, None) is None
    selected = bar.render(None, None, "CAN", CountryStatus.ALLIANCE, None)

    assert selected == bar.country_selector.render.return_value
    assert bar.active_tag == "CAN"
    assert bar.country_status is CountryStatus.ALLIANCE
    assert bar.is_own is False
    bar._render_background.assert_called_once()
    bar._render_sphere_meters.assert_called_once()
    bar._render_country_section.assert_called_once()
    bar._render_quick_actions.assert_called_once()
    bar._render_time_section.assert_called_once()
    bar._render_ticker.assert_called_once()
    assert imgui.end.call_count == 2
    assert create_session.call_args.args == ("Main_Bar", (20.0, 30.0), (1000.0, 80.0))


def test_background_and_sphere_meters_render_data_and_unavailable_values(monkeypatch):
    imgui = _imgui_mock(monkeypatch)
    ui = Mock()
    ui.rect.return_value = SimpleNamespace(y=45.0)
    bounds = GMLRect(2.0, 3.0, 100.0, 20.0)

    CentralBar._render_background(bounds, ui)

    draw = imgui.get_window_draw_list.return_value
    assert draw.add_rect_filled.call_count == 2
    draw.add_rect.assert_called_once()
    draw.add_line.assert_called_once()

    bar = object.__new__(CentralBar)
    bar.active_tag = "UKR"
    metrics = {
        "frmMeterPolitic": SimpleNamespace(value=None, label="Politics"),
        "frmMeterMilitary": SimpleNamespace(value=75.0, label="Military"),
    }
    monkeypatch.setattr(central_bar_module, "main_bar_sphere_metrics", Mock(return_value=metrics))

    bar._render_sphere_meters(SimpleNamespace(), ui)

    assert ui.segmented_meter.call_count == 2
    assert ui.segmented_meter.call_args_list[0].args[1] == 0.0
    assert ui.segmented_meter.call_args_list[1].args[1] == 0.75
    assert ui.segmented_meter.call_args_list[0].kwargs["tooltip"] == "Politics: unavailable"
    assert ui.segmented_meter.call_args_list[1].kwargs["tooltip"] == "Military: 75.0%"


def test_country_section_dispatches_focus_selector_and_optional_actions(monkeypatch):
    imgui = _imgui_mock(monkeypatch)
    imgui.get_item_rect_min.return_value = SimpleNamespace(x=10.0, y=20.0)
    imgui.get_item_rect_max.return_value = SimpleNamespace(x=100.0, y=40.0)
    layout = SimpleNamespace(window_position=(200.0, 300.0))
    monkeypatch.setattr(central_bar_module, "active_gml_layout", lambda: layout)
    monkeypatch.setattr(central_bar_module.UIPrimitives, "fit_text", Mock(return_value="United States"))
    flag_renderer, country_selector = Mock(), Mock()
    focus, relations, more_info = Mock(), Mock(), Mock()
    bar = object.__new__(CentralBar)
    bar.active_tag = "USA"
    bar.country_status = CountryStatus.PLAYER
    bar.flag_renderer = flag_renderer
    bar.country_selector = country_selector
    bar._focus_country_cb = focus
    bar._open_relations_cb = relations
    bar._open_more_info_cb = more_info
    country_selector.options.return_value = [CountryOption("USA", "United States")]
    ui = Mock()
    ui.rect.side_effect = [
        SimpleNamespace(x=2.0, y=3.0, width=12.0, height=9.0),
        SimpleNamespace(width=150.0),
    ]
    ui.hitbox.return_value = True
    ui.button.side_effect = [True, False, True, False]

    bar._render_country_section(SimpleNamespace(), ui)

    flag_renderer.draw_flag.assert_called_once_with("USA", 12.0, 9.0)
    focus.assert_called_once_with("USA")
    country_selector.open.assert_called_once_with((10.0, 40.0), 90.0)
    relations.assert_called_once_with()
    more_info.assert_not_called()
    assert ui.hitbox.call_args.kwargs["enabled"] is True
    imgui.push_style_color.assert_called_once()
    imgui.pop_style_color.assert_called_once_with()


def test_quick_actions_and_time_section_follow_callbacks_and_speed_state(monkeypatch):
    imgui = _imgui_mock(monkeypatch)
    bar = object.__new__(CentralBar)
    advisor, history, mail = Mock(), Mock(), Mock()
    bar._open_ai_cb, bar._open_statistics_cb, bar._open_mail_cb = advisor, history, mail
    bar._panel_visible_cb = lambda panel_id: panel_id == "HISTORY"
    bar.is_own = True
    ui = Mock()
    ui.toggle.side_effect = [(True, False), (False, False), (True, False)]

    bar._render_quick_actions(SimpleNamespace(unread_messages=3), ui)

    advisor.assert_called_once_with()
    history.assert_not_called()
    mail.assert_called_once_with()
    assert ui.toggle.call_args_list[0].kwargs["enabled"] is True

    bar.show_speed_controls = False
    ui.button.return_value = False
    net = Mock()
    net.get_display_date_text.return_value = None
    state = SimpleNamespace(time=SimpleNamespace(date_str="1936.01.01"))
    bar._render_time_section(state, net, ui)
    assert ui.text.call_args_list[-2].args == ("lblDate", "1936.01.01")
    assert ui.text.call_args_list[-1].args == ("lblTime", "")

    net.get_display_date_text.return_value = "1936.02.01 12:00"
    bar._render_time_section(state, net, ui)
    assert ui.text.call_args_list[-2].args == ("lblDate", "1936.02.01")
    assert ui.text.call_args_list[-1].args == ("lblTime", "12:00")

    ui.button.return_value = True
    bar._draw_speed_controls = Mock()
    bar._render_time_section(state, net, ui)
    assert bar.show_speed_controls is True
    bar._draw_speed_controls.assert_called_once_with(state, net, ui)


def test_country_section_and_quick_actions_support_missing_callbacks(monkeypatch):
    imgui = _imgui_mock(monkeypatch)
    imgui.get_item_rect_min.return_value = SimpleNamespace(x=10.0, y=20.0)
    imgui.get_item_rect_max.return_value = SimpleNamespace(x=100.0, y=40.0)
    monkeypatch.setattr(
        central_bar_module,
        "active_gml_layout",
        lambda: SimpleNamespace(window_position=(0.0, 0.0)),
    )
    monkeypatch.setattr(central_bar_module.UIPrimitives, "fit_text", Mock(return_value="USA"))
    bar = object.__new__(CentralBar)
    bar.active_tag = "USA"
    bar.country_status = CountryStatus.NEUTRAL
    bar.flag_renderer = Mock()
    bar.country_selector = Mock()
    bar.country_selector.options.return_value = []
    bar._focus_country_cb = None
    bar._open_relations_cb = None
    bar._open_more_info_cb = Mock()
    ui = Mock()
    ui.rect.side_effect = [SimpleNamespace(x=0, y=0, width=10, height=10), SimpleNamespace(width=100)]
    ui.hitbox.return_value = False
    ui.button.side_effect = [False, False, False, True]

    bar._render_country_section(SimpleNamespace(), ui)

    assert ui.hitbox.call_args.kwargs["enabled"] is False
    bar._open_more_info_cb.assert_called_once_with()
    assert ui.button.call_args_list[2].kwargs["enabled"] is False

    bar._open_ai_cb = None
    bar._open_statistics_cb = None
    bar._open_mail_cb = None
    bar._panel_visible_cb = None
    bar.is_own = False
    ui.toggle.side_effect = [(False, False), (False, False), (False, False)]
    bar._render_quick_actions(SimpleNamespace(unread_messages=0), ui)
    assert all(call.kwargs["enabled"] is False for call in ui.toggle.call_args_list[-3:])


def test_ticker_routes_location_news_toggle_and_unavailable_states(monkeypatch):
    imgui = _imgui_mock(monkeypatch)
    imgui.get_content_region_avail.return_value.x = 160.0
    child_state = {"open": True}

    @contextmanager
    def child_frame(*_args, **_kwargs):
        yield child_state["open"]

    monkeypatch.setattr(central_bar_module, "gml_child_frame", child_frame)
    monkeypatch.setattr(central_bar_module.UIPrimitives, "fit_text", Mock(return_value="Latest event"))
    locate, news = Mock(), Mock()
    visible = Mock(return_value=False)
    bar = object.__new__(CentralBar)
    bar._open_locate_cb = locate
    bar._open_news_cb = news
    bar._panel_visible_cb = visible
    ui = Mock()
    ui.path.side_effect = lambda path: path
    ui.hitbox.return_value = True
    ui.toggle.return_value = (True, False)
    summary = SimpleNamespace(ticker_text="Latest event", ticker_region_id=42)

    bar._render_ticker(summary, ui)

    locate.assert_called_once_with(42)
    news.assert_called_once_with()
    imgui.text_colored.assert_called_once_with(
        (0.74, 0.78, 0.74, 1.0), "Latest event", test_id="hud.ticker",
    )
    visible.assert_any_call("NEWS_LOG")

    child_state["open"] = False
    bar._open_locate_cb = None
    bar._open_news_cb = None
    bar._panel_visible_cb = None
    ui.toggle.return_value = (False, False)
    bar._render_ticker(SimpleNamespace(ticker_text="No map link", ticker_region_id=None), ui)
    assert imgui.text_colored.call_count == 1
    assert ui.hitbox.call_args.kwargs["enabled"] is False
    assert ui.toggle.call_args.kwargs["enabled"] is False
