from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

from src.client.ui.panels.military import battle_inspection_windows as windows_module
from src.client.ui.panels.military.battle_inspection_windows import BattleInspectionWindows


class FakeWidgets:
    buttons = set()
    calls = []

    def __init__(self, root):
        self.root = root

    def path(self, slot):
        return f"{self.root}/{slot}"

    def button(self, slot, label, test_id, **kwargs):
        self.calls.append(("button", self.root, slot, label, test_id, kwargs))
        return test_id in self.buttons

    def text(self, slot, value, **kwargs):
        self.calls.append(("text", self.root, slot, value, kwargs))

    def picture(self, slot, callback):
        self.calls.append(("picture", self.root, slot, callback))

    def meter(self, slot, value, color, **kwargs):
        self.calls.append(("meter", self.root, slot, value, color, kwargs))


class FakeSelection:
    STRATEGIES = ("defend", "attack", "retreat")

    def __init__(self):
        self.battle_id = ""
        self.country = "UKR"
        self.full = False
        self.open = Mock(side_effect=self._open)
        self.close = Mock(side_effect=self._close)

    def _open(self, _state, battle_id):
        self.battle_id = battle_id
        return True

    def _close(self):
        self.battle_id = ""


def install(monkeypatch, *, window_open=True, children=True, buttons=(), country_clicks=()):
    imgui = Mock()
    imgui.WindowFlags_ = SimpleNamespace(no_title_bar=1, horizontal_scrollbar=2)
    imgui.combo.return_value = (False, 0)
    imgui.is_item_hovered.return_value = False
    imgui.invisible_button.side_effect = lambda _label, *args, **kwargs: kwargs.get("test_id") in set(country_clicks)
    imgui.get_item_rect_min.return_value = SimpleNamespace(x=2, y=3)
    imgui.get_item_rect_max.return_value = SimpleNamespace(x=20, y=30)
    imgui.get_color_u32.return_value = "accent"
    FakeWidgets.buttons = set(buttons)
    FakeWidgets.calls = []
    monkeypatch.setattr(windows_module, "imgui", imgui)
    monkeypatch.setattr(windows_module, "GMLWidgets", FakeWidgets)
    monkeypatch.setattr(windows_module, "resolve_country_name", lambda _state, tag: f"Name:{tag}")
    monkeypatch.setattr(windows_module, "resolve_region_name", lambda _state, region: f"Region:{region}")
    monkeypatch.setattr(windows_module, "normalize_side", lambda side: list(side or []))
    monkeypatch.setattr(windows_module, "observed_category_counts", lambda *_args: None)
    monkeypatch.setattr(windows_module, "category_counts", lambda *_args: {key: 0 for key in "IGAN"})
    child_results = list(children) if isinstance(children, (tuple, list)) else [children]

    @contextmanager
    def window(*_args, **_kwargs):
        yield window_open

    @contextmanager
    def child(*_args, **_kwargs):
        yield child_results.pop(0) if child_results else False

    monkeypatch.setattr(windows_module.WindowManager, "window", staticmethod(window))
    monkeypatch.setattr(windows_module, "gml_child_frame", child)
    selection = FakeSelection()
    selection.recorded_losses = Mock(return_value=[])
    selection.own_postures = Mock(return_value=[])
    selection.groups = Mock(return_value=[])
    selection.poll_result = Mock(return_value=None)
    selection.display_row = Mock(return_value=None)
    selection.command = Mock(return_value=True)
    summary = Mock()
    flags = Mock()
    monkeypatch.setattr(windows_module, "BattleInspection", lambda *_args: selection)
    monkeypatch.setattr(windows_module, "BattleSummaryDialog", lambda *_args: summary)
    monkeypatch.setattr(windows_module, "FlagRenderer", lambda: flags)
    client = SimpleNamespace(player_id="player-1", send_action=Mock())
    windows = BattleInspectionWindows(client, "UKR")
    return windows, selection, summary, flags, imgui


