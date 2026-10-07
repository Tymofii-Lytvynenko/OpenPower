from __future__ import annotations

import unittest

import polars as pl

from modules.base.schema import ensure_base_tables
from modules.base.systems.world.ai_system import AISystem
from modules.base.systems.world.ai.infrastructure_policy import InfrastructurePolicy
from modules.base.systems.world.infrastructure_system import InfrastructureSystem
from src.core.ai_framework import AITableContext
from src.shared.actions import ActionInvestRegionalInfrastructure
from src.shared.events import EventNewDay
from src.shared.state import GameState

from tests.test_regional_infrastructure_fixtures import build_infrastructure_state


class InfrastructurePolicyTests(unittest.TestCase):
    def _context(self, *, player_tag: str = "", active_project: bool = False, policy_override=None):
        project_rows = (
            [{"region_id": 7, "category": "transport", "status": "in_progress"}]
            if active_project
            else []
        )
        return AITableContext(
            tables={
                "countries": pl.DataFrame(
                    {
                        "id": ["NPC"],
                        "is_playable": [True],
                        "money_reserves": [100_000.0],
                        "budget_infra_ratio": [0.2],
                        "budget_telecom_ratio": [0.2],
                        "budget_health_ratio": [0.2],
                    }
                ),
                "regions": pl.DataFrame(
                    {"id": [7], "owner": ["NPC"], "area_km2": [1_000.0]}
                ),
                "regional_infrastructure": pl.DataFrame(
                    {
                        "region_id": [7],
                        "category": ["transport"],
                        "level": [0.3],
                        "condition": [1.0],
                        "capacity": [0.3],
                        "maximum": [1.0],
                    }
                ),
                "infrastructure_projects": pl.DataFrame(
                    project_rows,
                    schema={
                        "region_id": pl.Int64,
                        "category": pl.Utf8,
                        "status": pl.Utf8,
                    },
                ),
                "infrastructure_damage_records": pl.DataFrame(
                    schema={
                        "region_id": pl.Int64,
                        "category": pl.Utf8,
                        "restoration_ceiling": pl.Float64,
                    }
                ),
            },
            day_ordinal=0,
            total_minutes=0,
            date_text="0001-01-01",
            player_tag=player_tag,
            globals=policy_override or {},
        )

    def test_selects_affordable_weak_region_and_resolves_to_semantic_server_action(self):
        policy = InfrastructurePolicy()
        candidates = policy.build_candidates(self._context()).collect()

        self.assertEqual(candidates.height, 1)
        action = policy.resolve_action(candidates.row(0, named=True))
        self.assertIsInstance(action, ActionInvestRegionalInfrastructure)
        self.assertEqual(action.player_id, "ai_system")
        self.assertEqual(action.country_tag, "NPC")
        self.assertEqual(action.region_id, 7)
        self.assertEqual(action.category, "transport")
        self.assertAlmostEqual(action.target_level, 0.35)

    def test_skips_player_country_and_categories_with_active_projects(self):
        policy = InfrastructurePolicy()

        player_candidates = policy.build_candidates(
            self._context(player_tag="NPC")
        ).collect()
        project_candidates = policy.build_candidates(
            self._context(active_project=True)
        ).collect()

        self.assertTrue(player_candidates.is_empty())
        self.assertTrue(project_candidates.is_empty())

    def test_uses_scenario_cost_policy_when_screening_available_treasury(self):
        policy = InfrastructurePolicy()
        context = self._context(
            policy_override={
                "infrastructure_category_policies": {
                    "transport": {"construction_cost_per_level": 500_000.0}
                }
            }
        )

        candidates = policy.build_candidates(context).collect()

        self.assertTrue(candidates.is_empty())

    def test_registered_ai_decision_is_accepted_by_authoritative_infrastructure_system(self):
        state = build_infrastructure_state()
        ensure_base_tables(state)
        InfrastructureSystem().update(state, 0.0)
        state.events.append(EventNewDay(day=2, month=1, year=2001))

        AISystem().update(state, 0.0)
        investment_actions = [
            action for action in state.current_actions
            if isinstance(action, ActionInvestRegionalInfrastructure)
        ]
        self.assertTrue(investment_actions)

        InfrastructureSystem().update(state, 0.0)

        projects = state.get_table("infrastructure_projects")
        self.assertGreater(projects.height, 0)
        self.assertEqual(projects.filter(pl.col("status") == "in_progress").height, len(investment_actions))
        self.assertTrue(state.journal.command_results)


if __name__ == "__main__":
    unittest.main()
