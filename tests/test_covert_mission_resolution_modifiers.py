import unittest

from src.shared.covert_mission_options import (
    mission_effect_modifier,
    mission_success_modifier,
)


class CovertMissionResolutionModifiersTest(unittest.TestCase):
    def test_source_complexity_changes_success_chance_in_inverse_order(self):
        mission_type = "civilian_espionage"

        self.assertEqual(
            mission_success_modifier(mission_type, "low", has_specific_target=False),
            2.0,
        )
        self.assertEqual(
            mission_success_modifier(mission_type, "medium", has_specific_target=False),
            1.0,
        )
        self.assertEqual(
            mission_success_modifier(mission_type, "high", has_specific_target=False),
            0.5,
        )

    def test_specific_resource_or_unit_target_reduces_spy_and_sabotage_chance(self):
        for mission_type in (
            "civilian_espionage",
            "military_espionage",
            "civilian_sabotage",
            "military_sabotage",
        ):
            with self.subTest(mission_type=mission_type):
                self.assertEqual(
                    mission_success_modifier(mission_type, "medium", has_specific_target=True),
                    0.75,
                )
                self.assertEqual(
                    mission_success_modifier(mission_type, "medium", has_specific_target=False),
                    1.0,
                )

    def test_political_missions_do_not_use_specific_sector_penalty(self):
        self.assertEqual(
            mission_success_modifier("assassination", "medium", has_specific_target=True),
            1.0,
        )

    def test_source_complexity_scales_effect_strength_and_partial_success(self):
        self.assertEqual(mission_effect_modifier("low", partial=False), 0.25)
        self.assertEqual(mission_effect_modifier("medium", partial=False), 1.0)
        self.assertEqual(mission_effect_modifier("high", partial=False), 2.0)
        self.assertEqual(mission_effect_modifier("high", partial=True), 1.0)


if __name__ == "__main__":
    unittest.main()
