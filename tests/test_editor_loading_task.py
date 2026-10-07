from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from src.client.tasks.editor_loading_task import EditorLoadingTask
from src.client.tasks.session_startup import TaskCancelledError


def _config(root: Path):
    return SimpleNamespace(
        project_root=root,
        get_data_dirs=lambda: [root],
        get_asset_path=lambda asset: root / asset,
    )


def test_editor_loading_cancellation_stops_before_asset_work(tmp_path: Path) -> None:
    task = EditorLoadingTask(object(), _config(tmp_path))
    task.cancel()

    with pytest.raises(TaskCancelledError):
        task.run()


def test_missing_technical_map_fails_with_clear_asset_error(tmp_path: Path) -> None:
    task = EditorLoadingTask(object(), _config(tmp_path))

    with pytest.raises(FileNotFoundError, match="Technical region map asset"):
        task.run()


def test_missing_terrain_is_nonfatal_and_cancellation_after_map_work_is_honored(tmp_path: Path) -> None:
    map_path = tmp_path / "regions" / "regions.png"
    map_path.parent.mkdir()
    map_path.touch()
    session = object()
    config = _config(tmp_path)
    task = EditorLoadingTask(session, config)
    map_data = object()

    with (
        patch("src.client.tasks.editor_loading_task.RegionMapData", return_value=map_data),
        patch("src.client.tasks.editor_loading_task.NetworkClient", return_value=object()),
    ):
        context = task.run()

    assert context.map_data is map_data
    assert context.map_path == map_path
    assert context.terrain_path == tmp_path / "missing_terrain_placeholder.png"

    cancelled_task = EditorLoadingTask(session, config)

    def cancel_during_map_load(path):
        cancelled_task.cancel()
        return map_data

    with (
        patch("src.client.tasks.editor_loading_task.RegionMapData", side_effect=cancel_during_map_load),
        pytest.raises(TaskCancelledError),
    ):
        cancelled_task.run()
