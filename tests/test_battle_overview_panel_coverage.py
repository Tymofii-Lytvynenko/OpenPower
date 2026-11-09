from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import src.client.ui.panels.military.battle_overview_panel as panel_module
from src.client.ui.panels.military.battle_overview_panel import BattleOverviewPanel


class Client:
    player_id = "player-1"

    def __init__(self):
        self.actions = []

    def send_action(self, action):
        self.actions.append(action)


def render_context(*, own=True, country="USA", on_focus=None, client=None):
    return SimpleNamespace(
        is_own_country=own,
        target_tag=country,
        net_client=client,
        on_focus_request=on_focus,
    )


def panel_imgui(*, click_inspect=False, click_attack=False, click_focus=False, progress=True):
    def small_button(label, *, test_id=None):
        return (
            (click_inspect and str(test_id).startswith("battle.overview.inspect."))
            or (click_attack and str(label).endswith("-attack"))
        )

    values = {
        "separator": Mock(),
        "text": Mock(),
        "text_disabled": Mock(),
        "same_line": Mock(),
        "new_line": Mock(),
        "small_button": small_button,
        "button": Mock(return_value=click_focus),
    }
    if progress:
        values["progress_bar"] = Mock()
    return SimpleNamespace(**values)


def battle_model():
    effect = {
        "unit_id": "unit-1",
        "attack_modifier": 1.1,
        "attack_risk_modifier": 0.9,
        "defense_modifier": 1.2,
        "readiness_modifier": 1.0,
        "holding_modifier": 1.1,
        "counterattack_modifier": 1.0,
        "casualty_modifier": 0.8,
    }
    return SimpleNamespace(
        balance=0.6,
        mode_label="Positional",
        status_label="Concluded",
        round=4,
        side_a_strength=90.0,
        side_b_strength=70.0,
        status=" concluded ",
        outcome_label="Victory: USA",
        side_a_losses=10,
        side_b_losses=20,
        readiness_distribution={"parked": 1, "ready": 2, "fortified": 3},
        side_a_countries=["USA"],
        side_b_countries=["CAN"],
        participants=[SimpleNamespace(country_id="USA", role="attacker", weighted_strength=90.0)],
        occupation={
            "controller_country_id": "USA",
            "garrison_strength": 10,
            "resistance": 5.0,
            "occupation_status": "active",
        },
        force_groups=[{
            "side": "A",
            "country_id": "USA",
            "unit_type": "infantry",
            "unit_count": 1,
            "strength": 90,
            "relative_positions": [(11.0, 21.0)],
        }],
        postures=[{
            "unit_type": "infantry",
            "unit_id": "unit-1",
            "strategy": "attack",
            "status": "active",
            "issuer_player_id": "player-1",
            "effective_at_minute": 12,
            "attack_modifier": 1.1,
            "attack_risk_modifier": 0.9,
            "defense_modifier": 1.2,
            "readiness_modifier": 1.0,
            "holding_modifier": 1.1,
            "counterattack_modifier": 1.0,
            "casualty_modifier": 0.8,
            "reason": "Commander order",
            "next_action_at_minute": 14,
            "next_action": "Continue attack",
        }],
        command_history=[{
            "effective_at_minute": 12,
            "strategy": "attack",
            "affected_forces": [{"unit_type": "infantry", "unit_id": "unit-1"}],
            "expected_effects": [effect],
            "status": "applied",
            "reason": "",
        }],
        loss_groups=[{
            "side": "B",
            "country_id": "CAN",
            "unit_type": "armor",
            "losses": 20,
        }],
    )


def install_battle(monkeypatch, *, model, imgui):
    monkeypatch.setattr(panel_module, "imgui", imgui)
    monkeypatch.setattr(panel_module, "draw_required_tables", Mock(return_value=True))
    monkeypatch.setattr(panel_module, "resolve_region_name", Mock(return_value="Frontier"))
    panel = BattleOverviewPanel(open_battle_cb=Mock())
    panel._presenter = Mock()
    panel._presenter.battles_for_country.return_value = [{
        "id": "battle-1",
        "region_id": 1,
        "balance": 0.5,
        "mode": "positional",
        "status": "ongoing",
        "round": 2,
        "side_a_strength": 50.0,
        "side_b_strength": 40.0,
        "anchor_latitude": 10.0,
        "anchor_longitude": 20.0,
    }]
    panel._presenter.battle_status.return_value = model
    panel._presenter.battle_force_summary.return_value = model.force_groups if model else []
    panel._presenter.battle_postures_for_country.return_value = model.postures if model else []
    panel._presenter.battle_command_history.return_value = model.command_history if model else []
    panel._presenter.battle_loss_summary.return_value = model.loss_groups if model else []
    return panel


def test_render_content_shows_battle_details_and_dispatches_player_actions(monkeypatch):
    imgui = panel_imgui(click_inspect=True, click_attack=True, click_focus=True)
    model = battle_model()
    panel = install_battle(monkeypatch, model=model, imgui=imgui)
    client = Client()
    opened = []
    focused = []
    panel._open_battle = opened.append

    panel._render_content(
        SimpleNamespace(globals={"player_country_map": {"player-1": "USA"}}),
        render_context(client=client, on_focus=focused.append),
    )

    assert opened == ["battle-1"]
    assert focused == [1]
    assert len(client.actions) == 1
    assert client.actions[0].strategy == "attack"
    panel._presenter.battle_status.assert_called_once()
    panel._presenter.battle_force_summary.assert_called_once()
    imgui.progress_bar.assert_called_once_with(0.6, (0.0, 12.0), "")


def test_render_content_handles_fallback_rows_and_missing_optional_progress_bar(monkeypatch):
    imgui = panel_imgui(progress=False)
    panel = install_battle(monkeypatch, model=None, imgui=imgui)
    panel._open_battle = None

    panel._render_content(
        SimpleNamespace(globals={"player_tag": " usa "}),
        render_context(own=False, country="CAN"),
    )

    panel._presenter.battle_status.assert_called_once_with(
        panel._presenter.battle_status.call_args.args[0], "battle-1", "USA"
    )
    assert imgui.text.call_count >= 3


@pytest.mark.parametrize("has_table", [False, True])
def test_render_content_returns_early_for_missing_or_empty_battle_data(monkeypatch, has_table):
    imgui = panel_imgui()
    monkeypatch.setattr(panel_module, "imgui", imgui)
    required = Mock(return_value=has_table)
    empty = Mock()
    monkeypatch.setattr(panel_module, "draw_required_tables", required)
    monkeypatch.setattr(panel_module, "draw_empty_state", empty)
    panel = BattleOverviewPanel()
    panel._presenter = Mock()
    panel._presenter.battles_for_country.return_value = []

    panel._render_content(SimpleNamespace(globals={}), render_context())

    if has_table:
        empty.assert_called_once_with("No active battles are tracked in the current state.")
    else:
        panel._presenter.battles_for_country.assert_not_called()
        imgui.separator.assert_not_called()


def test_render_closes_or_draws_the_battle_window(monkeypatch):
    panel = BattleOverviewPanel()
    panel._render_content = Mock()
    is_open = False

    @contextmanager
    def window(*_args, **_kwargs):
        yield is_open

    monkeypatch.setattr(panel_module.WindowManager, "window", window)
    state = SimpleNamespace(globals={})
    context = render_context()

    assert panel.render(state, context) is False
    panel._render_content.assert_not_called()
    is_open = True
    assert panel.render(state, context) is True
    panel._render_content.assert_called_once_with(state, context)
