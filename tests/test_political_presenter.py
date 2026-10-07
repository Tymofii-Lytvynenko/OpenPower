from __future__ import annotations

import json

import polars as pl

from src.client.ui.panels.politics.political_overview_presenter import PoliticalOverviewPresenter
from src.client.ui.panels.politics.political_overview_panel import PoliticalOverviewPanel
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.components.hud.panel_manager import PanelManager
from src.client.ui.layouts.game_panel_registry import build_game_panel_specs
from src.shared.state import GameState
import src.client.ui.panels.politics.political_overview_panel as political_overview_panel_module


def test_political_overview_projects_authoritative_state_and_deadlines() -> None:
    state = GameState(
        tables={
            "countries": pl.DataFrame(
                {
                    "id": ["AAA"],
                    "gvt_approval": [0.71],
                    "gvt_stability": [75.0],
                    "gvt_corruption": [0.12],
                }
            ),
            "country_governments": pl.DataFrame(
                {
                    "country_id": ["AAA"],
                    "government_type": ["Multi-party democracy"],
                    "government_form_id": ["multi-party democracy"],
                    "ruling_party_id": ["civic"],
                    "election_eligible": [True],
                    "next_election_at_minute": [2_500],
                    "crisis_status": ["protest"],
                }
            ),
            "political_parties": pl.DataFrame(
                {
                    "country_id": ["AAA", "AAA"],
                    "party_id": ["civic", "labor"],
                    "display_name": ["Civic Union", "Labor Party"],
                    "support_share": [0.6, 0.4],
                    "organization": [0.8, 0.5],
                    "policy_positions_json": ["{}", "{}"],
                    "eligible": [True, True],
                    "is_ruling": [True, False],
                    "updated_at_minute": [0, 0],
                }
            ),
            "country_laws": pl.DataFrame(
                {
                    "country_id": ["AAA"],
                    "law_id": ["labor"],
                    "group_name": ["Labor"],
                    "title": ["Collective bargaining"],
                    "status": ["Active"],
                    "value": ["protected"],
                    "notes": ["Approved by parliament"],
                }
            ),
            "law_transitions": pl.DataFrame(
                {
                    "id": ["law-1"],
                    "country_id": ["AAA"],
                    "law_id": ["labor"],
                    "target_value": ["restricted"],
                    "effective_at_minute": [2_000],
                    "status": ["scheduled"],
                }
            ),
            "political_crises": pl.DataFrame(
                {
                    "id": ["crisis-1"],
                    "country_id": ["AAA"],
                    "crisis_type": ["protest"],
                    "status": ["active"],
                    "reason": ["Approval fell below the configured threshold"],
                    "created_at_minute": [900],
                }
            ),
            "political_history": pl.DataFrame(
                {
                    "id": ["history-old", "history-new"],
                    "country_id": ["AAA", "AAA"],
                    "event_type": ["law", "crisis"],
                    "source_type": ["action", "threshold"],
                    "source_id": ["law-1", "approval"],
                    "game_minute": [500, 950],
                    "reason": ["Law approved", "Approval crossed threshold"],
                    "result": ["scheduled", "protest opened"],
                }
            ),
        }
    )
    state.time.total_minutes = 1_000

    overview = PoliticalOverviewPresenter().build(state, "AAA")

    assert overview.government_form == "Multi-party democracy"
    assert overview.ruling_party == "Civic Union"
    assert overview.election_eligible is True
    assert overview.days_to_next_election == 2
    assert overview.approval_pct == 71.0
    assert overview.stability_pct == 75.0
    assert overview.corruption_pct == 12.0
    assert overview.crisis_status == "protest"
    assert [party.party_id for party in overview.parties] == ["civic", "labor"]
    assert overview.laws[0].value == "protected"
    assert overview.pending_law_transitions[0].target_value == "restricted"
    assert overview.recent_causes[0].reason == "Approval crossed threshold"


def test_political_overview_marks_missing_values_instead_of_fabricating_zero() -> None:
    overview = PoliticalOverviewPresenter().build(GameState(), "UNKNOWN")

    assert overview.government_form == "Unavailable"
    assert overview.ruling_party == "Unavailable"
    assert overview.election_eligible is None
    assert overview.days_to_next_election is None
    assert overview.approval_pct is None
    assert overview.stability_pct is None
    assert overview.corruption_pct is None
    assert overview.parties == ()
    assert overview.laws == ()
    assert overview.recent_causes == ()


