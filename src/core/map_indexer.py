from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional, Tuple

import numpy as np

from src.core.cache_service import CacheService


logger = logging.getLogger(__name__)


class MapIndexer:
    """Build and cache compact dense region IDs for map textures."""

    CACHE_VERSION = 2
    CHUNK_PIXEL_LIMIT = 1 << 20

    def __init__(self, cache_service: CacheService):
        self.cache = cache_service

    def get_indices(
        self,
        source_path: Path,
        map_data_array: np.ndarray,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Load a verified index cache or build a compact memory-mapped index."""
        if map_data_array.ndim != 2:
            raise ValueError("Map index input must be a 2D region-ID grid.")
        if not map_data_array.size:
            raise ValueError("Map index input must not be empty.")

        metadata_path = self.cache.get_cache_path(source_path, "_index_v2.npz")
        dense_path = self.cache.get_cache_path(source_path, "_index_v2_dense.npy")
        current_hash = self.cache.compute_file_hash(source_path)

        if self.cache.is_cache_valid(source_path, metadata_path) and self.cache.is_cache_valid(
            source_path,
            dense_path,
        ):
            cached = self._load_from_cache(
                metadata_path,
                dense_path,
                current_hash,
                map_data_array.shape,
            )
            if cached is not None:
                logger.debug("Using validated memory-mapped region index for %s.", source_path)
                return cached

        logger.info("Building compact region index for %s.", source_path)
        return self._compute_and_cache(
            map_data_array,
            metadata_path,
            dense_path,
            current_hash,
        )

    def _load_from_cache(
        self,
        metadata_path: Path,
        dense_path: Path,
        current_hash: str,
        expected_shape: tuple[int, int],
    ) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        metadata = self.cache.load_numpy_archive(metadata_path)
        if not metadata:
            return None

        required_members = {"version", "hash", "unique_ids", "shape"}
        if not required_members.issubset(metadata):
            logger.warning(
                "Region index metadata %s is missing members: %s.",
                metadata_path,
                sorted(required_members.difference(metadata)),
            )
            return None

        version = np.asarray(metadata["version"])
        cached_hash = np.asarray(metadata["hash"])
        unique_ids = np.asarray(metadata["unique_ids"])
        cached_shape = np.asarray(metadata["shape"])
        if version.ndim != 0 or int(version.item()) != self.CACHE_VERSION:
            logger.warning("Region index metadata %s has an unsupported version.", metadata_path)
            return None
        if cached_hash.ndim != 0 or str(cached_hash.item()) != current_hash:
            logger.warning("Region index metadata %s has a stale source hash.", metadata_path)
            return None
        if unique_ids.ndim != 1 or not unique_ids.size:
            logger.warning("Region index metadata %s has invalid unique IDs.", metadata_path)
            return None
        if cached_shape.shape != (2,) or tuple(cached_shape.tolist()) != expected_shape:
            logger.warning("Region index metadata %s has an unexpected map shape.", metadata_path)
            return None

        dense_map = self.cache.load_numpy_array(dense_path, mmap_mode="r")
        if (
            dense_map is None
            or dense_map.ndim != 2
            or dense_map.shape != expected_shape
            or dense_map.dtype.kind not in "ui"
        ):
            logger.warning("Region index data %s is missing or malformed.", dense_path)
            return None

        return unique_ids, dense_map

    def _compute_and_cache(
        self,
        map_array: np.ndarray,
        metadata_path: Path,
        dense_path: Path,
        current_hash: str,
    ) -> Tuple[np.ndarray, np.ndarray]:
        unique_ids = self._collect_unique_ids(map_array)
        dense_dtype = self._smallest_unsigned_dtype(unique_ids.size)
        temporary_path = dense_path.with_name(f"{dense_path.stem}.tmp.npy")
        dense_map = None

        try:
            dense_map = np.lib.format.open_memmap(
                temporary_path,
                mode="w+",
                dtype=dense_dtype,
                shape=map_array.shape,
            )
            rows_per_chunk = max(1, self.CHUNK_PIXEL_LIMIT // map_array.shape[1])
            for row_start in range(0, map_array.shape[0], rows_per_chunk):
                row_end = min(map_array.shape[0], row_start + rows_per_chunk)
                source_rows = map_array[row_start:row_end]
                dense_map[row_start:row_end] = np.searchsorted(
                    unique_ids,
                    source_rows,
                ).astype(dense_dtype, copy=False)
            dense_map.flush()
            del dense_map
            dense_map = None
            os.replace(temporary_path, dense_path)
        except BaseException:
            if dense_map is not None:
                dense_map.flush()
                del dense_map
            if temporary_path.exists():
                temporary_path.unlink()
            raise

        self.cache.save_numpy_archive(
            metadata_path,
            version=np.asarray(self.CACHE_VERSION, dtype=np.int16),
            hash=np.asarray(current_hash),
            unique_ids=unique_ids,
            shape=np.asarray(map_array.shape, dtype=np.int64),
        )
        cached_map = self.cache.load_numpy_array(dense_path, mmap_mode="r")
        if cached_map is None:
            raise OSError(f"Failed to reopen region index cache: {dense_path}")
        return unique_ids, cached_map

    def _collect_unique_ids(self, map_array: np.ndarray) -> np.ndarray:
        rows_per_chunk = max(1, self.CHUNK_PIXEL_LIMIT // map_array.shape[1])
        unique_chunks = [
            np.unique(map_array[row_start : row_start + rows_per_chunk])
            for row_start in range(0, map_array.shape[0], rows_per_chunk)
        ]
        return np.unique(np.concatenate(unique_chunks))

    @staticmethod
    def _smallest_unsigned_dtype(item_count: int) -> np.dtype:
        if item_count <= np.iinfo(np.uint8).max + 1:
            return np.dtype(np.uint8)
        if item_count <= np.iinfo(np.uint16).max + 1:
            return np.dtype(np.uint16)
        if item_count <= np.iinfo(np.uint32).max + 1:
            return np.dtype(np.uint32)
        return np.dtype(np.uint64)
