from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest
from PIL import Image

from src.client.renderers.texture_manager import TextureManager


class _FakeTexture:
    def __init__(self):
        self.writes = []
        self.uses = []

    def write(self, data):
        self.writes.append(data)

    def use(self, unit):
        self.uses.append(unit)


class _FakeContext:
    NEAREST = "nearest"
    LINEAR = "linear"
    REPEAT = "repeat"
    CLAMP_TO_EDGE = "clamp"

    def __init__(self):
        self.created = []

    def texture(self, size, **kwargs):
        texture = _FakeTexture()
        self.created.append((size, kwargs, texture))
        return texture


class _FakeCache:
    def __init__(self, *, valid=False, array=None):
        self.valid = valid
        self.array = array
        self.paths = []
        self.loads = []
        self.saves = []

    def get_cache_path(self, source, suffix):
        self.paths.append((source, suffix))
        return Path("cache") / suffix

    def is_cache_valid(self, _source, _cache_path):
        return self.valid

    def load_numpy_array(self, cache_path, **kwargs):
        self.loads.append((cache_path, kwargs))
        return self.array

    def save_numpy_array(self, cache_path, array, *, in_background):
        self.saves.append((cache_path, array, in_background))


def _manager(*, cache=None, lut_dim=2):
    context = _FakeContext()
    cache = cache or _FakeCache()
    return TextureManager(context, cache, lut_dim=lut_dim), context, cache


@pytest.mark.parametrize("cached", [False, True])
def test_load_map_texture_uses_cache_or_generates_cpu_texture(tmp_path, cached):
    encoded = np.zeros((2, 2, 4), dtype=np.uint8)
    cache = _FakeCache(valid=cached, array=encoded)
    manager, context, _ = _manager(cache=cache, lut_dim=1)
    dense_map = np.asarray([0, 1, 2, 2], dtype=np.uint32)
    indexer = SimpleNamespace(get_indices=Mock(return_value=([0, 10, 20], dense_map)))
    map_path = tmp_path / "packed-map.png"

    manager.load_map_texture(map_path, dense_map, 2, 2, indexer)

    assert manager.dense_to_real == [0, 10, 20]
    assert manager.real_to_dense == {0: 0, 10: 1, 20: 2}
    assert manager.lut_dim == 2
    assert manager.map_texture.wrap_x == context.REPEAT
    assert manager.map_texture.wrap_y == context.CLAMP_TO_EDGE
    indexer.get_indices.assert_called_once_with(
        source_path=map_path,
        map_data_array=dense_map,
    )
    assert len(context.created) == 1
    assert context.created[0][0] == (2, 2)
    assert context.created[0][1]["filter"] == (context.NEAREST, context.NEAREST)
    if cached:
        assert cache.loads[0][1] == {}
        assert cache.saves == []
    else:
        assert cache.saves[0][2] is True
        assert cache.saves[0][1].shape == (2, 2, 4)


def test_map_resampling_and_size_helpers_cover_identity_and_gpu_limits():
    dense = np.arange(6, dtype=np.uint32).reshape((2, 3))

    assert TextureManager.resample_dense_map(dense, 3, 2, 3, 2).tolist() == dense.tolist()
    assert TextureManager.resample_dense_map(dense, 3, 2, 2, 1).tolist() == [[0, 1]]
    assert TextureManager.fit_texture_size(100, 50, 200, 200) == (100, 50)
    assert TextureManager.fit_texture_size(400, 200, 100, 200) == (100, 50)
    assert TextureManager.fit_texture_size(100, 400, 200, 100) == (25, 100)
    assert TextureManager.fit_texture_size(1, 1, 1, 1) == (1, 1)


def test_terrain_texture_cache_upload_and_missing_file(tmp_path, monkeypatch):
    rgba = np.full((2, 3, 4), 128, dtype=np.uint8)
    cache = _FakeCache(valid=True, array=rgba)
    manager, context, cache = _manager(cache=cache)
    terrain_path = tmp_path / "terrain.bin"
    terrain_path.write_bytes(b"cached")

    manager.load_terrain_texture(terrain_path)

    assert cache.loads[0][1] == {"mmap_mode": "r"}
    assert manager.terrain_texture.wrap_x == context.REPEAT
    assert manager.terrain_texture.wrap_y == context.CLAMP_TO_EDGE
    assert context.created[0][0] == (3, 2)
    assert context.created[0][1]["filter"] == (context.LINEAR, context.LINEAR)

    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", Image.MAX_IMAGE_PIXELS)
    with pytest.raises(FileNotFoundError, match="Terrain path not found"):
        manager.load_terrain_texture(tmp_path / "missing.png")


def test_terrain_texture_fallback_resizes_saves_and_wraps_errors(tmp_path, monkeypatch):
    module = __import__("src.client.renderers.texture_manager", fromlist=["TextureManager"])
    terrain_path = tmp_path / "terrain.png"
    Image.new("RGB", (2, 2), (10, 20, 30)).save(terrain_path)
    manager, context, cache = _manager(cache=_FakeCache())
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", Image.MAX_IMAGE_PIXELS)
    monkeypatch.setattr(TextureManager, "MAX_TERRAIN_TEXTURE_SIZE", (1, 1))

    manager.load_terrain_texture(terrain_path)

    assert context.created[0][0] == (1, 1)
    assert cache.saves[0][1].shape == (1, 1, 4)
    assert cache.saves[0][2] is True

    failed_manager, _, _ = _manager(cache=_FakeCache())
    monkeypatch.setattr(module.Image, "open", Mock(side_effect=OSError("decode failed")))
    with pytest.raises(RuntimeError, match="Failed to load terrain texture: decode failed"):
        failed_manager.load_terrain_texture(terrain_path)


