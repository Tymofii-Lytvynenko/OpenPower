import json
import shutil
import unittest
from pathlib import Path
from uuid import uuid4

import polars as pl

from modules.base.systems.military.combat_system import CombatSystem
from modules.base.systems.world.ai_system import AISystem
from modules.base.systems.world.treaty_diplomacy import DiplomacySystem
from src.core.saves import list_available_saves
from src.engine.simulator import Engine
from src.server.io.save_writer import SaveWriter
from src.server.session import GameSession
from src.shared.actions import (
    ActionCreateTreaty,
    ActionDeclareWar,
    ActionLeaveTreaty,
    ActionOfferPeace,
    ActionRespondTreaty,
    ActionSaveGame,
)
from src.shared.config import GameConfig
from src.shared.events import EventNewDay
from src.shared.mods import load_requested_mods, resolve_project_mods
from src.shared.state import GameState


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def make_temp_project(prefix: str) -> Path:
    root = PROJECT_ROOT / ".temp" / f"{prefix}-{uuid4().hex}"
    root.mkdir(parents=True, exist_ok=True)
    return root


def write_mod_manifest(root: Path, mod_id: str, dependencies: list[str]) -> None:
    mod_root = root / "modules" / mod_id
    (mod_root / "data").mkdir(parents=True, exist_ok=True)
    dependencies_literal = ", ".join(f'"{dependency}"' for dependency in dependencies)
    (mod_root / "mod.toml").write_text(
        "\n".join(
            [
                f'id = "{mod_id}"',
                f'name = "{mod_id}"',
                'version = "0.0.1"',
                f"dependencies = [{dependencies_literal}]",
                "",
            ]
        ),
        encoding="utf-8",
    )


class TestSaveActionAndWriter(unittest.TestCase):
    def setUp(self):
        self.project_root = make_temp_project("save-flow")
        write_mod_manifest(self.project_root, "base", [])
        (self.project_root / "mods.json").write_text(json.dumps({"active_mods": ["base"]}), encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.project_root, ignore_errors=True)

    def test_save_action_persists_listable_save_and_handles_invalid_names(self):
        config = GameConfig(self.project_root)
        state = GameState()
        state.update_table("regions", pl.DataFrame({"id": [1], "owner": ["USA"]}))

        session = GameSession(config, None, None, Engine(dev_mode=False), None, state)
        session.receive_action(ActionSaveGame(player_id="tester", save_name="autosave_1"))
        session.tick(0.1)

        save_dir = self.project_root / "user_data" / "saves" / "autosave_1"
        self.assertEqual(session.state.globals["tick"], 1)
        self.assertEqual(session.state.current_actions, [])
        self.assertEqual(session.state.journal.command_results[-1]["status"], "executed")
        self.assertTrue(save_dir.exists())
        self.assertTrue((save_dir / "meta.json").exists())
        self.assertTrue((save_dir / "tables" / "regions.parquet").exists())

        saves = list_available_saves(config)
        self.assertEqual([entry["name"] for entry in saves], ["autosave_1"])
        self.assertEqual(saves[0]["tick"], 0)

        writer = SaveWriter(config)
        self.assertTrue(writer.delete_save("autosave_1"))
        self.assertFalse(save_dir.exists())
        self.assertFalse(writer.delete_save("autosave_1"))
        self.assertFalse(writer.save_game(GameState(), "!!!"))


class TestModResolutionVariations(unittest.TestCase):
    def setUp(self):
        self.project_root = make_temp_project("mod-variations")

    def tearDown(self):
        shutil.rmtree(self.project_root, ignore_errors=True)

    def test_requested_mods_are_deduplicated_and_sorted_by_dependencies(self):
        write_mod_manifest(self.project_root, "base", [])
        write_mod_manifest(self.project_root, "expansion", ["base"])
        (self.project_root / "mods.json").write_text(
            json.dumps({"active_mods": ["expansion", "base", "expansion", ""]}),
            encoding="utf-8",
        )

        self.assertEqual(load_requested_mods(self.project_root), ["expansion", "base"])
        self.assertEqual([manifest.id for manifest in resolve_project_mods(self.project_root)], ["base", "expansion"])
        self.assertEqual(GameConfig(self.project_root).active_mods, ["base", "expansion"])

    def test_missing_mods_json_defaults_to_base(self):
        write_mod_manifest(self.project_root, "base", [])
        self.assertEqual(load_requested_mods(self.project_root), ["base"])

    def test_dependency_failures_raise_clear_errors(self):
        missing_root = self.project_root / "missing"
        missing_root.mkdir(parents=True, exist_ok=True)
        write_mod_manifest(missing_root, "expansion", ["missing"])
        (missing_root / "mods.json").write_text(json.dumps({"active_mods": ["expansion"]}), encoding="utf-8")

        cycle_root = self.project_root / "cycle"
        cycle_root.mkdir(parents=True, exist_ok=True)
        write_mod_manifest(cycle_root, "base", ["expansion"])
        write_mod_manifest(cycle_root, "expansion", ["base"])
        (cycle_root / "mods.json").write_text(json.dumps({"active_mods": ["base"]}), encoding="utf-8")

        with self.assertRaisesRegex(RuntimeError, "Missing dependency"):
            resolve_project_mods(missing_root)

        with self.assertRaisesRegex(RuntimeError, "Circular dependency"):
            resolve_project_mods(cycle_root)


