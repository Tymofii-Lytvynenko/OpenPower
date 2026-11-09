from types import SimpleNamespace

from src.client.ui.layouts import main_pillar_positions


def _use_viewport(monkeypatch, width: float, fallback_width: float = 0.0) -> None:
    monkeypatch.setattr(
        main_pillar_positions,
        "imgui",
        SimpleNamespace(
            get_io=lambda: SimpleNamespace(display_size=SimpleNamespace(x=width)),
            get_main_viewport=lambda: SimpleNamespace(size=SimpleNamespace(x=fallback_width)),
        ),
    )


def test_main_pillar_position_uses_compact_layout_below_wide_threshold(monkeypatch):
    _use_viewport(monkeypatch, main_pillar_positions.WIDE_LAYOUT_MIN_WIDTH - 1)

    assert main_pillar_positions.main_pillar_position("treaties") == (535.0, 42.0)


def test_main_pillar_position_uses_wide_layout_at_threshold(monkeypatch):
    _use_viewport(monkeypatch, main_pillar_positions.WIDE_LAYOUT_MIN_WIDTH)

    assert main_pillar_positions.main_pillar_position("military") == (700.0, 164.0)


def test_main_pillar_position_falls_back_to_main_viewport_width(monkeypatch):
    _use_viewport(monkeypatch, 0.0, 1600.0)

    assert main_pillar_positions.main_pillar_position("economy") == (0.0, 130.0)
