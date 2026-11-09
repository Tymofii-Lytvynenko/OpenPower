import hashlib
import os
from pathlib import Path
from unittest.mock import Mock

import numpy as np
import pytest

from src.core.cache_service import CacheService
from src.core.paths import ProjectPaths
import src.core.paths as paths_module


@pytest.fixture
def cache_service(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> CacheService:
    cache_dir = tmp_path / "cache"
    monkeypatch.setattr(ProjectPaths, "cache", lambda: cache_dir)
    return CacheService(tmp_path)


def test_project_root_uses_executable_parent_when_frozen(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ProjectPaths, "_ROOT_CACHE", None)
    monkeypatch.setattr(paths_module.sys, "frozen", True, raising=False)
    monkeypatch.setattr(paths_module.sys, "executable", str(tmp_path / "OpenPower.exe"))

    assert ProjectPaths.root() == tmp_path


def test_project_root_uses_fallback_when_no_development_markers_exist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = tmp_path / "src" / "core" / "paths.py"
    monkeypatch.setattr(ProjectPaths, "_ROOT_CACHE", None)
    monkeypatch.setattr(paths_module.sys, "frozen", False, raising=False)
    monkeypatch.setattr(paths_module.Path, "resolve", lambda _path: current)
    monkeypatch.setattr(paths_module.Path, "exists", lambda _path: False)

    assert ProjectPaths.root() == tmp_path


def test_project_path_helpers_join_the_root_and_module(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ProjectPaths, "_ROOT_CACHE", tmp_path)

    assert ProjectPaths.assets("custom") == tmp_path / "modules" / "custom" / "assets"
    assert ProjectPaths.data("custom") == tmp_path / "modules" / "custom" / "data"
    assert ProjectPaths.user_data() == tmp_path / "user_data"
    assert ProjectPaths.cache() == tmp_path / ".cache"


def test_initialization_uses_default_root_and_creates_cache_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "project"
    cache_dir = tmp_path / "cache"
    monkeypatch.setattr(ProjectPaths, "root", lambda: project_root)
    monkeypatch.setattr(ProjectPaths, "cache", lambda: cache_dir)

    service = CacheService()

    assert service.project_root == project_root
    assert service.cache_dir == cache_dir
    assert cache_dir.is_dir()


def test_initialization_reports_cache_directory_creation_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cache_dir = tmp_path / "cache"
    monkeypatch.setattr(ProjectPaths, "cache", lambda: cache_dir)

    def fail_mkdir(*_args, **_kwargs) -> None:
        raise OSError("read-only filesystem")

    monkeypatch.setattr(Path, "mkdir", fail_mkdir)

    CacheService(tmp_path)

    assert "Critical Error" in capsys.readouterr().out


def test_get_cache_path_keeps_names_readable_and_distinguishes_sources(
    cache_service: CacheService,
    tmp_path: Path,
) -> None:
    first = cache_service.get_cache_path(tmp_path / "north" / "terrain.png", ".npy")
    second = cache_service.get_cache_path(tmp_path / "south" / "terrain.png", ".npy")

    assert first.parent == cache_service.cache_dir
    assert first.name.startswith("terrain_")
    assert first.suffix == ".npy"
    assert first != second


def test_get_asset_path_joins_module_and_asset_parts(
    cache_service: CacheService,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assets_root = tmp_path / "assets"
    monkeypatch.setattr(ProjectPaths, "assets", lambda module: assets_root / module)

    result = cache_service.get_asset_path("base", "images", "terrain.png")

    assert result == assets_root / "base" / "images" / "terrain.png"


def test_compute_file_hash_returns_sha256_and_missing_sentinel(
    cache_service: CacheService,
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"cache contents")

    assert cache_service.compute_file_hash(source) == hashlib.sha256(b"cache contents").hexdigest()
    assert cache_service.compute_file_hash(tmp_path / "missing.bin") == "FILE_NOT_FOUND"


def test_is_cache_valid_handles_missing_newer_and_stale_files(
    cache_service: CacheService,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "source.dat"
    cached = tmp_path / "cached.dat"
    source.write_bytes(b"source")

    assert not cache_service.is_cache_valid(source, cached)
    assert "MISS" in capsys.readouterr().out

    cached.write_bytes(b"cache")
    source_time = source.stat().st_mtime
    os.utime(cached, (source_time + 10, source_time + 10))
    assert cache_service.is_cache_valid(source, cached)

    os.utime(cached, (source_time, source_time))
    assert not cache_service.is_cache_valid(source, cached)
    assert "STALE" in capsys.readouterr().out


def test_is_cache_valid_handles_stat_errors(
    cache_service: CacheService,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = Mock()
    source.stat.side_effect = OSError("source disappeared")
    cached = Mock()
    cached.exists.return_value = True
    cached.name = "cached.dat"

    assert not cache_service.is_cache_valid(source, cached)
    assert "ERROR" in capsys.readouterr().out


def test_load_numpy_array_returns_none_for_missing_and_loads_with_mmap(
    cache_service: CacheService,
    tmp_path: Path,
) -> None:
    assert cache_service.load_numpy_array(tmp_path / "missing.npy") is None

    path = tmp_path / "array.npy"
    expected = np.arange(6, dtype=np.int64).reshape(2, 3)
    np.save(path, expected)

    loaded = cache_service.load_numpy_array(path, mmap_mode="r")

    assert isinstance(loaded, np.memmap)
    np.testing.assert_array_equal(loaded, expected)


def test_load_numpy_array_deletes_corrupt_file(
    cache_service: CacheService,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "corrupt.npy"
    path.write_bytes(b"invalid numpy data")
    monkeypatch.setattr(np, "load", Mock(side_effect=ValueError("corrupt")))

    assert cache_service.load_numpy_array(path) is None
    assert not path.exists()
    assert "Deleting" in capsys.readouterr().out


def test_load_numpy_array_ignores_unlink_errors(
    cache_service: CacheService,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "locked.npy"
    path.write_bytes(b"invalid numpy data")
    monkeypatch.setattr(np, "load", Mock(side_effect=ValueError("corrupt")))
    original_unlink = Path.unlink

    def fail_for_target(target: Path, *args, **kwargs) -> None:
        if target == path:
            raise OSError("file is locked")
        original_unlink(target, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_for_target)

    assert cache_service.load_numpy_array(path) is None
    assert path.exists()


def test_save_numpy_array_runs_inline_or_starts_non_daemon_thread(
    cache_service: CacheService,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "array.npy"
    data = np.arange(3)
    inline_worker = Mock()
    monkeypatch.setattr(cache_service, "_save_numpy_worker", inline_worker)

    cache_service.save_numpy_array(path, data, in_background=False)

    inline_worker.assert_called_once_with(path, data)

    created_threads = []

    class ThreadStub:
        def __init__(self, *, target, args, daemon) -> None:
            self.target = target
            self.args = args
            self.daemon = daemon
            self.started = False
            created_threads.append(self)

        def start(self) -> None:
            self.started = True

    monkeypatch.setattr("src.core.cache_service.threading.Thread", ThreadStub)

    cache_service.save_numpy_array(path, data)

    started_thread = created_threads[0]
    assert started_thread.target == inline_worker
    assert started_thread.args == (path, data)
    assert started_thread.daemon is False
    assert started_thread.started


def test_save_numpy_worker_atomically_writes_array(
    cache_service: CacheService,
    tmp_path: Path,
) -> None:
    path = tmp_path / "array.npy"
    expected = np.arange(4, dtype=np.int64)

    cache_service._save_numpy_worker(path, expected)

    np.testing.assert_array_equal(np.load(path), expected)
    assert not (tmp_path / "array.npy.tmp.npy").exists()


def test_save_numpy_worker_cleans_up_after_write_failure(
    cache_service: CacheService,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "array.npy"
    temporary_path = tmp_path / "array.npy.tmp.npy"

    def fail_after_partial_write(target: Path, _data: np.ndarray) -> None:
        target.write_bytes(b"partial")
        raise OSError("disk full")

    monkeypatch.setattr(np, "save", fail_after_partial_write)

    cache_service._save_numpy_worker(path, np.arange(2))

    assert not temporary_path.exists()
    assert "Save failed" in capsys.readouterr().out


def test_save_numpy_worker_swallows_temporary_file_cleanup_failure(
    cache_service: CacheService,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "array.npy"
    temporary_path = tmp_path / "array.npy.tmp.npy"
    original_unlink = Path.unlink

    def fail_after_partial_write(target: Path, _data: np.ndarray) -> None:
        target.write_bytes(b"partial")
        raise OSError("disk full")

    def fail_temporary_unlink(target: Path, *args, **kwargs) -> None:
        if target == temporary_path:
            raise OSError("file is locked")
        original_unlink(target, *args, **kwargs)

    monkeypatch.setattr(np, "save", fail_after_partial_write)
    monkeypatch.setattr(Path, "unlink", fail_temporary_unlink)

    cache_service._save_numpy_worker(path, np.arange(2))

    assert temporary_path.exists()


def test_load_numpy_archive_returns_none_when_missing_or_unreadable(
    cache_service: CacheService,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    assert cache_service.load_numpy_archive(tmp_path / "missing.npz") is None

    unreadable = tmp_path / "unreadable.npz"
    unreadable.write_bytes(b"not a zip archive")

    assert cache_service.load_numpy_archive(unreadable) is None
    assert "will be regenerated" in caplog.text


def test_load_numpy_archive_returns_independent_array_copies(
    cache_service: CacheService,
    tmp_path: Path,
) -> None:
    path = tmp_path / "values.npz"
    expected = np.array([1, 2, 3])
    np.savez_compressed(path, values=expected)

    loaded = cache_service.load_numpy_archive(path)

    assert loaded is not None
    loaded["values"][0] = 99
    np.testing.assert_array_equal(np.load(path)["values"], expected)


def test_save_numpy_archive_atomically_replaces_cache(
    cache_service: CacheService,
    tmp_path: Path,
) -> None:
    path = tmp_path / "values.npz"
    expected = np.array([4, 5, 6])

    cache_service.save_numpy_archive(path, values=expected)

    loaded = cache_service.load_numpy_archive(path)
    assert loaded is not None
    np.testing.assert_array_equal(loaded["values"], expected)
    assert not path.with_name(f"{path.name}.tmp.npz").exists()


def test_save_numpy_archive_cleans_up_after_write_failure(
    cache_service: CacheService,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    path = tmp_path / "values.npz"
    temporary_path = path.with_name(f"{path.name}.tmp.npz")

    def fail_after_partial_write(target: Path, **_arrays) -> None:
        target.write_bytes(b"partial")
        raise TypeError("unsupported value")

    monkeypatch.setattr(np, "savez_compressed", fail_after_partial_write)

    cache_service.save_numpy_archive(path, values=np.arange(2))

    assert not temporary_path.exists()
    assert "Could not write cache archive" in caplog.text


def test_save_numpy_archive_reports_temporary_file_cleanup_failure(
    cache_service: CacheService,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    path = tmp_path / "values.npz"
    temporary_path = path.with_name(f"{path.name}.tmp.npz")
    original_unlink = Path.unlink

    def fail_after_partial_write(target: Path, **_arrays) -> None:
        target.write_bytes(b"partial")
        raise TypeError("unsupported value")

    def fail_temporary_unlink(target: Path, *args, **kwargs) -> None:
        if target == temporary_path:
            raise OSError("file is locked")
        original_unlink(target, *args, **kwargs)

    monkeypatch.setattr(np, "savez_compressed", fail_after_partial_write)
    monkeypatch.setattr(Path, "unlink", fail_temporary_unlink)

    cache_service.save_numpy_archive(path, values=np.arange(2))

    assert temporary_path.exists()
    assert "Could not remove temporary cache archive" in caplog.text
