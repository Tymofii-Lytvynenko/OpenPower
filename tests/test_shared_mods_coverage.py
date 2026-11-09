from __future__ import annotations

import json

import pytest

from src.shared.mods import (
    ModManifest,
    discover_mods,
    load_requested_mods,
    read_engine_version,
    validate_engine_compatibility,
)


def test_requested_mods_fall_back_when_configuration_is_empty_or_invalid(tmp_path):
    config_path = tmp_path / "mods.json"
    config_path.write_text(json.dumps({"active_mods": []}), encoding="utf-8")
    assert load_requested_mods(tmp_path) == ["base"]

    config_path.write_text(json.dumps({"active_mods": ["", "   "]}), encoding="utf-8")
    assert load_requested_mods(tmp_path) == ["base"]

    config_path.write_text(json.dumps({"active_mods": "base"}), encoding="utf-8")
    assert load_requested_mods(tmp_path) == ["base"]


def test_discovery_skips_files_and_supports_registration_only_modules(tmp_path):
    modules_dir = tmp_path / "modules"
    modules_dir.mkdir()
    (modules_dir / "README.txt").write_text("not a module directory", encoding="utf-8")
    legacy_mod = modules_dir / "legacy_mod"
    legacy_mod.mkdir()
    (legacy_mod / "registration.py").write_text("", encoding="utf-8")

    discovered = discover_mods(modules_dir)

    assert list(discovered) == ["legacy_mod"]
    assert discovered["legacy_mod"].version == "0.0.1"


def test_discovery_rejects_invalid_dependency_lists(tmp_path):
    mod_dir = tmp_path / "modules" / "bad_mod"
    mod_dir.mkdir(parents=True)
    (mod_dir / "mod.toml").write_text(
        'id = "bad_mod"\ndependencies = ["   "]\n',
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="invalid dependencies list"):
        discover_mods(tmp_path / "modules")


def test_engine_version_uses_fallback_and_reports_invalid_metadata(tmp_path):
    assert read_engine_version(tmp_path) == "0.1.0"

    pyproject_path = tmp_path / "pyproject.toml"
    pyproject_path.write_text("[project\nversion = '0.2.0'\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Unable to read engine version"):
        read_engine_version(tmp_path)

    pyproject_path.write_text('[project]\nname = "OpenPower"\n', encoding="utf-8")
    with pytest.raises(RuntimeError, match="Engine version is missing"):
        read_engine_version(tmp_path)


def test_engine_compatibility_rejects_reversed_version_bounds():
    manifest = ModManifest(
        id="incompatible_bounds",
        name="Incompatible bounds",
        version="1.0.0",
        min_engine_version="0.2.0",
        max_engine_version="0.1.0",
    )

    with pytest.raises(RuntimeError, match="min_engine_version greater than max_engine_version"):
        validate_engine_compatibility(manifest, "0.1.0")
