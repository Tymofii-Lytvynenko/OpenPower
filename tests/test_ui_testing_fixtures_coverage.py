from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import polars as pl
import pytest

import src.simulation.ui_testing.fixtures as ui_fixtures
from src.shared.state import GameState


def _state() -> GameState:
    state = GameState(tables={"countries": pl.DataFrame({"id": ["UKR"]})})
    state.globals.update(
        ui_system_errors=["startup warning"],
        ui_command_results={"TestAction": [{"status": "ok"}]},
    )
    state.time = replace(state.time, total_minutes=120, date_str="2001-01-01 02:00")
    return state


def test_recording_client_captures_commands_events_and_fixture_snapshots():
    state = _state()
    client = ui_fixtures.RecordingClient(state)

    class TestAction:
        pass

    action = TestAction()
    client.send_action(action)
    client.deliver_event("test.event", {"value": 1}, "event-1")
    client.deliver_snapshot({"globals": {"snapshot_loaded": True}})

    assert client.get_state() is state
    assert client.actions == [action]
    assert state.journal.command_results[-1]["status"] == "ok"
    assert state.journal.domain_events[-1]["event_id"] == "event-1"
    assert client.get_system_errors() == ["startup warning"]
    assert client.get_presentation_total_minutes() == 120.0
    assert client.get_display_date_text() == "2001-01-01 02:00"
    assert client.get_display_total_minutes() == 120.0

    client.clear_system_errors()
    client.request_save("ignored", force=True)
    assert client.get_system_errors() == []
    assert client.requests == [{"type": "clear_errors"}, {"type": "save"}]


def test_fixture_snapshot_updates_tables_journal_globals_and_time():
    state = _state()
    ui_fixtures.apply_fixture_snapshot(state, {
        "tables": {"countries": [{"id": "POL"}]},
        "globals": {"tick": 3},
        "journal": {
            "domain_events": [{"event_id": "snapshot-event"}],
            "command_results": [{"status": "accepted"}],
        },
        "time": {"total_minutes": 180, "date_str": "2001-01-01 03:00"},
    })

    assert state.get_table("countries")["id"].to_list() == ["POL"]
    assert state.globals["tick"] == 3
    assert state.journal.domain_events[-1]["event_id"] == "snapshot-event"
    assert state.journal.command_results[-1]["status"] == "accepted"
    assert state.time.total_minutes == 180
    with pytest.raises(ValueError, match="must contain a list"):
        ui_fixtures.apply_fixture_snapshot(state, {"tables": {"countries": "invalid"}})


def test_recording_adapters_preserve_requested_settings_navigation_and_viewport_state():
    repository = ui_fixtures.MemorySettingsRepository()
    settings = repository.load()
    updated = replace(settings, fullscreen=True)
    repository.save(updated)
    assert repository.load() is updated
    assert ui_fixtures.TestDisplayCatalog().list_screens()[0].label == "UI test display"

    window = ui_fixtures.TestWindow((1280, 720))
    window.set_fullscreen(True)
    window.set_size(1600, 900)
    assert window.fullscreen is True
    assert window.get_size() == (1600, 900)

    navigation = ui_fixtures.RecordingNavigation(window)
    navigation.show_main_menu()
    navigation.show_load_game()
    navigation.show_load_game_screen()
    navigation.load_saved_game(None, "campaign-1")
    navigation.stop_game()
    assert navigation.requests == [
        "main_menu",
        "load_game",
        "load_game",
        {"type": "load_saved_game", "save_name": "campaign-1"},
        {"type": "stop_game"},
    ]

    viewport = ui_fixtures.RecordingViewport()
    viewport.focus_on_region(4)
    assert viewport.focus_on_country("UKR") == 1
    viewport.select_region_by_id(5)
    viewport.set_map_mode("economic")
    assert viewport.current_mode_key == "economic"
    assert viewport.requests == [
        {"region": 4},
        {"country": "UKR"},
        {"selected_region": 5},
        {"map_mode": "economic"},
    ]


def test_world_builder_loads_fixture_region_support_and_settings_factory():
    project_root = Path(__file__).resolve().parents[1]
    fixture = {
        "test_support": {"country_info_regions_from_base_data": ["UKR"]},
    }
    base_regions = pl.DataFrame([{"id": 99, "owner": "UKR", "name": "Source region"}])

    from unittest.mock import patch

    with patch(
        "src.client.ui.testing.country_info_assets.load_country_info_regions",
        return_value=base_regions,
    ) as load_regions:
        state = ui_fixtures.build_test_world(project_root, fixture)

    load_regions.assert_called_once_with(project_root, ["UKR"])
    assert state.get_table("regions")["id"].to_list() == [99]
    assert ui_fixtures.test_settings().fullscreen_screen_options()
