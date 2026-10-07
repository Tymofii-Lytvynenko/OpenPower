from __future__ import annotations

import unittest

from modules.base.schema import ensure_base_tables
from modules.base.systems.world.infrastructure_system import InfrastructureSystem
from src.client.ui.components.hud.panel_manager import PanelManager
from src.client.ui.layouts.game_panel_registry import build_game_panel_specs
from src.client.ui.panels.infrastructure_presenter import InfrastructurePresenter
from src.client.ui.panels.region_infrastructure_panel import RegionInfrastructurePanel
from src.shared.actions import ActionInvestRegionalInfrastructure
from tests.test_regional_infrastructure_fixtures import build_infrastructure_state


class InfrastructurePresenterTest(unittest.TestCase):
    def test_selected_region_panel_is_registered_in_the_existing_hud(self):
        specs = build_game_panel_specs(PanelManager())

        panel_spec = next(spec for spec in specs if spec.id == "REGIONAL_INFRASTRUCTURE")

        self.assertEqual(panel_spec.title, "Regional Infrastructure")
        self.assertIsInstance(panel_spec.factory(), RegionInfrastructurePanel)

    def test_region_and_country_summaries_are_read_only_and_explain_current_state(self):
        state = build_infrastructure_state()
        ensure_base_tables(state)
        InfrastructureSystem().update(state, 0.0)
        before_revisions = dict(state.table_revisions)
        before_tables = {name: frame.clone() for name, frame in state.tables.items()}

        presenter = InfrastructurePresenter()
        region = presenter.build_region_summary(state, 101)
        country = presenter.build_country_summary(state, "USA")

        self.assertEqual(region.region_id, 101)
        self.assertEqual(region.owner, "USA")
        self.assertEqual({row.category for row in region.categories}, {"transport", "utilities", "industrial", "telecom"})
        self.assertTrue(all(row.maintenance_need >= 0.0 for row in region.categories))
        self.assertAlmostEqual(dict(region.downstream_effects)["transport_access"], 0.36)
        self.assertGreaterEqual(country.transport_access, 0.0)
        self.assertIsNotNone(country.weakest_region_id)
        self.assertEqual(dict(state.table_revisions), before_revisions)
        for name, frame in before_tables.items():
            self.assertEqual(state.get_table(name).to_dicts(), frame.to_dicts())

    def test_summary_reports_active_investment_progress_and_reason(self):
        state = build_infrastructure_state()
        ensure_base_tables(state)
        system = InfrastructureSystem()
        system.update(state, 0.0)
        state.current_actions = [
            ActionInvestRegionalInfrastructure("player-1", "USA", 101, "transport", 0.6)
        ]
        system.update(state, 0.0)

        summary = InfrastructurePresenter().build_region_summary(state, 101)
        transport = next(row for row in summary.categories if row.category == "transport")

        self.assertEqual(transport.project_status, "in_progress")
        self.assertEqual(transport.project_progress, 0.0)
        self.assertGreater(transport.maintenance_need, 0.0)
        self.assertEqual(transport.last_source_type, "legacy")


if __name__ == "__main__":
    unittest.main()
