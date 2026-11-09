from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, call

import polars as pl

from src.client.ui.panels.service import news_panel
from src.client.ui.panels.service.event_feed_presenter import EventCategory, EventFeedItem
from src.client.ui.panels.service.news_panel import NewsPanel
from src.shared.actions import ActionRespondToRandomEvent, ActionSetRandomEventControls


class Ui:
    def __init__(self, *, buttons=(), buttons_at=(), toggles=None):
        self.buttons = set(buttons)
        self.buttons_at = set(buttons_at)
        self.toggles = toggles or {}
        self.button_calls = []
        self.button_at_calls = []
        self.toggle_calls = []

    def button(self, slot, label, test_id, **kwargs):
        self.button_calls.append((slot, label, test_id, kwargs))
        return test_id in self.buttons and kwargs.get("enabled", True)

    def button_at(self, slot, label, test_id, **kwargs):
        self.button_at_calls.append((slot, label, test_id, kwargs))
        return test_id in self.buttons_at

    def toggle(self, component_id, enabled, **kwargs):
        self.toggle_calls.append((component_id, enabled, kwargs))
        return self.toggles.get(kwargs["test_id"], (False, enabled))


class Client:
    player_id = "player-1"

    def __init__(self):
        self.actions = []

    def send_action(self, action):
        self.actions.append(action)


def install_imgui(monkeypatch):
    fake = MagicMock()
    fake.WindowFlags_ = SimpleNamespace(no_title_bar=1)
    fake.StyleVar_ = SimpleNamespace(window_padding=2)
    monkeypatch.setattr(news_panel, "imgui", fake)
    return fake


def test_render_positions_feed_and_returns_window_open_state(monkeypatch):
    panel = NewsPanel()
    imgui = install_imgui(monkeypatch)
    imgui.get_io.return_value.display_size = SimpleNamespace(x=1280, y=720)
    rendered = Mock()
    panel._render_content = rendered
    windows = []

    @contextmanager
    def window(*args, **kwargs):
        windows.append((args, kwargs))
        yield kwargs.pop("is_open", True)

    monkeypatch.setattr(news_panel.WindowManager, "window", window)
    context = SimpleNamespace()

    assert panel.render(SimpleNamespace(), context) is True
    assert windows[0][0] == ("EVENT FEED",)
    assert windows[0][1]["x"] == 396.0
    assert windows[0][1]["y"] == 260.5
    rendered.assert_called_once()

    @contextmanager
    def closed_window(*_args, **kwargs):
        yield False

    monkeypatch.setattr(news_panel.WindowManager, "window", closed_window)
    rendered.reset_mock()
    assert panel.render(SimpleNamespace(), context) is False
    rendered.assert_not_called()


def test_content_filters_events_opens_controls_and_focuses_selected_region(monkeypatch):
    panel = NewsPanel()
    general = EventFeedItem("g1", EventCategory.GENERAL, "", "World update", "", "Minute 1")
    political = EventFeedItem("p1", EventCategory.POLITICAL, "USA", "Treaty signed", "", "Minute 2", region_id=42)
    panel._presenter.items = Mock(return_value=[general, political])
    panel._selected_event_id = "p1"
    panel._render_item = Mock()
    panel._render_filters = Mock()
    panel._render_event_controls = Mock()
    ui = Ui(buttons={"news.goto"}, buttons_at={"news.random_event_settings"})
    monkeypatch.setattr(news_panel, "GMLWidgets", lambda _root: ui)
    imgui = install_imgui(monkeypatch)
    imgui.begin_child.return_value = True
    imgui.begin_popup.return_value = True
    focus = Mock()
    context = SimpleNamespace(on_focus_request=focus)

    panel._render_content(SimpleNamespace(), context)

    assert panel._render_item.call_args_list == [
        ((general, context),), ((political, context),),
    ]
    panel._render_event_controls.assert_called_once()
    panel._render_filters.assert_called_once()
    focus.assert_called_once_with(42)
    imgui.open_popup.assert_called_once_with("NewsRandomEventControls")
    imgui.end_popup.assert_called_once_with()
    imgui.end_child.assert_called_once_with()
    imgui.pop_style_var.assert_called_once_with()


