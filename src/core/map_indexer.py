import logging
from pathlib import Path
from typing import Optional, Tuple

import numpy as np

from src.core.cache_service import CacheService


logger = logging.getLogger(__name__)


class MapIndexer:
    """
    Handles calculation of map indices. 
    Relies on CacheService for storage and integrity checks.
    """

    def __init__(self, cache_service: CacheService):
        self.cache = cache_service

    def get_indices(self, 
                    source_path: Path, 
                    map_data_array: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Retrieves map indices from cache if valid, otherwise computes them.
        """
        if map_data_array.ndim != 2:
            raise ValueError("Map index input must be a 2D region-ID grid.")

        cache_path = self.cache.get_cache_path(source_path, "_index.npz")
        current_hash = self.cache.compute_file_hash(source_path)

        if self.cache.is_cache_valid(source_path, cache_path):
            cached_data = self._load_from_cache(
                cache_path,
                current_hash,
                map_data_array.shape,
            )
        else:
            cached_data = None

        if cached_data is not None:
            logger.debug("Using validated map index cache for %s.", source_path)
            return cached_data

        logger.info("Rebuilding map index cache for %s.", source_path)
        return self._compute_and_cache(map_data_array, cache_path, current_hash)

    def _load_from_cache(
        self,
        cache_path: Path,
        current_hash: str,
        expected_shape: tuple[int, int],
    ) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        data = self.cache.load_numpy_archive(cache_path)
        if not data:
            return None

        required_members = {"hash", "unique_ids", "dense_map"}
        if not required_members.issubset(data):
            logger.warning(
                "Map index cache %s is missing members: %s.",
                cache_path,
                sorted(required_members.difference(data)),
            )
            return None

        cached_hash = np.asarray(data["hash"])
        if cached_hash.ndim != 0 or str(cached_hash.item()) != current_hash:
            logger.warning("Map index cache %s has a stale or malformed source hash.", cache_path)
            return None

        unique_ids = np.asarray(data["unique_ids"])
        dense_map = np.asarray(data["dense_map"])
        if unique_ids.ndim != 1:
            logger.warning("Map index cache %s has a non-vector unique-ID array.", cache_path)
            return None
        if dense_map.ndim != 2 or dense_map.shape != expected_shape:
            logger.warning(
                "Map index cache %s has dense-map shape %s; expected %s.",
                cache_path,
                dense_map.shape,
                expected_shape,
            )
            return None

        return unique_ids, dense_map

    def _compute_and_cache(self, 
                           map_array: np.ndarray, 
                           cache_path: Path, 
                           current_hash: str) -> Tuple[np.ndarray, np.ndarray]:
        
        unique_ids, dense_map = np.unique(map_array, return_inverse=True)
        dense_map = dense_map.reshape(map_array.shape)

        self.cache.save_numpy_archive(
            cache_path,
            unique_ids=unique_ids,
            dense_map=dense_map,
            hash=np.asarray(current_hash),
        )

        return unique_ids, dense_map
