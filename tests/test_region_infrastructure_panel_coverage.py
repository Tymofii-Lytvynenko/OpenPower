from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.client.ui.panels import region_infrastructure_panel as panel_module
from src.client.ui.panels.region_infrastructure_panel import RegionInfrastructurePanel
from src.shared.actions import ActionCancelInfrastructureProject, ActionInvestRegionalInfrastructure


class RecordingImGui:
    def __init__(self, clicked: set[str] | None = None) -> None:
        self.clicked = clicked or set()
        self.calls: list[tuple[str, object]] = []

    def text(self, value: str) -> None:
        self.calls.append(("text", value))

    def text_disabled(self, value: str) -> None:
        self.calls.append(("text_disabled", value))

    def text_wrapped(self, value: str) -> None:
        self.calls.append(("text_wrapped", value))

    def separator(self) -> None:
        self.calls.append(("separator", None))

    def small_button(self, label: str) -> bool:
        self.calls.append(("small_button", label))
        return label in self.clicked


class FakeWindowManager:
    is_open = True

    @classmethod
    def window(cls, *_args, **_kwargs):
        return nullcontext(cls.is_open)


def install_panel_ui(monkeypatch, *, clicked: set[str] | None = None, is_open: bool = True):
    imgui = RecordingImGui(clicked)
    FakeWindowManager.is_open = is_open
    monkeypatch.setattr(panel_module, "imgui", imgui)
    monkeypatch.setattr(panel_module, "WindowManager", FakeWindowManager)
    return imgui


def make_context(
    *,
    selected_region_id: int | None = 42,
    is_own_country: bool = True,
    target_tag: str = "USA",
    net_client=None,
):
    return SimpleNamespace(
        selected_region_id=selected_region_id,
        is_own_country=is_own_country,
        target_tag=target_tag,
        net_client=net_client,
    )


