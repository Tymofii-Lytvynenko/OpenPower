from __future__ import annotations

import polars as pl

from src.client.ui.panels.service.campaign_presenter import CampaignPresenter


class _State:
    def __init__(self, **tables):
        self.tables = tables


def test_campaign_overview_projects_latest_campaign_and_sorts_active_guidance() -> None:
    state = _State(
        campaigns=pl.DataFrame(
            {
                "id": ["old", "active"],
                "scenario_id": ["old_scenario", "new_scenario"],
                "actor_country_id": ["USA", "USA"],
                "started_at_minute": [10, 20],
                "outcome": ["victory", "ongoing"],
            }
        ),
        campaign_scenarios=pl.DataFrame(
            {"id": ["new_scenario"], "title": ["Current Scenario"]}
        ),
        objectives=pl.DataFrame(
            {
                "id": ["first", "other", "legacy"],
                "campaign_id": ["active", "active", ""],
                "country_id": ["USA", "USA", "USA"],
                "status": ["active", "completed", "active"],
                "progress": [0.3, 1.0, 0.8],
                "deadline_at_minute": [100, 50, -1],
            }
        ),
        advisor_recommendations=pl.DataFrame(
            {
                "id": ["low", "high", "inactive"],
                "actor_country_id": ["USA", "USA", "USA"],
                "urgency": [0.4, 0.9, 1.0],
                "expires_at_minute": [500, 300, 100],
                "status": ["active", "active", "stale"],
            }
        ),
        sphere_delegations=pl.DataFrame(
            {
                "id": ["owner", "other_campaign"],
                "campaign_id": ["active", "old"],
                "owner_country_id": ["USA", "USA"],
                "scope_type": ["country", "country"],
                "scope_id": ["USA", "USA"],
            }
        ),
    )

    overview = CampaignPresenter().build_overview(state, "usa")

    assert overview.campaign["id"] == "active"
    assert overview.scenario["title"] == "Current Scenario"
    assert [row["id"] for row in overview.objectives] == ["first", "other"]
    assert [row["id"] for row in overview.recommendations] == ["high", "low"]
    assert [row["id"] for row in overview.delegations] == ["owner"]


def test_legacy_objectives_remain_visible_without_campaign_records() -> None:
    state = _State(
        objectives=pl.DataFrame(
            {
                "id": ["legacy-goal"],
                "country_id": ["CAN"],
                "title": ["Keep reserves positive"],
                "status": ["active"],
                "progress": [0.6],
            }
        )
    )

    overview = CampaignPresenter().build_overview(state, "CAN")

    assert overview.campaign is None
    assert [row["id"] for row in overview.objectives] == ["legacy-goal"]
    assert overview.recommendations == ()


def test_failed_and_cancelled_objectives_sort_after_actionable_goals_and_keep_progress_fields() -> None:
    evidence = '[{"source_table":"regions","game_minute":25,"current_value":1,"target_value":2}]'
    state = _State(
        campaigns=pl.DataFrame([{
            "id": "active", "scenario_id": "scenario", "actor_country_id": "USA",
            "started_at_minute": 0, "outcome": "ongoing", "actor_scope": "sphere",
        }]),
        campaign_scenarios=pl.DataFrame([{"id": "scenario", "title": "Sphere objectives"}]),
        objectives=pl.DataFrame([
            {"id": "failed", "campaign_id": "active", "country_id": "USA", "status": "failed", "deadline_at_minute": 10, "progress": 0.5},
            {"id": "actionable", "campaign_id": "active", "country_id": "USA", "status": "active", "deadline_at_minute": 20, "progress": 0.25, "current_value": 1.0, "target_value": 2.0, "remaining": 1.0, "held_minutes": 5, "evidence_json": evidence},
            {"id": "cancelled", "campaign_id": "active", "country_id": "USA", "status": "cancelled", "deadline_at_minute": 5, "progress": 0.0},
        ]),
        advisor_recommendations=pl.DataFrame(),
        sphere_delegations=pl.DataFrame(),
    )

    overview = CampaignPresenter().build_overview(state, "USA")

    assert [row["id"] for row in overview.objectives] == ["actionable", "cancelled", "failed"]
    objective = overview.objectives[0]
    assert (objective["current_value"], objective["target_value"], objective["remaining"]) == (1.0, 2.0, 1.0)
    assert objective["held_minutes"] == 5
    assert CampaignPresenter.latest_evidence(objective) == {
        "source_table": "regions", "game_minute": 25, "current_value": 1, "target_value": 2,
    }