def test_lookup_capacity_dimension_and_initial_gpu_textures():
    assert TextureManager.required_lut_dimension(0, 0) == 1
    assert TextureManager.required_lut_dimension(5, 1) == 4

    manager, context, _ = _manager(lut_dim=2)
    previous = manager.lut_data
    manager._ensure_lookup_capacity(4)
    assert manager.lut_data is previous
    manager._ensure_lookup_capacity(17)
    assert manager.lut_dim == 8
    assert manager.lut_data.shape == (64, 4)

    manager.init_lookup_texture()
    assert manager.lookup_texture.writes == [manager.lut_data.tobytes()]
    assert manager.previous_lookup_texture.writes == [manager.lut_data.tobytes()]
    assert len(context.created) == 2


def test_overlay_changes_retarget_transition_and_preserve_displayed_blend(monkeypatch):
    module = __import__("src.client.renderers.texture_manager", fromlist=["TextureManager"])
    manager, _, _ = _manager(lut_dim=2)
    manager.real_to_dense = {10: 1, 20: 2}
    manager.lookup_texture = _FakeTexture()
    manager.previous_lookup_texture = _FakeTexture()
    manager.lut_data[1] = [10, 20, 30, 100]
    manager._active_color_map = {10: (10, 20, 30, 100)}
    monkeypatch.setattr(module.time, "perf_counter", lambda: 2.0)

    manager.update_overlay({10: (10, 20, 30, 100)})
    assert manager.overlay_revision == 0

    manager.update_overlay({10: (200, 100, 50)})
    assert manager.overlay_revision == 1
    assert manager._transition_started_at == 2.0
    assert manager.previous_lookup_texture.writes
    assert manager.lookup_texture.writes
    assert manager.lut_data[1].tolist() == [200, 100, 50, 200]

    manager._previous_lut_data = np.zeros_like(manager.lut_data)
    manager.lut_data[1] = [100, 100, 100, 100]
    manager._transition_started_at = 2.0
    monkeypatch.setattr(module.time, "perf_counter", lambda: 2.125)
    visible = manager._visible_lut_data()
    assert visible[1].tolist() == [50, 50, 50, 50]
    manager._transition_started_at = 2.0
    monkeypatch.setattr(module.time, "perf_counter", lambda: 2.25)
    completed = manager._visible_lut_data()
    assert np.array_equal(completed, manager.lut_data)
    assert manager._transition_started_at is None
    assert manager.overlay_transition_progress(now=2.3) == 1.0


def test_lut_rebuild_selection_transitions_and_uniform_bindings():
    manager, _, _ = _manager(lut_dim=2)
    manager.real_to_dense = {10: 1, 20: 2, 30: 5, 40: 0}
    manager.multi_select_dense_ids = {2}
    manager._active_color_map = {
        10: (1, 2, 3),
        20: (4, 5, 6, 90),
        30: (7, 8, 9, 100),
        40: (10, 11, 12, 13),
        50: (20, 21, 22, 23),
    }
    manager._rebuild_lut_array()
    assert manager.lut_data[1].tolist() == [1, 2, 3, 200]
    assert manager.lut_data[2].tolist() == [4, 5, 6, 255]

    manager.lut_data[1, 3] = 100
    manager.lut_data[2, 3] = 0
    manager.multi_select_dense_ids = {1, 4, 5}
    manager.lookup_texture = _FakeTexture()
    manager.update_selection({1, 2, 5})
    assert manager.lut_data[1, 3] == 255
    assert manager.lut_data[2, 3] == 0
    assert len(manager.lookup_texture.writes) == 1

    manager.lookup_texture = None
    manager.update_selection(set())
    assert manager.lut_data[1, 3] == 200

    program = {}
    manager.bind_textures(program)
    manager.set_uniforms(program)
    assert program == {"u_lut_dim": 2.0}

    manager.map_texture = _FakeTexture()
    manager.lookup_texture = _FakeTexture()
    manager.previous_lookup_texture = _FakeTexture()
    manager.terrain_texture = _FakeTexture()
    manager.bind_textures(program)
    assert manager.map_texture.uses == [0]
    assert manager.lookup_texture.uses == [1]
    assert manager.previous_lookup_texture.uses == [3]
    assert manager.terrain_texture.uses == [2]
    assert program == {
        "u_lut_dim": 2.0,
        "u_map_texture": 0,
        "u_lookup_texture": 1,
        "u_previous_lookup_texture": 3,
        "u_terrain_texture": 2,
    }


def test_overlay_without_previous_texture_has_no_transition_and_mapping_is_read_only():
    manager, _, _ = _manager(lut_dim=2)
    manager.real_to_dense = {1: 1}
    manager.update_overlay({1: (4, 5, 6, 7)})

    assert manager._transition_started_at is None
    assert manager.overlay_transition_progress() == 1.0
    assert manager.active_color_map[1] == (4, 5, 6, 7)
    with pytest.raises(TypeError):
        manager.active_color_map[2] = (1, 2, 3)
