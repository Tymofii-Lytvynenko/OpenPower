from __future__ import annotations

import unittest

from modules.base.systems.military.capability_catalog import (
    CAPABILITY_BOUNDS,
    CAPABILITY_METADATA,
    DEFAULT_ROLE_PROFILES,
    FIXED_ROLE_CHARACTERISTICS,
    canonical_role,
    design_capability_error,
    get_role_profile,
    project_capabilities,
    researched_capabilities,
    trained_capabilities,
    training_bonus,
)


class CapabilityCatalogTest(unittest.TestCase):
    def test_default_catalog_covers_land_air_naval_and_strategic_roles(self) -> None:
        domains = {profile.domain for profile in DEFAULT_ROLE_PROFILES.values()}
        self.assertEqual(domains, {"land", "air", "naval", "strategic"})
        self.assertGreaterEqual(len(DEFAULT_ROLE_PROFILES), 20)
        self.assertEqual(canonical_role("Tank"), "tanks")
        self.assertEqual(canonical_role("anti-submarine helicopter"), "anti_submarine_helicopters")

    def test_every_capability_has_complete_design_metadata(self) -> None:
        self.assertEqual(set(CAPABILITY_METADATA), set(CAPABILITY_BOUNDS))
        required_fields = {
            "unit",
            "adjustability",
            "minimum",
            "maximum",
            "prerequisite",
            "production_effect",
            "interaction",
            "zero_semantics",
            "effect_scope",
        }
        for name, metadata in CAPABILITY_METADATA.items():
            with self.subTest(capability=name):
                self.assertEqual(set(metadata), required_fields)
                self.assertEqual((metadata["minimum"], metadata["maximum"]), CAPABILITY_BOUNDS[name])
                self.assertEqual(metadata["adjustability"], "design_variable")
                self.assertTrue(metadata["unit"])
                self.assertTrue(metadata["prerequisite"])
                self.assertTrue(metadata["production_effect"])
                self.assertTrue(metadata["interaction"])
                self.assertTrue(metadata["zero_semantics"])

        self.assertEqual(
            set(FIXED_ROLE_CHARACTERISTICS),
            {"role", "domain", "valid_targets", "vulnerabilities"},
        )
        self.assertTrue(all(FIXED_ROLE_CHARACTERISTICS.values()))

    def test_every_default_role_has_a_bounded_profile_and_explicit_interactions(self) -> None:
        self.assertTrue(DEFAULT_ROLE_PROFILES)
        for role, profile in DEFAULT_ROLE_PROFILES.items():
            with self.subTest(role=role):
                self.assertEqual(profile.role, role)
                self.assertIn(profile.domain, {"land", "air", "naval", "strategic"})
                self.assertTrue(profile.valid_targets)
                self.assertTrue(profile.vulnerabilities)
                self.assertEqual(set(profile.capabilities), set(CAPABILITY_BOUNDS))
                projected = project_capabilities(profile)
                for capability, value in projected.items():
                    minimum, maximum = CAPABILITY_BOUNDS[capability]
                    self.assertGreaterEqual(value, minimum)
                    self.assertLessEqual(value, maximum)

    def test_design_capabilities_are_bounded_and_role_domain_is_fixed(self) -> None:
        profile = get_role_profile("tank", "air")
        result = project_capabilities(profile, {"speed": 99999, "stealth": -1, "unknown": 4})
        self.assertEqual(profile.domain, "land")
        self.assertEqual(result["speed"], CAPABILITY_BOUNDS["speed"][1])
        self.assertEqual(result["stealth"], CAPABILITY_BOUNDS["stealth"][0])
        self.assertNotIn("unknown", result)

    def test_training_improves_only_role_relevant_operational_characteristics(self) -> None:
        base = project_capabilities(get_role_profile("fighter"))
        elite = trained_capabilities(base, "Elite")
        self.assertGreater(elite["speed"], base["speed"])
        self.assertGreater(elite["sensors"], base["sensors"])
        self.assertGreater(elite["gun_precision"], base["gun_precision"])
        self.assertEqual(elite["gun_damage"], base["gun_damage"])
        self.assertEqual(elite["armor"], base["armor"])
        self.assertEqual(trained_capabilities(base, "Recruit"), base)

    def test_research_bonus_is_bounded_and_does_not_change_unspecified_capabilities(self) -> None:
        base = project_capabilities(get_role_profile("fighter"))
        improved = researched_capabilities(base, 20, {
            "sensors": {"per_level": 0.1, "max_bonus": 0.25},
            "armor": -0.5,
            "not_a_capability": 0.5,
        })

        self.assertAlmostEqual(improved["sensors"], base["sensors"] * 1.25)
        self.assertEqual(improved["armor"], base["armor"])
        self.assertEqual(improved["speed"], base["speed"])

    def test_design_error_explains_missing_required_stats_and_weapon_profile(self) -> None:
        message = design_capability_error("air defense", {})

        self.assertIn("missing required capabilities", message)
        self.assertIn("complete gun or missile profile", message)

    def test_design_error_reports_missing_weapon_profile_after_required_stats_pass(self) -> None:
        message = design_capability_error(
            "air_defense",
            {"sensors": 1, "speed": 1, "armor": 1},
        )

        self.assertEqual(
            message,
            "The selected design needs a complete gun or missile profile.",
        )

    def test_invalid_training_level_falls_back_to_recruit(self) -> None:
        self.assertEqual(training_bonus("unlisted training"), 0.0)

    def test_invalid_capability_values_are_normalized_to_safe_defaults(self) -> None:
        profile = get_role_profile("tanks")
        projected = project_capabilities(profile, {"speed": "not-a-number"})
        base = project_capabilities(profile)

        self.assertEqual(projected["speed"], CAPABILITY_BOUNDS["speed"][0])
        self.assertEqual(
            researched_capabilities(base, "not-a-number", {"speed": 0.1}),
            base,
        )


if __name__ == "__main__":
    unittest.main()
