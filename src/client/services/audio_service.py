import logging
import math
from pathlib import Path
from typing import Optional

import arcade


logger = logging.getLogger(__name__)


class AudioService:
    """
    Manages global audio playback (Music & SFX).
    Persists across Views via the MainWindow.
    """
    def __init__(self):
        self.current_player: Optional[arcade.Sound] = None
        self.current_stream = None # The active streaming object
        self.current_track_path: Optional[str] = None
        self.volume = 0.5

    def play_music(self, file_path: Path, loop: bool = True):
        """
        Plays a music track. If the same track is already playing, it does nothing.
        """
        path = Path(file_path)
        if not path.exists():
            logger.warning("Music track does not exist: %s", path)
            return

        normalized_path = path.resolve()

        # Don't restart if it's the same track
        if self.current_track_path == str(normalized_path) and self.is_playing():
            return

        # Stop previous track
        self.stop_music()

        try:
            # Load and play
            player = arcade.load_sound(path)
            
            # play_sound returns a player object we must keep a reference to
            stream = arcade.play_sound(
                player,
                volume=self.volume, 
                loop=loop
            )
            self.current_player = player
            self.current_stream = stream
            self.current_track_path = str(normalized_path)
            
        except Exception as e:
            logger.warning("Music playback failed for %s: %s", path, e)
            self.current_player = None
            self.current_stream = None
            self.current_track_path = None

    def stop_music(self):
        """Stops currently playing music."""
        stream = self.current_stream
        if stream is not None:
            try:
                arcade.stop_sound(stream)
            except Exception as exc:
                logger.debug("Audio stream had already stopped: %s", exc)
        self.current_stream = None
        self.current_player = None
        self.current_track_path = None

    def set_volume(self, volume: float):
        """Sets volume (0.0 to 1.0)."""
        volume = float(volume)
        self.volume = max(0.0, min(1.0, volume)) if math.isfinite(volume) else 0.0
        if self.current_stream:
            self.current_stream.volume = self.volume

    def is_playing(self) -> bool:
        return self.current_stream is not None and bool(
            getattr(self.current_stream, "playing", False)
        )
