from __future__ import annotations

import unittest
from unittest.mock import MagicMock, call, patch

from modules.base.systems.military.capability_catalog import DEFAULT_ROLE_PROFILES
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.panels.military.presenter import (
    ForceBucket,
    MilitarySummaryViewModel,
    UnitListRow,
)
from src.client.ui.panels.military_panel import MilitaryPanel
from src.client.ui.panels.military.unit_design_panel import UnitDesignPanel
from src.client.ui.panels.military.unit_type_options import unit_type_options_for_roles
from src.client.ui.panels.military.unit_list_panel import UnitListPanel


class UnitListPanelTest(unittest.TestCase):
    def test_unit_row_tooltip_explains_training_market_and_upkeep_markers(self) -> None:
        row = UnitListRow(
            unit_id="USA-fighter-001",
            owner_name="United States",
            unit_type="Fighter",
            strength=10,
            quantity=10,
            location="Washington",
            status="Ready",
            progress_pct=0.0,
            design_id="fighter-design",
            design_name="Fighter",
            design_cost=125_000.0,
            upkeep=5_001_000.0,
            training_level="Veteran",
            for_sale=True,
        )

        entry = UnitListPanel._entry_from_unit(row)

        self.assertIn("Training: Veteran", entry.tooltip)
        self.assertIn("Listed for sale", entry.tooltip)
        self.assertIn("Annual OpenPower budget estimate, not the REFERENCE formula", entry.tooltip)

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
        entries = panel._foreign_entries(object(), "USA")

        estimate, tanks = entries
        self.assertEqual(estimate.name, "Mexico")
        self.assertEqual(estimate.unit_type, "Estimated forces")
        self.assertEqual(estimate.quantity_text, "8–12")
        self.assertEqual(estimate.position, "CAN · t=42")
        self.assertEqual(estimate.status, "Estimate")
        self.assertIn("Estimated force strength: 8–12 units", estimate.tooltip)
        self.assertIn("Source CAN (allied)", estimate.tooltip)
        self.assertIn("Confidence 75%", estimate.tooltip)
        self.assertIn("freshness 50%", estimate.tooltip)
        self.assertIn("Observer telecom 80%", estimate.tooltip)
        self.assertIn("Target telecom 50%", estimate.tooltip)
        self.assertIn("Intelligence coverage sustained", estimate.tooltip)
        self.assertLessEqual(max(map(len, estimate.tooltip.splitlines())), 60)
        self.assertEqual(tanks.unit_type, "Tanks")
        self.assertEqual(tanks.quantity_text, "2–4")
        self.assertIn("Estimated tanks range: 2–4", tanks.tooltip)
        self.assertNotIn("unit-id", tanks.tooltip)

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
        estimate = panel._foreign_entries(object(), "USA")[0]

        self.assertEqual(estimate.status, "Outdated")
        self.assertEqual(estimate.quantity_text, "Unknown")
        self.assertIn("Outdated intelligence; current force size unknown", estimate.tooltip)
        self.assertNotIn("0 units", estimate.tooltip)

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
        estimate = panel._foreign_entries(object(), "USA")[0]

        self.assertEqual(estimate.status, "Unknown")
        self.assertEqual(estimate.quantity_text, "Unknown")
        self.assertIn("Force strength unknown", estimate.tooltip)
        self.assertIn("No intelligence source is available", estimate.tooltip)
        self.assertNotIn("0 units", estimate.tooltip)

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
        signal = panel._foreign_entries(object(), "USA")[0]

        self.assertEqual(signal.name, "Canada")
        self.assertEqual(signal.unit_type, "Land signal")
        self.assertEqual(signal.status, "parked → ready")
        self.assertIn("Confidence 82%", signal.tooltip)
        self.assertIn("Observer telecom 80%", signal.tooltip)
        self.assertIn("Intelligence coverage limited", signal.tooltip)
        self.assertNotIn("unit-id", signal.tooltip)
        self.assertEqual(signal.unit_id, "")

    def test_military_summary_respects_source_centered_columns(self) -> None:
        panel = MilitaryPanel()
        panel._presenter = MagicMock()
        panel._presenter.build_summary.return_value = MilitarySummaryViewModel(
            branches=(
                ForceBucket("LAND", 120, 3),
                ForceBucket("AIR", 80, 2),
                ForceBucket("NAVAL", 40, 1),
                ForceBucket("STRATEGIC", 20, 1),
            ),
            moving_units=0,
            active_wars=0,
            covert_cells=0,
            strategic_ready=1,
            strategic_total=2,
            missile_defense_pct=50.0,
        )
        widgets = MagicMock()
        widgets.button.return_value = False
        widgets.button_at.return_value = False

        with patch(
            "src.client.ui.panels.military_panel.GMLWidgets",
            return_value=widgets,
        ):
            panel._render_content(object(), "USA", True)

        text_calls = widgets.text.call_args_list
        self.assertIn(
            call(
                "frmConventionalWarfare/lblSoldiers",
                "UNITS",
                test_id="military.units_header",
            ),
            text_calls,
        )
        self.assertIn(
            call("frmConventionalWarfare/lblLandRank", 3),
            text_calls,
        )
        self.assertIn(
            call("frmStrategicWeapons/txtMissileDefenseStatus", "50%"),
            text_calls,
        )

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
        mock_imgui.button.return_value = False
        mock_imgui.combo.side_effect = [
            (False, [option.role for option in unit_type_options_for_roles(DEFAULT_ROLE_PROFILES)].index("tanks")),
            (False, 0),
        ]

        with patch("src.client.ui.panels.military.unit_design_panel.imgui", mock_imgui), patch(
            "src.client.ui.panels.military.unit_design_panel.draw_required_tables"
        ):
            panel._render_content(
                object(),
                PanelRenderContext(
                    target_tag="USA",
                    is_own_country=True,
                    net_client=MagicMock(),
                ),
            )

        rendered = " ".join(str(call.args[0]) for call in mock_imgui.text.call_args_list + mock_imgui.text_disabled.call_args_list + mock_imgui.text_wrapped.call_args_list)
        self.assertIn("Fixed role definition", rendered)
        self.assertIn("Design-adjustable capabilities are bounded by the role catalog", rendered)
        self.assertIn("Fixed targets: armor, infantry", rendered)
        self.assertIn("Fixed counter vulnerabilities: air, anti_armor", rendered)


if __name__ == "__main__":
    unittest.main()
