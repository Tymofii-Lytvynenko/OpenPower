from dataclasses import replace
from types import SimpleNamespace

from src.client.services.autosave_scheduler import AutosaveScheduler
from src.client.services.game_settings_service import GameSettings, GameSettingsRepository, GameSettingsService
from src.client.ui.components.shared.command_feedback import CommandFeedback
from src.client.ui.components.settings_content import GameSettingsContent


class Settings:
    def __init__(self):
        self.settings = GameSettings(autosave_enabled=True, autosave_incremental=True, autosave_interval_minutes=1)

    def set_autosave_counter(self, counter):
        self.settings = replace(self.settings, autosave_counter=counter % 10000)


class Client:
    player_id = "local"

    def __init__(self):
        self.actions = []

    def send_action(self, action):
        self.actions.append(action)
        return f"save-{len(self.actions)}"


def test_autosave_waits_for_result_then_uses_persistent_incrementing_names():
    now = [0.0]
    settings, client = Settings(), Client()
    scheduler = AutosaveScheduler(settings, client, clock=lambda: now[0])
    scheduler.update([])
    now[0] = 60
    assert scheduler.update([]) == {"save-1"}
    assert client.actions[0].save_name == "Autosave0000"
    assert settings.settings.autosave_counter == 1
    now[0] = 600
    assert scheduler.update([]) == {"save-1"}
    assert len(client.actions) == 1
    assert scheduler.update([{"command_id": "save-1", "status": "executed"}]) == {"save-1"}
    now[0] = 660
    scheduler.update([])
    assert client.actions[1].save_name == "Autosave0001"


def test_autosave_does_not_run_during_game_over_and_keeps_elapsed_time():
    now = [0.0]
    settings, client = Settings(), Client()
    scheduler = AutosaveScheduler(settings, client, clock=lambda: now[0])

    scheduler.update([], game_over=True)
    now[0] = 60.0
    scheduler.update([], game_over=False)
    assert len(client.actions) == 1


def test_autosave_without_command_identity_is_throttled_until_next_interval():
    class ClientWithoutCommandId:
        player_id = "local"

        def __init__(self):
            self.calls = 0

        def send_action(self, action):
            self.calls += 1
            return None

    now = [0.0]
    settings = Settings()
    client = ClientWithoutCommandId()
    scheduler = AutosaveScheduler(settings, client, clock=lambda: now[0])

    scheduler.update([])
    now[0] = 60.0
    assert scheduler.update([]) == set()
    assert scheduler.update([]) == set()
    assert client.calls == 1


def test_autosave_settings_and_counter_survive_restart_and_name_change_resets_counter(tmp_path):
    path = tmp_path / "settings.json"
    service = GameSettingsService.from_path(path)
    service.apply_options(replace(
        service.settings,
        autosave_enabled=True,
        autosave_incremental=True,
        autosave_interval_minutes=3,
        autosave_name="Campaign",
    ))
    service.set_autosave_counter(27)

    restarted = GameSettingsService.from_path(path)
    assert restarted.settings.autosave_enabled is True
    assert restarted.settings.autosave_incremental is True
    assert restarted.settings.autosave_interval_minutes == 3
    assert restarted.settings.autosave_name == "Campaign"
    assert restarted.settings.autosave_counter == 27

    restarted.apply_options(replace(restarted.settings, autosave_name="Campaign2"))
    assert GameSettingsRepository(path).load().autosave_counter == 0


def test_options_reject_an_unsafe_enabled_autosave_name_until_corrected(tmp_path):
    service = GameSettingsService.from_path(tmp_path / "settings.json")
    content = GameSettingsContent(service, None, staged=True)
    content.update_options(autosave_enabled=True, autosave_name="../unsafe")

    assert content.autosave_validation_error
    assert content.apply() is False
    assert service.settings.autosave_enabled is False

    content.update_options(autosave_name="Campaign")
    assert content.autosave_validation_error == ""
    assert content.apply() is True
    assert service.settings.autosave_enabled is True
    assert service.settings.autosave_name == "Campaign"


def test_autosave_results_are_quiet_but_manual_save_results_are_reported():
    notices = []
    feedback = CommandFeedback(SimpleNamespace(enqueue=lambda *args, **kwargs: notices.append((args, kwargs))))
    records = [
        {"command_id": "auto", "actor_id": "local", "action_type": "ActionSaveGame", "status": "executed"},
        {"command_id": "manual", "actor_id": "local", "action_type": "ActionSaveGame", "status": "executed"},
        {"command_id": "auto-failed", "actor_id": "local", "action_type": "ActionSaveGame", "status": "failed", "message": "Disk full"},
        {"command_id": "failed", "actor_id": "local", "action_type": "ActionSaveGame", "status": "failed", "message": "Disk full"},
    ]
    feedback.update(records, "local", {"auto", "auto-failed"})
    assert len(notices) == 2
    assert notices[0][0][0] == "Save game"
    assert notices[1][0][1] == "Disk full"


def test_scheduled_save_reaches_real_session_and_writes_a_loadable_slot(tmp_path):
    import polars as pl
    from src.client.services.network_client_service import NetworkClient
    from src.core.saves import list_available_saves
    from src.engine.simulator import Engine
    from src.server.session import GameSession
    from src.shared.config import GameConfig
    from src.shared.state import GameState

    config = GameConfig(tmp_path)
    state = GameState()
    state.update_table("regions", pl.DataFrame({"id": [1], "owner": ["USA"]}))
    session = GameSession(config, None, None, Engine(dev_mode=False), None, state)
    now = [0.0]
    settings = Settings()
    client = NetworkClient(session)
    scheduler = AutosaveScheduler(settings, client, clock=lambda: now[0])
    notices = []
    feedback = CommandFeedback(SimpleNamespace(enqueue=lambda *args, **kwargs: notices.append((args, kwargs))))
    scheduler.update(state.journal.command_results)
    now[0] = 60.0
    pending = scheduler.update(state.journal.command_results)
    session.tick(0.1)
    result = state.journal.command_results[-1]
    assert result["command_id"] in pending
    assert result["status"] == "executed"
    assert [item["name"] for item in list_available_saves(config)] == ["Autosave0000"]
    assert (tmp_path / "user_data" / "saves" / "Autosave0000" / "tables" / "regions.parquet").exists()
    quiet_results = scheduler.update(state.journal.command_results)
    assert quiet_results == pending
    feedback.update(state.journal.command_results, client.player_id, quiet_results)
    assert notices == []
