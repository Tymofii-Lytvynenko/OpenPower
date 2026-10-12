"""Small deterministic world and ports for UI runs without a server or Arcade window."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import polars as pl

from src.shared.state import GameState
from src.client.services.game_settings_service import GameSettings, GameSettingsService


class RecordingClient:
    def __init__(self, state: GameState):
        self.state = state
        self.player_id = "ui-test-player"
        self.player_country = "UKR"
        self.actions: list = []
        self.requests: list[dict] = []
        self.session = self

    def get_state(self):
        return self.state

    def send_action(self, action):
        self.actions.append(action)

    def get_system_errors(self):
        return []

    def clear_system_errors(self):
        self.requests.append({"type": "clear_errors"})

    def get_presentation_total_minutes(self):
        return float(self.state.time.total_minutes)

    def get_display_date_text(self):
        return self.state.time.date_str

    def get_display_total_minutes(self):
        return float(self.state.time.total_minutes)

    def request_save(self, *args, **kwargs):
        self.requests.append({"type": "save"})


class MemorySettingsRepository:
    def __init__(self):
        self.value = GameSettings()

    def load(self):
        return self.value

    def save(self, settings):
        self.value = settings


class TestDisplayCatalog:
    def list_screens(self):
        from src.client.services.display_modes import DisplayScreenOption, DisplayModeOption
        modes = tuple(DisplayModeOption(w, h, 60, f"{w}×{h} @ 60 Hz", None)
                      for w, h in ((1280, 720), (1920, 1080)))
        return (DisplayScreenOption(0, "UI test display", 1920, 1080, modes, None),)


class TestWindow:
    def __init__(self, size):
        self.width, self.height = size
        self.fullscreen = False

    def set_fullscreen(self, fullscreen, **kwargs):
        self.fullscreen = fullscreen

    def set_size(self, width, height):
        self.width, self.height = width, height

    def get_size(self):
        return self.width, self.height


class RecordingNavigation:
    def __init__(self, window=None):
        self.requests = []
        self.window = window

    def show_main_menu(self, *args, **kwargs):
        self.requests.append("main_menu")

    def show_load_game(self, *args, **kwargs):
        self.requests.append("load_game")

    def show_load_game_screen(self, *args, **kwargs):
        self.requests.append("load_game")


class RecordingViewport:
    def __init__(self):
        self.requests = []
        from types import SimpleNamespace
        self.map_modes = {key: SimpleNamespace(name=title) for key, title in
                          (("political", "Political"), ("economic", "Economic"))}
        self.current_mode_key = "political"
        self.show_all_units = False
        self.show_engagement_zones = False

    def focus_on_region(self, region_id):
        self.requests.append({"region": region_id})

    def focus_on_country(self, tag):
        self.requests.append({"country": tag})
        return 1

    def select_region_by_id(self, region_id):
        self.requests.append({"selected_region": region_id})

    def set_map_mode(self, mode):
        self.current_mode_key = mode
        self.requests.append({"map_mode": mode})


def build_test_world(project_root: Path, fixture: dict | None = None) -> GameState:
    from src.client.ui.testing.budget import _fixture_state
    from src.engine.mod_manager import ModManager
    from src.shared.config import GameConfig

    state = _fixture_state()
    country = state.tables["countries"].to_dicts()[0]
    country.update(name="Ukraine", population=1_000_000, stability=0.72, human_dev=0.7,
                   gdp=100_000_000.0, government_form="democracy")
    state.tables["countries"] = pl.DataFrame([country, {**country, "id": "POL", "name": "Poland"}])
    state.tables["regions"] = pl.DataFrame([
        {"id": 1, "name": "Kyiv", "owner": "UKR", "controller": "UKR", "population": 1_000_000,
         "gdp": 10_000_000.0, "lat": 50.45, "lon": 30.52},
        {"id": 2, "name": "Warsaw", "owner": "POL", "controller": "POL", "population": 1_000_000,
         "gdp": 10_000_000.0, "lat": 52.23, "lon": 21.01},
    ])
    state.tables["units"] = pl.DataFrame([
        {"id": "unit-1", "owner": "UKR", "type": "infantry", "name": "1st Brigade",
         "region_id": 1, "location": 1, "strength": 1000, "status": "ready"},
    ])
    manager = ModManager(GameConfig(project_root))
    manager.resolve_load_order()
    schemas = manager.load_runtime().schemas
    schemas.ensure_state(state)
    state.update_table("unit_designs", pl.DataFrame([
        {"id": "design-1", "country_id": "UKR", "branch": "land", "display_name": "Infantry",
         "class_name": "infantry", "quality": 0.7, "cost": 1000.0, "speed": 10.0, "firepower": 5.0},
    ]))
    if fixture:
        for name, rows in fixture.get("tables", {}).items():
            if not isinstance(rows, list):
                raise ValueError(f"Fixture table '{name}' must contain a list of row objects.")
            empty = state.tables[name].clear() if name in state.tables else pl.DataFrame()
            state.update_table(name, pl.DataFrame(rows) if rows else empty)
        state.globals.update(fixture.get("globals", {}))
        if "time" in fixture:
            state.time = replace(state.time, **fixture["time"])
    return state


def test_settings():
    return GameSettingsService(MemorySettingsRepository(), TestDisplayCatalog())