class TestDiplomacyVariations(unittest.TestCase):
    def setUp(self):
        self.system = DiplomacySystem()

    def test_treaty_variations_and_noops(self):
        state = self._build_state()

        state.current_actions = [
            ActionCreateTreaty(
                player_id="tester",
                source_country_tag="USA",
                target_country_tag="USA",
                treaty_type="trade accord",
                title="Self Deal",
                terms="Should be ignored",
            )
        ]
        self.system.update(state, 0.1)
        self.assertTrue(state.get_table("pending_treaties").is_empty())

        state.current_actions = [
            ActionCreateTreaty(
                player_id="tester",
                source_country_tag="USA",
                target_country_tag="CAN",
                treaty_type="trade accord",
                title="North Trade",
                terms="Lower tariffs",
            )
        ]
        self.system.update(state, 0.1)
        self.assertEqual(len(state.get_table("pending_treaties")), 1)
        proposal_id = state.get_table("pending_treaties")["id"][0]

        state.current_actions = [
            ActionCreateTreaty(
                player_id="tester",
                source_country_tag="USA",
                target_country_tag="CAN",
                treaty_type="trade accord",
                title="North Trade",
                terms="Lower tariffs",
            )
        ]
        self.system.update(state, 0.1)
        self.assertEqual(len(state.get_table("pending_treaties")), 1)

        state.current_actions = [
            ActionRespondTreaty(
                player_id="tester",
                treaty_id=proposal_id,
                responder_country_tag="USA",
                accept=True,
            )
        ]
        self.system.update(state, 0.1)
        self.assertEqual(len(state.get_table("pending_treaties")), 1)
        self.assertEqual(len(state.get_table("countries_treaties")), 0)

        state.current_actions = [
            ActionRespondTreaty(
                player_id="tester",
                treaty_id=proposal_id,
                responder_country_tag="CAN",
                accept=True,
            )
        ]
        self.system.update(state, 0.1)
        self.assertEqual(len(state.get_table("pending_treaties")), 0)
        self.assertEqual(len(state.get_table("countries_treaties")), 1)

        treaty_id = state.get_table("countries_treaties")["id"][0]
        state.current_actions = [
            ActionLeaveTreaty(
                player_id="tester",
                treaty_id=treaty_id,
                country_tag="FRA",
            )
        ]
        self.system.update(state, 0.1)
        self.assertEqual(len(state.get_table("countries_treaties")), 1)

        state.current_actions = [
            ActionLeaveTreaty(
                player_id="tester",
                treaty_id=treaty_id,
                country_tag="CAN",
            )
        ]
        self.system.update(state, 0.1)
        self.assertEqual(len(state.get_table("countries_treaties")), 0)

    def test_war_overlap_and_invalid_peace_are_handled(self):
        state = self._build_state()
        state.update_table(
            "countries_treaties",
            pl.DataFrame(
                [
                    {
                        "id": "usa_can",
                        "name": "USA-CAN Pact",
                        "type": "military_alliance",
                        "members": ["USA", "CAN"],
                        "status": "active",
                        "terms": "Shared defense",
                        "created_at": "2001-01-01 00:00",
                        "source_country_id": "USA",
                        "target_country_id": "CAN",
                    },
                    {
                        "id": "can_gbr",
                        "name": "CAN-GBR Pact",
                        "type": "defensive_pact",
                        "members": ["CAN", "GBR"],
                        "status": "active",
                        "terms": "Defend Canada",
                        "created_at": "2001-01-01 00:00",
                        "source_country_id": "CAN",
                        "target_country_id": "GBR",
                    },
                ],
                schema={
                    "id": pl.Utf8,
                    "name": pl.Utf8,
                    "type": pl.Utf8,
                    "members": pl.List(pl.Utf8),
                    "status": pl.Utf8,
                    "terms": pl.Utf8,
                    "created_at": pl.Utf8,
                    "source_country_id": pl.Utf8,
                    "target_country_id": pl.Utf8,
                },
            ),
        )

        state.current_actions = [
            ActionDeclareWar(
                player_id="tester",
                source_country_tag="USA",
                target_country_tag="CAN",
                casus_belli="Border dispute",
            )
        ]
        self.system.update(state, 0.1)

        wars = state.get_table("countries_wars")
        self.assertEqual(len(wars), 1)
        self.assertEqual(set(wars["side_a"][0].to_list()), {"USA"})
        self.assertEqual(set(wars["side_b"][0].to_list()), {"CAN", "GBR"})
        self.assertEqual(self._relation_value(state.get_table("countries_relations"), "USA", "CAN"), -100.0)
        self.assertEqual(self._relation_value(state.get_table("countries_relations"), "USA", "GBR"), -100.0)

        state.current_actions = [
            ActionDeclareWar(
                player_id="tester",
                source_country_tag="USA",
                target_country_tag="CAN",
                casus_belli="Border dispute",
            )
        ]
        self.system.update(state, 0.1)
        self.assertEqual(len(state.get_table("countries_wars")), 1)

        state.current_actions = [
            ActionOfferPeace(
                player_id="tester",
                war_id="war-missing",
                source_country_tag="USA",
                terms="No effect",
            )
        ]
        self.system.update(state, 0.1)
        self.assertEqual(len(state.get_table("countries_wars")), 1)

    def _build_state(self) -> GameState:
        return GameState(
            tables={
                "countries": pl.DataFrame({"id": ["USA", "CAN", "GBR", "FRA"]}),
                "countries_relations": pl.DataFrame(
                    {
                        "source": ["USA", "CAN", "USA", "GBR", "FRA"],
                        "target": ["CAN", "USA", "GBR", "USA", "USA"],
                        "value": [25.0, 25.0, 10.0, 10.0, 5.0],
                    }
                ),
            }
        )

    def _relation_value(self, relations: pl.DataFrame, source: str, target: str) -> float:
        match = relations.filter((pl.col("source") == source) & (pl.col("target") == target))
        self.assertFalse(match.is_empty(), f"Missing relation for {source}->{target}")
        return float(match["value"][0])


