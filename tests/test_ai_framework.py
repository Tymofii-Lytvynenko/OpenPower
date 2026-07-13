import unittest
from collections.abc import Mapping
from typing import Any

import polars as pl

from src.core.ai_framework import (
    AITableContext,
    DeclarativeAIFramework,
    scheduled_countries,
)
from src.shared.actions import ActionUpdateBudget, GameAction


class _Policy:
    id = "test_policy"
    required_tables = frozenset({"countries"})
    cadence_days = 1

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def build_candidates(self, context: AITableContext) -> pl.LazyFrame:
        return pl.DataFrame(self.rows).lazy()

    def resolve_action(self, row: Mapping[str, Any]) -> GameAction | None:
        return ActionUpdateBudget(
            "test",
            str(row["country_id"]),
            {"personal_income_tax_rate": float(row["utility"])},
        )


class _InvalidPolicy(_Policy):
    id = "invalid"

    def build_candidates(self, context: AITableContext) -> pl.DataFrame:
        return pl.DataFrame(self.rows)


class TestDeclarativeAIFramework(unittest.TestCase):
    def test_rank_quota_and_conflict_deduplication_are_deterministic(self):
        rows = [
            self._row("AAA", "budget", 0.90, "same", 1, "top"),
            self._row("AAA", "budget", 0.80, "same", 1, "duplicate"),
            self._row("AAA", "budget", 0.70, "other", 1, "over_quota"),
            self._row("AAA", "orders", 0.90, "unit-1", 2, "first"),
            self._row("AAA", "orders", 0.80, "unit-2", 2, "second"),
            self._row("AAA", "orders", 0.70, "unit-3", 2, "third"),
        ]
        context = AITableContext(
            tables={"countries": pl.DataFrame({"id": ["AAA"]})},
            day_ordinal=1,
            total_minutes=1440,
            date_text="2001-01-02 00:00",
        )

        result = DeclarativeAIFramework(_Policy(rows)).evaluate(context)

        self.assertEqual(len(result.actions), 3)
        self.assertEqual(result.decisions["reason_code"].to_list(), ["top", "first", "second"])
        self.assertEqual(result.decisions["rank"].to_list(), [1, 1, 2])
        self.assertTrue(
            {
                "country_id",
                "policy_id",
                "domain",
                "utility",
                "conflict_key",
                "action_kind",
                "reason_code",
                "quota",
                "rank",
            }.issubset(result.decisions.columns)
        )

    def test_equal_utility_conflicts_use_payload_as_a_stable_tiebreaker(self):
        rows = [
            {**self._row("AAA", "procurement", 0.75, "same", 1, "tie"), "design_id": "Z-design"},
            {**self._row("AAA", "procurement", 0.75, "same", 1, "tie"), "design_id": "A-design"},
        ]
        context = AITableContext(
            tables={"countries": pl.DataFrame({"id": ["AAA"]})},
            day_ordinal=1,
            total_minutes=1440,
            date_text="2001-01-02 00:00",
        )

        forward = DeclarativeAIFramework(_Policy(rows)).evaluate(context)
        reverse = DeclarativeAIFramework(_Policy(list(reversed(rows)))).evaluate(context)

        self.assertEqual(forward.decisions["design_id"].to_list(), ["A-design"])
        self.assertEqual(reverse.decisions["design_id"].to_list(), ["A-design"])

    def test_register_is_fluent_and_rejects_duplicate_ids(self):
        framework = DeclarativeAIFramework()
        policy = _Policy([self._row("AAA", "budget", 1.0, "a", 1, "a")])

        self.assertIs(framework.register(policy), framework)
        self.assertEqual(framework.policy_ids, ("test_policy",))
        with self.assertRaises(ValueError):
            framework.register(policy)

    def test_missing_required_table_skips_only_that_policy(self):
        result = DeclarativeAIFramework(_Policy([])).evaluate(
            AITableContext({}, 0, 0, "2001-01-01 00:00")
        )

        self.assertEqual(result.actions, ())
        self.assertEqual(result.skipped_policies, ("test_policy",))
        self.assertTrue(result.decisions.is_empty())

    def test_policy_must_return_lazy_frame(self):
        context = AITableContext(
            {"countries": pl.DataFrame({"id": ["AAA"]})},
            0,
            0,
            "2001-01-01 00:00",
        )
        with self.assertRaises(TypeError):
            DeclarativeAIFramework(_InvalidPolicy([])).evaluate(context)

    def test_cadence_uses_stable_tag_slots_and_filters_controlled_countries(self):
        countries = pl.DataFrame(
            {
                "id": ["CCC", "AAA", "PLAYER", "BBB", "DISABLED"],
                "is_playable": [True, True, True, True, False],
            }
        ).lazy()
        context = AITableContext(
            {},
            day_ordinal=1,
            total_minutes=1440,
            date_text="2001-01-02 00:00",
            player_tag="PLAYER",
        )

        selected = scheduled_countries(countries, context, 2).collect()

        self.assertEqual(selected["country_id"].to_list(), ["BBB"])

    def _row(
        self,
        country: str,
        domain: str,
        utility: float,
        conflict_key: str,
        quota: int,
        reason: str,
    ) -> dict[str, Any]:
        return {
            "country_id": country,
            "policy_id": "test_policy",
            "domain": domain,
            "utility": utility,
            "conflict_key": conflict_key,
            "action_kind": "update_budget",
            "reason_code": reason,
            "quota": quota,
        }


if __name__ == "__main__":
    unittest.main()
