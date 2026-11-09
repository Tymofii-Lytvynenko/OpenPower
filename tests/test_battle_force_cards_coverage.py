from types import SimpleNamespace
from unittest.mock import Mock

import src.client.ui.panels.military.battle_force_cards as force_cards_module
from src.client.ui.panels.military.battle_force_cards import render_battle_force_cards


def imgui_stub(monkeypatch, *, child_open=True, selected=(False, False), clicked_strategy=""):
    imgui = Mock()
    imgui.TableFlags_.borders_inner = 1
    imgui.ChildFlags_.borders = 2
    imgui.begin_table.return_value = True
    imgui.begin_child.side_effect = child_open if isinstance(child_open, list) else lambda *_args, **_kwargs: child_open
    imgui.get_content_region_avail.return_value = SimpleNamespace(x=180.0)
    imgui.selectable.return_value = selected
    imgui.small_button.side_effect = lambda _label, *, test_id=None: str(test_id).endswith(f".{clicked_strategy}")
    monkeypatch.setattr(force_cards_module, "imgui", imgui)
    return imgui


def test_render_cards_shows_losses_postures_and_dispatches_selected_force_orders(monkeypatch):
    imgui = imgui_stub(monkeypatch, child_open=[True, False], selected=(True, False), clicked_strategy="attack")
    empty = Mock()
    monkeypatch.setattr(force_cards_module, "draw_empty_state", empty)
    groups = [{
        "side": "A", "country_id": "USA", "unit_type": "infantry", "unit_count": 1,
        "strength": 100, "relative_positions": [],
    }]
    losses = [
        {"side": "A", "country_id": "USA", "unit_type": "infantry", "losses": 5},
        {"side": "B", "country_id": "CAN", "unit_type": "armor", "losses": 8},
        {"side": "", "country_id": "", "unit_type": "", "losses": 100},
    ]
    postures = [
        {"country_id": "usa", "unit_type": "Infantry", "strategy": "hold position"},
        {"country_id": "USA", "unit_type": "infantry", "strategy": "hold position"},
        {"country_id": "", "unit_type": "infantry", "strategy": "attack"},
    ]
    commands = []
    selected = []

    render_battle_force_cards(
        groups,
        "USA",
        "CAN",
        "USA",
        active=True,
        command=lambda *args: commands.append(args),
        losses=losses,
        postures=postures,
        selected_force=("USA", "infantry"),
        on_select=selected.append,
    )

    assert commands == [("attack", "infantry")]
    assert selected == [("USA", "infantry")]
    assert empty.call_count == 0
    assert imgui.end_child.call_count == 2
    assert imgui.end_disabled.call_count == 1
    assert any("Recorded casualties: 5 personnel" in call.args[0] for call in imgui.text_disabled.call_args_list)
    assert any("Hold Position ×2" in call.args[0] for call in imgui.text_disabled.call_args_list)
    assert imgui.small_button.call_count == 4


def test_render_cards_handles_missing_groups_closed_children_and_disabled_orders(monkeypatch):
    empty = Mock()
    monkeypatch.setattr(force_cards_module, "draw_empty_state", empty)
    imgui = imgui_stub(monkeypatch, child_open=True, clicked_strategy="attack")

    render_battle_force_cards([], "USA", "CAN", "USA", active=False, command=Mock())

    assert empty.call_count == 2
    assert imgui.begin_child.call_count == 0

    imgui = imgui_stub(monkeypatch, child_open=[True, False], selected=(False, False), clicked_strategy="")
    render_battle_force_cards(
        [{"side": "A", "country_id": "USA", "unit_type": "armor", "unit_count": 2, "strength": 300}],
        "USA", "CAN", "USA", active=False, command=Mock(),
    )

    assert imgui.begin_disabled.call_args.args == (True,)
    assert imgui.end_disabled.call_count == 1
    assert imgui.end_child.call_count == 1


def test_render_cards_returns_when_the_table_cannot_be_opened(monkeypatch):
    imgui = imgui_stub(monkeypatch)
    imgui.begin_table.return_value = False
    empty = Mock()
    monkeypatch.setattr(force_cards_module, "draw_empty_state", empty)

    render_battle_force_cards([], "USA", "CAN", "USA", active=True, command=Mock())

    imgui.table_next_column.assert_not_called()
    empty.assert_not_called()
