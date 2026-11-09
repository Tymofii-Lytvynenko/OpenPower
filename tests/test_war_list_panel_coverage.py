from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import polars as pl

from src.client.ui.panels.military import war_list_panel as war_ui
from src.client.ui.panels.military.war_list_panel import WarListPanel
from src.shared.actions import ActionJoinWar, ActionOfferPeace


class RecordingWidgets:
    results = {}
    calls = []

    def __init__(self, root):
        self.root = root
        self.calls.append(("init", root))

    def path(self, slot):
        return f"{self.root}/{slot}"

    def text(self, slot, value, **kwargs):
        self.calls.append(("text", self.root, slot, value, kwargs))

    def button(self, slot, label, test_id, **kwargs):
        self.calls.append(("button", self.root, slot, label, test_id, kwargs))
        return self.results.get(test_id, False)

    def picture(self, slot, draw):
        self.calls.append(("picture", self.root, slot))
        draw(22.0, 13.0)


class FakeClient:
    player_id = "player-1"

    def __init__(self):
        self.actions = []

    def send_action(self, action):
        self.actions.append(action)


def context(*, own=True, tag="UKR", client=None):
    return SimpleNamespace(is_own_country=own, target_tag=tag, net_client=client)


def country_state():
    return SimpleNamespace(tables={
        "countries": pl.DataFrame({"id": ["UKR", "POL", "USA"], "name": ["Ukraine", "Poland", "United States"]})
    })


def war(war_id="war-1", *, side_a=None, side_b=None, leader_a="UKR", leader_b="POL"):
    return {
        "id": war_id,
        "leader_a": leader_a,
        "leader_b": leader_b,
        "side_a": side_a if side_a is not None else [leader_a, "USA"],
        "side_b": side_b if side_b is not None else [leader_b],
        "intent_a": "peace",
        "intent_b": "war",
    }


def install_widgets(monkeypatch):
    RecordingWidgets.results = {}
    RecordingWidgets.calls = []
    monkeypatch.setattr(war_ui, "GMLWidgets", RecordingWidgets)
    return RecordingWidgets


def install_imgui(monkeypatch, *, origin=(10.0, 20.0), width=600.0):
    native = MagicMock()
    native.Col_.button = "button"
    native.Col_.button_hovered = "button_hovered"
    native.Col_.button_active = "button_active"
    native.get_cursor_screen_pos.return_value = SimpleNamespace(x=origin[0], y=origin[1])
    native.get_content_region_avail.return_value = SimpleNamespace(x=width)
    native.get_window_draw_list.return_value = MagicMock()
    native.get_color_u32.side_effect = lambda value: value
    native.calc_text_size.side_effect = lambda text: SimpleNamespace(x=float(len(str(text)) * 5), y=10.0)
    native.get_main_viewport.return_value.size = SimpleNamespace(x=1000.0, y=800.0)
    native.is_item_hovered.return_value = False
    native.is_mouse_hovering_rect.return_value = False
    monkeypatch.setattr(war_ui, "imgui", native)
    monkeypatch.setattr(war_ui.Prims, "fit_text", lambda text, _width: str(text))
    return native


def install_child_frame(monkeypatch, *, visible=True):
    calls = []

    @contextmanager
    def child(path, **kwargs):
        calls.append((path, kwargs))
        yield visible

    monkeypatch.setattr(war_ui, "gml_child_frame", child)
    return calls


def test_render_centers_window_and_returns_false_when_window_is_closed(monkeypatch):
    native = install_imgui(monkeypatch)
    monkeypatch.setattr(war_ui, "get_gml_layout", lambda _name: SimpleNamespace(width=600, height=400))
    calls = []

    @contextmanager
    def window(*args, **kwargs):
        calls.append((args, kwargs))
        yield True

    monkeypatch.setattr(war_ui.WindowManager, "window", window)
    panel = WarListPanel()
    panel._render_content = Mock()
    assert panel.render(None, context()) is True
    assert calls[0][1]["x"] == 200.0
    assert calls[0][1]["y"] == 200.0
    panel._render_content.assert_called_once()

    @contextmanager
    def closed_window(*_args, **_kwargs):
        yield False

    monkeypatch.setattr(war_ui.WindowManager, "window", closed_window)
    assert panel.render(None, context()) is False
    assert native.get_main_viewport.called


