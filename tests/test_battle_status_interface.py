import unittest

import polars as pl

from src.client.ui.panels.military.presenter import MilitaryPresenter, battle_balance_estimate_label
from src.shared.state import GameState


class BattleStatusInterfaceTest(unittest.TestCase):
    def test_projection_aggregates_participants_and_legacy_defaults(self) -> None:
        state = GameState(tables={
            "battles": pl.DataFrame({
                "id": ["battle-1"], "region_id": [2], "attacker_side": ["USA,MEX"],
                "defender_side": ["CAN"], "mode": ["assault"], "balance": [0.6], "status": ["active"],
                "side_a_strength": [150.0], "side_b_strength": [100.0],
            }),
            "battle_participants": pl.DataFrame({
                "battle_id": ["battle-1", "battle-1"], "country_id": ["MEX", "USA"],
                "side": ["attacker", "attacker"], "role": ["ally", "principal"],
                "unit_count": [1, 2], "weighted_strength": [50.0, 100.0],
            }),
            "battle_units": pl.DataFrame({
                "battle_id": ["battle-1", "battle-1"], "country_id": ["MEX", "USA"],
                "readiness_status": ["fortified", "ready"],
            }),
            "occupations": pl.DataFrame({
                "region_id": [2], "controller_country_id": ["USA"], "garrison_strength": [80],
                "resistance": [0.0], "occupation_status": ["active"],
            }),
        })
        model = MilitaryPresenter().battle_status(state, "battle-1", "USA")
        self.assertIsNotNone(model)
        assert model is not None
        self.assertEqual(model.side_a_countries, ("USA", "MEX"))
        self.assertEqual(model.participants[0].role, "ally")
        self.assertEqual(model.participants[0].readiness, ("fortified",))
        self.assertEqual(model.occupation["resistance"], 0.0)
        self.assertEqual(model.mode, "assault")
        self.assertEqual(model.mode_label, "Active")
        self.assertEqual(model.status_label, "Active")
        self.assertEqual(state.current_actions, [])

    def test_posture_and_command_history_are_projected_for_the_authorized_country(self) -> None:
        state = GameState(tables={
            "battles": pl.DataFrame({
                "id": ["battle-1"], "attacker_side": ["USA"], "defender_side": ["CAN"],
                "status": ["active"],
            }),
            "units": pl.DataFrame([
                {"id": "usa-1", "owner": "USA", "unit_type": "infantry", "strength": 100},
                {"id": "can-1", "owner": "CAN", "unit_type": "fighter", "strength": 20},
            ]),
            "battle_force_postures": pl.DataFrame([
                {"battle_id": "battle-1", "unit_id": "usa-1", "country_id": "USA", "strategy": "attack", "issuer_player_id": "player-1", "effective_at_minute": 12, "status": "active", "reason": "Commander order", "attack_modifier": 1.1, "defense_modifier": 1.0, "casualty_modifier": 1.1},
                {"battle_id": "battle-1", "unit_id": "can-1", "country_id": "CAN", "strategy": "retreat", "issuer_player_id": "player-2", "effective_at_minute": 13, "status": "retreating", "reason": "Private order", "attack_modifier": 0.65, "defense_modifier": 1.0, "casualty_modifier": 0.7},
            ]),
            "battle_command_orders": pl.DataFrame([
                {"id": "order-1", "battle_id": "battle-1", "country_id": "USA", "strategy": "attack", "issuer_player_id": "player-1", "created_at_minute": 12, "effective_at_minute": 12, "status": "applied", "reason": "", "affected_unit_ids": ["usa-1", "can-1"]},
            ]),
        })

        presenter = MilitaryPresenter()
        postures = presenter.battle_postures_for_country(state, "battle-1", "USA")
        history = presenter.battle_command_history(state, "battle-1", "USA")

        self.assertEqual([row["unit_id"] for row in postures], ["usa-1"])
        self.assertEqual(postures[0]["effective_at_minute"], 12)
        self.assertEqual(postures[0]["attack_modifier"], 1.1)
        self.assertEqual(postures[0]["next_action"], "Continue attack posture at the next battle resolution")
        self.assertEqual(history[0]["affected_forces"], [{"unit_id": "usa-1", "unit_type": "infantry"}])
        self.assertEqual(history[0]["expected_effects"][0]["casualty_modifier"], 1.1)
        self.assertEqual({
            key for key in history[0]["expected_effects"][0] if key.endswith("_modifier")
        }, {
            "attack_modifier", "defense_modifier", "casualty_modifier", "attack_risk_modifier",
            "readiness_modifier", "holding_modifier", "counterattack_modifier",
        })
        self.assertEqual(presenter.battle_command_history(state, "battle-1", "CAN"), [])

    def test_outcome_and_balance_labels_distinguish_pending_victory_and_draw(self) -> None:
        self.assertEqual(battle_balance_estimate_label(0.567), "Balance estimate 57%")
        state = GameState(tables={
            "battles": pl.DataFrame({
                "id": ["battle-1"], "attacker_side": ["USA"], "defender_side": ["CAN"],
                "status": ["concluded"], "victor_side": ["SIDE_A"], "balance": [0.6],
            }),
        })
        presenter = MilitaryPresenter()
        victory = presenter.battle_status(state, "battle-1", "USA")
        assert victory is not None
        self.assertEqual(victory.outcome_label, "Victory: USA")

        battle_rows = state.get_table("battles").to_dicts()
        battle_rows[0]["victor_side"] = ""
        state.update_table("battles", pl.DataFrame(battle_rows))
        draw = presenter.battle_status(state, "battle-1", "USA")
        assert draw is not None
        self.assertEqual(draw.outcome_label, "Draw")

        battle_rows[0]["status"] = "active"
        state.update_table("battles", pl.DataFrame(battle_rows))
        pending = presenter.battle_status(state, "battle-1", "USA")
        assert pending is not None
        self.assertEqual(pending.outcome_label, "Outcome pending")


if __name__ == "__main__":
    unittest.main()