def test_content_shows_empty_state_and_clears_selection_hidden_by_filters(monkeypatch):
    panel = NewsPanel()
    panel._enabled_filters.clear()
    panel._selected_event_id = "hidden"
    panel._presenter.items = Mock(return_value=[
        EventFeedItem("p1", EventCategory.POLITICAL, "USA", "Treaty signed", "", "Minute 2")
    ])
    panel._render_filters = Mock()
    ui = Ui()
    monkeypatch.setattr(news_panel, "GMLWidgets", lambda _root: ui)
    imgui = install_imgui(monkeypatch)
    imgui.begin_child.return_value = True
    imgui.begin_popup.return_value = False
    empty = Mock()
    monkeypatch.setattr(news_panel, "draw_empty_state", empty)

    panel._render_content(SimpleNamespace(), SimpleNamespace(on_focus_request=None))

    assert panel._selected_event_id is None
    empty.assert_called_once_with("No events match the selected filters.")


def test_filter_toggles_add_and_remove_categories():
    panel = NewsPanel()
    ui = Ui(toggles={
        "news.filter.political": (True, False),
        "news.filter.economic": (True, True),
    })
    counts = {category: index for index, category in enumerate(EventCategory)}

    panel._render_filters(ui, counts)

    assert EventCategory.POLITICAL not in panel._enabled_filters
    assert EventCategory.ECONOMIC in panel._enabled_filters
    assert len(ui.toggle_calls) == 4
    assert ui.toggle_calls[0][2]["tooltip"] == "Political events: 2"


def test_render_item_draws_selected_country_event_and_dispatches_response(monkeypatch):
    panel = NewsPanel()
    item = EventFeedItem(
        id="instance:event-1",
        category=EventCategory.ECONOMIC,
        country_tag="USA",
        headline="Crop failure",
        body="Harvest fell sharply",
        created_at="Minute 9",
        region_id=9,
        response_options=(("aid", 1200.0), ("ration", 0.0)),
    )
    panel._selected_event_id = item.id
    panel._flag_renderer.draw_flag = Mock()
    panel._render_item_tooltip = Mock()
    monkeypatch.setattr(news_panel.UIPrimitives, "fit_text", lambda text, _width: text)
    imgui = install_imgui(monkeypatch)
    imgui.get_content_region_avail.return_value = SimpleNamespace(x=440.0)
    imgui.get_cursor_pos.return_value = SimpleNamespace(x=10.0, y=20.0)
    imgui.get_cursor_screen_pos.return_value = SimpleNamespace(x=100.0, y=200.0)
    imgui.get_window_draw_list.return_value = MagicMock()
    imgui.calc_text_size.return_value = SimpleNamespace(x=84.0)
    imgui.invisible_button.return_value = True
    imgui.is_item_hovered.return_value = True
    imgui.small_button.side_effect = [True, False]
    client = Client()

    panel._render_item(item, SimpleNamespace(net_client=client))

    draw_list = imgui.get_window_draw_list.return_value
    assert draw_list.add_rect_filled.call_count == 2
    assert draw_list.add_line.call_count == 1
    panel._flag_renderer.draw_flag.assert_called_once_with("USA", 27.0, 18.0)
    panel._render_item_tooltip.assert_called_once_with(item)
    action = client.actions[0]
    assert isinstance(action, ActionRespondToRandomEvent)
    assert action.event_id == "event-1"
    assert action.response_id == "aid"
    assert action.country_tag == "USA"
    imgui.set_cursor_pos.assert_any_call((19.0, 26.0))
    imgui.set_cursor_pos.assert_called_with((10.0, 77.0))


