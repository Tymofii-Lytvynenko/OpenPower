from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.client.services.audio_service import AudioService
from src.client.services.navigation_service import NavigationService


def test_audio_service_reuses_active_track_and_clamps_volume(tmp_path: Path) -> None:
    track = tmp_path / "music.ogg"
    track.write_bytes(b"audio")
    player = object()
    stream = SimpleNamespace(playing=True, volume=0.5)
    service = AudioService()

    with (
        patch("src.client.services.audio_service.arcade.load_sound", return_value=player) as load_sound,
        patch("src.client.services.audio_service.arcade.play_sound", return_value=stream) as play_sound,
        patch("src.client.services.audio_service.arcade.stop_sound") as stop_sound,
    ):
        service.play_music(track)
        service.play_music(track)
        assert service.is_playing()
        service.set_volume(2.0)
        assert stream.volume == 1.0
        service.stop_music()

    load_sound.assert_called_once_with(track)
    play_sound.assert_called_once_with(player, volume=0.5, loop=True)
    stop_sound.assert_called_once_with(stream)
    assert not service.is_playing()


def test_audio_service_ignores_missing_tracks_without_crashing(tmp_path: Path) -> None:
    service = AudioService()
    missing = tmp_path / "missing.ogg"
    with patch("src.client.services.audio_service.arcade.load_sound") as load_sound:
        service.play_music(missing)
    load_sound.assert_not_called()


def test_navigation_service_builds_target_view_and_delegates_transition() -> None:
    window = Mock()
    service = NavigationService(window)
    session = object()
    config = object()

    with patch("src.client.views.new_game_view.NewGameView") as new_game_view:
        service.show_new_game_screen(session, config)

    new_game_view.assert_called_once_with(session, config)
    window.show_view.assert_called_once_with(new_game_view.return_value)
