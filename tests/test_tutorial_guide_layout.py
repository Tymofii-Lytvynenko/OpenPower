from src.client.ui.components.tutorial_guide_content import (
    TutorialGuideContent,
    resolve_tutorial_guide_layout,
)


def test_tutorial_guide_height_tracks_wrapped_body_without_status() -> None:
    short = resolve_tutorial_guide_layout(body_height=32.0)
    long = resolve_tutorial_guide_layout(body_height=64.0)

    assert short.status_y is None
    assert short.buttons_y == 106.0
    assert short.window_height == 156.0
    assert long.window_height - short.window_height == 32.0


def test_tutorial_guide_reserves_status_before_navigation_controls() -> None:
    layout = resolve_tutorial_guide_layout(body_height=48.0, status_height=16.0)

    assert layout.status_y == 116.0
    assert layout.buttons_y == 144.0
    assert not layout.stack_buttons
    assert layout.window_height == 194.0


def test_narrow_tutorial_guides_stack_navigation_controls() -> None:
    layout = resolve_tutorial_guide_layout(
        body_height=80.0,
        status_height=32.0,
        window_width=277.0,
    )

    assert layout.stack_buttons
    assert layout.buttons_y == 192.0
    assert layout.window_height == 310.0


def test_tutorial_guides_expose_the_current_source_control_target() -> None:
    content = TutorialGuideContent()

    assert content.arrow_target is None
    content.open("interface")
    assert content.arrow_target == "world.viewport"

    content.open("military")
    assert content.arrow_target == "hud.panel.mil"

    content.close()
    assert content.arrow_target is None
