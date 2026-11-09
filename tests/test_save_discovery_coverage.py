from types import SimpleNamespace

from src.core.saves import list_available_saves


def test_save_discovery_handles_missing_root_and_metadata(tmp_path):
    config = SimpleNamespace(project_root=tmp_path)
    assert list_available_saves(config) == []

    save_root = tmp_path / "user_data" / "saves"
    (save_root / "missing-metadata").mkdir(parents=True)

    assert list_available_saves(config) == []


def test_save_discovery_skips_duplicate_non_directory_and_unreadable_backups(
    tmp_path,
    caplog,
):
    save_root = tmp_path / "user_data" / "saves"
    save_root.mkdir(parents=True)
    (save_root / "occupied").mkdir()
    (save_root / ".occupied.backup").mkdir()
    (save_root / ".file.backup").write_text("not a directory", encoding="utf-8")
    (save_root / ".broken.backup").mkdir()
    (save_root / ".broken.backup" / "meta.json").write_text("{", encoding="utf-8")

    saves = list_available_saves(SimpleNamespace(project_root=tmp_path))

    assert saves == []
    assert "Skipping unreadable save backup" in caplog.text
