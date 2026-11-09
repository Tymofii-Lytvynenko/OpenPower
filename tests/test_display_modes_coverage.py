from src.client.services.display_modes import (
    DisplayModeOption,
    choose_best_mode,
    clamp_index,
)


def test_clamp_index_handles_an_empty_display_catalog():
    assert clamp_index(4, 0) == 0


def test_choose_best_mode_returns_none_when_no_modes_are_available():
    assert choose_best_mode([], 1920, 1080, 60) is None


def test_choose_best_mode_prefers_nearest_rate_at_matching_resolution():
    modes = [
        DisplayModeOption(1920, 1080, 60, "1920x1080 @ 60Hz", None),
        DisplayModeOption(1920, 1080, 75, "1920x1080 @ 75Hz", None),
        DisplayModeOption(1280, 720, 120, "1280x720 @ 120Hz", None),
    ]

    selected = choose_best_mode(modes, 1920, 1080, 72)

    assert selected == modes[1]
