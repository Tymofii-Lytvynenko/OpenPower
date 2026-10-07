from __future__ import annotations

import unittest

import polars as pl

from modules.base.schema import ensure_base_tables
from modules.base.systems.military.military_system import UNIT_SCHEMA, UnitFactory
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.panels.military.battle_overview_panel import BattleOverviewPanel
from src.client.ui.panels.military.presenter import MilitaryPresenter
from src.core.map.geo import GeoCoordinate
from src.shared.state import GameState


class _Client:
    player_id = "player-1"


class BattleVisibilityTest(unittest.TestCase):
    def _state(self) -> GameState:
        factory = UnitFactory()
        state = GameState(tables={
            "countries": pl.DataFrame({"id": ["USA", "CAN", "MEX"]}),
            "regions": pl.DataFrame([{
                "id": 1, "owner": "CAN", "controller": "CAN", "name": "Frontier",
                "latitude": 10.0, "longitude": 20.0,
            }]),
            "units": pl.DataFrame([
                factory.create("usa-1", "USA", "infantry", 90, 1, GeoCoordinate(10.0, 20.0), 0),
                factory.create("can-1", "CAN", "armor", 70, 1, GeoCoordinate(10.1, 20.1), 0),
            ], schema=UNIT_SCHEMA),
            "battles": pl.DataFrame([{
                "id": "battle-1", "war_id": "war-1", "region_id": 1,
                "attacker_side": "USA", "defender_side": "CAN", "status": "concluded",
                "side_a_strength": 90.0, "side_b_strength": 70.0,
                "side_a_losses": 10, "side_b_losses": 20,
                "victor_side": "SIDE_A", "concluded_at_minute": 20,
            }]),
        })
        ensure_base_tables(state)
        state.update_table("battle_units", pl.DataFrame([
            {"battle_id": "battle-1", "unit_id": "usa-1", "country_id": "USA", "side": "attacker"},
            {"battle_id": "battle-1", "unit_id": "can-1", "country_id": "CAN", "side": "defender"},
        ], schema=state.get_table("battle_units").schema))
        state.update_table("battle_participants", pl.DataFrame([
            {"battle_id": "battle-1", "country_id": "USA", "side": "attacker", "unit_count": 1, "weighted_strength": 90.0},
            {"battle_id": "battle-1", "country_id": "CAN", "side": "defender", "unit_count": 1, "weighted_strength": 70.0},
        ], schema=state.get_table("battle_participants").schema))
        state.update_table("battle_force_postures", pl.DataFrame([
            {"unit_id": "usa-1", "battle_id": "battle-1", "country_id": "USA", "strategy": "attack", "issuer_player_id": "player-1", "status": "active", "effective_at_minute": 12, "reason": "Commander order"},
            {"unit_id": "can-1", "battle_id": "battle-1", "country_id": "CAN", "strategy": "retreat", "issuer_player_id": "player-2", "status": "retreating", "effective_at_minute": 13, "reason": "Private order"},
        ], schema=state.get_table("battle_force_postures").schema))
        state.update_table("battle_command_orders", pl.DataFrame([
            {"id": "order-usa", "battle_id": "battle-1", "country_id": "USA", "strategy": "attack", "issuer_player_id": "player-1", "created_at_minute": 12, "effective_at_minute": 12, "status": "applied", "affected_unit_ids": ["usa-1"]},
            {"id": "order-can", "battle_id": "battle-1", "country_id": "CAN", "strategy": "retreat", "issuer_player_id": "player-2", "created_at_minute": 13, "effective_at_minute": 13, "status": "applied", "affected_unit_ids": ["can-1"]},
        ], schema=state.get_table("battle_command_orders").schema))
        state.update_table("battle_casualty_records", pl.DataFrame([
            {"id": "loss-usa", "battle_id": "battle-1", "country_id": "USA", "side": "attacker", "unit_type": "infantry", "losses": 10},
            {"id": "loss-can", "battle_id": "battle-1", "country_id": "CAN", "side": "defender", "unit_type": "armor", "losses": 20},
        ], schema=state.get_table("battle_casualty_records").schema))
        state.globals["player_country_map"] = {"player-1": "USA"}
        return state

    def test_nonparticipant_cannot_inspect_battle_force_or_loss_details(self) -> None:
        state = self._state()
        presenter = MilitaryPresenter()

        self.assertEqual(presenter.battles_for_country(state, "MEX"), [])
        self.assertIsNone(presenter.battle_status(state, "battle-1", "MEX"))
        self.assertEqual(presenter.battle_force_summary(state, "battle-1", "MEX"), [])
        self.assertEqual(presenter.battle_loss_summary(state, "battle-1", "MEX"), [])
        self.assertEqual(presenter.battle_postures_for_country(state, "battle-1", "MEX"), [])
        self.assertEqual(presenter.battle_command_history(state, "battle-1", "MEX"), [])

    def test_battle_participant_can_inspect_participating_sides_and_own_commands(self) -> None:
        state = self._state()
        presenter = MilitaryPresenter()

        self.assertEqual([row["id"] for row in presenter.battles_for_country(state, "USA")], ["battle-1"])
        model = presenter.battle_status(state, "battle-1", "USA")
        self.assertIsNotNone(model)
        assert model is not None
        self.assertEqual(model.outcome_label, "Victory: USA")
        self.assertEqual({participant.country_id for participant in model.participants}, {"USA", "CAN"})
        force_groups = presenter.battle_force_summary(state, "battle-1", "USA")
        self.assertEqual(len(force_groups), 2)
        usa_group = next(row for row in force_groups if row["country_id"] == "USA")
        self.assertEqual((usa_group["unit_type"], usa_group["unit_count"], usa_group["strength"]), ("infantry", 1, 90))
        self.assertEqual(usa_group["relative_positions"], [(10.0, 20.0)])
        losses = presenter.battle_loss_summary(state, "battle-1", "USA")
        self.assertEqual([(row["country_id"], row["unit_type"], row["losses"]) for row in losses], [
            ("USA", "infantry", 10), ("CAN", "armor", 20),
        ])
        self.assertEqual([row["unit_id"] for row in presenter.battle_postures_for_country(state, "battle-1", "USA")], ["usa-1"])
        self.assertEqual(
            presenter.battle_postures_for_country(state, "battle-1", "USA")[0]["next_action"],
            "Continue attack posture at the next battle resolution",
        )
        history = presenter.battle_command_history(state, "battle-1", "USA")
        self.assertEqual([row["id"] for row in history], ["order-usa"])
        self.assertEqual(history[0]["issuer_player_id"], "player-1")
        self.assertEqual(history[0]["effective_at_minute"], 12)

    def test_overview_uses_actual_player_country_instead_of_selected_target(self) -> None:
        panel = BattleOverviewPanel()
        context = PanelRenderContext(target_tag="CAN", is_own_country=False, net_client=_Client())

        viewer = panel._viewer_country(self._state(), context)

        self.assertEqual(viewer, "USA")


if __name__ == "__main__":
    unittest.main()
