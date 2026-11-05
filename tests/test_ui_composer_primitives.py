from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

from src.client.ui.core.composer import UIComposer
from src.client.ui.core.primitives import UIPrimitives


def _theme():
    return SimpleNamespace(
        colors=SimpleNamespace(
            bg_input=(0.1, 0.2, 0.3, 1.0),
            bg_window=(0.02, 0.03, 0.04, 1.0),
            accent=(0.4, 0.6, 0.8, 1.0),
            text_main=(0.9, 0.8, 0.7, 1.0),
        )
    )


def test_composer_header_meter_and_currency_row_delegate_to_primitives(monkeypatch):
    theme = _theme()
    calls = []

    def record(name, *args, **kwargs):
        calls.append((name, args, kwargs))

    monkeypatch.setattr(
        UIPrimitives,
        "header",
        lambda label, **kwargs: record("header", label, **kwargs),
    )
    monkeypatch.setattr(
        UIPrimitives,
        "meter",
        lambda label, value, color, **kwargs: record(
            "meter", label, value, color, **kwargs
        ),
    )
    monkeypatch.setattr(
        UIPrimitives,
        "currency_row",
        lambda label, value, color=None, **kwargs: record(
            "currency_row", label, value, color, **kwargs
        ),
    )
    composer = UIComposer(theme)

    composer.draw_section_header("SUMMARY", show_more_btn=False)
    composer.draw_meter("Health", 75.0, (0.2, 0.7, 0.3), show_percentage=False)
    composer.draw_currency_row("Balance", 1200.0, color_val=(0.4, 0.5, 0.6, 1.0))

    assert calls == [
        ("header", ("SUMMARY",), {"theme": theme}),
        ("meter", ("Health", 75.0, (0.2, 0.7, 0.3)), {"theme": theme}),
        (
            "currency_row",
            ("Balance", 1200.0, (0.4, 0.5, 0.6, 1.0)),
            {"theme": theme},
        ),
    ]


def test_shared_primitives_use_the_supplied_theme_and_accept_rgb_meter_colors():
    native = MagicMock()
    native.get_cursor_screen_pos.return_value = SimpleNamespace(x=10.0, y=20.0)
    native.get_content_region_avail.return_value = SimpleNamespace(x=240.0)
    native.calc_text_size.side_effect = lambda text: SimpleNamespace(
        x=len(text) * 6.0,
        y=12.0,
    )
    native.get_cursor_pos_x.return_value = 0.0
    native.get_color_u32.side_effect = lambda color: color
    native.is_item_hovered.return_value = False
    theme = _theme()

    with patch("src.client.ui.core.primitives.imgui", native):
        UIPrimitives.header("SUMMARY", theme=theme)
        UIPrimitives.meter("Health", 75.0, (0.2, 0.7, 0.3), theme=theme)
        UIPrimitives.currency_row("Balance", 1200.0, theme=theme)

    native.get_color_u32.assert_any_call(theme.colors.bg_input)
    native.get_color_u32.assert_any_call((0.2, 0.7, 0.3, 1.0))
    native.text_colored.assert_any_call(theme.colors.text_main, "SUMMARY")
    native.text_colored.assert_any_call(theme.colors.text_main, "$ 1 200")


def test_currency_row_fits_long_label_and_keeps_its_full_text_in_tooltip():
    native = MagicMock()
    native.get_cursor_pos_x.return_value = 0.0
    native.get_content_region_avail.return_value = SimpleNamespace(x=120.0)
    native.calc_text_size.side_effect = lambda text: SimpleNamespace(x=len(text) * 6.0)
    native.is_item_hovered.return_value = True
    label = "Long budget category label"

    with patch("src.client.ui.core.primitives.imgui", native):
        UIPrimitives.currency_row(label, 1200.0, theme=_theme())

    assert native.text.call_args.args[0] != label
    native.set_tooltip.assert_any_call(label)
    assert 0.0 <= native.same_line.call_args.args[0] <= 120.0
    native.text_colored.assert_any_call(_theme().colors.text_main, "$ 1 200")


