from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock, call

import src.client.ui.components.shared.advisor_recommendation_window as advisor_module
from src.client.ui.components.shared.advisor_recommendation_window import AdvisorRecommendationWindow
from src.shared.actions import ActionResolveAdvisorRecommendation


def _imgui_mock(monkeypatch):
    imgui = Mock()
    imgui.WindowFlags_.no_resize = 1
    imgui.WindowFlags_.no_scrollbar = 2
    imgui.WindowFlags_.no_scroll_with_mouse = 4
    imgui.MouseButton_.left = 1
    imgui.get_main_viewport.return_value = SimpleNamespace(
        pos=SimpleNamespace(x=10.0, y=20.0),
        size=SimpleNamespace(x=1280.0, y=720.0),
    )
    imgui.get_mouse_pos.return_value = SimpleNamespace(x=115.0, y=225.0)
    imgui.get_scroll_x.return_value = 0.0
    imgui.get_scroll_y.return_value = 0.0
    imgui.get_style.return_value = SimpleNamespace(font_scale_main=1.0, font_scale_dpi=1.0)
    monkeypatch.setattr(advisor_module, "imgui", imgui)
    return imgui


def _window_context(monkeypatch, opened):
    @contextmanager
    def window(*_args, **_kwargs):
        yield opened

    monkeypatch.setattr(advisor_module.WindowManager, "window", window)


def test_open_rejects_invalid_or_busy_requests():
    window = AdvisorRecommendationWindow(Mock(), " ukr ")

    assert window._country_tag == "UKR"
    assert window.open({"id": "  "}) is False
    assert window.open({"id": " first "}) is True
    assert window.open({"id": "second"}) is False

    window._requested_id = ""
    window._queued_ids = ["queued"]
    assert window.open({"id": "third"}) is False


def test_render_filters_actionable_requests_and_preserves_review_order():
    net = Mock()
    window = AdvisorRecommendationWindow(net, "USA")
    presenter = Mock()
    first = {"id": "first", "action": "accept"}
    second = {"id": "second", "action": "accept"}
    ignored = {"id": "ignored", "action": ""}
    presenter.build_overview.return_value = SimpleNamespace(recommendations=[first, second, ignored])
    presenter.recommendation_action_label.side_effect = lambda item: item["action"]
    window._presenter = presenter
    window._render_recommendation = Mock()
    window._submitted_ids = {"first", "stale"}

    assert window.open(second) is True
    state = SimpleNamespace()
    window.render(state)

    assert window._requested_id == ""
    assert window._queued_ids == ["second"]
    assert window._submitted_ids == {"first"}
    window._render_recommendation.assert_called_once_with(second)
    presenter.build_overview.assert_called_once_with(state, "USA")


def test_render_discards_stale_requests_and_skips_empty_country_context():
    window = AdvisorRecommendationWindow(Mock(), "")
    presenter = Mock()
    window._presenter = presenter
    window.render(SimpleNamespace())
    presenter.build_overview.assert_not_called()

    window._country_tag = "USA"
    presenter.build_overview.return_value = SimpleNamespace(recommendations=[{"id": "active"}])
    presenter.recommendation_action_label.return_value = "Review"
    window._requested_id = "stale"
    window._render_recommendation = Mock()
    window.render(SimpleNamespace())
    assert window._requested_id == ""
    assert window._queued_ids == []
    window._render_recommendation.assert_not_called()

    window._queued_ids = ["active"]
    window._submitted_ids = {"active", "stale"}
    window.render(SimpleNamespace())
    assert window._queued_ids == []
    assert window._submitted_ids == {"active"}


def test_resolve_sends_each_recommendation_only_once():
    net = Mock()
    net.player_id = "player-1"
    window = AdvisorRecommendationWindow(net, "USA")
    window._queued_ids = ["first", "second"]

    window._resolve("first", True)
    window._resolve("first", False)
    window._resolve("", True)
    window._resolve("second", False)

    assert window._submitted_ids == {"first", "second"}
    assert window._queued_ids == []
    assert net.send_action.call_args_list == [
        call(ActionResolveAdvisorRecommendation(
            player_id="player-1", recommendation_id="first", accept=True,
        )),
        call(ActionResolveAdvisorRecommendation(
            player_id="player-1", recommendation_id="second", accept=False,
        )),
    ]


