import unittest
import polars as pl
from modules.base.schema import ensure_base_tables
from modules.base.systems.military.research_program_system import ResearchProgramSystem
from src.shared.actions import ActionUpdateResearchFunding
from src.shared.state import GameState
from src.shared.events import EventSystemError

class TestGameStateIPC(unittest.TestCase):
    def test_ipc_roundtrip_all_tables(self):
        state = GameState()
        df_regions = pl.DataFrame({"id": [1, 2], "owner": ["USA", "CAN"]})
        df_trade = pl.DataFrame({
            "exporter_id": ["USA"], 
            "importer_id": ["WORLD"], 
            "game_resource_id": ["electricity"], 
            "trade_value_usd": [5000.0]
        })
        
        state.update_table("regions", df_regions)
        state.update_table("trade_network", df_trade)
        state.time.total_minutes = 300
        state.globals["tick"] = 5
        state.system_state["base.time"] = {"real_sec_timer": 0.4, "last_event_total_minutes": 240}
        state.events.append(EventSystemError("test.system", "boom", "traceback"))
        
        # 1. Roundtrip serialization
        ipc_data = state.to_ipc()
        self.assertIn("trade_network", ipc_data["tables"])  # Verify trade_network is NOT excluded
        
        # 2. Deserialization
        restored = GameState.from_ipc(ipc_data)
        self.assertEqual(restored.time.total_minutes, 300)
        self.assertEqual(restored.globals["tick"], 5)
        self.assertEqual(restored.system_state, {"base.time": {"real_sec_timer": 0.4, "last_event_total_minutes": 240}})
        self.assertEqual(len(restored.events), 1)
        self.assertIsInstance(restored.events[0], EventSystemError)
        self.assertEqual(restored.events[0].system_id, "test.system")
        
        # 3. Assert content equality
        self.assertTrue(restored.get_table("regions").equals(df_regions))
        self.assertTrue(restored.get_table("trade_network").equals(df_trade))

    def test_ipc_roundtrip_preserves_political_lifecycle_records(self):
        state = GameState(
            tables={
                "countries": pl.DataFrame({"id": ["AAA"]}),
                "country_governments": pl.DataFrame(
                    {
                        "country_id": ["AAA"],
                        "government_form_id": ["multi-party democracy"],
                        "next_election_at_minute": [48_000],
                    }
                ),
            }
        )
        ensure_base_tables(state)
        state.update_table(
            "law_transitions",
            pl.DataFrame(
                {
                    "id": ["transition-1"],
                    "country_id": ["AAA"],
                    "law_id": ["civil_rights"],
                    "effective_at_minute": [24_000],
                    "status": ["scheduled"],
                }
            ),
        )
        state.update_table(
            "political_elections",
            pl.DataFrame(
                {
                    "id": ["election-1"],
                    "country_id": ["AAA"],
                    "scheduled_at_minute": [48_000],
                    "status": ["scheduled"],
                }
            ),
        )
        state.update_table(
            "political_crises",
            pl.DataFrame(
                {
                    "id": ["crisis-1"],
                    "country_id": ["AAA"],
                    "crisis_type": ["coup_attempt"],
                    "support": [0.7],
                    "status": ["active"],
                }
            ),
        )

        restored = GameState.from_ipc(state.to_ipc())

        for table_name in (
            "country_governments",
            "government_form_rules",
            "political_parties",
            "country_laws",
            "law_transitions",
            "political_elections",
            "political_crises",
            "political_effects",
            "political_history",
        ):
            self.assertTrue(
                restored.get_table(table_name).equals(state.get_table(table_name)),
                table_name,
            )

    def test_ipc_roundtrip_preserves_military_capability_and_intelligence_records(self):
        state = GameState(tables={"countries": pl.DataFrame({"id": ["USA"]})})
        ensure_base_tables(state)
        state.update_table("unit_training_facilities", pl.DataFrame([{
            "id": "site-1", "country_id": "USA", "region_id": 4,
            "supported_domains": ["land"], "capacity": 2,
            "instructor_count": 1, "enabled": True,
        }], schema=state.get_table("unit_training_facilities").schema))
        state.update_table("unit_training_orders", pl.DataFrame([{
            "id": "training-1", "unit_id": "unit-1", "country_id": "USA",
            "facility_id": "site-1", "training_location_region_id": 4,
            "from_level": "Recruit", "target_level": "Regular", "progress": 0.4,
            "required_days": 30.0, "cost": 100.0, "status": "active",
            "return_region_id": 4, "return_latitude": 1.0, "return_longitude": 2.0,
            "started_at_minute": 10, "updated_at_minute": 20,
            "completed_at_minute": 0, "cancelled_at_minute": 0,
            "last_event": "resumed", "last_event_at_minute": 15,
            "blocking_reason": "",
        }], schema=state.get_table("unit_training_orders").schema))
        state.update_table("unit_capability_projections", pl.DataFrame([{
            "unit_id": "unit-1", "country_id": "USA", "role": "tanks", "domain": "land",
            "capabilities_json": '{"gun_damage":12.0}', "valid_targets_json": '["armor"]',
            "vulnerabilities_json": '["air"]', "training_level": "Recruit",
            "research_level": 2, "updated_at_minute": 20,
        }], schema=state.get_table("unit_capability_projections").schema))
        state.update_table("covert_findings", pl.DataFrame([{
            "id": "finding-1", "owner_country_id": "USA", "target_country_id": "CAN",
            "category": "military_mobilization", "value_json": '{"domain":"land"}',
            "confidence": 0.6, "freshness": 1.0,
            "discovered_at_minute": 20, "expires_at_minute": 200,
        }], schema=state.get_table("covert_findings").schema))

        restored = GameState.from_ipc(state.to_ipc())

        for table_name in (
            "unit_training_facilities",
            "unit_training_orders",
            "unit_capability_projections",
            "covert_findings",
        ):
            self.assertTrue(restored.get_table(table_name).equals(state.get_table(table_name)), table_name)

    def test_research_noop_and_funding_change_continue_identically_after_ipc(self):
        state = GameState(tables={
            "countries": pl.DataFrame({
                "id": ["USA"], "gdp": [100.0], "budget_research_ratio": [0.1],
                "money_reserves": [1000.0], "military_count": [1],
            }),
        })
        ensure_base_tables(state)
        state.globals["player_country_map"] = {"player": "USA"}
        restored = GameState.from_ipc(state.to_ipc())

        for candidate in (state, restored):
            before = dict(candidate.table_revisions)
            ResearchProgramSystem().update(candidate, 0.0)
            self.assertEqual(dict(candidate.table_revisions), before)
            candidate.current_actions = [ActionUpdateResearchFunding("player", "USA", "ground", 0.5)]
            ResearchProgramSystem().update(candidate, 0.0)

        for table_name in ("research_tracks", "unit_designs", "production_orders", "countries"):
            self.assertTrue(state.get_table(table_name).equals(restored.get_table(table_name)), table_name)
