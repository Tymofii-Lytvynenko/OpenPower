from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.client.services.audio_service import AudioService


def test_track_identity_is_normalized_and_active_track_is_not_restarted(tmp_path: Path) -> None:
    track = tmp_path / "music.ogg"
    track.write_bytes(b"audio")
    (tmp_path / "assets").mkdir()
    alias = tmp_path / "assets" / ".." / "music.ogg"
    player = object()
    stream = SimpleNamespace(playing=True, volume=0.5)
    service = AudioService()

    with (
        patch("src.client.services.audio_service.arcade.load_sound", return_value=player) as load_sound,
        patch("src.client.services.audio_service.arcade.play_sound", return_value=stream) as play_sound,
    ):
        service.play_music(track)
        service.play_music(alias)

    assert service.current_track_path == str(track.resolve())
    load_sound.assert_called_once_with(track)
    play_sound.assert_called_once_with(player, volume=0.5, loop=True)


def test_replacing_music_stops_old_stream_and_stop_clears_track_state(tmp_path: Path) -> None:
    first = tmp_path / "first.ogg"
    second = tmp_path / "second.ogg"
    first.touch()
    second.touch()
    old_stream = SimpleNamespace(playing=True, volume=0.5)
    new_stream = SimpleNamespace(playing=True, volume=0.5)
    service = AudioService()

    with (
        patch("src.client.services.audio_service.arcade.load_sound", side_effect=[object(), object()]),
        patch("src.client.services.audio_service.arcade.play_sound", side_effect=[old_stream, new_stream]),
        patch("src.client.services.audio_service.arcade.stop_sound") as stop_sound,
    ):
        service.play_music(first)
        service.play_music(second, loop=False)
        assert service.current_track_path == str(second.resolve())
        service.stop_music()

    assert stop_sound.call_count == 2
    assert stop_sound.call_args_list[0].args == (old_stream,)
    assert stop_sound.call_args_list[1].args == (new_stream,)
    assert service.current_stream is None
    assert service.current_player is None
    assert service.current_track_path is None


def test_missing_track_does_not_interrupt_current_music(tmp_path: Path) -> None:
    current = tmp_path / "current.ogg"
    current.touch()
    stream = SimpleNamespace(playing=True, volume=0.5)
    service = AudioService()

    with (
        patch("src.client.services.audio_service.arcade.load_sound", return_value=object()),
        patch("src.client.services.audio_service.arcade.play_sound", return_value=stream),
        patch("src.client.services.audio_service.arcade.stop_sound") as stop_sound,
    ):
        service.play_music(current)
        service.play_music(tmp_path / "missing.ogg")

    assert service.current_stream is stream
    assert service.current_track_path == str(current.resolve())
    stop_sound.assert_not_called()


def test_backend_failure_leaves_no_partial_player_and_is_logged(tmp_path: Path, caplog) -> None:
    track = tmp_path / "music.ogg"
    track.touch()
    service = AudioService()

    with (
        caplog.at_level(logging.WARNING),
        patch("src.client.services.audio_service.arcade.load_sound", return_value=object()),
        patch("src.client.services.audio_service.arcade.play_sound", side_effect=RuntimeError("device unavailable")),
    ):
        service.play_music(track)

    assert service.current_player is None
    assert service.current_stream is None
    assert service.current_track_path is None
    assert "device unavailable" in caplog.text


def test_stop_releases_player_even_when_backend_returns_no_stream() -> None:
    service = AudioService()
    service.current_player = object()
    service.current_track_path = "music.ogg"

    service.stop_music()

    assert service.current_player is None
    assert service.current_track_path is None


def test_volume_is_finite_bounded_and_applied_to_active_stream() -> None:
    stream = SimpleNamespace(playing=True, volume=0.5)
    service = AudioService()
    service.current_stream = stream

    service.set_volume(2.0)
    assert service.volume == 1.0
    assert stream.volume == 1.0
    service.set_volume(float("nan"))
    assert service.volume == 0.0
    assert stream.volume == 0.0
