from pathlib import Path

import pytest

from src.shared import config as config_module
from src.shared.config import GameConfig


def test_config_falls_back_to_requested_mods_when_resolution_fails(tmp_path, monkeypatch):
    calls = 0

    def load_requested_mods(_project_root: Path) -> list[str]:
        nonlocal calls
        calls += 1
        return ["base", "expansion"]

    def resolve_project_mods(_project_root: Path):
        raise ValueError("invalid mod manifest")

    monkeypatch.setattr(config_module, "load_requested_mods", load_requested_mods)
    monkeypatch.setattr(config_module, "resolve_project_mods", resolve_project_mods)

    config = GameConfig(tmp_path)

    assert calls == 2
    assert config.requested_mods == ["base", "expansion"]
    assert config.active_mods == ["base", "expansion"]


def test_config_preserves_defaults_when_both_mod_loading_attempts_fail(
    tmp_path, monkeypatch, capsys
):
    def fail_loading(_project_root: Path) -> list[str]:
        raise OSError("mods.json is unavailable")

    monkeypatch.setattr(config_module, "load_requested_mods", fail_loading)

    config = GameConfig(tmp_path)

    assert config.requested_mods == ["base"]
    assert config.active_mods == ["base"]
    output = capsys.readouterr().out
    assert "Failed to resolve active mods" in output
    assert "Failed to load mods.json" in output


def test_empty_active_mod_list_writes_to_base_data_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(config_module, "load_requested_mods", lambda _root: [])
    monkeypatch.setattr(config_module, "resolve_project_mods", lambda _root: [])
    config = GameConfig(tmp_path)

    assert config.active_mods == []
    assert config.get_write_data_dir() == tmp_path / "modules" / "base" / "data"
    config.active_mods = ["base", "expansion"]
    assert config.get_write_data_dir() == tmp_path / "modules" / "expansion" / "data"


def test_localization_skips_missing_base_catalog_and_loads_mod_catalog(tmp_path, monkeypatch):
    monkeypatch.setattr(config_module, "load_requested_mods", lambda _root: ["expansion"])
    monkeypatch.setattr(config_module, "resolve_project_mods", lambda _root: [])
    config = GameConfig(tmp_path)
    catalog = (
        tmp_path
        / "modules"
        / "expansion"
        / "assets"
        / "localization"
        / "en-US.json"
    )
    catalog.parent.mkdir(parents=True)
    catalog.write_text('{"menu.play":"Begin"}', encoding="utf-8")

    assert config.load_localization("en-US") == {"menu.play": "Begin"}


def test_localization_reports_invalid_json_and_non_string_values(tmp_path, monkeypatch):
    monkeypatch.setattr(config_module, "load_requested_mods", lambda _root: ["expansion"])
    monkeypatch.setattr(config_module, "resolve_project_mods", lambda _root: [])
    config = GameConfig(tmp_path)
    catalog = (
        tmp_path
        / "modules"
        / "expansion"
        / "assets"
        / "localization"
        / "en-US.json"
    )
    catalog.parent.mkdir(parents=True)

    catalog.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid localization catalog"):
        config.load_localization("en-US")

    catalog.write_text('{"menu.play": 7}', encoding="utf-8")
    with pytest.raises(ValueError, match="must map string keys to string values"):
        config.load_localization("en-US")
