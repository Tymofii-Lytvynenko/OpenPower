import hashlib
import threading
import os
import shutil
import numpy as np
from pathlib import Path
from typing import Optional, Any, Dict

class CacheService:
    """
    Centralized service for managing disk caching of generated assets.
    Handles path resolution, hashing, validation, and threaded I/O.
    """
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.cache_dir = self.project_root / ".cache"
        self._ensure_cache_dir()

    def _ensure_cache_dir(self):
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            print(f"[CacheService] Critical Error: Could not create cache dir: {e}")

    # --- Path Management ---

    def get_cache_path(self, source_path: Path, suffix: str) -> Path:
        """
        Generates a consistent, unique cache path using a hash of the full source path.
        Prevents collisions when multiple files have the same name (e.g. 'terrain.png').
        """
        # Create a hash of the absolute path to ensure uniqueness
        path_hash = hashlib.md5(str(source_path.resolve()).encode('utf-8')).hexdigest()[:12]
        
        # Keep the stem for readability, but append hash
        filename = f"{source_path.stem}_{path_hash}{suffix}"
        return self.cache_dir / filename

    def get_asset_path(self, module: str, *parts: str) -> Path:
        """Helper to resolve paths to raw assets (e.g. modules/base/assets/...)."""
        return self.project_root / "modules" / module / "assets" / Path(*parts)

    # --- Validation ---

    def compute_file_hash(self, file_path: Path) -> str:
        """Computes SHA-256 hash of a file for integrity checking."""
        sha256 = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096 * 1024), b""):
                    sha256.update(chunk)
            return sha256.hexdigest()
        except FileNotFoundError:
            return "FILE_NOT_FOUND"

    def is_cache_valid(self, source_path: Path, cache_path: Path) -> bool:
        """Fast check based on file modification timestamps."""
        if not cache_path.exists():
            print(f"[CacheService] MISS: Cache file not found: {cache_path.name}")
            return False
            
        try:
            src_mtime = source_path.stat().st_mtime
            cache_mtime = cache_path.stat().st_mtime
            
            # Debug prints to solve the mystery
            if cache_mtime <= src_mtime:
                print(f"[CacheService] STALE: {cache_path.name}")
                print(f"    - Source: {src_mtime} | Cache: {cache_mtime}")
                print(f"    - Diff: {cache_mtime - src_mtime}s")
                return False
                
            return True
            
        except OSError as e:
            print(f"[CacheService] ERROR: accessing file stats: {e}")
            return False

    # --- I/O Operations ---

    def load_numpy_array(self, path: Path, mmap_mode: str = None) -> Optional[np.ndarray]:
        """Loads a standard .npy file."""
        if not path.exists():
            return None
        try:
            return np.load(path, mmap_mode=mmap_mode)
        except Exception as e:
            # If load fails (corrupt file), delete it so it can be regenerated
            print(f"[CacheService] Load failed (corrupt?): {path.name}. Deleting.")
            try:
                path.unlink()
            except OSError:
                pass
            return None

    def save_numpy_array(self, path: Path, data: np.ndarray, in_background: bool = True):
        """Saves a .npy file using atomic write pattern."""
        if in_background:
            # non-daemon thread ensures data is saved even if app initiates exit
            threading.Thread(target=self._save_numpy_worker, args=(path, data), daemon=False).start()
        else:
            self._save_numpy_worker(path, data)

    def _save_numpy_worker(self, path: Path, data: np.ndarray):
        """
        Atomic Write: Writes to .tmp file first, then renames.
        Prevents partial/corrupt files if the process crashes mid-write.
        """
        # FIX: We must ensure the temp path ends in .npy, otherwise 
        # np.save will append it automatically, creating a filename mismatch.
        tmp_path = path.parent / f"{path.name}.tmp.npy"
        
        try:
            # np.save sees .npy at the end and writes exactly to tmp_path
            np.save(tmp_path, data)
            
            # Atomic replace (overwrite if exists)
            os.replace(tmp_path, path)
            # print(f"[CacheService] Saved: {path.name}") 
            
        except Exception as e:
            print(f"[CacheService] Save failed for {path.name}: {e}")
            # Clean up
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

    def load_numpy_archive(self, path: Path) -> Optional[Dict[str, Any]]:
        """Loads a compressed .npz archive."""
        if not path.exists():
            return None
        try:
            return np.load(path)
        except Exception as e:
            print(f"[CacheService] Archive load failed {path.name}: {e}")
            return None

    def save_numpy_archive(self, path: Path, **kwargs):
        """Saves compressed .npz archive."""
        try:
            np.savez_compressed(path, **kwargs)
            # print(f"[CacheService] Archived: {path.name}")
        except Exception as e:
            print(f"[CacheService] Archive save failed {path.name}: {e}")