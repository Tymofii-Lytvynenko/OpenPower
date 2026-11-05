from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock, patch

import polars as pl
import pytest

from src.client.ui.components.hud.panel_manager import PanelManager
from src.client.ui.components.hud.context_menu import ContextMenu
from src.client.ui.components.shared.dirty_close_confirmation import CloseDecision
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.panels.politics.internal_laws_panel import InternalLawsPanel


class DeferredPanel:
    def __init__(self):
        self.requests = 0
        self.keep_open = True

    def request_close(self):
        self.requests += 1

    def render(self, state, context):
        return self.keep_open


def test_navigation_hide_waits_for_panel_resolution():
    manager = PanelManager()
    panel = DeferredPanel()
    manager.register("test", panel, visible=True)
    manager.toggle("test")
    assert manager.is_visible("test")
    assert panel.requests == 1
    manager.render_all(None, None)
    assert manager.is_visible("test")
    panel.keep_open = False
    manager.render_all(None, None)
    assert not manager.is_visible("test")
    manager.toggle("test")
    assert manager.is_visible("test")
    assert panel.requests == 1


def test_panels_without_close_port_keep_immediate_visibility_behavior():
    manager = PanelManager()
    manager.register("test", SimpleNamespace(render=lambda *_: True), visible=True)
    manager.set_visible("test", False)
    assert not manager.is_visible("test")
    manager.toggle("test")
    assert manager.is_visible("test")


def test_context_menu_close_all_respects_deferred_panel_close():
    manager = PanelManager()
    deferred = DeferredPanel()
    manager.register("draft", deferred, visible=True)
    manager.register("simple", SimpleNamespace(render=lambda *_: True), visible=True)
    composer = Mock()
    composer.draw_menu_item.return_value = True
    menu = ContextMenu(composer, manager, Mock())

    with patch("src.client.ui.components.hud.context_menu.imgui"):
        menu._render_system_actions()

    assert deferred.requests == 1
    assert manager.is_visible("draft")
    assert not manager.is_visible("simple")
    deferred.keep_open = False
    manager.render_all(None, None)
    assert not manager.is_visible("draft")


@pytest.mark.parametrize("decision", ["apply", "discard", "stale", "clean"])
def test_actual_internal_laws_handles_navigation_close(monkeypatch, decision):
    panel = InternalLawsPanel()
    panel._law_draft.select_country("UKR")
    row = dict(country_id="UKR", law_id="speech", value="Old", allowed_values_json='["Old", "New"]')
    state = SimpleNamespace(tables={"country_laws": pl.DataFrame([row])})
    if decision != "clean":
        panel._law_draft.choose(row, "New")
    if decision == "stale":
        state.tables.clear()
    actions = []
    context = PanelRenderContext("UKR", True, net_client=SimpleNamespace(player_id="player", send_action=actions.append))

    @contextmanager
    def window(*args, **kwargs):
        yield True

    monkeypatch.setattr("src.client.ui.panels.politics.internal_laws_panel.WindowManager.window", window)
    panel._identity.render_notices = lambda: None
    panel._close_confirmation.render = lambda *args, **kwargs: CloseDecision.DISCARD if decision == "discard" else CloseDecision.APPLY
    manager = PanelManager()
    manager.register("laws", panel, visible=True)
    manager.set_visible("laws", False)
    assert manager.is_visible("laws")
    manager.render_all(state, context)
    assert manager.is_visible("laws") is (decision == "stale")
    assert len(actions) == int(decision == "apply")
    assert bool(panel._law_draft.pending) is (decision == "stale")
    assert panel._law_notice.is_open is (decision == "stale")


@pytest.mark.parametrize("kind", ["budget", "resources", "advisor", "economic-health"])
def test_existing_dirty_panels_compose_the_deferred_navigation_signal(kind):
    from src.client.ui.panels.budget_panel import BudgetPanel
    from src.client.ui.panels.resources_panel import ResourcesPanel
    from src.client.ui.panels.service.advisor_settings_panel import AdvisorSettingsPanel
    from src.client.ui.panels.economic_health_panel import EconomicHealthPanel
    panel = {
        "budget": BudgetPanel,
        "resources": ResourcesPanel,
        "advisor": AdvisorSettingsPanel,
        "economic-health": EconomicHealthPanel,
    }[kind]()
    manager = PanelManager()
    manager.register(kind, panel, visible=True)
    manager.set_visible(kind, False)
    assert manager.is_visible(kind)
    assert panel._close_intent.consume()
    assert not panel._close_intent.consume()


def test_stale_close_uses_shared_notice_sink_when_composed_in_hud():
    panel = InternalLawsPanel()
    panel._law_draft.select_country("UKR")
    panel._law_draft.choose(dict(law_id="speech", value="Old", allowed_values_json='["Old", "New"]'), "New")
    notices = []
    context = PanelRenderContext("UKR", True, net_client=SimpleNamespace(player_id="player"),
                                 on_notice=lambda *args, **kwargs: notices.append((args, kwargs)))
    assert panel._finish_close(CloseDecision.APPLY, SimpleNamespace(tables={}), context)
    assert len(notices) == 1
    assert not panel._law_notice.is_open