def test_content_selects_current_war_and_routes_overview_or_peace_page(monkeypatch):
    widgets = install_widgets(monkeypatch)
    panel = WarListPanel()
    wars = [war("first"), war("second")]
    game_state = country_state()
    render_context = context()
    panel._presenter.all_wars = Mock(return_value=wars)
    panel._draw_page_icon = Mock()
    panel._render_war_overview = Mock()
    panel._render_peace_page = Mock()
    widgets.results["war_list.page"] = False
    panel._render_content(game_state, render_context)
    assert panel._selected_war_id == "first"
    panel._render_war_overview.assert_called_once_with(game_state, wars, wars[0], render_context)

    panel._selected_war_id = "missing"
    panel._show_peace_page = True
    panel._render_content(game_state, render_context)
    assert panel._selected_war_id == "first"
    panel._render_peace_page.assert_called_once()

    panel._presenter.all_wars.return_value = []
    panel._selected_war_id = None
    panel._render_content(game_state, render_context)
    panel._render_peace_page.assert_called_with(game_state, None, render_context)
    assert panel._draw_page_icon.call_count == 3
    assert panel._selected_war([]) is None


def test_title_button_toggles_peace_page_and_empty_overview_keeps_selection(monkeypatch):
    widgets = install_widgets(monkeypatch)
    panel = WarListPanel()
    panel._presenter.all_wars = Mock(return_value=[])
    panel._draw_page_icon = Mock()
    panel._render_war_overview = Mock()
    panel._render_peace_page = Mock()
    widgets.results["war_list.page"] = True

    game_state = country_state()
    render_context = context()
    panel._render_content(game_state, render_context)

    assert panel._show_peace_page is True
    button_call = next(call for call in widgets.calls if call[0] == "button")
    assert button_call[5]["tooltip"] == "Open structured peace terms"
    panel._render_peace_page.assert_called_once_with(game_state, None, render_context)


def test_overview_composes_war_list_and_details_and_list_respects_frame_visibility(monkeypatch):
    widgets = install_widgets(monkeypatch)
    panel = WarListPanel()
    game_state = country_state()
    render_context = context()
    wars = [war()]
    selected = wars[0]
    panel._render_war_list = Mock()
    panel._render_details = Mock()
    panel._render_war_overview(game_state, wars, selected, render_context)
    panel._render_war_list.assert_called_once_with(game_state, wars)
    panel._render_details.assert_called_once_with(game_state, selected, render_context)

    panel = WarListPanel()
    panel._render_war_rows = Mock()
    child_calls = install_child_frame(monkeypatch, visible=False)
    panel._render_war_list(game_state, wars)
    assert [call[2] for call in widgets.calls if call[0] == "text"] == [
        "txtTransparentLabel1", "txtTransparentLabel2",
        "txtTransparentLabel4", "txtTransparentLabel3",
    ]
    assert child_calls[0] == (
        "War_List_Window/frmInner/frmWarList/lstWar",
        {"padding": (0.0, 0.0), "bordered": True},
    )
    panel._render_war_rows.assert_not_called()

    install_child_frame(monkeypatch, visible=True)
    panel._render_war_list(game_state, wars)
    panel._render_war_rows.assert_called_once_with(game_state, wars)


def test_war_list_rows_draw_empty_notice_select_rows_and_normalize_display(monkeypatch):
    native = install_imgui(monkeypatch, origin=(20.0, 30.0), width=700.0)
    panel = WarListPanel()
    panel._draw_flag_at = Mock()
    panel._selected_war_id = "first"
    panel._render_war_rows(country_state(), [])
    native.text_disabled.assert_called_once_with("No active wars")
    assert native.set_cursor_screen_pos.call_args.args == ((24.0, 33.0),)

    native.set_cursor_screen_pos.reset_mock()
    native.text_disabled.reset_mock()
    native.invisible_button.side_effect = [False, True]
    native.is_item_hovered.side_effect = [False, True]
    panel._render_war_rows(country_state(), [war("first"), war("second", leader_a="usa")])
    assert panel._selected_war_id == "second"
    assert native.invisible_button.call_args_list[0].args[1] == (492.0, 16.0)
    assert native.get_window_draw_list.return_value.add_rect_filled.call_count == 2
    assert panel._draw_flag_at.call_count == 4
    assert native.set_cursor_screen_pos.call_args_list[-1].args == ((20.0, 62.0),)


def test_draw_cell_aligns_right_and_clamps_oversized_text_width(monkeypatch):
    native = install_imgui(monkeypatch)
    draw = Mock()
    WarListPanel._draw_cell(draw, 10, 20, 4, "Text", "color", align="right")
    draw.add_text.assert_called_once_with((10, 20), "color", "Text")
    assert WarListPanel._tag("  usa ") == "USA"
    assert WarListPanel._tag(None) == ""
    assert WarListPanel._intent(" PEACE ") == "peace"
    assert WarListPanel._intent(None) == "war"
    assert native.calc_text_size.call_count == 1


