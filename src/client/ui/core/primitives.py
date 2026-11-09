import contextlib
from dataclasses import dataclass

from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.testability import record_last_item
from src.client.ui.core.theme import GAMETHEME, UITheme


@dataclass(frozen=True, slots=True)
class UnitCompositionRow:
    """Small value object for compact unit composition overlays."""

    label: str
    value: int
    color: tuple


class UIPrimitives:
    """Stateless functional UI widgets shared by panels and HUD components."""

    @staticmethod
    def fit_text(text: str, width: float) -> str:
        if imgui.calc_text_size(text).x <= width:
            return text
        if imgui.calc_text_size("...").x > width:
            return ""
        value = text
        while value and imgui.calc_text_size(value + "...").x > width:
            value = value[:-1]
        return value + "..."

    @staticmethod
    def button(
        label: str,
        *,
        test_id: str | None = None,
        size: tuple[float, float] | None = None,
        enabled: bool = True,
        gml_id: str | None = None,
        gml_enabled: bool | None = None,
    ) -> bool:
        """Draw a button with optional stable identity and test telemetry."""
        stable_label = f"{label}###{test_id}" if test_id is not None else label
        clicked = (
            imgui.button(stable_label, gml_id=gml_id, gml_enabled=gml_enabled)
            if size is None
            else imgui.button(
                stable_label, size, gml_id=gml_id, gml_enabled=gml_enabled
            )
        )
        if test_id is not None:
            record_last_item(test_id, label, "button", enabled=enabled)
        return clicked

    @staticmethod
    def slider_float(
        label: str,
        value: float,
        minimum: float,
        maximum: float,
        format_string: str,
        *,
        test_id: str,
        enabled: bool = True,
        gml_id: str | None = None,
    ) -> tuple[bool, float]:
        """Draw a float slider with a stable ImGui ID and test telemetry."""
        changed, updated_value = imgui.slider_float(
            f"{label}###{test_id}", value, minimum, maximum, format_string,
            gml_id=gml_id,
        )
        record_last_item(test_id, label, "slider_float", enabled=enabled)
        return changed, updated_value

    @staticmethod
    def invisible_button(
        size: tuple[float, float],
        *,
        test_id: str,
        label: str | None = None,
        enabled: bool = True,
        gml_id: str | None = None,
    ) -> bool:
        """Draw an invisible hit target that remains addressable in test reports."""
        semantic_label = label or test_id
        clicked = imgui.invisible_button(
            f"{semantic_label}###{test_id}", size, gml_id=gml_id
        )
        record_last_item(test_id, semantic_label, "invisible_button", enabled=enabled)
        return clicked

    @staticmethod
    def header(
        label: str,
        show_bg: bool = True,
        theme: UITheme | None = None,
    ):
        """Draws a styled section header."""
        theme = theme or GAMETHEME
        if show_bg:
            p = imgui.get_cursor_screen_pos()
            w = imgui.get_content_region_avail().x
            h = 24.0
            draw_list = imgui.get_window_draw_list()

            draw_list.add_rect_filled(
                p,
                (p.x + w, p.y + h),
                imgui.get_color_u32(theme.colors.bg_input),
                4.0,
            )

            text_size = imgui.calc_text_size(label)
            text_y = p.y + (h - text_size.y) / 2

            imgui.set_cursor_screen_pos((p.x + 8, text_y))
            imgui.text_colored(theme.colors.text_main, label)

            imgui.set_cursor_screen_pos((p.x, p.y + h + 5))
        else:
            imgui.text_colored(theme.colors.text_main, label)
            imgui.separator()

    @staticmethod
    def _draw_horizontal_bar(
        draw_list,
        origin,
        width: float,
        height: float,
        fraction: float,
        background_color: tuple,
        fill_color: tuple,
        rounding: float = 0.0,
        border_color: tuple | None = None,
    ) -> None:
        end = (origin.x + width, origin.y + height)
        imgui_background = imgui.get_color_u32(background_color)
        draw_list.add_rect_filled(origin, end, imgui_background, rounding)

        if fraction > 0.0:
            fill_end = (origin.x + width * fraction, origin.y + height)
            imgui_fill = imgui.get_color_u32(fill_color)
            draw_list.add_rect_filled(origin, fill_end, imgui_fill, rounding)

        if border_color is not None:
            draw_list.add_rect(
                origin,
                end,
                imgui.get_color_u32(border_color),
                rounding,
            )

    @staticmethod
    def meter(
        label: str,
        value_pct: float,
        color: tuple,
        height: float = 12.0,
        theme: UITheme | None = None,
    ):
        """Draws a custom progress bar/meter."""
        theme = theme or GAMETHEME
        if label:
            imgui.text(label)

        w = imgui.get_content_region_avail().x
        p = imgui.get_cursor_screen_pos()
        draw_list = imgui.get_window_draw_list()
        fraction = max(0.0, min(value_pct, 100.0)) / 100.0
        fill_color = color if len(color) == 4 else (*color, 1.0)
        UIPrimitives._draw_horizontal_bar(
            draw_list,
            p,
            w,
            height,
            fraction if fraction > 0.01 else 0.0,
            theme.colors.bg_input,
            fill_color,
            rounding=height / 2,
        )

        imgui.dummy((0, height + 5))

    @staticmethod
    def meter_row(
        label: str,
        value_pct: float,
        color: tuple,
        value_text: str | None = None,
        label_width: float = 130.0,
        height: float = 12.0,
    ):
        """Draws a compact label/bar/value row for dense info panels."""
        value_text = value_text if value_text is not None else f"{value_pct:.1f} %"
        origin_x = imgui.get_cursor_pos_x()
        available = imgui.get_content_region_avail().x
        label_width = min(label_width, max(0.0, available * 0.5))
        imgui.text_disabled(UIPrimitives.fit_text(label, label_width - 4.0))
        imgui.same_line(origin_x + label_width)
        value_text = UIPrimitives.fit_text(value_text, max(0.0, available - label_width - 32.0))
        value_width = imgui.calc_text_size(value_text).x
        available_width = imgui.get_content_region_avail().x
        bar_width = max(24.0, available_width - value_width - 8.0)

        p = imgui.get_cursor_screen_pos()
        draw_list = imgui.get_window_draw_list()
        fraction = max(0.0, min(value_pct, 100.0)) / 100.0
        UIPrimitives._draw_horizontal_bar(
            draw_list,
            p,
            bar_width,
            height,
            fraction if fraction > 0.01 else 0.0,
            GAMETHEME.colors.bg_input,
            color,
            rounding=height / 2,
        )

        imgui.dummy((bar_width, height))
        imgui.same_line()
        imgui.text_colored(color, value_text)

    @staticmethod
    def progress_bar(
        fraction: float,
        text: str = "",
        width: float = -1.0,
        height: float = 20.0,
        theme: UITheme | None = None,
    ) -> None:
        """Draw a themed progress bar with centered status text."""
        theme = theme or GAMETHEME
        origin = imgui.get_cursor_screen_pos()
        actual_width = (
            width if width > 0.0 else imgui.get_content_region_avail().x
        )
        draw_list = imgui.get_window_draw_list()
        fraction = max(0.0, min(fraction, 1.0))
        UIPrimitives._draw_horizontal_bar(
            draw_list,
            origin,
            actual_width,
            height,
            fraction,
            theme.colors.bg_window,
            theme.colors.accent,
            border_color=theme.colors.accent,
        )

        if text:
            text_size = imgui.calc_text_size(text)
            text_x = origin.x + (actual_width - text_size.x) / 2
            text_y = origin.y + (height - text_size.y) / 2
            draw_list.add_text((text_x + 1, text_y + 1), 0xFF000000, text)
            draw_list.add_text((text_x, text_y), 0xFFFFFFFF, text)

        imgui.dummy((actual_width, height + 5))

    @staticmethod
    def value_row(
        label: str,
        value: str,
        color: tuple | None = None,
        label_width: float = 150.0,
        dim_label: bool = True,
    ):
        """Draws a compact left-label, right-value row."""
        origin_x = imgui.get_cursor_pos_x()
        available = imgui.get_content_region_avail().x
        value_width = min(imgui.calc_text_size(value).x, available * 0.6)
        label_width = min(label_width, max(0.0, available - value_width - 6.0))
        display_label = UIPrimitives.fit_text(label, label_width)
        if dim_label:
            imgui.text_disabled(display_label)
        else:
            imgui.text(display_label)
        if display_label != label and imgui.is_item_hovered():
            imgui.set_tooltip(label)
        # same_line offsets are window-local, including inside later table columns.
        imgui.same_line(origin_x + label_width)
        UIPrimitives.right_align_text(value, color or GAMETHEME.colors.text_main)

    @staticmethod
    def currency_row(
        label: str,
        value: float,
        color: tuple | None = None,
        theme: UITheme | None = None,
    ):
        """Aligned row: Label ...... $Value."""
        theme = theme or GAMETHEME
        val_str = f"$ {value:,.0f}".replace(",", " ")
        col = color if color else theme.colors.text_main
        UIPrimitives.value_row(label, val_str, color=col, dim_label=False)

    @staticmethod
    def right_align_text(text: str, color: tuple | None = None):
        avail_w = imgui.get_content_region_avail().x
        display = UIPrimitives.fit_text(text, max(0.0, avail_w))
        width = imgui.calc_text_size(display).x
        imgui.set_cursor_pos_x(imgui.get_cursor_pos_x() + max(0.0, avail_w - width))

        if color:
            imgui.text_colored(color, display)
        else:
            imgui.text(display)
        if display != text and imgui.is_item_hovered():
            imgui.set_tooltip(text)


    @staticmethod
    def icon_toggle(
        icon: str,
        color: tuple,
        is_active: bool,
        width: float = 50,
        height: float = 50,
        show_inactive_indicator: bool = False,
        test_id: str | None = None,
        accessible_label: str | None = None,
        gml_id: str | None = None,
        theme: UITheme | None = None,
    ) -> bool:
        """Draws a square icon toggle with an optional bottom indicator."""
        theme = theme or GAMETHEME
        bg = theme.colors.interaction_active if is_active else theme.colors.bg_input
        imgui.push_style_color(imgui.Col_.button, bg)
        imgui.push_style_var(imgui.StyleVar_.frame_rounding, 8.0)

        # Demographics and Migration share an icon; a domain ID prevents both
        # toggles from aliasing the same native ImGui item in the HUD window.
        label = f"{icon}###{test_id}" if test_id is not None else icon
        clicked = imgui.button(label, (width, height), gml_id=gml_id)
        if test_id is not None:
            record_last_item(test_id, accessible_label or icon, "button")

        imgui.pop_style_var()
        imgui.pop_style_color()

        if is_active or show_inactive_indicator:
            p_min = imgui.get_item_rect_min()
            p_max = imgui.get_item_rect_max()
            draw_list = imgui.get_window_draw_list()
            indicator_color = color if is_active else theme.colors.text_dim
            ind_col = imgui.get_color_u32((indicator_color[0], indicator_color[1], indicator_color[2], 1.0))

            draw_list.add_rect_filled(
                (p_min.x + 5, p_max.y - 6),
                (p_max.x - 5, p_max.y - 2),
                ind_col,
                2.0,
            )

        return clicked

    @staticmethod
    def unit_composition_plate(
        draw_list: imgui.ImDrawList,
        x: float,
        y: float,
        rows: tuple[UnitCompositionRow, ...],
        max_value: int | None = None,
    ) -> None:
        """Draws the compact selected-unit troop composition plate."""
        plate_w = 118.0
        plate_h = 58.0
        row_h = 11.0
        rows_top = y + 7.0
        label_x = x + 7.0
        bar_x = label_x + 11.0
        bar_w = 31.0
        value_x = bar_x + bar_w + 7.0

        draw_list.add_rect_filled(
            (x, y),
            (x + plate_w, y + plate_h),
            imgui.get_color_u32((0.03, 0.04, 0.045, 0.88)),
        )
        draw_list.add_rect(
            (x, y),
            (x + plate_w, y + plate_h),
            imgui.get_color_u32((0.50, 0.62, 0.72, 0.75)),
        )

        if max_value is None:
            max_value = max((max(0, int(row.value)) for row in rows), default=1)
        max_value = max(1, int(max_value))

        for index, row in enumerate(rows):
            row_y = rows_top + index * row_h
            value = max(0, int(row.value))
            value_text = f"{value:,}".replace(",", " ")

            draw_list.add_text(
                (label_x, row_y - 1.0),
                imgui.get_color_u32(GAMETHEME.colors.text_main),
                row.label,
            )
            draw_list.add_rect_filled(
                (bar_x, row_y + 2.0),
                (bar_x + bar_w, row_y + 6.0),
                imgui.get_color_u32((0.05, 0.06, 0.065, 1.0)),
            )

            fill_w = bar_w * min(1.0, value / max_value)
            if fill_w > 0:
                draw_list.add_rect_filled(
                    (bar_x, row_y + 2.0),
                    (bar_x + max(2.0, fill_w), row_y + 6.0),
                    imgui.get_color_u32(row.color),
                )

            draw_list.add_rect(
                (bar_x, row_y + 2.0),
                (bar_x + bar_w, row_y + 6.0),
                imgui.get_color_u32((0.42, 0.45, 0.44, 0.95)),
            )
            draw_list.add_text(
                (value_x, row_y - 1.0),
                imgui.get_color_u32(GAMETHEME.colors.text_main),
                value_text,
            )

    @staticmethod
    @contextlib.contextmanager
    def dark_child_box(id: str, width: float = -1.0, height: float = 0.0, border: bool = True):
        """Balance child styles and expose whether ImGui wants its contents drawn."""
        imgui.push_style_color(imgui.Col_.child_bg, GAMETHEME.colors.panel_bg_dark)
        imgui.push_style_var(imgui.StyleVar_.child_rounding, 0.0)
        try:
            visible = imgui.begin_child(
                id, (width, height), border, imgui.WindowFlags_.none
            )
            yield visible
        finally:
            imgui.end_child()
            imgui.pop_style_var()
            imgui.pop_style_color()

    @staticmethod
    def combo_row(label: str, selected_idx: int, items: list[str], label_width: float = 80.0) -> int:
        origin_x = imgui.get_cursor_pos_x()
        imgui.align_text_to_frame_padding()
        imgui.text_disabled(label)
        imgui.same_line(origin_x + label_width)
        imgui.set_next_item_width(-1)
        _, new_idx = imgui.combo(f"##{label}", selected_idx, items)
        return new_idx
