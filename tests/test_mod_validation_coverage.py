import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.modding import validation
from src.modding.validation import _project_import_path, validate_mod


def _manifest(project_root: Path, *, dependencies: object = ...) -> SimpleNamespace:
    if dependencies is ...:
        dependencies = []
    return SimpleNamespace(
        id="fixture_mod",
        path=project_root / "modules" / "fixture_mod",
        dependencies=dependencies,
    )


def test_validate_mod_reports_missing_module(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(validation, "discover_mods", lambda _path: {})

    with pytest.raises(FileNotFoundError, match="fixture_mod.*modules"):
        validate_mod(tmp_path, "fixture_mod")


def test_validate_mod_rejects_directory_manifest_id_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest(tmp_path)
    manifest.path = tmp_path / "modules" / "renamed_mod"
    monkeypatch.setattr(validation, "discover_mods", lambda _path: {"fixture_mod": manifest})

    with pytest.raises(ValueError, match="must match manifest id"):
        validate_mod(tmp_path, "fixture_mod")


@pytest.mark.parametrize(
    "dependencies",
    [None, [7], ["  "]],
    ids=["not-a-list", "non-string-entry", "blank-entry"],
)
def test_validate_mod_rejects_invalid_dependencies(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    dependencies: object,
) -> None:
    manifest = _manifest(tmp_path, dependencies=dependencies)
    monkeypatch.setattr(validation, "discover_mods", lambda _path: {"fixture_mod": manifest})

    with pytest.raises(TypeError, match="dependencies must be non-empty strings"):
        validate_mod(tmp_path, "fixture_mod")


def test_validate_mod_builds_report_and_restores_import_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path.resolve()
    manifest = _manifest(root)
    monkeypatch.setattr(validation, "discover_mods", Mock(return_value={"fixture_mod": manifest}))

    config = SimpleNamespace()
    config_factory = Mock(return_value=config)
    monkeypatch.setattr(validation, "GameConfig", config_factory)

    class FirstAction:
        pass

    class SecondAction:
        pass

    session = SimpleNamespace(
        engine=SimpleNamespace(
            execution_order=[SimpleNamespace(id="system_b"), SimpleNamespace(id="system_a")],
            handled_action_types=[SecondAction, FirstAction],
        ),
        schemas=SimpleNamespace(table_names=("regions", "countries")),
        state=SimpleNamespace(tables={"regions": object(), "countries": object()}),
        tick=Mock(),
    )
    create_session = Mock(return_value=session)
    monkeypatch.setattr(validation, "GameSession", SimpleNamespace(create_headless=create_session))

    import_path = str(root)
    assert import_path not in sys.path

    report = validate_mod(root, " fixture_mod ")

    assert report.mod_id == "fixture_mod"
    assert report.load_order == ("fixture_mod",)
    assert report.system_ids == ("system_b", "system_a")
    assert report.table_schemas == ("regions", "countries")
    assert report.state_tables == ("countries", "regions")
    assert report.action_types == tuple(
        sorted(
            (
                f"{FirstAction.__module__}.{FirstAction.__qualname__}",
                f"{SecondAction.__module__}.{SecondAction.__qualname__}",
            )
        )
    )
    assert config.requested_mods == ["fixture_mod"]
    assert config.active_mods == ["fixture_mod"]
    assert config.dev_mode is True
    config_factory.assert_called_once_with(root)
    validation.discover_mods.assert_called_once_with(root / "modules")
    create_session.assert_called_once_with(config)
    session.tick.assert_called_once_with(0.0)
    assert import_path not in sys.path


def test_project_import_path_removes_inserted_entry_after_exception(tmp_path: Path) -> None:
    import_path = str(tmp_path)

    with pytest.raises(RuntimeError, match="session failed"):
        with _project_import_path(tmp_path):
            assert sys.path[0] == import_path
            raise RuntimeError("session failed")

    assert import_path not in sys.path


def test_project_import_path_preserves_preexisting_entry(tmp_path: Path) -> None:
    import_path = str(tmp_path)
    sys.path.insert(0, import_path)

    try:
        with _project_import_path(tmp_path):
            assert sys.path[0] == import_path
        assert sys.path.count(import_path) == 1
    finally:
        sys.path.remove(import_path)
