from pathlib import Path
from types import SimpleNamespace

import pytest

import src.server.session as session_module
from src.engine.simulator import Engine
from src.server.session import GameSession
from src.shared.config import GameConfig
from src.shared.state import GameState


def _session(project_root: Path, *, state=None, exporter=None, schema_registry=None):
    return GameSession(
        GameConfig(project_root),
        None,
        exporter,
        Engine(dev_mode=False),
        None,
        state or GameState(),
        schema_registry=schema_registry,
    )


def test_session_rejects_state_that_failed_tactical_migration(monkeypatch, tmp_path):
    monkeypatch.setattr(
        session_module,
        "validate_tactical_combat_state",
        lambda _state: ["missing battle anchor"],
    )

    with pytest.raises(RuntimeError, match="Tactical combat state migration failed: missing battle anchor"):
        _session(tmp_path)


def test_session_reports_world_schema_issues(monkeypatch, tmp_path):
    issue = SimpleNamespace(table="countries", code="missing-id")
    registry = SimpleNamespace(
        capture_state=lambda _state: None,
        ensure_state=lambda _state: None,
        validate_state=lambda _state: [issue],
    )

    with pytest.raises(RuntimeError, match="Session state violates world schemas: countries:missing-id"):
        _session(tmp_path, schema_registry=registry)


def test_session_restores_each_actor_sequence_from_prior_command_results(tmp_path):
    state = GameState()
    state.journal.append_command_result({"actor_id": "pilot", "sequence": 3})
    state.journal.append_command_result({"actor_id": "pilot", "sequence": 5})
    state.journal.append_command_result({"actor_id": "", "sequence": 8})

    session = _session(tmp_path, state=state)

    assert session._next_sequence["pilot"] == 5


def test_load_map_data_uses_first_existing_mod_map(monkeypatch, tmp_path):
    data_dir = tmp_path / "mod"
    map_path = data_dir / "regions" / "regions.png"
    map_path.parent.mkdir(parents=True)
    map_path.write_bytes(b"test map placeholder")
    config = SimpleNamespace(
        get_data_dirs=lambda: [data_dir, tmp_path / "later-mod"],
        get_asset_path=lambda _asset: pytest.fail("base map should not be consulted"),
    )
    monkeypatch.setattr(session_module, "RegionMapData", lambda path: path)

    assert GameSession._load_map_data(config) == str(map_path)


def test_load_map_data_falls_back_to_the_base_asset(monkeypatch, tmp_path):
    fallback = tmp_path / "assets" / "regions.png"
    config = SimpleNamespace(
        get_data_dirs=lambda: [tmp_path / "empty-mod"],
        get_asset_path=lambda asset: fallback if asset == "map/regions.png" else None,
    )
    monkeypatch.setattr(session_module, "RegionMapData", lambda path: path)

    assert GameSession._load_map_data(config) == str(fallback)


def test_non_positive_empty_tick_clears_actions_without_advancing_the_engine(tmp_path, monkeypatch):
    session = _session(tmp_path)
    session.state.current_actions.append(object())
    monkeypatch.setattr(
        session.engine,
        "step",
        lambda *_args: pytest.fail("an empty non-positive tick should not step the engine"),
    )

    session.tick(0.0)

    assert session.state.current_actions == []


def test_get_state_snapshot_returns_the_authoritative_state(tmp_path):
    session = _session(tmp_path)

    assert session.get_state_snapshot() is session.state


def test_save_map_changes_requires_an_exporter(tmp_path):
    session = _session(tmp_path)

    with pytest.raises(RuntimeError, match="This session has no data exporter"):
        session.save_map_changes()


def test_save_map_changes_delegates_the_current_state_to_its_exporter(tmp_path):
    saved_states = []
    exporter = SimpleNamespace(save_regions=saved_states.append)
    session = _session(tmp_path, exporter=exporter)

    session.save_map_changes()

    assert saved_states == [session.state]
