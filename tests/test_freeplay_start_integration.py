from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from main import create_local_session
from src.client.client_session import ClientSessionProxy
from src.client.tasks.freeplay_start_task import FreeplayStartTask
from src.client.tasks.load_game_task import LoadGameTask
from src.server.io.save_writer import SaveWriter
from src.shared.actions import ActionMoveUnit, ActionSaveGame, ActionSetPaused
from src.shared.config import GameConfig


def test_freeplay_start_reaches_first_real_server_snapshot_without_campaign_rows():
    project_root = Path(__file__).resolve().parents[1]
    task = FreeplayStartTask(
        SimpleNamespace(session_factory=create_local_session, session=None),
        GameConfig(project_root),
        player_tag="USA",
    )
    context = None
    session = None

    try:
        context = task.run()
        session = context.session

        assert isinstance(session, ClientSessionProxy)
        assert session.process.pid is not None
        assert task.status_text == "Ready."
        assert task.progress == 1.0
        assert context.player_tag == "USA"
        assert context.start_pos is not None

        state = session.get_state_snapshot()
        assert state is not None
        assert state.globals["player_tag"] == "USA"
        assert state.tables["campaigns"].is_empty()
        assert state.tables["objectives"].is_empty()
    finally:
        if session is None:
            session = getattr(task, "_session", None)
        if session is not None:
            process = session.process
            session.shutdown()
            if process.is_alive():
                process.terminate()
                process.join(timeout=5.0)
            assert not process.is_alive()


