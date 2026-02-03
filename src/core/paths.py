import sys
from pathlib import Path

class ProjectPaths:
    """
    Static utility to resolve project paths reliably.
    Works for both development (source) and frozen (PyInstaller) environments.
    """
    _ROOT_CACHE: Path | None = None

    @classmethod
    def root(cls) -> Path:
        """Returns the absolute path to the project root (where main.py resides)."""
        if cls._ROOT_CACHE:
            return cls._ROOT_CACHE

        # 1. Handle Frozen (PyInstaller/Nuitka)
        if getattr(sys, 'frozen', False):
            cls._ROOT_CACHE = Path(sys.executable).parent
            return cls._ROOT_CACHE

        # 2. Handle Dev: Traverse up until we find 'main.py' or 'modules' folder
        # Start from this file: src/core/paths.py
        current = Path(__file__).resolve()
        for parent in [current] + list(current.parents):
            if (parent / "main.py").exists() and (parent / "modules").exists():
                cls._ROOT_CACHE = parent
                return cls._ROOT_CACHE

        # Fallback: Assume we are in src/core/paths.py -> go up 2 levels
        cls._ROOT_CACHE = current.parents[2]
        return cls._ROOT_CACHE

    @classmethod
    def assets(cls, module: str = "base") -> Path:
        """Returns path to: modules/{module}/assets"""
        return cls.root() / "modules" / module / "assets"

    @classmethod
    def data(cls, module: str = "base") -> Path:
        """Returns path to: modules/{module}/data"""
        return cls.root() / "modules" / module / "data"

    @classmethod
    def user_data(cls) -> Path:
        """Returns path to: user_data/"""
        return cls.root() / "user_data"

    @classmethod
    def cache(cls) -> Path:
        """Returns path to: .cache/"""
        return cls.root() / ".cache"