def test_open_close_and_render_lifecycle_dispatch(monkeypatch):
    windows, selection, summary, _flags, _imgui = install(monkeypatch)
    windows._ally, windows._enemy, windows._strategy, windows._selected_force = "POL", "DEU", 2, "key"
    state = object()

    assert windows.open(state, 42) is True
    selection.open.assert_called_once_with(state, "42")
    assert (windows._ally, windows._enemy, windows._strategy, windows._selected_force) == ("", "", 0, None)
    summary.dismiss.assert_called_once_with()
    selection.open.side_effect = None
    selection.open.return_value = False
    assert windows.open(state, "missing") is False

    selection.battle_id = ""
    windows.render(object())
    selection.poll_result.assert_not_called()

    selection.battle_id = "battle-1"
    selection.poll_result.return_value = {"event_type": "EventBattleEnded"}
    selection.display_row.return_value = None
    windows.render(object())
    summary.show.assert_called_once_with(
        {"event_type": "EventBattleEnded"}, losses=[],
    )
    selection.close.assert_called_once_with()


def test_render_dispatches_small_and_full_views_and_renders_summary(monkeypatch):
    windows, selection, summary, _flags, _imgui = install(monkeypatch)
    windows._render_small = Mock()
    windows._render_full = Mock()
    selection.battle_id = "battle-1"
    selection.display_row.return_value = {"id": "battle-1"}
    selection.full = False

    windows.render(object())
    windows._render_small.assert_called_once()
    summary.render.assert_called_once()

    windows._render_small.reset_mock()
    summary.render.reset_mock()
    selection.full = True
    windows.render(object())
    windows._render_full.assert_called_once()
    summary.render.assert_called_once()


def test_small_inspection_shows_observed_and_unknown_country_rows(monkeypatch):
    windows, _selection, _summary, flags, imgui = install(monkeypatch, children=[True, True])
    imgui.is_item_hovered.return_value = True
    monkeypatch.setattr(
        windows_module,
        "observed_category_counts",
        lambda _state, _row, side: (
            None if side == "B" else {"I": 1, "G": 2, "A": 0, "N": 3}
        ),
    )
    row = {"defender_side": ["UKR", "POL"], "attacker_side": []}

    windows._render_small(object(), row)

    flags.draw_flag.assert_has_calls([
        unittest_call("UKR", 22.0, 13.0),
        unittest_call("POL", 22.0, 13.0),
    ])
    assert any(call.args == ("Unknown",) for call in imgui.text.call_args_list)
    assert any(call[0] == "text" and call[3] == "—" for call in FakeWidgets.calls)
    assert any(call[0] == "text" and call[3] == "3" for call in FakeWidgets.calls)
    assert any(
        call[0] == "text" and call[2] == "frmSideA" and call[3] == "Counts not observed"
        for call in FakeWidgets.calls
    )


def unittest_call(*args):
    from unittest.mock import call
    return call(*args)


def test_small_inspection_closes_when_native_window_is_hidden(monkeypatch):
    windows, selection, summary, _flags, _imgui = install(monkeypatch, window_open=False)

    windows._render_small(object(), {})

    selection.close.assert_called_once_with()
    summary.dismiss.assert_called_once_with()


def test_full_inspection_closes_on_window_exit_and_rejects_unavailable_window(monkeypatch):
    windows, selection, _summary, _flags, _imgui = install(monkeypatch, window_open=False)
    windows._render_full(object(), {})
    selection.close.assert_called_once_with()

    windows, selection, _summary, _flags, _imgui = install(
        monkeypatch, buttons={"battle.inspection.close"},
    )
    windows._render_full(object(), {"region_id": 1})
    selection.close.assert_called_once_with()
    assert any(call[0] == "text" and call[3] == "Region:1" for call in FakeWidgets.calls)