def test_recommendation_window_close_rejects_and_source_click_accepts(monkeypatch):
    imgui = _imgui_mock(monkeypatch)
    net = Mock()
    net.player_id = "player-1"
    window = AdvisorRecommendationWindow(net, "USA")
    window._presenter = Mock()
    window._presenter.recommendation_action_label.return_value = "Open policy"
    window._queued_ids = ["closed", "accepted"]

    _window_context(monkeypatch, False)
    window._render_recommendation({"id": "closed"})

    session = Mock()
    session.window_position = (100.0, 200.0)
    component = SimpleNamespace(font_size=10.0, text_offset=(2.0, 3.0))
    session.layout.component.return_value = component
    monkeypatch.setattr(advisor_module, "active_gml_layout", lambda: session)
    _window_context(monkeypatch, True)
    draw_list = imgui.get_window_draw_list.return_value
    plan_rect = SimpleNamespace(x=1.0, y=2.0, width=200.0, height=40.0)
    text_rect = SimpleNamespace(x=4.0, y=5.0, width=150.0, height=30.0)
    button_rect = SimpleNamespace(x=10.0, y=20.0, width=30.0, height=12.0)
    ui = Mock()
    ui.path.side_effect = lambda slot: slot
    ui.rect.side_effect = [plan_rect, text_rect, text_rect, button_rect]
    ui.button.return_value = False
    monkeypatch.setattr(advisor_module, "GMLWidgets", Mock(return_value=ui))
    imgui.is_mouse_clicked.return_value = True
    imgui.is_window_hovered.return_value = True

    window._focus_requested = True
    window._render_recommendation({
        "id": "accepted",
        "title": "Review policy",
        "reason": "The policy has matured.",
        "actor_country_id": "ukr",
    })

    assert net.send_action.call_args_list[0].args[0] == ActionResolveAdvisorRecommendation(
        player_id="player-1", recommendation_id="closed", accept=False,
    )
    assert net.send_action.call_args_list[1].args[0] == ActionResolveAdvisorRecommendation(
        player_id="player-1", recommendation_id="accepted", accept=True,
    )
    assert window._focus_requested is False
    imgui.set_next_window_focus.assert_called_once_with()
    assert session.resize_component.call_count == 4
    assert session.move_subtree.call_count == 2
    assert draw_list.push_clip_rect.call_count == 2
    assert imgui.pop_font.call_count == 2
    assert ui.text_at.call_args_list[-1].args[1] == "Target: UKR"


def test_geometry_action_row_and_wrapped_text_handle_missing_layout(monkeypatch):
    imgui = _imgui_mock(monkeypatch)
    ui = Mock()
    ui.path.side_effect = lambda slot: slot
    ui.rect.return_value = None
    window = AdvisorRecommendationWindow(Mock(), "USA")
    monkeypatch.setattr(advisor_module, "active_gml_layout", lambda: None)

    window._apply_source_plan_geometry(44.0)
    window._draw_action_row(ui, "Review", {"id": "rec"})
    window._wrapped_text(ui, "problem", "text", "test")

    assert [call.args[0] for call in ui.rect.call_args_list] == ["frmPlan", "problem"]
    imgui.get_window_draw_list.assert_not_called()


def test_wrapped_text_skips_missing_component_and_restores_unscaled_text(monkeypatch):
    imgui = _imgui_mock(monkeypatch)
    window = AdvisorRecommendationWindow(Mock(), "USA")
    ui = Mock()
    ui.path.side_effect = lambda slot: slot
    rect = SimpleNamespace(x=10.0, y=20.0, width=100.0, height=30.0)
    component = SimpleNamespace(font_size=None, text_offset=(0.0, 0.0))
    session = SimpleNamespace(
        window_position=(5.0, 7.0),
        layout=SimpleNamespace(component=Mock(side_effect=[None, component])),
    )
    ui.rect.side_effect = [None, rect]
    monkeypatch.setattr(advisor_module, "active_gml_layout", lambda: session)

    window._wrapped_text(ui, "missing", "ignored", "missing")
    window._wrapped_text(ui, "problem", "wrapped", "visible")

    imgui.text_wrapped.assert_called_once_with("wrapped", gml_id="problem", test_id="visible")
    assert imgui.push_font.call_count == 0
    assert imgui.pop_font.call_count == 0
    assert imgui.pop_text_wrap_pos.call_count == 1
    assert imgui.get_window_draw_list.return_value.pop_clip_rect.call_count == 1
