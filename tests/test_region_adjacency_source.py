from __future__ import annotations

import os
from pathlib import Path

import polars as pl
from PIL import Image

from src.core.region_adjacency_source import (
    _load_region_adjacency,
    load_region_adjacency,
)


class _Config:
    def __init__(self, data_dir: Path, fallback: Path) -> None:
        self._data_dir = data_dir
        self._fallback = fallback

    def get_data_dirs(self) -> list[Path]:
        return [self._data_dir]

    def get_asset_path(self, subpath: str) -> Path:
        return self._fallback


def _write_region_map(path: Path, right_color: tuple[int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (2, 1))
    image.putpixel((0, 0), (1, 2, 3))
    image.putpixel((1, 0), right_color)
    image.save(path)


def test_region_adjacency_reuses_decoded_map_for_repeated_sessions(tmp_path: Path) -> None:
    _load_region_adjacency.cache_clear()
    image_path = tmp_path / "module" / "regions" / "regions.png"
    fallback = tmp_path / "assets" / "regions.png"
    _write_region_map(image_path, (1, 2, 4))
    config = _Config(image_path.parent.parent, fallback)

    first = load_region_adjacency(config, [0x010203, 0x010204])
    second = load_region_adjacency(config, [0x010203, 0x010204])

    assert first.equals(second)
    assert first.rows() == [(0x010203, 0x010204)]
    assert _load_region_adjacency.cache_info().hits == 1


def test_region_adjacency_cache_invalidates_when_map_file_changes(tmp_path: Path) -> None:
    _load_region_adjacency.cache_clear()
    image_path = tmp_path / "module" / "regions" / "regions.png"
    fallback = tmp_path / "assets" / "regions.png"
    _write_region_map(image_path, (1, 2, 4))
    config = _Config(image_path.parent.parent, fallback)
    valid_ids = [0x010203, 0x010204, 0x010205]

    first = load_region_adjacency(config, valid_ids)
    previous_stat = image_path.stat()
    _write_region_map(image_path, (1, 2, 5))
    os.utime(
        image_path,
        ns=(previous_stat.st_atime_ns, previous_stat.st_mtime_ns + 1_000_000_000),
    )

    second = load_region_adjacency(config, valid_ids)

    assert first.rows() == [(0x010203, 0x010204)]
    assert second.rows() == [(0x010203, 0x010205)]
    assert _load_region_adjacency.cache_info().misses == 2

