from types import SimpleNamespace

import polars as pl

from src.client.ui.components.hud.panel_manager import PanelManager
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.layouts.game_panel_registry import build_game_panel_specs
from src.client.ui.panels.demographics_panel import DemographicsPanel
from src.client.ui.panels.migration_panel import MigrationPanel
from src.client.ui.panels.migration_presenter import MigrationPresenter
from src.shared.actions import ActionUpdateMigrationPolicy
from src.shared.state import GameState


def _state():
    return GameState(tables={
        "countries": pl.DataFrame({"id": ["AAA"]}),
        "regions": pl.DataFrame({
            "id": [1, 2, 3, 4],
            "owner": ["AAA", "AAA", "BBB", "AAA"],
            "pop_14": [0, 4, 0, 0],
            "pop_15_64": [100, 16, 80, 0],
            "pop_65": [0, 0, 0, 0],
            "housing_capacity": [200, 200, 100, 0],
            "employment_capacity": [200, 100, 100, 0],
            "service_capacity": [200, 50, 100, 0],
            "transport_capacity": [200, 120, 100, 0],
        }),
        "migration_policies": pl.DataFrame({
            "country_id": ["AAA"],
            "migration_policy": ["managed"],
            "border_policy": ["open"],
            "entry_rate": [0.6],
            "exit_rate": [0.4],
            "asylum_rate": [0.3],
            "family_reunification_rate": [0.5],
            "skilled_worker_preference": [0.2],
            "enforcement_strength": [0.5],
        }),
        "migration_signals": pl.DataFrame({
            "country_id": ["AAA"],
            "gross_inflow": [40],
            "gross_outflow": [8],
            "net_flow": [32],
            "working_age_delta": [24],
            "service_pressure": [0.4],
            "political_pressure": [0.3],
            "law_pressure": [0.15],
            "window_start_minute": [0],
            "updated_at_minute": [100],
        }),
        "migration_flows": pl.DataFrame({
            "id": ["completed", "pending", "rejected"],
            "origin_region_id": [1, 3, 4],
            "destination_region_id": [2, 2, 1],
            "origin_country_id": ["AAA", "BBB", "AAA"],
            "destination_country_id": ["AAA", "AAA", "AAA"],
            "population_count": [40, 12, 0],
            "status": ["completed", "pending", "rejected"],
            "reason_code": ["eligible_domestic", "eligible_mobility_agreement", "no_destination_capacity"],
            "created_at_minute": [50, 90, 95],
        }),
    })


def test_country_summary_exposes_policy_current_window_routes_and_reasons_without_mutation():
    state = _state()
    before = {name: frame.clone() for name, frame in state.tables.items()}

    summary = MigrationPresenter().present_country(state, "AAA")

    assert summary is not None
    assert (summary.migration_policy, summary.border_policy) == ("managed", "open")
    assert (summary.gross_inflow, summary.gross_outflow, summary.net_flow) == (40, 8, 32)
    assert summary.service_pressure == 0.4
    assert summary.recent_trend == "net inflow"
    assert summary.top_routes[0].population_count == 40
    assert summary.top_routes[0].reason_label == "Eligible domestic movement"
    assert dict(summary.status_counts)["pending"] == 1
    assert all(state.tables[name].equals(frame) for name, frame in before.items())


def test_region_summary_includes_capacity_pressure_pending_flow_and_reason():
    summary = MigrationPresenter().present_region(_state(), 2)

    assert summary is not None
    assert summary.owner == "AAA"
    assert (summary.incoming_population, summary.outgoing_population, summary.pending_population) == (40, 0, 12)
    assert summary.net_migration == 40
    assert summary.capacity_pressure == 32 / 50
    assert summary.top_routes[0].origin_region_id == 1
    assert summary.top_routes[0].reason_label == "Eligible domestic movement"


def test_country_summary_exposes_redirected_capacity_outcome():
    state = _state()
    state.update_table(
        "migration_flows",
        state.get_table("migration_flows").with_columns(
            pl.when(pl.col("id") == "completed")
            .then(pl.lit("redirected"))
            .otherwise(pl.col("status"))
            .alias("status"),
            pl.when(pl.col("id") == "completed")
            .then(pl.lit("redirected_capacity"))
            .otherwise(pl.col("reason_code"))
            .alias("reason_code"),
        ),
    )

    summary = MigrationPresenter().present_country(state, "AAA")

    assert summary is not None
    assert dict(summary.status_counts)["redirected"] == 1
    redirected = next(route for route in summary.top_routes if route.status == "redirected")
    assert redirected.reason_label == "Rerouted because the original destination is full"


def test_migration_panel_is_registered_and_constructible():
    panel = next(
        spec for spec in build_game_panel_specs(PanelManager()) if spec.id == "MIGRATION"
    )

    assert isinstance(panel.factory(), MigrationPanel)


def test_demographics_panel_opens_the_registered_migration_panel():
    manager = PanelManager()
    specs = {spec.id: spec for spec in build_game_panel_specs(manager)}
    manager.register_spec(specs["MIGRATION"])
    demographics = specs["DEM"].factory()

    assert demographics.open_migration_policy()

    assert manager.is_visible("MIGRATION")


def test_demographics_panel_opens_the_budget_panel_for_social_programs():
    manager = PanelManager()
    specs = {spec.id: spec for spec in build_game_panel_specs(manager)}
    manager.register_spec(specs["BUDGET"])
    demographics = specs["DEM"].factory()

    assert demographics.open_social_programs()

    assert manager.is_visible("BUDGET")


def test_demographics_panel_retains_its_standalone_constructor():
    panel = DemographicsPanel()

    assert isinstance(panel, DemographicsPanel)
    assert not panel.open_migration_policy()
    assert not panel.open_social_programs()


def test_migration_panel_edits_and_dispatches_all_policy_controls():
    state = _state()
    summary = MigrationPresenter().present_country(state, "AAA")
    assert summary is not None
    sent_actions = []
    client = SimpleNamespace(player_id="player", send_action=sent_actions.append)
    context = PanelRenderContext(
        target_tag="AAA",
        is_own_country=True,
        net_client=client,
    )
    controls = {
        "Entry rate": 0.75,
        "Exit rate": 0.60,
        "Asylum rate": 0.90,
        "Family reunification rate": 0.25,
        "Skilled worker preference": 0.80,
        "Enforcement strength": 0.70,
    }
    ui = SimpleNamespace(
        separator=lambda: None,
        text=lambda *args: None,
        combo=lambda label, index, options: (False, index),
        slider_float=lambda label, value, *args: (False, controls[label]),
        button=lambda label, *args: label == "Apply migration policy",
    )

    MigrationPanel(imgui_api=ui)._render_policy_controls(state, context, summary)

    assert len(sent_actions) == 1
    action = sent_actions[0]
    assert isinstance(action, ActionUpdateMigrationPolicy)
    assert (
        action.entry_rate,
        action.exit_rate,
        action.asylum_rate,
        action.family_reunification_rate,
        action.skilled_worker_preference,
        action.enforcement_strength,
    ) == (0.75, 0.60, 0.90, 0.25, 0.80, 0.70)
