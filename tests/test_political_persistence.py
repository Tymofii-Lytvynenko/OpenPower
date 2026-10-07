from __future__ import annotations

import json

import orjson
import polars as pl

from modules.base.schema import build_base_schema_registry
from modules.base.systems.politics.political_lifecycle_system import PoliticalLifecycleSystem
from src.server.io.data_load_manager import DataLoader
from src.server.io.save_writer import SaveWriter
from src.shared.config import GameConfig
from src.shared.actions import ActionResolvePoliticalCrisis
from src.shared.snapshots import StateSnapshotDecoder, StateSnapshotEncoder
from src.shared.state import GameState
from tests.test_political_regime_changes import _state


def test_active_crisis_pending_law_and_election_continue_identically_after_all_persistence_paths(tmp_path):
    state = _pending_lifecycle_state()
    original_tables = (
        "country_governments",
        "political_parties",
        "country_laws",
        "law_transitions",
        "political_elections",
        "political_crises",
        "political_effects",
        "political_history",
    )

    encoder = StateSnapshotEncoder()
    snapshot = StateSnapshotDecoder().decode(encoder.encode(state))
    ipc = GameState.from_ipc(state.to_ipc())
    config = GameConfig(tmp_path)
    assert SaveWriter(config).save_game(state, "political-pending")
    save_meta = orjson.loads(
        (tmp_path / "user_data" / "saves" / "political-pending" / "meta.json").read_bytes()
    )
    assert save_meta["schema_versions"]["political_crises"] == 1
    assert save_meta["schema_versions"]["political_elections"] == 1
    loaded = DataLoader(
        config,
        schema_registry=build_base_schema_registry(),
    ).load_save("political-pending")

    schema_versions = loaded.schema_registry.versions()
    assert all(
        schema_versions.get(table_name) == 1
        for table_name in original_tables
    )
    continuations = (state, snapshot, ipc, loaded)
    for candidate in continuations:
        for table_name in original_tables:
            assert candidate.get_table(table_name).to_dicts() == state.get_table(table_name).to_dicts()

    for candidate in continuations:
        candidate.time.total_minutes = 6_000
        candidate.current_actions = []
        candidate.events = []
        PoliticalLifecycleSystem().update(candidate, 0.0)

    for candidate in continuations:
        assert candidate.get_table("country_laws").filter(
            pl.col("law_id") == "party_system"
        )["value"][0] == "Competitive"
        assert candidate.get_table("law_transitions").filter(
            pl.col("id") == "transition-1"
        )["status"][0] == "effective"

    for candidate in continuations:
        candidate.time.total_minutes = 10_000
        candidate.current_actions = []
        candidate.events = []
        PoliticalLifecycleSystem().update(candidate, 0.0)

    for candidate in continuations:
        election = candidate.get_table("political_elections").filter(
            pl.col("id") == "election-old"
        ).row(0, named=True)
        assert election["status"] == "resolved"
        assert election["winner_party_id"]

    for candidate in continuations:
        candidate.current_actions = [
            ActionResolvePoliticalCrisis("AAA", "AAA", "crisis-1", "constitutional")
        ]
        PoliticalLifecycleSystem().update(candidate, 0.0)

    for candidate in continuations[1:]:
        for table_name in original_tables:
            assert candidate.get_table(table_name).to_dicts() == state.get_table(table_name).to_dicts()
        assert candidate.determinism == state.determinism
        assert candidate.journal.command_results == state.journal.command_results
    assert state.get_table("political_crises").filter(
        pl.col("id") == "crisis-1"
    )["outcome"][0] == "failed"


def _pending_lifecycle_state() -> GameState:
    state = _state(support=0.2)
    government_rows = state.get_table("country_governments").to_dicts()
    for row in government_rows:
        if row["country_id"] == "AAA":
            row.update(
                {
                    "government_form_id": "transitional republic",
                    "government_type": "Transitional republic",
                    "election_eligible": True,
                    "next_election_at_minute": 10_000,
                    "crisis_status": "coup_attempt",
                }
            )
    state.update_table(
        "country_governments",
        pl.DataFrame(government_rows, schema=state.get_table("country_governments").schema),
    )

    form_rows = state.get_table("government_form_rules").to_dicts()
    for row in form_rows:
        if row["government_form_id"] == "transitional republic":
            row.update(
                {
                    "election_eligible": True,
                    "election_interval_minutes": 10_000,
                    "regime_change_paths_json": json.dumps([
                        {
                            "id": "constitutional",
                            "crisis_types": ["coup_attempt"],
                            "minimum_support": 0.7,
                            "minimum_approval": 40.0,
                            "minimum_stability": 40.0,
                            "outcome": {
                                "government_form_id": "transitional republic",
                                "ruling_party_id": "beta",
                                "approval_delta": 4.0,
                            },
                            "failure_effects": {
                                "approval_delta": -4.0,
                                "stability_delta": -9.0,
                                "corruption_delta": 3.0,
                            },
                        }
                    ]),
                }
            )
    state.update_table(
        "government_form_rules",
        pl.DataFrame(form_rows, schema=state.get_table("government_form_rules").schema),
    )

    state.update_table(
        "law_transitions",
        pl.DataFrame(
            [
                {
                    "id": "transition-1",
                    "country_id": "AAA",
                    "law_id": "party_system",
                    "player_id": "AAA",
                    "government_form_id": "transitional republic",
                    "previous_value": "Single-party",
                    "target_value": "Competitive",
                    "created_at_minute": 4_000,
                    "effective_at_minute": 6_000,
                    "carry_over_rule": "carry_over",
                    "effects_json": json.dumps([
                        {"domain": "rights", "effect": "political_competition", "value": 0.2}
                    ]),
                    "status": "scheduled",
                }
            ],
            schema=state.get_table("law_transitions").schema,
        ),
    )
    state.update_table(
        "political_elections",
        pl.DataFrame(
            [
                {
                    "id": "election-old",
                    "country_id": "AAA",
                    "government_form_id": "transitional republic",
                    "scheduled_at_minute": 10_000,
                    "status": "scheduled",
                }
            ],
            schema=state.get_table("political_elections").schema,
        ),
    )
    state.time.total_minutes = 5_000
    state.current_actions = []
    state.events = []
    return state
