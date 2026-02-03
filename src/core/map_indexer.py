import numpy as np
from pathlib import Path
from typing import Tuple, Dict, Optional
from src.client.services.cache_service import CacheService

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
        # 1. Define Cache Path
        cache_path = self.cache.get_cache_path(source_path, "_index.npz")
        
        # 2. Compute integrity hash
        current_hash = self.cache.compute_file_hash(source_path)

        # 3. Try Load
        cached_data = self._load_from_cache(cache_path, current_hash)
        if cached_data:
            print(f"[MapIndexer] Cache hit for {source_path.name}.")
            return cached_data

        # 4. Compute & Save
        print(f"[MapIndexer] Cache miss for {source_path.name}. Computing...")
        return self._compute_and_cache(map_data_array, cache_path, current_hash)

    def _load_from_cache(self, cache_path: Path, current_hash: str) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        data = self.cache.load_numpy_archive(cache_path)
        if not data:
            return None

        # Verify Integrity
        if str(data['hash']) != current_hash:
            print("[MapIndexer] Hash mismatch (Outdated cache).")
            return None
            
        return data['unique_ids'], data['dense_map']

    def _compute_and_cache(self, 
                           map_array: np.ndarray, 
                           cache_path: Path, 
                           current_hash: str) -> Tuple[np.ndarray, np.ndarray]:
        
        # Heavy computation
        unique_ids, dense_map = np.unique(map_array, return_inverse=True)
        
        # Save via service
        self.cache.save_numpy_archive(
            cache_path, 
            unique_ids=unique_ids, 
            dense_map=dense_map, 
            hash=current_hash
        )
        
        return unique_ids, dense_map