def test_full_inspection_renders_sides_forces_positions_and_strategy_commands(monkeypatch):
    windows, selection, _summary, flags, imgui = install(
        monkeypatch, children=[True, True, True, True],
        buttons={"battle.inspection.retreat"},
        country_clicks={"battle.inspection.country.POL", "battle.inspection.country.DEU"},
    )
    selection.battle_id = "battle-1"
    selection.country = "UKR"
    selection.STRATEGIES = ("defend", "attack", "retreat")
    selection.groups.return_value = [
        {"country_id": "UKR", "side": "SIDE_A", "unit_type": "infantry", "unit_count": 2},
    ]
    state = object()
    imgui.combo.return_value = (True, 1)
    monkeypatch.setattr(windows_module, "render_battle_force_cards", Mock())
    monkeypatch.setattr(windows_module, "render_battle_positions", Mock())
    monkeypatch.setattr(windows_module, "category_counts", lambda _groups, side: {
        "I": 2 if side == "A" else 1, "G": 0, "A": 0, "N": 0,
    })
    row = {
        "region_id": 12, "attacker_side": ["UKR", "FRA"],
        "defender_side": ["POL", "DEU"], "balance": 1.5,
        "status": "active", "mode": "land", "round": 3,
    }

    windows._render_full(state, row)

    assert windows._ally == "UKR"
    assert windows._enemy in {"POL", "DEU"}
    flags.draw_flag.assert_any_call("UKR", 22.0, 13.0)
    flags.draw_flag.assert_any_call("FRA", 22.0, 13.0)
    assert any(call[0] == "meter" and call[3] == 1.0 for call in FakeWidgets.calls)
    windows_module.render_battle_force_cards.assert_called_once()
    windows_module.render_battle_positions.assert_called_once()
    assert windows_module.render_battle_positions.call_args.kwargs["own_side"] == "A"
    selection.command.assert_any_call(state, "attack")
    selection.command.assert_any_call(state, "retreat")
    assert imgui.begin_disabled.call_args.args == (False,)


def test_country_flag_grid_handles_visibility_empty_side_selection_and_rows(monkeypatch):
    windows, _selection, _summary, flags, imgui = install(
        monkeypatch,
        children=[False, True, True, True],
        country_clicks={"battle.inspection.country.DEU", "battle.inspection.country.POL"},
    )
    imgui.is_item_hovered.return_value = True
    windows._ally = "UKR"
    windows._enemy = ""
    state = object()

    windows._render_country_flag_grid(
        state, FakeWidgets("Battle_Window"), "lstFlagsYou",
        ["UKR", "POL", "DEU", "FRA", "ITA", "ESP", "NLD", "SWE"], own=True,
    )
    assert flags.draw_flag.call_count == 0

    windows._render_country_flag_grid(
        state, FakeWidgets("Battle_Window"), "lstFlagsYou", [], own=True,
    )
    imgui.text_disabled.assert_called_once_with("Unknown")

    windows._render_country_flag_grid(
        state, FakeWidgets("Battle_Window"), "lstFlagsYou",
        ["UKR", "POL", "DEU", "FRA", "ITA", "ESP", "NLD", "SWE"], own=True,
    )
    assert flags.draw_flag.call_count == 8
    assert (1.0, 16.0) in [call.args[0] for call in imgui.set_cursor_pos.call_args_list]
    assert windows._ally == "DEU"
    assert imgui.set_tooltip.call_count == 8
    imgui.get_window_draw_list.return_value.add_rect.assert_called()

    windows._render_country_flag_grid(
        state, FakeWidgets("Battle_Window"), "lstFlagsEnemy", ["POL"], own=False,
    )
    assert windows._enemy == "POL"


def test_force_summary_selects_force_and_reports_public_categories(monkeypatch):
    windows, selection, _summary, _flags, imgui = install(monkeypatch)
    selection.country = "UKR"
    selection.recorded_losses.return_value = [{"losses": 1}]
    selection.own_postures.return_value = [{"strategy": "defend"}]
    groups = [{"country_id": "UKR", "unit_type": "infantry"}]
    state = object()
    monkeypatch.setattr(windows_module, "render_battle_force_cards", Mock())
    monkeypatch.setattr(windows_module, "category_counts", lambda _groups, side: {
        "I": 1, "G": 2, "A": 3, "N": 4,
    })

    windows._render_forces(
        state,
        {"mode": "air_defense", "round": 2, "status": "active"},
        groups,
    )
    windows._select_force(("UKR", "infantry"))

    assert windows._selected_force == ("UKR", "infantry")
    assert windows_module.render_battle_force_cards.call_args.args[0] == groups
    assert windows_module.render_battle_force_cards.call_args.kwargs["active"] is True
    assert imgui.text.call_count == 4