def test_composer_menu_button_delegates_while_preserving_disabled_tooltip_and_spacing(
    monkeypatch,
):
    theme = _theme()
    calls = []
    native = SimpleNamespace(
        HoveredFlags_=SimpleNamespace(allow_when_disabled=1),
        begin_disabled=lambda disabled: calls.append(("begin_disabled", disabled)),
        end_disabled=lambda: calls.append(("end_disabled",)),
        is_item_hovered=lambda flags: calls.append(("is_item_hovered", flags)) or True,
        set_tooltip=lambda text: calls.append(("tooltip", text)),
    )
    monkeypatch.setattr("src.client.ui.core.composer.imgui", native)
    monkeypatch.setattr(
        UIPrimitives,
        "button",
        lambda label, **kwargs: calls.append(("button", label, kwargs)) or False,
    )
    composer = UIComposer(theme)
    composer.dummy = lambda size: calls.append(("dummy", size))

    clicked = composer.draw_menu_button(
        "Continue",
        test_id="main.continue",
        gml_id="Main/frmInner/btnContinue",
        enabled=False,
        tooltip="Unavailable until a save is selected.",
    )

    assert clicked is False
    assert calls == [
        ("begin_disabled", True),
        (
            "button",
            "Continue",
            {
                "test_id": "main.continue",
                "size": (-1, 40),
                "enabled": False,
                "gml_id": "Main/frmInner/btnContinue",
                "gml_enabled": False,
            },
        ),
        ("end_disabled",),
        ("is_item_hovered", 1),
        ("tooltip", "Unavailable until a save is selected."),
        ("dummy", (0, 5)),
    ]


def test_shared_button_supports_missing_test_id_and_forwards_gml_enabled():
    native = MagicMock()
    native.button.side_effect = [True, False]
    record = MagicMock()

    with (
        patch("src.client.ui.core.primitives.imgui", native),
        patch("src.client.ui.core.primitives.record_last_item", record),
    ):
        clicked_without_test_id = UIPrimitives.button(
            "Continue",
            size=(420, 40),
            enabled=False,
            gml_id="Main/frmInner/btnContinue",
            gml_enabled=False,
        )
        clicked_with_test_id = UIPrimitives.button(
            "Exit",
            test_id="main.exit",
            size=(420, 40),
            gml_id="Main/frmInner/btnExit",
            gml_enabled=True,
        )

    assert clicked_without_test_id is True
    assert clicked_with_test_id is False
    assert native.button.call_args_list == [
        call(
            "Continue",
            (420, 40),
            gml_id="Main/frmInner/btnContinue",
            gml_enabled=False,
        ),
        call(
            "Exit###main.exit",
            (420, 40),
            gml_id="Main/frmInner/btnExit",
            gml_enabled=True,
        ),
    ]
    record.assert_called_once_with(
        "main.exit", "Exit", "button", enabled=True
    )


def test_composer_progress_bar_delegates_with_its_theme(monkeypatch):
    theme = _theme()
    calls = []
    monkeypatch.setattr(
        UIPrimitives,
        "progress_bar",
        lambda fraction, text, width, height, **kwargs: calls.append(
            (fraction, text, width, height, kwargs)
        ),
    )
    composer = UIComposer(theme)

    composer.draw_progress_bar(0.45, "Loading", 320.0, 18.0)

    assert calls == [(0.45, "Loading", 320.0, 18.0, {"theme": theme})]


def test_shared_progress_bar_draws_clamped_fill_and_centered_text():
    draw_list = MagicMock()
    native = MagicMock()
    native.get_cursor_screen_pos.return_value = SimpleNamespace(x=10.0, y=20.0)
    native.get_content_region_avail.return_value = SimpleNamespace(x=180.0)
    native.get_window_draw_list.return_value = draw_list
    native.calc_text_size.return_value = SimpleNamespace(x=40.0, y=10.0)
    theme = _theme()

    with patch("src.client.ui.core.primitives.imgui", native):
        UIPrimitives.progress_bar(1.5, "Loading", 100.0, 20.0, theme=theme)

    bg_color = native.get_color_u32.return_value
    accent_color = native.get_color_u32.return_value
    assert native.get_color_u32.call_args_list == [
        call(theme.colors.bg_window),
        call(theme.colors.accent),
        call(theme.colors.accent),
    ]
    assert draw_list.add_rect_filled.call_args_list == [
        call(SimpleNamespace(x=10.0, y=20.0), (110.0, 40.0), bg_color, 0.0),
        call(SimpleNamespace(x=10.0, y=20.0), (110.0, 40.0), accent_color, 0.0),
    ]
    draw_list.add_rect.assert_called_once_with(
        SimpleNamespace(x=10.0, y=20.0), (110.0, 40.0), accent_color, 0.0
    )
    draw_list.add_text.assert_has_calls(
        [
            call((41.0, 26.0), 0xFF000000, "Loading"),
            call((40.0, 25.0), 0xFFFFFFFF, "Loading"),
        ]
    )
    native.dummy.assert_called_once_with((100.0, 25.0))