def make_category(**overrides):
    values = {
        "category": "transport",
        "level": 0.5,
        "maximum": 1.0,
        "capacity": 0.8,
        "condition": 0.9,
        "maintenance_need": 1234,
        "project_status": None,
        "project_progress": 0.0,
        "project_reason": None,
        "last_source_type": None,
        "last_change_minute": None,
        "project_id": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_render_returns_false_when_window_is_closed(monkeypatch) -> None:
    install_panel_ui(monkeypatch, is_open=False)
    presenter = Mock()

    assert RegionInfrastructurePanel(presenter).render(object(), make_context()) is False
    presenter.build_region_summary.assert_not_called()


def test_render_requests_region_selection_when_none_is_selected(monkeypatch) -> None:
    imgui = install_panel_ui(monkeypatch)
    presenter = Mock()
    context = make_context(selected_region_id=None)

    assert RegionInfrastructurePanel(presenter).render(object(), context) is True

    presenter.build_region_summary.assert_not_called()
    assert ("text_disabled", "Select a region to inspect its infrastructure.") in imgui.calls


def test_render_displays_summary_and_optional_project_details(monkeypatch) -> None:
    imgui = install_panel_ui(monkeypatch)
    state = object()
    first = make_category(
        project_status="paused",
        project_progress=0.4,
        project_reason="Waiting for funding",
        last_source_type="investment",
        last_change_minute=18,
    )
    second = make_category(category="utilities")
    summary = SimpleNamespace(
        region_id=42,
        owner=None,
        categories=[first, second],
        downstream_effects=[("transport_access", 0.6), ("utilities_capacity", 0.7)],
    )
    presenter = SimpleNamespace(build_region_summary=Mock(return_value=summary))
    context = make_context(is_own_country=False)

    assert RegionInfrastructurePanel(presenter).render(state, context) is True

    presenter.build_region_summary.assert_called_once_with(state, 42)
    rendered_text = [value for kind, value in imgui.calls if kind == "text"]
    assert "Region 42 · Owner Unowned" in rendered_text
    assert "Project: paused (40%)" in rendered_text
    assert "Last change: investment · minute 18" in rendered_text
    assert "Regional effects — transport 60%, utilities 70%, industrial 0%, telecom 0%" in rendered_text
    assert ("text_wrapped", "Waiting for funding") in imgui.calls


def test_render_action_skips_non_owned_missing_client_and_other_owner() -> None:
    category = make_category()
    cases = [
        make_context(is_own_country=False, net_client=SimpleNamespace(send_action=Mock())),
        make_context(net_client=None),
        make_context(net_client=SimpleNamespace(send_action=Mock())),
    ]

    RegionInfrastructurePanel._render_action(object(), cases[0], "USA", category)
    RegionInfrastructurePanel._render_action(object(), cases[1], "USA", category)
    RegionInfrastructurePanel._render_action(object(), cases[2], "CAN", category)

    cases[0].net_client.send_action.assert_not_called()
    cases[2].net_client.send_action.assert_not_called()


def test_render_action_cancels_active_project_when_requested(monkeypatch) -> None:
    install_panel_ui(monkeypatch, clicked={"Cancel##transport"})
    client = SimpleNamespace(player_id="player-1", send_action=Mock())
    category = make_category(project_status="in_progress", project_id="project-7")

    RegionInfrastructurePanel._render_action(object(), make_context(net_client=client), "usa", category)

    client.send_action.assert_called_once_with(
        ActionCancelInfrastructureProject("player-1", "project-7")
    )


def test_render_action_does_not_offer_cancel_without_a_project_id(monkeypatch) -> None:
    imgui = install_panel_ui(monkeypatch, clicked={"Cancel##transport"})
    client = SimpleNamespace(player_id="player-1", send_action=Mock())
    category = make_category(project_status="paused", project_id=None)

    RegionInfrastructurePanel._render_action(object(), make_context(net_client=client), "USA", category)

    assert not any(kind == "small_button" for kind, _value in imgui.calls)
    client.send_action.assert_not_called()


@pytest.mark.parametrize("clicked", [True, False], ids=["repair-confirmed", "repair-dismissed"])
def test_render_action_offers_repair_for_low_capacity(monkeypatch, clicked: bool) -> None:
    label = "Repair##transport"
    imgui = install_panel_ui(monkeypatch, clicked={label} if clicked else set())
    client = SimpleNamespace(player_id="player-1", send_action=Mock())
    category = make_category(level=0.5, maximum=1.0, capacity=0.2)

    RegionInfrastructurePanel._render_action(object(), make_context(net_client=client), "USA", category)

    assert ("small_button", label) in imgui.calls
    if clicked:
        client.send_action.assert_called_once_with(
            ActionInvestRegionalInfrastructure("player-1", "USA", 42, "transport", 0.25)
        )
    else:
        client.send_action.assert_not_called()


def test_render_action_skips_repair_button_when_target_is_not_above_capacity(monkeypatch) -> None:
    imgui = install_panel_ui(monkeypatch, clicked={"Repair##transport"})
    client = SimpleNamespace(player_id="player-1", send_action=Mock())
    category = make_category(level=0.4, maximum=0.1, capacity=0.9)

    RegionInfrastructurePanel._render_action(object(), make_context(net_client=client), "USA", category)

    assert not any(kind == "small_button" for kind, _value in imgui.calls)
    client.send_action.assert_not_called()


@pytest.mark.parametrize("clicked", [True, False], ids=["investment-confirmed", "investment-dismissed"])
def test_render_action_offers_investment_until_maximum(monkeypatch, clicked: bool) -> None:
    label = "Invest +0.05##transport"
    imgui = install_panel_ui(monkeypatch, clicked={label} if clicked else set())
    client = SimpleNamespace(player_id="player-1", send_action=Mock())
    category = make_category(level=0.5, maximum=1.0, capacity=0.8)

    RegionInfrastructurePanel._render_action(object(), make_context(net_client=client), "USA", category)

    assert ("small_button", label) in imgui.calls
    if clicked:
        client.send_action.assert_called_once_with(
            ActionInvestRegionalInfrastructure("player-1", "USA", 42, "transport", 0.55)
        )
    else:
        client.send_action.assert_not_called()


def test_render_action_does_not_offer_investment_at_maximum(monkeypatch) -> None:
    imgui = install_panel_ui(monkeypatch, clicked={"Invest +0.05##transport"})
    client = SimpleNamespace(player_id="player-1", send_action=Mock())
    category = make_category(level=1.0, maximum=1.0, capacity=1.0)

    RegionInfrastructurePanel._render_action(object(), make_context(net_client=client), "USA", category)

    assert not any(kind == "small_button" for kind, _value in imgui.calls)
    client.send_action.assert_not_called()
