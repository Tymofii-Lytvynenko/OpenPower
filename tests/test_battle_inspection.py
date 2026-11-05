import json
from pathlib import Path

import polars as pl

from modules.base.schema import ensure_base_tables
from modules.base.systems.military.battle_strategy_system import BattleStrategySystem
from modules.base.systems.military.military_system import UNIT_SCHEMA
from src.client.ui.components.shared.battle_summary_dialog import (
    _category_loss_counts,
    _combat_side,
    _outcome_for_side,
)
from src.client.ui.panels.military.battle_force_cards import _merge_force_losses, _posture_counts
from src.client.ui.panels.military.battle_inspection import BattleInspection, category_counts
from src.shared.state import GameState


def make_state():
    fixture = json.loads(Path("tests/ui/fixtures/reference-battle-inspection.json").read_text(encoding="utf-8"))
    state = GameState(tables={key: pl.DataFrame(rows) for key, rows in fixture["tables"].items()})
    state.update_table("units", pl.DataFrame(fixture["tables"]["units"], schema=UNIT_SCHEMA))
    ensure_base_tables(state)
    return state


def result(battle_id="battle-own"):
    return dict(event_type="EventBattleEnded", payload=dict(battle_id=battle_id,
                participant_countries=["UKR", "POL"], side_a_losses=4))


def test_selection_preserves_battle_context_and_restricts_foreign_commands():
    state, actions = make_state(), []
    selection = BattleInspection("UKR", actions.append, "UKR")
    assert selection.open(state, "battle-own") and selection.full
    assert selection.command(state, "defend", "infantry")
    assert actions[0].battle_id == "battle-own"
    assert actions[0].country_tag == "UKR"
    assert not selection.command(state, "attack", "armor")
    assert selection.open(state, "battle-observer") and not selection.full
    assert selection.groups(state) == []
    assert not selection.command(state, "retreat")
    assert len(actions) == 1
    assert not selection.open(state, "missing")


def test_real_strategy_system_accepts_selected_owner_command():
    state, actions = make_state(), []
    selection = BattleInspection("UKR", actions.append, "UKR")
    selection.open(state, "battle-own")
    selection.command(state, "defend", "infantry")
    state.current_actions = actions
    BattleStrategySystem().update(state, 0)
    assert state.tables["units"].filter(pl.col("id") == "ukr-infantry")["combat_posture"][0] == "defend"
    assert state.tables["battle_command_orders"]["affected_unit_ids"][0].to_list() == ["ukr-infantry"]


def test_concluded_or_replaced_battle_cannot_dispatch_stale_commands():
    state, actions = make_state(), []
    selection = BattleInspection("UKR", actions.append, "UKR")
    selection.open(state, "battle-own")
    state.update_table("battles", state.tables["battles"].with_columns(pl.lit("concluded").alias("status")))
    assert not selection.command(state, "attack")
    assert not actions


def test_matching_result_waits_for_final_snapshot_and_is_delivered_once():
    state = make_state()
    state.journal.domain_events.append(result())
    selection = BattleInspection("UKR", lambda action: None, "UKR")
    selection.open(state, "battle-own")
    assert selection.poll_result(state) is None
    state.journal.domain_events.append(result("other"))
    assert selection.poll_result(state) is None
    state.journal.domain_events.append(result())
    assert selection.poll_result(state) is None
    state.update_table("battles", state.tables["battles"].filter(pl.col("id") != "battle-own"))
    assert selection.poll_result(state)["side_a_losses"] == 4
    assert selection.display_row(state)["status"] == "concluded"
    assert selection.poll_result(state) is None
    selection.close()
    assert not selection.battle_id


def test_observed_categories_and_coordinates_do_not_invent_missing_data():
    state = make_state()
    selection = BattleInspection("UKR", lambda action: None, "UKR")
    selection.open(state, "battle-own")
    groups = selection.groups(state)
    assert category_counts(groups, "A") == {"I": 1, "G": 0, "A": 0, "N": 0}
    assert category_counts(groups, "B")["G"] == 1
    state.update_table("units", state.tables["units"].with_columns(pl.lit(None).cast(pl.Float64).alias("latitude")))
    assert all(not group["relative_positions"] for group in selection.groups(state))


