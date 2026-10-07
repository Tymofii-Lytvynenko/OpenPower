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


class _ScopedDiplomacyPolicy(_Policy):
    id = "diplomacy"


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

    def test_delegated_country_is_scheduled_but_only_within_declared_ai_authority(self):
        rows = [
            self._row("PLAYER", "budget", 0.9, "budget-action", 1, "delegated_budget"),
            self._row("PLAYER", "diplomacy", 0.9, "diplomacy-action", 1, "not_delegated"),
            self._row("BBB", "budget", 0.8, "ai_budget", 1, "ordinary_ai"),
        ]
        context = AITableContext(
            tables={"countries": pl.DataFrame({"id": ["PLAYER", "BBB"]})},
            day_ordinal=1,
            total_minutes=1440,
            date_text="2001-01-02 00:00",
            player_tag="PLAYER",
            delegated_domains={"PLAYER": frozenset({"economy"})},
        )

        result = DeclarativeAIFramework(_Policy(rows)).evaluate(context)

        self.assertEqual(result.decisions["country_id"].to_list(), ["BBB", "PLAYER"])
        self.assertEqual(result.decisions["domain"].to_list(), ["budget", "budget"])

        countries = pl.DataFrame(
            {"id": ["PLAYER", "BBB"], "is_playable": [True, True]}
        ).lazy()
        scheduled = scheduled_countries(countries, context, 1).collect()
        self.assertEqual(scheduled["country_id"].to_list(), ["BBB", "PLAYER"])

    def test_sphere_delegation_limits_diplomacy_to_treaty_members_and_treaty_id(self):
        rows = [
            {**self._row("PLAYER", "diplomacy", 0.9, "member-proposal", 1, "allowed"),
             "policy_id": "diplomacy", "action_kind": "create_treaty", "target_country": "CAN"},
            {**self._row("PLAYER", "diplomacy", 0.8, "outside-proposal", 1, "blocked"),
             "policy_id": "diplomacy", "action_kind": "create_treaty", "target_country": "MEX"},
            {**self._row("PLAYER", "diplomacy", 0.7, "member-response", 1, "allowed"),
             "policy_id": "diplomacy", "action_kind": "respond_treaty", "source_country": "CAN", "treaty_id": "pending-1"},
            {**self._row("PLAYER", "diplomacy", 0.6, "sphere-join", 1, "allowed"),
             "policy_id": "diplomacy", "action_kind": "join_treaty", "treaty_id": "trade-union"},
            {**self._row("PLAYER", "diplomacy", 0.5, "outside-join", 1, "blocked"),
             "policy_id": "diplomacy", "action_kind": "join_treaty", "treaty_id": "other-treaty"},
        ]
        for row in rows:
            row["quota"] = 10
        context = AITableContext(
            tables={"countries": pl.DataFrame({"id": ["PLAYER"]})},
            day_ordinal=1,
            total_minutes=1440,
            date_text="2001-01-02 00:00",
            player_tag="PLAYER",
            delegated_domains={"PLAYER": frozenset({"diplomacy"})},
            delegated_targets={"PLAYER": frozenset({"CAN"})},
            delegated_treaty_ids={"PLAYER": frozenset({"trade-union"})},
        )

        result = DeclarativeAIFramework(_ScopedDiplomacyPolicy(rows)).evaluate(context)

        self.assertEqual(
            set(result.decisions["conflict_key"].to_list()),
            {"member-proposal", "member-response", "sphere-join"},
        )

    def test_sphere_scope_filters_before_policy_quota_ranking(self):
        rows = [
            {**self._row("PLAYER", "diplomacy", 0.6, "member-proposal", 1, "allowed"),
             "policy_id": "diplomacy", "action_kind": "create_treaty", "target_country": "CAN"},
            {**self._row("PLAYER", "diplomacy", 1.0, "outside-proposal", 1, "blocked"),
             "policy_id": "diplomacy", "action_kind": "create_treaty", "target_country": "MEX"},
        ]
        context = AITableContext(
            tables={"countries": pl.DataFrame({"id": ["PLAYER"]})},
            day_ordinal=1, total_minutes=1440, date_text="2001-01-02 00:00",
            player_tag="PLAYER", delegated_domains={"PLAYER": frozenset({"diplomacy"})},
            delegated_targets={"PLAYER": frozenset({"CAN"})},
        )

        result = DeclarativeAIFramework(_ScopedDiplomacyPolicy(rows)).evaluate(context)

        self.assertEqual(result.decisions["conflict_key"].to_list(), ["member-proposal"])

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