def test_details_draw_leaders_status_and_side_lists_for_selected_war(monkeypatch):
    widgets = install_widgets(monkeypatch)
    panel = WarListPanel()
    panel._draw_flag = Mock()
    panel._draw_status_marker = Mock()
    panel._render_member_list = Mock()
    panel._render_side_actions = Mock()
    selected = war(side_a=["UKR", "USA"], side_b=["POL"])

    panel._render_details(country_state(), selected, context())

    text_values = [call[3] for call in widgets.calls if call[0] == "text"]
    assert "Ukraine" in text_values and "Poland" in text_values
    assert [call[2] for call in widgets.calls if call[0] == "picture"] == ["picFlag", "picFlag1"]
    assert panel._draw_status_marker.call_count == 2
    assert panel._render_member_list.call_count == 2
    panel._render_member_list.assert_any_call(
        panel._render_member_list.call_args_list[0].args[0],
        "War_List_Window/frmInner/frmWarDetails/lstWar",
        ["USA"], selected,
        side_name="attacker",
    )
    panel._render_side_actions.assert_called_once()
    assert panel._render_side_actions.call_args.args[0] == selected
    assert panel._render_side_actions.call_args.args[2:] == ("UKR", "POL", "peace", "war")

    panel._render_member_list.reset_mock()
    panel._render_side_actions.reset_mock()
    panel._render_details(country_state(), None, context())
    assert panel._render_member_list.call_count == 0
    assert panel._render_side_actions.call_count == 0


def test_member_list_renders_flags_names_exhaustion_and_skips_hidden_frame(monkeypatch):
    native = install_imgui(monkeypatch)
    install_child_frame(monkeypatch)
    native.get_content_region_avail.return_value.x = 100.0
    native.is_mouse_hovering_rect.side_effect = [True, False]
    panel = WarListPanel()
    panel._draw_flag = Mock()
    panel._draw_cell = Mock()
    panel._war_exhaustion = Mock(side_effect=[31.2, None])
    state = SimpleNamespace(tables={})
    panel._render_member_list(state, "members", ["USA", "FRA"], war(), side_name="attacker")
    assert panel._draw_flag.call_count == 2
    assert panel._draw_cell.call_count == 2
    native.set_tooltip.assert_called_once_with("United States — war exhaustion 31")

    panel._draw_flag.reset_mock()
    install_child_frame(monkeypatch, visible=False)
    panel._render_member_list(state, "members", ["USA"], war(), side_name="attacker")
    panel._draw_flag.assert_not_called()


def test_side_actions_send_join_actions_for_nonparticipant_and_guard_context(monkeypatch):
    widgets = install_widgets(monkeypatch)
    panel = WarListPanel()
    client = FakeClient()
    widgets.results.update({"war_list.join.attacker": True, "war_list.join.defender": True})
    selected = war("w-7")

    panel._render_side_actions(selected, context(tag="FRA", client=client), "UKR", "POL", "peace", "war")
    assert [type(action) for action in client.actions] == [ActionJoinWar, ActionJoinWar]
    assert [action.side for action in client.actions] == ["attacker", "defender"]
    assert all(action.source_country_tag == "FRA" and action.war_id == "w-7" for action in client.actions)

    panel._render_side_actions(selected, context(own=False, tag="USA", client=client), "UKR", "POL", "peace", "war")
    panel._render_side_actions(selected, context(tag="", client=client), "UKR", "POL", "peace", "war")
    assert len(client.actions) == 2


def test_side_members_get_status_actions_and_leader_permissions_control_enablement(monkeypatch):
    install_widgets(monkeypatch)
    panel = WarListPanel()
    panel._render_status_actions = Mock()
    selected = war(side_a=["UKR", "USA"], side_b=["POL"], leader_a="UKR")

    panel._render_side_actions(selected, context(tag="POL", client=FakeClient()), "UKR", "POL", "peace", "war")

    assert panel._render_status_actions.call_count == 2
    assert panel._render_status_actions.call_args_list[0].args[4] is False
    assert panel._render_status_actions.call_args_list[1].args[4] is True


def test_status_actions_dispatch_peace_and_war_and_status_button_restores_style(monkeypatch):
    native = install_imgui(monkeypatch)
    widgets = install_widgets(monkeypatch)
    client = FakeClient()
    panel = WarListPanel()
    panel._status_button = Mock(side_effect=[True, True])
    panel._render_status_actions(context(client=client), "peace", "war", "attacker", True,
                                 "peace", "w-1", "UKR")
    assert len(client.actions) == 2
    assert all(isinstance(action, ActionOfferPeace) for action in client.actions)
    assert [action.terms for action in client.actions] == ["peace", "war"]

    ui = RecordingWidgets("War_List_Window")
    widgets.results["active"] = True
    native.Col_.button = "button"
    assert WarListPanel._status_button(
        ui, "slot", "PEACE", "active", True, True, (0.1, 0.2, 0.3, 1.0), "tooltip"
    ) is True
    assert native.push_style_color.call_count == 3
    native.pop_style_color.assert_called_once_with(3)


