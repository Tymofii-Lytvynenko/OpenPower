from __future__ import annotations

from contextlib import contextmanager
import importlib
from types import SimpleNamespace
from unittest.mock import Mock

import polars as pl

from src.client.ui.components.shared.battle_summary_dialog import (
    BattleSummaryDialog,
    _category_loss_counts,
    _combat_side,
    _outcome_for_side,
)


class _Widgets:
    def __init__(self):
        self.text_calls = []

    def text(self, *args, **kwargs):
        self.text_calls.append((args, kwargs))

    def path(self, value):
        return value


def _install_render_mocks(monkeypatch, *, opened: bool):
    module = importlib.import_module("src.client.ui.components.shared.battle_summary_dialog")
    imgui = Mock()
    imgui.get_io.return_value = SimpleNamespace(
        display_size=SimpleNamespace(x=1280.0, y=720.0)
    )
    imgui.is_item_hovered.return_value = True
    ui = _Widgets()
    flags = Mock()

    @contextmanager
    def window(*_args, **_kwargs):
        yield opened

    @contextmanager
    def child_frame(*_args, **_kwargs):
        yield True

    monkeypatch.setattr(module, "imgui", imgui)
    monkeypatch.setattr(module.WindowManager, "window", window)
    monkeypatch.setattr(module, "GMLWidgets", lambda *_args: ui)
    monkeypatch.setattr(module, "FlagRenderer", lambda: flags)
    monkeypatch.setattr(module, "center_window", lambda *_args: (10.0, 20.0))
    monkeypatch.setattr(module, "gml_child_frame", child_frame)
    monkeypatch.setattr(module, "resolve_region_name", lambda _state, region_id: f"Region {region_id}")
    monkeypatch.setattr(module, "resolve_country_name", lambda _state, tag: f"Country {tag}")
    return module, imgui, ui, flags


def test_dialog_state_returns_without_result_and_dismisses_closed_window(monkeypatch) -> None:
    _module, imgui, _ui, _flags = _install_render_mocks(monkeypatch, opened=False)
    dialog = BattleSummaryDialog()

    dialog.render(None)
    dialog.show({"region_id": 7, "battle_id": "battle-1"}, losses=[])
    dialog.render(SimpleNamespace(tables={}))

    assert dialog._result is None
    assert dialog._losses is None
    assert imgui.get_io.call_count == 1


def test_open_dialog_renders_country_lists_and_loss_outcomes(monkeypatch) -> None:
    module, imgui, ui, flags = _install_render_mocks(monkeypatch, opened=True)
    dialog = BattleSummaryDialog(test_prefix="summary-test")
    dialog.show(
        {
            "region_id": 7,
            "battle_id": "battle-1",
            "side_a_country_ids": ["USA"],
            "side_a_losses": 3,
            "side_b_losses": 0,
            "victor_side": "SIDE_A",
        }
    )
    state = SimpleNamespace(tables={
        "battles": pl.DataFrame([{
            "id": "battle-1",
            "defender_side": [],
            "attacker_side": ["CAN"],
        }]),
    })

    dialog.render(state)

    assert flags.draw_flag.call_args.args == ("USA", 22.0, 13.0)
    assert any(args[0] == "Not recorded" for args, _kwargs in imgui.text.call_args_list)
    assert any(args[0] == "USA" for args, _kwargs in imgui.text.call_args_list)
    assert any(kwargs.get("test_id") == "summary-test.outcome.A" for _args, kwargs in ui.text_calls)
    imgui.set_tooltip.assert_called_once_with("Country USA")

    cursor_calls = imgui.set_cursor_pos.call_count

    @contextmanager
    def closed_child_frame(*_args, **_kwargs):
        yield False

    monkeypatch.setattr(module, "gml_child_frame", closed_child_frame)
    dialog._render_countries(state, ui, "frmSideB", "B", ("CAN",))

    assert imgui.set_cursor_pos.call_count == cursor_calls


def test_loss_and_outcome_helpers_validate_detail_totals() -> None:
    losses = [
        {"side": "ATTACKERS", "unit_type": "infantry", "losses": 3},
        {"side": "DEFENDERS", "unit_type": "naval", "losses": 4},
    ]

    assert _category_loss_counts(None, "SIDE_A", 0) is None
    assert _category_loss_counts(losses, "SIDE_A", 3) == {"I": 3, "G": 0, "A": 0, "N": 0}
    assert _category_loss_counts(losses, "SIDE_A", 2) is None
    assert _category_loss_counts(
        [{"side": "SIDE_A", "unit_type": "unknown", "losses": 1}], "SIDE_A", 1
    ) is None
    assert _combat_side("side-a") == "SIDE_A"
    assert _combat_side("side b") == "SIDE_B"
    assert _combat_side("unassigned") == ""
    assert _outcome_for_side({"victor_side": "A"}, "SIDE_A", ()) == "Victory"
    assert _outcome_for_side({"victor_side": "A"}, "SIDE_B", ()) == "Defeat"
    assert _outcome_for_side({"victor_tag": "unknown"}, "SIDE_A", ("USA",)) == "Unknown"
    assert _outcome_for_side({"victor_tag": "USA"}, "SIDE_A", ("USA",)) == "Victory"
    assert _outcome_for_side({"victor_tag": "USA"}, "SIDE_A", ("CAN",)) == "Defeat"
    assert _outcome_for_side({"victor_tag": "USA"}, "SIDE_A", ()) == "Unknown"
