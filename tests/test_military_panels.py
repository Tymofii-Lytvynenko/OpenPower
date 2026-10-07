from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from src.client.ui.panels.military.unit_design_panel import UnitDesignPanel
from src.client.ui.panels.military.unit_list_panel import UnitListPanel


class UnitListPanelTest(unittest.TestCase):
    def test_foreign_estimates_show_ranges_sources_freshness_and_non_sensitive_factors(self) -> None:
        panel = UnitListPanel()
        panel._presenter = MagicMock()
        panel._presenter.mobilization_signals_for_country.return_value = []
        panel._presenter.foreign_force_estimates_for_country.return_value = [{
            "target_country_id": "MEX",
            "target_country_name": "Mexico",
            "source_country_id": "CAN",
            "source_type": "allied",
            "observed_at_minute": 42,
            "confidence": 0.75,
            "freshness": 0.5,
            "status": "estimated",
            "total_count_range": (8, 12),
            "role_count_ranges": (("tanks", 2, 4),),
            "source_factors": {
                "observer_telecom": 0.8,
                "target_telecom": 0.5,
                "intelligence_coverage": "sustained",
            },
        }]
        mock_imgui = MagicMock()

        with patch("src.client.ui.panels.military.unit_list_panel.imgui", mock_imgui):
            panel._render_foreign_estimates(object(), "USA")

        rendered = " ".join(str(call.args[0]) for call in mock_imgui.text.call_args_list + mock_imgui.text_disabled.call_args_list + mock_imgui.text_wrapped.call_args_list)
        self.assertIn("Mexico: estimated 8–12 units", rendered)
        self.assertIn("Tanks 2–4", rendered)
        self.assertIn("Source CAN (allied)", rendered)
        self.assertIn("confidence 75%", rendered)
        self.assertIn("freshness 50%", rendered)
        self.assertIn("observer telecom 80%", rendered)
        self.assertIn("intelligence coverage sustained", rendered)

    def test_expired_estimates_do_not_render_a_zero_force(self) -> None:
        panel = UnitListPanel()
        panel._presenter = MagicMock()
        panel._presenter.mobilization_signals_for_country.return_value = []
        panel._presenter.foreign_force_estimates_for_country.return_value = [{
            "target_country_id": "MEX",
            "target_country_name": "Mexico",
            "source_country_id": "USA",
            "source_type": "owned",
            "observed_at_minute": 1,
            "confidence": 0.9,
            "freshness": 0.0,
            "status": "outdated",
            "total_count_range": None,
            "role_count_ranges": (),
            "source_factors": {},
        }]
        mock_imgui = MagicMock()

        with patch("src.client.ui.panels.military.unit_list_panel.imgui", mock_imgui):
            panel._render_foreign_estimates(object(), "USA")

        rendered = " ".join(str(call.args[0]) for call in mock_imgui.text.call_args_list)
        self.assertIn("outdated intelligence; current force size unknown", rendered)
        self.assertNotIn("0 units", rendered)

    def test_unobserved_enemy_is_labeled_unknown_not_zero(self) -> None:
        panel = UnitListPanel()
        panel._presenter = MagicMock()
        panel._presenter.mobilization_signals_for_country.return_value = []
        panel._presenter.foreign_force_estimates_for_country.return_value = [{
            "target_country_id": "MEX",
            "target_country_name": "Mexico",
            "source_country_id": "",
            "source_type": "none",
            "observed_at_minute": 0,
            "confidence": 0.0,
            "freshness": 0.0,
            "status": "unknown",
            "total_count_range": None,
            "role_count_ranges": (),
            "source_factors": {},
        }]
        mock_imgui = MagicMock()

        with patch("src.client.ui.panels.military.unit_list_panel.imgui", mock_imgui):
            panel._render_foreign_estimates(object(), "USA")

        rendered = " ".join(str(call.args[0]) for call in mock_imgui.text.call_args_list)
        self.assertIn("Mexico: force strength unknown", rendered)
        self.assertNotIn("0 units", rendered)

    def test_mobilization_signal_displays_readiness_change_without_unit_identity(self) -> None:
        panel = UnitListPanel()
        panel._presenter = MagicMock()
        panel._presenter.foreign_force_estimates_for_country.return_value = []
        panel._presenter.mobilization_signals_for_country.return_value = [{
            "target_country_id": "CAN",
            "target_country_name": "Canada",
            "domain": "land",
            "from_readiness": "parked",
            "to_readiness": "ready",
            "source_country_id": "USA",
            "source_type": "owned",
            "observed_at_minute": 42,
            "confidence": 0.82,
            "freshness": 0.75,
            "status": "estimated",
            "source_factors": {"observer_telecom": 0.8, "intelligence_coverage": "limited"},
        }]
        mock_imgui = MagicMock()

        with patch("src.client.ui.panels.military.unit_list_panel.imgui", mock_imgui):
            panel._render_foreign_estimates(object(), "USA")

        rendered = " ".join(str(call.args[0]) for call in mock_imgui.text.call_args_list + mock_imgui.text_disabled.call_args_list)
        self.assertIn("Canada: Land readiness signal (parked → ready)", rendered)
        self.assertIn("confidence 82%", rendered)
        self.assertIn("intelligence coverage limited", rendered)
        self.assertNotIn("unit-id", rendered)

    def test_design_panel_separates_fixed_role_interactions_from_adjustable_values(self) -> None:
        panel = UnitDesignPanel()
        panel._presenter = MagicMock()
        panel._presenter.designs_for_country.return_value = [{
            "id": "tank-design", "display_name": "Tank", "branch": "land",
            "class_name": "tanks", "domain": "land", "research_level": 2,
            "cost": 10.0, "maintenance_cost": 2.0, "quality": 0.7,
            "speed": 0.6, "firepower": 0.8,
            "capabilities_json": '{"speed":70,"armor":80}',
            "valid_targets_json": '["armor","infantry"]',
            "vulnerabilities_json": '["air","anti_armor"]',
            "research_requirements_json": '{"land":1}',
        }]
        mock_imgui = MagicMock()

        with patch("src.client.ui.panels.military.unit_design_panel.imgui", mock_imgui), patch(
            "src.client.ui.panels.military.unit_design_panel.draw_required_tables"
        ):
            panel._render_content(object(), "USA")

        rendered = " ".join(str(call.args[0]) for call in mock_imgui.text.call_args_list + mock_imgui.text_disabled.call_args_list + mock_imgui.text_wrapped.call_args_list)
        self.assertIn("Fixed role definition", rendered)
        self.assertIn("Design-adjustable capabilities are bounded by the role catalog", rendered)
        self.assertIn("Fixed targets: armor, infantry", rendered)
        self.assertIn("Fixed counter vulnerabilities: air, anti_armor", rendered)


if __name__ == "__main__":
    unittest.main()