def test_peace_page_handles_hidden_missing_war_and_selected_war(monkeypatch):
    native = install_imgui(monkeypatch)
    panel = WarListPanel()
    panel._draw_coalition_summary = Mock()
    panel._peace_editor.render = Mock()

    install_child_frame(monkeypatch, visible=False)
    panel._render_peace_page(country_state(), war(), context(),)
    panel._draw_coalition_summary.assert_not_called()

    install_child_frame(monkeypatch, visible=True)
    panel._render_peace_page(country_state(), None, context())
    native.text_disabled.assert_called_once_with("Select an active war to negotiate peace.")
    panel._render_peace_page(country_state(), war(), context())
    panel._draw_coalition_summary.assert_called_once()
    panel._peace_editor.render.assert_called_once()


def test_markers_icons_exhaustion_and_coalition_summary_cover_missing_and_active_rows(monkeypatch):
    native = install_imgui(monkeypatch)
    panel = WarListPanel()
    rect = SimpleNamespace(x=10, y=20, width=12, height=8)
    ui = RecordingWidgets("War_List_Window")
    ui.rect = Mock(return_value=rect)
    session = SimpleNamespace(window_position=(100, 200))
    monkeypatch.setattr(war_ui, "active_gml_layout", lambda: session)

    panel._draw_status_marker(ui, "picState", "peace")
    panel._draw_status_marker(ui, "picState", "war")
    panel._draw_page_icon(ui)
    panel._show_peace_page = True
    panel._draw_page_icon(ui)
    assert native.get_window_draw_list.return_value.add_circle_filled.call_count == 2
    assert native.get_window_draw_list.return_value.add_line.call_count == 6

    panel._draw_flag = Mock()
    panel._draw_flag_at(5.0, 6.0, "USA")
    assert native.set_cursor_screen_pos.call_args.args == ((5.0, 6.0),)
    panel._draw_flag.assert_called_once_with("USA", 22.0, 13.0)

    monkeypatch.setattr(war_ui, "active_gml_layout", lambda: None)
    panel._draw_status_marker(ui, "missing", "peace")
    panel._draw_page_icon(ui)
    monkeypatch.setattr(war_ui, "active_gml_layout", lambda: session)
    ui.rect.return_value = None
    panel._draw_status_marker(ui, "missing", "war")
    panel._draw_page_icon(ui)

    data = war("w-2")
    exhaustion = pl.DataFrame({"war_id": ["w-2", "w-2"], "country_id": ["ukr", "USA"], "exhaustion_index": [12.5, None]})
    state = SimpleNamespace(tables={"war_exhaustion_states": exhaustion})
    assert panel._war_exhaustion(state, data, "UKR") == 12.5
    assert panel._war_exhaustion(state, data, "POL") is None
    assert panel._war_exhaustion(SimpleNamespace(tables={}), data, "UKR") is None
    assert panel._war_exhaustion(state, None, "UKR") is None

    panel._draw_coalition_summary(SimpleNamespace(tables={}), data)
    panel._draw_coalition_summary(SimpleNamespace(tables={"coalition_pacts": pl.DataFrame()}), data)
    coalitions = pl.DataFrame({
        "id": ["z", "a", "inactive"],
        "status": ["active", "active", "inactive"],
        "primary_target_country_id": ["POL", "UKR", "USA"],
        "member_country_ids": [["USA"], ["UKR", "POL"], ["USA"]],
    })
    panel._draw_coalition_summary(SimpleNamespace(tables={"coalition_pacts": coalitions}), data)
    text = native.text_wrapped.call_args.args[0]
    assert text.index("UKR: UKR, POL") < text.index("POL: USA")


def test_coalition_summary_skips_when_no_active_coalition_matches_war(monkeypatch):
    native = install_imgui(monkeypatch)
    table = pl.DataFrame({
        "id": ["inactive"], "status": ["inactive"],
        "primary_target_country_id": ["POL"], "member_country_ids": [["USA"]],
    })
    panel = WarListPanel()
    panel._draw_coalition_summary(SimpleNamespace(tables={"coalition_pacts": table}), war())
    native.text_wrapped.assert_not_called()
