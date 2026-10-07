import polars as pl

from modules.base.schema import ensure_base_tables
from src.client.ui.panels.politics.recognition_presenter import RecognitionPresenter
from src.shared.state import GameState


def test_presenter_projects_roster_counts_selected_vote_status_and_sorted_cases():
    state = GameState(
        tables={
            "countries": pl.DataFrame({"id": ["USA", "CAN"]}),
            "recognition_cases": pl.DataFrame(
                {
                    "id": ["later", "sooner"],
                    "annexation_claim_id": ["claim-later", "claim-sooner"],
                    "region_id": [2, 1],
                    "claimant_id": ["A", "B"],
                    "former_owner_id": ["C", "D"],
                    "eligible_voters": [["CAN", "USA"], ["CAN", "USA"]],
                    "opened_at_minute": [0, 0],
                    "deadline_at_minute": [200, 100],
                    "status": ["pending", "passed"],
                }
            ),
            "recognition_votes": pl.DataFrame(
                {
                    "id": ["later:USA", "later:CAN"],
                    "case_id": ["later", "later"],
                    "country_id": ["USA", "CAN"],
                    "vote": ["yes", "no"],
                }
            ),
            "regional_recognition_status": pl.DataFrame(
                {
                    "id": ["sooner:USA"],
                    "case_id": ["sooner"],
                    "region_id": [1],
                    "country_id": ["USA"],
                    "claimant_id": ["B"],
                    "status": ["recognized"],
                }
            ),
        }
    )
    ensure_base_tables(state)

    cases = RecognitionPresenter().cases_for_country(state, "USA")

    assert [case["id"] for case in cases] == ["sooner", "later"]
    assert cases[0]["my_status"] == "recognized"
    assert cases[1]["my_vote"] == "yes"
    assert (cases[1]["yes_votes"], cases[1]["no_votes"]) == (1, 1)
    assert cases[1]["days_remaining"] == 1

    region = RecognitionPresenter().for_region(state, 1, "USA")
    assert region is not None
    assert region["claimant_id"] == "B"
    assert region["former_owner_id"] == "D"
    assert region["recognized_count"] == 1
    assert region["country_status"] == "recognized"
