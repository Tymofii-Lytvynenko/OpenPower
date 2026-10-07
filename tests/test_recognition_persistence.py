from modules.base.schema import build_base_schema_registry
from modules.base.systems.world.recognition_system import (
    DEFAULT_VOTING_WINDOW_DAYS,
    MINUTES_PER_DAY,
    RecognitionSystem,
)
from src.server.io.data_load_manager import DataLoader
from src.server.io.save_writer import SaveWriter
from src.shared.actions import ActionCastRecognitionVote
from src.shared.config import GameConfig
from src.shared.state import GameState
from tests.test_recognition_system import _state


def test_recognition_records_survive_snapshot_save_load_and_deadline_resolution(tmp_path):
    state = _state()
    system = RecognitionSystem()
    system.update(state, 0.0)
    case_id = state.tables["recognition_cases"]["id"][0]
    state.current_actions = [
        ActionCastRecognitionVote("player-a", case_id, "YES_A", "yes"),
        ActionCastRecognitionVote("player-b", case_id, "YES_B", "yes"),
        ActionCastRecognitionVote("player-c", case_id, "NO_C", "no"),
    ]
    system.update(state, 0.0)
    state.current_actions = []

    snapshot = GameState.from_ipc(state.to_ipc())
    build_base_schema_registry().ensure_state(snapshot)
    for table_name in (
        "recognition_cases",
        "recognition_votes",
        "regional_recognition_status",
    ):
        assert snapshot.tables[table_name].to_dicts() == state.tables[table_name].to_dicts()

    config = GameConfig(tmp_path)
    assert SaveWriter(config).save_game(state, "recognition")
    loaded = DataLoader(
        config,
        schema_registry=build_base_schema_registry(),
    ).load_save("recognition")
    for table_name in (
        "recognition_cases",
        "recognition_votes",
        "regional_recognition_status",
    ):
        assert loaded.tables[table_name].to_dicts() == state.tables[table_name].to_dicts()

    deadline = DEFAULT_VOTING_WINDOW_DAYS * MINUTES_PER_DAY
    for candidate in (state, loaded):
        candidate.time.total_minutes = deadline
        candidate.current_actions = []
        RecognitionSystem().update(candidate, 0.0)

    assert state.tables["recognition_cases"].to_dicts() == loaded.tables["recognition_cases"].to_dicts()
    assert state.tables["recognition_votes"].to_dicts() == loaded.tables["recognition_votes"].to_dicts()
    assert state.tables["regional_recognition_status"].to_dicts() == loaded.tables["regional_recognition_status"].to_dicts()
    assert state.tables["recognition_cases"]["status"][0] == "passed"
