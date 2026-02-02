import arcade
from pathlib import Path
from typing import Optional

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
        if not file_path.exists():
            print(f"[Audio] Error: File not found: {file_path}")
            return

        # Don't restart if it's the same track
        if self.current_track_path == str(file_path) and self.is_playing():
            return

        # Stop previous track
        self.stop_music()

        try:
            # Load and play
            print(f"[Audio] Playing: {file_path.name}")
            self.current_player = arcade.load_sound(file_path)
            
            # play_sound returns a player object we must keep a reference to
            self.current_stream = arcade.play_sound(
                self.current_player, 
                volume=self.volume, 
                loop=loop
            )
            self.current_track_path = str(file_path)
            
        except Exception as e:
            print(f"[Audio] Playback Failed: {e}")
            self.current_track_path = None

    def stop_music(self):
        """Stops currently playing music."""
        if self.current_stream:
            try:
                arcade.stop_sound(self.current_stream)
            except Exception:
                pass # Stream might already be dead
            self.current_stream = None
            self.current_player = None # Release resource

    def set_volume(self, volume: float):
        """Sets volume (0.0 to 1.0)."""
        self.volume = max(0.0, min(1.0, volume))
        if self.current_stream:
            self.current_stream.volume = self.volume

    def is_playing(self) -> bool:
        return self.current_stream is not None and self.current_stream.playing