def test_political_overview_projects_configured_overrides_and_authoritative_election_records() -> None:
    state = _election_overview_state()

    overview = PoliticalOverviewPresenter().build(state, "AAA")

    postpone = next(
        option
        for option in overview.election_override_options
        if option.override_type == "postpone"
    )
    assert postpone.available is True
    assert postpone.minimum_duration_days == 2
    assert postpone.maximum_duration_days == 20
    assert postpone.default_duration_days == 4
    assert postpone.cost == 12.5
    assert postpone.approval_delta == -3.0
    assert postpone.stability_delta == -2.0
    resolved = next(record for record in overview.recent_elections if record.status == "resolved")
    scheduled = next(record for record in overview.recent_elections if record.status == "scheduled")
    assert resolved.winner_party_id == "alpha"
    assert resolved.turnout_pct == 72.0
    assert scheduled.scheduled_at_minute == 6_760
    assert scheduled.override_type == "postpone"


def test_political_overview_explains_when_configured_override_is_unavailable() -> None:
    state = _election_overview_state(crisis_status="government_crisis")

    overview = PoliticalOverviewPresenter().build(state, "AAA")

    assert overview.election_override_options[0].available is False
    assert "crisis" in overview.election_override_options[0].unavailable_reason.lower()


def test_political_overview_panel_dispatches_override_intent_without_mutating_state(monkeypatch) -> None:
    state = _election_overview_state()
    overview = PoliticalOverviewPresenter().build(state, "AAA")

    class Client:
        player_id = "player-1"

        def __init__(self) -> None:
            self.actions = []

        def send_action(self, action) -> None:
            self.actions.append(action)

    class FakeImGui:
        @staticmethod
        def spacing() -> None:
            return None

        @staticmethod
        def text(value: str) -> None:
            return None

        @staticmethod
        def separator() -> None:
            return None

        @staticmethod
        def slider_int(label: str, value: int, minimum: int, maximum: int):
            return True, 7

        @staticmethod
        def text_disabled(value: str) -> None:
            return None

        @staticmethod
        def small_button(label: str) -> bool:
            return True

    client = Client()
    monkeypatch.setattr(political_overview_panel_module, "imgui", FakeImGui)
    PoliticalOverviewPanel()._render_election_overrides(
        overview,
        PanelRenderContext(target_tag="AAA", is_own_country=True, net_client=client),
    )

    assert len(client.actions) == 1
    action = client.actions[0]
    assert action.player_id == "player-1"
    assert action.country_tag == "AAA"
    assert action.override_type == "postpone"
    assert action.duration_days == 7


def test_political_overview_is_reachable_from_the_registered_politics_panels() -> None:
    specs = build_game_panel_specs(PanelManager())

    overview_spec = next(spec for spec in specs if spec.id == "POLITICAL_OVERVIEW")
    politics_spec = next(spec for spec in specs if spec.id == "POL")

    assert overview_spec.title == "Political Overview"
    assert overview_spec.show_in_toggle_bar is False
    assert isinstance(overview_spec.factory(), PoliticalOverviewPanel)
    assert politics_spec.factory()._open_constitution_cb is not None


def _election_overview_state(*, crisis_status: str = "none") -> GameState:
    rule = {
        "type": "postpone",
        "minimum_duration_days": 2,
        "maximum_duration_days": 20,
        "default_duration_days": 4,
        "cost": 12.5,
        "cooldown_days": 10,
        "approval_delta": -3.0,
        "stability_delta": -2.0,
    }
    state = GameState(
        tables={
            "countries": pl.DataFrame(
                {
                    "id": ["AAA"],
                    "gvt_approval": [60.0],
                    "gvt_stability": [55.0],
                    "gvt_corruption": [10.0],
                    "money_reserves": [100.0],
                }
            ),
            "country_governments": pl.DataFrame(
                {
                    "country_id": ["AAA"],
                    "government_type": ["Transitional republic"],
                    "government_form_id": ["transitional republic"],
                    "ruling_party_id": ["alpha"],
                    "election_eligible": [True],
                    "next_election_at_minute": [6_760],
                    "crisis_status": [crisis_status],
                }
            ),
            "government_form_rules": pl.DataFrame(
                {
                    "government_form_id": ["transitional republic"],
                    "election_eligible": [True],
                    "election_overrides_json": [json.dumps([rule])],
                }
            ),
            "political_parties": pl.DataFrame(
                {
                    "country_id": ["AAA"],
                    "party_id": ["alpha"],
                    "display_name": ["Alpha Party"],
                    "support_share": [0.6],
                    "organization": [0.8],
                    "eligible": [True],
                    "is_ruling": [True],
                }
            ),
            "political_elections": pl.DataFrame(
                {
                    "id": ["election-aaa-result", "election-aaa-006760"],
                    "country_id": ["AAA", "AAA"],
                    "scheduled_at_minute": [1_000, 6_760],
                    "resolved_at_minute": [900, 0],
                    "turnout": [0.72, 0.0],
                    "winner_party_id": ["alpha", ""],
                    "override_type": ["", "postpone"],
                    "status": ["resolved", "scheduled"],
                    "reason": ["Election results were recorded.", "The election was postponed."],
                }
            ),
        }
    )
    state.time.total_minutes = 1_000
    return state
