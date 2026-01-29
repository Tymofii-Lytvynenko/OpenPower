import arcade
from pathlib import Path
from typing import Dict, Optional

class FlagRenderer:
    """
    Service responsible for loading, caching, and providing Flag Textures.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(FlagRenderer, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        
        # FIX: Allow 'None' in the dictionary values to cache missing flags
        self._cache: Dict[str, Optional[arcade.Texture]] = {}
        
        self._missing_key = "MISSING"
        self._initialized = True

    def get_texture(self, tag: str) -> Optional[arcade.Texture]:
        """
        Returns an Arcade Texture for the given country tag.
        Returns a fallback texture or None if not found.
        """
        if tag in self._cache:
            return self._cache[tag]

        # 1. Try to load specific flag
        # Note: In a real app, pass GameConfig to resolve this path dynamically.
        path = Path(f"modules/base/assets/flags/{tag}.png")
        
        if not path.exists():
            # 2. Try Fallback
            path = Path("modules/base/assets/flags/XXX.png")

        if not path.exists():
            # 3. Cache failure (None) so we don't hit the disk every frame
            self._cache[tag] = None 
            return None

        try:
            texture = arcade.load_texture(str(path))
            self._cache[tag] = texture
            return texture
        except Exception as e:
            print(f"[FlagRenderer] Error loading {tag}: {e}")
            self._cache[tag] = None
            return None