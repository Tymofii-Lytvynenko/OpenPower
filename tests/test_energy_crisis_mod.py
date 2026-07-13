import unittest
from pathlib import Path

import polars as pl

from modules.energy_crisis.actions import ActionSetEnergyPolicy
from modules.energy_crisis.events import EventEnergyPolicyChanged
from modules.energy_crisis.systems.energy_crisis_system import EnergyCrisisSystem
from src.engine.mod_manager import ModManager
from src.server.session import GameSession
from src.shared.config import GameConfig
from src.shared.events import EventNewDay
from src.shared.state import GameState
from src.simulation.actions import ActionScript


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCENARIO_PATH = (
    PROJECT_ROOT
    / "modules"
    / "energy_crisis"
    / "scenarios"
    / "policy_response.json"
)


class TestEnergyCrisisReferenceMod(unittest.TestCase):
    def _config(self) -> GameConfig:
        config = GameConfig(PROJECT_ROOT)
        config.requested_mods = ["energy_crisis"]
        config.active_mods = ["energy_crisis"]
        config.dev_mode = True
        return config

    def test_contribution_data_action_and_migration_use_the_real_runtime(self):
        manager = ModManager(self._config())
        manifests = manager.resolve_load_order()
        runtime = manager.load_runtime()

        self.assertEqual([manifest.id for manifest in manifests], ["base", "energy_crisis"])
        self.assertIn(
            "energy_crisis.simulation",
            {system.id for system in runtime.systems},
        )
        self.assertIn("energy_crises", runtime.schemas.table_names)

        meta = {"version": 1}
        tables: dict[str, pl.DataFrame] = {}
        runtime.migrations.migrate(meta, tables)
        self.assertEqual(meta["schema_versions"]["energy_crisis"], 1)
        self.assertEqual(
            tables["energy_crises"].columns,
            [
                "country_id",
                "policy",
                "reserve_days",
                "import_dependency",
                "shock_intensity",
                "response_level",
                "stress_index",
                "economic_drag",
            ],
        )

        session = GameSession.create_headless(
            self._config(),
            player_tag="UKR",
            random_seed=42,
        )
        self.assertEqual(session.config.active_mods, ["base", "energy_crisis"])
        ukraine = (
            session.state.get_table("countries")
            .filter(pl.col("id") == "UKR")
            .to_dicts()[0]
        )
        self.assertEqual(ukraine["budget_env_ratio"], 0.45)

        script = ActionScript.from_path(
            SCENARIO_PATH,
            action_types=session.engine.handled_action_types,
        )
        actions = script.actions_for(day=1, tick=1, minute=1440)
        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], ActionSetEnergyPolicy)

        session.receive_action(actions[0])
        session.tick(0.0)
        status = (
            session.state.get_table("energy_crises")
            .filter(pl.col("country_id") == "UKR")
            .to_dicts()[0]
        )
        self.assertEqual(status["policy"], "rationing")
        self.assertEqual(status["response_level"], 0.85)
        self.assertTrue(
            any(
                event["event_type"] == "EventEnergyPolicyChanged"
                for event in session.state.journal.domain_events
            )
        )

    def test_system_advances_deterministically_without_engine_internals(self):
        state = GameState(
            tables={
                "countries": pl.DataFrame({"id": ["UKR"]}),
                "energy_crises": pl.DataFrame(
                    {
                        "country_id": ["UKR"],
                        "policy": ["conservation"],
                        "reserve_days": [45.0],
                        "import_dependency": [0.7],
                        "shock_intensity": [0.6],
                        "response_level": [0.8],
                        "stress_index": [0.0],
                        "economic_drag": [0.0],
                    }
                ),
            }
        )
        state.current_actions = [
            ActionSetEnergyPolicy(
                player_id="test",
                country_tag="UKR",
                policy="rationing",
                response_level=0.9,
            )
        ]
        state.events = [EventNewDay(day=2, month=1, year=2025)]

        EnergyCrisisSystem().update(state, 0.6)

        status = state.get_table("energy_crises").to_dicts()[0]
        self.assertEqual(status["policy"], "rationing")
        self.assertGreater(status["stress_index"], 0.0)
        self.assertGreater(status["reserve_days"], 0.0)
        self.assertTrue(
            any(isinstance(event, EventEnergyPolicyChanged) for event in state.events)
        )
        country = state.get_table("countries").to_dicts()[0]
        self.assertLess(country["energy_security_index"], 1.0)


if __name__ == "__main__":
    unittest.main()
