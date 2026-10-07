import os
from time import perf_counter

import polars as pl
import pytest

from modules.base.schema import ensure_base_tables
from modules.base.systems.world.recognition_system import RecognitionSystem
from src.shared.events import EventNewDay
from src.shared.state import GameState


@pytest.mark.skipif(
    os.environ.get("RUN_RECOGNITION_BENCHMARKS") != "1",
    reason="Set RUN_RECOGNITION_BENCHMARKS=1 to run the controlled recognition scale benchmark.",
)
def test_daily_recognition_update_scales_with_due_cases_not_stored_status_history():
    case_count = 1_000
    relationships_per_case = 10
    country_ids = [f"V{index:02d}" for index in range(relationships_per_case)]
    state = GameState(
        tables={
            "countries": pl.DataFrame(
                {"id": country_ids, "un_member": [True] * relationships_per_case}
            ),
            "regions": pl.DataFrame(
                {"id": [], "owner": [], "controller": []},
                schema={"id": pl.Int32, "owner": pl.Utf8, "controller": pl.Utf8},
            ),
        }
    )
    ensure_base_tables(state)
    system = RecognitionSystem()
    system.update(state, 0.0)

    cases = []
    votes = []
    statuses = []
    for index in range(case_count):
        case_id = f"case-{index:04d}"
        claim_id = f"claim-{index:04d}"
        claimant = f"CLAIM-{index:04d}"
        region_id = index + 1
        cases.append(
            {
                "id": case_id,
                "annexation_claim_id": claim_id,
                "region_id": region_id,
                "claimant_id": claimant,
                "former_owner_id": "FORMER",
                "eligible_voters": country_ids,
                "opened_at_minute": 0,
                "deadline_at_minute": 100_000,
                "status": "pending",
            }
        )
        for country_id in country_ids:
            votes.append(
                {
                    "id": f"{case_id}:{country_id}",
                    "case_id": case_id,
                    "country_id": country_id,
                    "vote": "yes",
                    "cast_at_minute": 1,
                    "source": "ai",
                }
            )
            statuses.append(
                {
                    "id": f"{case_id}:{country_id}",
                    "annexation_claim_id": claim_id,
                    "case_id": case_id,
                    "region_id": region_id,
                    "country_id": country_id,
                    "claimant_id": claimant,
                    "status": "recognized",
                    "granted_at_minute": 0,
                }
            )
    state.update_table("recognition_cases", pl.DataFrame(cases))
    state.update_table("recognition_votes", pl.DataFrame(votes))
    state.update_table("regional_recognition_status", pl.DataFrame(statuses))
    state.events = [EventNewDay(day=2, month=1, year=2001)]

    started = perf_counter()
    system.update(state, 0.0)
    elapsed = perf_counter() - started

    print(
        f"recognition benchmark: {case_count:,} pending cases, "
        f"{case_count * relationships_per_case:,} votes and statuses; {elapsed:.3f}s"
    )
    assert state.tables["recognition_cases"].height == case_count
    assert state.tables["recognition_votes"].height == case_count * relationships_per_case
    assert state.tables["regional_recognition_status"].height == case_count * relationships_per_case
    assert elapsed < 0.25
