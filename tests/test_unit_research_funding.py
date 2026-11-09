from __future__ import annotations

import unittest

from src.shared.research_funding import (
    RESEARCH_CATEGORY_FUNDING_GROUP,
    STRATEGIC_PROGRAM_FUNDING_GROUP,
    _ratio,
    linked_research_funding_group,
    redistribute_linked_funding,
)


class LinkedResearchFundingTests(unittest.TestCase):
    def test_main_category_delta_is_distributed_proportionally(self) -> None:
        initial = {
            "ground": 0.4,
            "air": 0.3,
            "naval": 0.2,
            "strategic": 0.1,
        }

        result = redistribute_linked_funding(
            initial,
            "ground",
            0.5,
            RESEARCH_CATEGORY_FUNDING_GROUP,
        )

        self.assertAlmostEqual(result["ground"], 0.5)
        self.assertAlmostEqual(result["air"], 0.25)
        self.assertAlmostEqual(result["naval"], 1.0 / 6.0)
        self.assertAlmostEqual(result["strategic"], 1.0 / 12.0)
        self.assertAlmostEqual(sum(result.values()), 1.0)

    def test_strategic_detail_distribution_stays_within_its_own_group(self) -> None:
        initial = {
            "ground": 0.4,
            "strategic_program": 0.2,
            "strategic_weapons": 0.3,
            "strategic_defense": 0.5,
        }

        result = redistribute_linked_funding(
            initial,
            "strategic_program",
            0.5,
            STRATEGIC_PROGRAM_FUNDING_GROUP,
        )

        self.assertAlmostEqual(result["strategic_program"], 0.5)
        self.assertAlmostEqual(result["strategic_weapons"], 0.1875)
        self.assertAlmostEqual(result["strategic_defense"], 0.3125)
        self.assertAlmostEqual(
            sum(result[branch] for branch in (
                "strategic_program", "strategic_weapons", "strategic_defense"
            )),
            1.0,
        )
        self.assertAlmostEqual(result["ground"], 0.4)

    def test_zero_valued_peers_follow_source_clamping_behavior(self) -> None:
        result = redistribute_linked_funding(
            {"ground": 0.0, "air": 0.0, "naval": 0.0, "strategic": 0.0},
            "ground",
            0.4,
            RESEARCH_CATEGORY_FUNDING_GROUP,
        )

        self.assertEqual(result, {"ground": 0.4, "air": 0.0, "naval": 0.0, "strategic": 0.0})

    def test_locked_linked_cursor_is_excluded_from_redistribution(self) -> None:
        result = redistribute_linked_funding(
            {"ground": 0.2, "air": 0.3, "naval": 0.3, "strategic": 0.2},
            "ground",
            0.4,
            RESEARCH_CATEGORY_FUNDING_GROUP,
            locked_branches=("strategic",),
        )

        self.assertEqual(result["strategic"], 0.2)
        self.assertAlmostEqual(result["air"], 0.2)
        self.assertAlmostEqual(result["naval"], 0.2)
        self.assertAlmostEqual(result["ground"], 0.4)

    def test_known_research_branches_share_their_source_cursor_groups(self) -> None:
        self.assertEqual(linked_research_funding_group("air"), RESEARCH_CATEGORY_FUNDING_GROUP)
        self.assertEqual(
            linked_research_funding_group("strategic_weapons"),
            STRATEGIC_PROGRAM_FUNDING_GROUP,
        )
        self.assertEqual(linked_research_funding_group("general"), ("general",))

    def test_unlinked_branch_updates_only_the_selected_ratio(self) -> None:
        result = redistribute_linked_funding(
            {"ground": 0.2, "general": 0.4},
            "general",
            1.5,
            ("ground",),
        )

        self.assertEqual(result, {"ground": 0.2, "general": 1.0})

    def test_linked_funding_returns_early_when_there_are_no_peers(self) -> None:
        result = redistribute_linked_funding(
            {"ground": 0.4}, "ground", 0.4, ("ground",)
        )

        self.assertEqual(result, {"ground": 0.4})

    def test_ratio_defaults_to_zero_for_invalid_and_nonfinite_values(self) -> None:
        self.assertEqual(_ratio("not-a-number"), 0.0)
        self.assertEqual(_ratio(float("inf")), 0.0)


if __name__ == "__main__":
    unittest.main()