def test_ground_air_defense_uses_its_canonical_domain():
    counts = category_counts([dict(side="SIDE_A", unit_type="air_defense", unit_count=2)], "A")
    assert counts["G"] == 2 and counts["A"] == 0
    vehicles = category_counts([dict(side="SIDE_A", unit_type="infantry_vehicles", unit_count=3)], "A")
    assert vehicles["G"] == 3 and vehicles["I"] == 0


def test_force_card_details_merge_recorded_losses_and_aggregate_orders():
    groups = [{
        "side": "SIDE_A", "country_id": "UKR", "unit_type": "infantry",
        "unit_count": 2, "strength": 900, "relative_positions": [],
    }]
    losses = [
        {"side": "SIDE_A", "country_id": "UKR", "unit_type": "infantry", "losses": 75},
        {"side": "SIDE_B", "country_id": "POL", "unit_type": "armor", "losses": 40},
    ]
    cards = _merge_force_losses(groups, losses)
    assert [(card["country_id"], card["unit_type"], card["unit_count"], card["losses"]) for card in cards] == [
        ("UKR", "infantry", 2, 75),
        ("POL", "armor", 0, 40),
    ]
    postures = _posture_counts([
        {"country_id": "UKR", "unit_type": "infantry", "strategy": "hold"},
        {"country_id": "UKR", "unit_type": "infantry", "strategy": "attack"},
        {"country_id": "POL", "unit_type": "armor", "strategy": "retreat"},
    ])
    assert postures == {
        ("POL", "armor"): [("retreat", 1)],
        ("UKR", "infantry"): [("attack", 1), ("hold", 1)],
    }


def test_battle_summary_uses_source_side_order_and_only_complete_category_losses():
    losses = [
        {"side": "SIDE_A", "unit_type": "infantry", "losses": 21},
        {"side": "defender", "unit_type": "tanks", "losses": 87},
    ]

    assert _combat_side("attacker") == "SIDE_A"
    assert _combat_side("defender") == "SIDE_B"
    assert _category_loss_counts(losses, "SIDE_B", 87) == {"I": 0, "G": 87, "A": 0, "N": 0}
    assert _category_loss_counts(losses, "SIDE_A", 21) == {"I": 21, "G": 0, "A": 0, "N": 0}
    assert _category_loss_counts(losses, "SIDE_B", 80) is None
    assert _category_loss_counts(losses, "SIDE_B", 0) is None
    assert _category_loss_counts([], "SIDE_B", 0) is None
    assert _outcome_for_side({"victor_side": "SIDE_A"}, "SIDE_B", ("POL",)) == "Defeat"
    assert _outcome_for_side({"victor_side": "SIDE_A"}, "SIDE_A", ("UKR",)) == "Victory"
    assert _outcome_for_side({"victor_side": "", "victor_tag": "Undecided"}, "SIDE_A", ("UKR",)) == "Unknown"


def test_game_view_routes_an_empty_map_click_to_the_drawn_battle():
    from types import SimpleNamespace
    from unittest.mock import Mock
    from src.client.views.game_view import GameView
    import arcade

    interactions = SimpleNamespace(on_mouse_release=Mock(return_value=False), clear_selection=Mock())
    layout = SimpleNamespace(select_battle_at=Mock(return_value=True))
    viewport = SimpleNamespace(on_mouse_press=Mock())
    renderer = object()
    view = SimpleNamespace(unit_interactions=interactions, layout=layout, viewport_ctrl=viewport,
                           battle_effect_renderer=renderer, window=SimpleNamespace(height=720),
                           _drag_start_pos=(120, 130), _is_small_drag=lambda *args: True,
                           _selection_rect_start=None, _selection_rect_current=None)
    GameView.on_game_mouse_release(view, 120, 130, arcade.MOUSE_BUTTON_LEFT, 0)
    layout.select_battle_at.assert_called_once_with(renderer, 120, 130, 720)
    viewport.on_mouse_press.assert_not_called()
