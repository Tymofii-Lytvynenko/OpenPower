from types import SimpleNamespace
from unittest.mock import Mock

import src.client.ui.components.hud.unit_order_targeting_prompt as targeting_module
from src.client.ui.components.hud.unit_order_targeting_prompt import UnitOrderTargetingPrompt


def _imgui_mock():
    imgui = Mock()
    imgui.Cond_.always = 1
    imgui.WindowFlags_.no_decoration = 1
    imgui.WindowFlags_.no_move = 2
    imgui.WindowFlags_.no_saved_settings = 4
    imgui.WindowFlags_.always_auto_resize = 8
    imgui.get_io.return_value.display_size = SimpleNamespace(x=800, y=600)
    return imgui


def test_render_does_nothing_without_an_active_order(monkeypatch):
    imgui = _imgui_mock()
    monkeypatch.setattr(targeting_module, "imgui", imgui)

    UnitOrderTargetingPrompt().render(None, Mock())

    imgui.get_io.assert_not_called()
    imgui.begin.assert_not_called()


def test_render_balances_closed_window_and_displays_move_and_attack_modes(monkeypatch):
    imgui = _imgui_mock()
    imgui.begin.side_effect = [(False, None), (True, None), (True, None)]
    imgui.button.side_effect = [False, True]
    monkeypatch.setattr(targeting_module, "imgui", imgui)
    on_cancel = Mock()
    panel = UnitOrderTargetingPrompt()

    panel.render("move", on_cancel)
    panel.render("move", on_cancel)
    panel.render("attack", on_cancel)

    assert imgui.end.call_count == 3
    assert [call.args[0] for call in imgui.text.call_args_list] == [
        "MOVE — click a destination. Esc or right-click cancels.",
        "ATTACK MOVE — click a destination. Hostile contact triggers combat; neutral entry needs confirmation.",
    ]
    assert imgui.same_line.call_count == 2
    assert imgui.button.call_count == 2
    on_cancel.assert_called_once_with()
    assert all(call.args[0] == (400.0, 48.0) for call in imgui.set_next_window_pos.call_args_list)
