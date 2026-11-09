from __future__ import annotations

from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock

from src.client.ui.components.shared.dirty_close_confirmation import CloseDecision
from src.client.ui.panels import resources_panel as resources_panel_module
from src.client.ui.panels.resources_panel import ResourcePolicyDraft, ResourcesPanel


def render_imgui():
    from unittest.mock import MagicMock

    ui = MagicMock()
    ui.Col_.button = 1
    ui.StyleVar_.frame_padding = 1
    return ui


def render_context(client, *, own=True):
    return SimpleNamespace(
        target_tag="usa",
        is_own_country=own,
        net_client=client,
        save_confirmation_preferences=None,
    )


def test_render_applies_dirty_policy_and_dispatches_production_dialog(monkeypatch) -> None:
    panel = ResourcesPanel()
    panel._policy_drafts[("USA", "grain")] = ResourcePolicyDraft(0, 0, 0, 1, 1, 20)
    panel._increase_production_dialog = SimpleNamespace(
        is_open=True,
        country_tag="USA",
        resource_id="grain",
        render=Mock(return_value=15),
    )
    panel._render_content = Mock()
    panel.close_confirmation.render = Mock(return_value=None)
    client = SimpleNamespace(player_id="player-1", send_action=Mock())
    state = SimpleNamespace(journal=SimpleNamespace(command_results=[]), tables={})
    ui = render_imgui()
    monkeypatch.setattr(resources_panel_module, "imgui", ui)
    monkeypatch.setattr(resources_panel_module.WindowManager, "window", lambda *args, **kwargs: nullcontext(True))
    monkeypatch.setattr(resources_panel_module.Prims, "button", Mock(return_value=True))

    keep_open = panel.render(state, render_context(client))

    assert keep_open is True
    panel._render_content.assert_called_once_with(state, "usa", True)
    panel.close_confirmation.render.assert_called_once()
    panel._increase_production_dialog.render.assert_called_once_with(state, can_apply=True)
    assert client.send_action.call_count == 2
    policy_action, production_action = [call.args[0] for call in client.send_action.call_args_list]
    assert policy_action.resource_id == "grain"
    assert policy_action.tax_rate == 0.2
    assert production_action.resource_id == "grain"
    assert production_action.increase_percent == 15


def test_render_consumes_navigation_close_and_discards_dirty_draft(monkeypatch) -> None:
    panel = ResourcesPanel()
    panel._policy_drafts[("USA", "grain")] = ResourcePolicyDraft(0, 0, 0, 1, 0, 10)
    panel.has_unsaved_changes = True
    panel.selected_resource = "grain"
    panel.request_close()
    panel.close_confirmation.request_close = Mock(return_value=CloseDecision.DISCARD)
    panel._render_content = Mock()
    ui = render_imgui()
    monkeypatch.setattr(resources_panel_module, "imgui", ui)
    monkeypatch.setattr(resources_panel_module.WindowManager, "window", lambda *args, **kwargs: nullcontext(True))
    client = SimpleNamespace(player_id="player-1", send_action=Mock())
    state = SimpleNamespace(tables={"domestic_production": None})

    keep_open = panel.render(state, render_context(client))

    assert keep_open is False
    panel.close_confirmation.request_close.assert_called_once()
    panel._render_content.assert_not_called()
    assert set(panel._policy_drafts) == {("USA", "grain")}
    assert panel._policy_drafts[("USA", "grain")].is_dirty is False
    assert panel.current_policy_key == ("USA", "grain")
    assert client.send_action.call_count == 0


def test_render_closes_clean_panel_without_dirty_confirmation(monkeypatch) -> None:
    panel = ResourcesPanel()
    panel._render_content = Mock()
    panel.close_confirmation.render = Mock()
    ui = render_imgui()
    monkeypatch.setattr(resources_panel_module, "imgui", ui)
    monkeypatch.setattr(resources_panel_module.WindowManager, "window", lambda *args, **kwargs: nullcontext(False))

    keep_open = panel.render(SimpleNamespace(tables={}), render_context(None))

    assert keep_open is False
    panel.close_confirmation.render.assert_not_called()
    panel._render_content.assert_not_called()


def test_render_finishes_close_when_confirmation_returns_a_decision(monkeypatch) -> None:
    panel = ResourcesPanel()
    panel._render_content = Mock()
    panel.close_confirmation.render = Mock(return_value=CloseDecision.DISCARD)
    panel._finish_close = Mock()
    ui = render_imgui()
    monkeypatch.setattr(resources_panel_module, "imgui", ui)
    monkeypatch.setattr(resources_panel_module.WindowManager, "window", lambda *args, **kwargs: nullcontext(True))
    monkeypatch.setattr(resources_panel_module.Prims, "button", Mock(return_value=False))
    state = SimpleNamespace(tables={})

    keep_open = panel.render(state, render_context(None))

    assert keep_open is False
    panel.close_confirmation.render.assert_called_once()
    panel._finish_close.assert_called_once_with(CloseDecision.DISCARD, state, "usa", None)