def _wait_for_client_state(session, predicate, description: str, timeout: float = 60.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        session.tick(0.0)
        state = session.get_state_snapshot()
        if state is not None and predicate(state):
            return state
        time.sleep(0.01)
    raise AssertionError(f"Timed out waiting for {description}.")


def _friendly_move(session, state):
    owner_by_region = {
        int(row["id"]): str(row["owner"] or "").strip().upper()
        for row in state.tables["regions"].iter_rows(named=True)
    }
    neighbors_by_region: dict[int, list[int]] = {}
    for region_id, neighbor_id in state.tables["region_adjacency"].select(
        "region_id", "neighbor_region_id"
    ).iter_rows():
        neighbors_by_region.setdefault(int(region_id), []).append(int(neighbor_id))

    for unit in state.tables["units"].iter_rows(named=True):
        if str(unit.get("owner") or "").strip().upper() != "USA":
            continue
        source = unit.get("current_region_id")
        if source is None:
            continue
        destination = next(
            (
                candidate
                for candidate in neighbors_by_region.get(int(source), [])
                if owner_by_region.get(candidate) == "USA"
            ),
            None,
        )
        if destination is None:
            continue
        command_id = session.receive_action(
            ActionMoveUnit("local_admin", str(unit["id"]), destination)
        )
        return str(unit["id"]), destination, command_id

    raise AssertionError("The USA start has no unit with an adjacent friendly region.")


def _shutdown(session) -> None:
    if session is None:
        return
    process = session.process
    session.shutdown()
    if process.is_alive():
        process.terminate()
    process.join(timeout=5.0)
    assert not process.is_alive()


def test_freeplay_save_resumes_after_server_process_restart(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    config = GameConfig(project_root)
    save_name = f"freeplay-audit-{uuid4().hex}"
    save_path = project_root / "user_data" / "saves" / save_name
    sessions = []

    try:
        start_task = FreeplayStartTask(
            SimpleNamespace(session_factory=create_local_session, session=None),
            config,
            player_tag="USA",
        )
        start_context = start_task.run()
        first_session = start_context.session
        sessions.append(first_session)
        state = first_session.get_state_snapshot()
        assert state is not None
        assert state.tables["campaigns"].is_empty()
        assert state.tables["objectives"].is_empty()

        pause_command = first_session.receive_action(ActionSetPaused("local_admin", True))
        paused_state = _wait_for_client_state(
            first_session,
            lambda current: current.time.is_paused and any(
                result.get("command_id") == pause_command
                for result in current.journal.command_results
            ),
            "the pause command result",
        )
        unit_id, destination, move_command = _friendly_move(first_session, paused_state)
        moved_state = _wait_for_client_state(
            first_session,
            lambda current: any(
                result.get("command_id") == move_command
                for result in current.journal.command_results
            ),
            "the movement command result",
        )
        pending_order = moved_state.tables["unit_pending_orders"].filter(
            (moved_state.tables["unit_pending_orders"]["unit_id"] == unit_id)
            & (moved_state.tables["unit_pending_orders"]["target_region_id"] == destination)
        )
        movement_route = moved_state.tables["unit_movement_routes"].filter(
            (moved_state.tables["unit_movement_routes"]["unit_id"] == unit_id)
            & (moved_state.tables["unit_movement_routes"]["destination_region_id"] == destination)
        )
        movement_feedback = moved_state.tables["unit_order_feedback"].filter(
            moved_state.tables["unit_order_feedback"]["unit_id"] == unit_id
        )
        assert not pending_order.is_empty() or not movement_route.is_empty(), (
            f"Movement command had no persistent order: "
            f"{movement_feedback.to_dicts()}"
        )
        expected_date = moved_state.time.date_str
        expected_minute = moved_state.time.total_minutes
        expected_tax = moved_state.tables["countries"].filter(
            moved_state.tables["countries"]["id"] == "USA"
        ).item(0, "personal_income_tax_rate")
        expected_player = moved_state.globals["player_tag"]

        save_command = first_session.receive_action(ActionSaveGame("local_admin", save_name))
        _wait_for_client_state(
            first_session,
            lambda current: any(
                result.get("command_id") == save_command
                for result in current.journal.command_results
            )
            and save_path.joinpath("meta.json").is_file(),
            "the atomic freeplay save",
        )
        assert save_path.is_dir()
        _shutdown(first_session)
        sessions.remove(first_session)

        load_task = LoadGameTask(
            SimpleNamespace(session_factory=create_local_session, session=None),
            config,
            save_name,
        )
        resumed_session = load_task.run()
        sessions.append(resumed_session)
        resumed = resumed_session.get_state_snapshot()
        assert resumed is not None
        assert load_task.status_text == "Ready."
        assert resumed.globals["player_tag"] == expected_player == "USA"
        assert resumed.time.date_str == expected_date
        assert resumed.time.total_minutes == expected_minute
        assert resumed.time.is_paused
        assert resumed.tables["countries"].filter(
            resumed.tables["countries"]["id"] == "USA"
        ).item(0, "personal_income_tax_rate") == expected_tax
        assert resumed.tables["campaigns"].is_empty()
        assert resumed.tables["objectives"].is_empty()
        route = resumed.tables["unit_movement_routes"].filter(
            (resumed.tables["unit_movement_routes"]["unit_id"] == unit_id)
            & (resumed.tables["unit_movement_routes"]["destination_region_id"] == destination)
        )
        pending_order = resumed.tables["unit_pending_orders"].filter(
            (resumed.tables["unit_pending_orders"]["unit_id"] == unit_id)
            & (resumed.tables["unit_pending_orders"]["target_region_id"] == destination)
        )
        assert not route.is_empty() or not pending_order.is_empty()

        resume_command = resumed_session.receive_action(
            ActionSetPaused("local_admin", False)
        )
        continued = _wait_for_client_state(
            resumed_session,
            lambda current: current.time.total_minutes > expected_minute
            and any(
                result.get("command_id") == resume_command
                for result in current.journal.command_results
            ),
            "the freeplay simulation to advance after process restart",
        )
        assert continued.globals["player_tag"] == "USA"
        assert continued.tables["campaigns"].is_empty()
        continued_route = continued.tables["unit_movement_routes"].filter(
            (continued.tables["unit_movement_routes"]["unit_id"] == unit_id)
            & (continued.tables["unit_movement_routes"]["destination_region_id"] == destination)
        )
        continued_order = continued.tables["unit_pending_orders"].filter(
            (continued.tables["unit_pending_orders"]["unit_id"] == unit_id)
            & (continued.tables["unit_pending_orders"]["target_region_id"] == destination)
        )
        assert not continued_route.is_empty() or not continued_order.is_empty()
    finally:
        for session in reversed(sessions):
            _shutdown(session)
        if save_path.exists():
            assert SaveWriter(config).delete_save(save_name)