class TestCombatVariations(unittest.TestCase):
    def setUp(self):
        self.system = CombatSystem()

    def test_friendly_stationary_units_and_moving_enemies_do_not_start_battles(self):
        state = self._build_state(
            units=[
                {"id": "usa-1", "owner": "USA", "strength": 100, "current_region_id": 1, "is_moving": False},
                {"id": "usa-2", "owner": "USA", "strength": 60, "current_region_id": 1, "is_moving": False},
                {"id": "can-1", "owner": "CAN", "strength": 120, "current_region_id": 1, "is_moving": True},
            ],
            wars=[{"side_a": ["USA"], "side_b": ["CAN"]}],
            region_owner="USA",
            region_controller="USA",
        )

        self.system.update(state, 0.1)

        self.assertTrue(state.get_table("battles").is_empty())
        self.assertTrue(state.get_table("battle_units").is_empty())
        self.assertEqual(state.get_table("regions")["controller"][0], "USA")

    def test_unclaimed_regions_are_not_occupied(self):
        state = self._build_state(
            units=[
                {"id": "usa-1", "owner": "USA", "strength": 100, "current_region_id": 1, "is_moving": False},
            ],
            wars=[{"side_a": ["USA"], "side_b": ["CAN"]}],
            region_owner="",
            region_controller="",
        )

        self.system.update(state, 0.1)

        self.assertTrue(state.get_table("battles").is_empty())
        self.assertTrue(state.get_table("battle_units").is_empty())
        self.assertEqual(state.get_table("regions")["controller"][0], "")

    def _build_state(
        self,
        units: list[dict],
        wars: list[dict],
        region_owner: str,
        region_controller: str,
    ) -> GameState:
        wars_frame = (
            pl.DataFrame(wars)
            if wars
            else pl.DataFrame(schema={"side_a": pl.List(pl.Utf8), "side_b": pl.List(pl.Utf8)})
        )
        return GameState(
            tables={
                "countries": pl.DataFrame(
                    {
                        "id": ["USA", "CAN"],
                        "military_count": [240, 120],
                    }
                ),
                "regions": pl.DataFrame(
                    {
                        "id": [1],
                        "owner": [region_owner],
                        "controller": [region_controller],
                    }
                ),
                "units": pl.DataFrame(units),
                "countries_wars": wars_frame,
            }
        )


class TestAISystemVariations(unittest.TestCase):
    def setUp(self):
        self.system = AISystem()

    def test_ai_stays_idle_when_all_thresholds_fail(self):
        state = GameState(
            tables={
                "countries": pl.DataFrame(
                    {
                        "id": ["USA", "CAN"],
                        "gdp": [1_000.0, 1_000.0],
                        "money_reserves": [0.0, 0.0],
                        "total_annual_revenue": [10.0, 10.0],
                        "total_annual_expense": [10.0, 10.0],
                        "human_dev": [0.5, 0.5],
                        "trait_threat_perception": [1.0, 1.0],
                        "military_count": [0, 0],
                        "personal_income_tax_rate": [0.2, 0.2],
                    }
                ),
            }
        )
        state.events.append(EventNewDay(day=2, month=1, year=2001))

        self.system.update(state, 0.1)

        self.assertEqual(state.current_actions, [])

    def test_ai_debug_cache_starts_empty(self):
        self.assertTrue(self.system.last_decisions.is_empty())
        self.assertIn("reason_code", self.system.last_decisions.columns)


if __name__ == "__main__":
    unittest.main()