def test_render_item_uses_world_marker_without_country_flag(monkeypatch):
    panel = NewsPanel()
    item = EventFeedItem("world", EventCategory.GENERAL, "", "Global note", "", "Minute 1")
    panel._render_item_tooltip = Mock()
    monkeypatch.setattr(news_panel.UIPrimitives, "fit_text", lambda text, _width: text)
    imgui = install_imgui(monkeypatch)
    imgui.get_content_region_avail.return_value = SimpleNamespace(x=300.0)
    imgui.get_cursor_pos.return_value = SimpleNamespace(x=0.0, y=0.0)
    imgui.get_cursor_screen_pos.return_value = SimpleNamespace(x=10.0, y=20.0)
    imgui.get_window_draw_list.return_value = MagicMock()
    imgui.calc_text_size.return_value = SimpleNamespace(x=60.0)
    imgui.invisible_button.return_value = False
    imgui.is_item_hovered.return_value = False

    panel._render_item(item, SimpleNamespace(net_client=None))

    draw_list = imgui.get_window_draw_list.return_value
    texts = [call.args[2] for call in draw_list.add_text.call_args_list]
    assert texts[0] == news_panel.icons_fontawesome_6.ICON_FA_GLOBE
    assert "WORLD" in texts
    panel._render_item_tooltip.assert_not_called()
    assert imgui.invisible_button.call_args.args[1] == (300.0, 30.0)


def test_event_tooltip_includes_body_and_timestamp_only_when_present(monkeypatch):
    imgui = install_imgui(monkeypatch)
    imgui.get_font_size.return_value = 14.0

    NewsPanel._render_item_tooltip(EventFeedItem("e1", EventCategory.GENERAL, "", "Headline", "Details", "Minute 4"))
    NewsPanel._render_item_tooltip(EventFeedItem("e2", EventCategory.GENERAL, "", "Headline", "", ""))

    imgui.begin_tooltip.assert_has_calls([call(), call()])
    imgui.text_unformatted.assert_called_once_with("Details")
    imgui.text_disabled.assert_called_once_with("Minute 4")
    assert imgui.push_text_wrap_pos.call_args.args == (420.0,)
    assert imgui.end_tooltip.call_count == 2


def test_event_controls_send_bounded_settings_and_category_actions(monkeypatch):
    imgui = install_imgui(monkeypatch)
    imgui.button.return_value = True
    imgui.small_button.return_value = True
    max_seed = (1 << 63) - 1
    state = SimpleNamespace(
        globals={
            "random_events_enabled": False,
            "random_event_frequency_multiplier": 3.9,
            "random_event_seed": max_seed,
        },
        determinism=SimpleNamespace(seed=10),
        tables={"random_event_controls": pl.DataFrame([
            {"category": "military", "enabled": True},
            {"category": "political", "enabled": False},
        ])},
    )
    client = Client()

    NewsPanel._render_event_controls(state, SimpleNamespace(net_client=client))

    assert all(isinstance(action, ActionSetRandomEventControls) for action in client.actions)
    assert client.actions[0].enabled is True
    assert client.actions[1].frequency_multiplier == 3.65
    assert client.actions[2].frequency_multiplier == 4.0
    assert client.actions[3].seed == max_seed - 1
    assert client.actions[4].seed == max_seed
    assert [(action.category, action.category_enabled) for action in client.actions[5:]] == [
        ("military", False), ("political", True),
    ]


def test_event_controls_skip_without_client_and_without_category_table(monkeypatch):
    imgui = install_imgui(monkeypatch)
    NewsPanel._render_event_controls(SimpleNamespace(), SimpleNamespace(net_client=None))
    imgui.button.assert_not_called()

    imgui.reset_mock()
    client = Client()
    imgui.button.return_value = False
    imgui.small_button.return_value = False
    state = SimpleNamespace(
        globals={},
        determinism=SimpleNamespace(seed=5),
        tables={},
    )
    NewsPanel._render_event_controls(state, SimpleNamespace(net_client=client))

    imgui.separator.assert_called_once_with()
    assert client.actions == []
