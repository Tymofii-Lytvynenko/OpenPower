from collections.abc import Callable
from dataclasses import dataclass

from imgui_bundle import imgui
from src.client.ui.core.theme import GAMETHEME


@dataclass(frozen=True, slots=True)
class UnitCompositionRow:
    """Small value object for compact unit composition overlays."""

    label: str
    value: int
    color: tuple


class UIPrimitives:
    """Stateless functional UI widgets shared by panels and HUD components."""

    @staticmethod
    def header(label: str, show_bg: bool = True):
        """Draws a styled section header."""
        if show_bg:
            p = imgui.get_cursor_screen_pos()
            w = imgui.get_content_region_avail().x
            h = 24.0
            draw_list = imgui.get_window_draw_list()

            draw_list.add_rect_filled(
                p,
                (p.x + w, p.y + h),
                imgui.get_color_u32(GAMETHEME.colors.bg_input),
                4.0,
            )

            text_size = imgui.calc_text_size(label)
            text_y = p.y + (h - text_size.y) / 2

            imgui.set_cursor_screen_pos((p.x + 8, text_y))
            imgui.text_colored(GAMETHEME.colors.text_main, label)

            imgui.set_cursor_screen_pos((p.x, p.y + h + 5))
        else:
            imgui.text_colored(GAMETHEME.colors.text_main, label)
            imgui.separator()

    @staticmethod
    def meter(label: str, value_pct: float, color: tuple, height: float = 12.0):
        """Draws a custom progress bar/meter."""
        if label:
            imgui.text(label)

        w = imgui.get_content_region_avail().x
        p = imgui.get_cursor_screen_pos()
        draw_list = imgui.get_window_draw_list()

        draw_list.add_rect_filled(
            p,
            (p.x + w, p.y + height),
            imgui.get_color_u32(GAMETHEME.colors.bg_input),
            height / 2,
        )

        fraction = max(0.0, min(value_pct, 100.0)) / 100.0
        if fraction > 0.01:
            draw_list.add_rect_filled(
                p,
                (p.x + w * fraction, p.y + height),
                imgui.get_color_u32(color),
                height / 2,
            )

        imgui.dummy((0, height + 5))

    @staticmethod
    def currency_row(label: str, value: float, color: tuple | None = None):
        """Aligned row: Label ...... $Value."""
        imgui.text(label)
        imgui.same_line()

        val_str = f"$ {value:,.0f}".replace(",", " ")
        col = color if color else GAMETHEME.colors.text_main
        UIPrimitives.right_align_text(val_str, col)

    @staticmethod
    def right_align_text(text: str, color: tuple | None = None):
        width = imgui.calc_text_size(text).x
        avail_w = imgui.get_content_region_avail().x
        imgui.set_cursor_pos_x(imgui.get_cursor_pos_x() + avail_w - width)

        if color:
            imgui.text_colored(color, text)
        else:
            imgui.text(text)


    @staticmethod
    def icon_toggle(
        icon: str,
        color: tuple,
        is_active: bool,
        width: float = 50,
        height: float = 50,
        show_inactive_indicator: bool = False,
    ) -> bool:
        """Draws a square icon toggle with an optional bottom indicator."""
        bg = GAMETHEME.colors.interaction_active if is_active else GAMETHEME.colors.bg_input
        imgui.push_style_color(imgui.Col_.button, bg)
        imgui.push_style_var(imgui.StyleVar_.frame_rounding, 8.0)

        clicked = imgui.button(icon, (width, height))

        imgui.pop_style_var()
        imgui.pop_style_color()

        if is_active or show_inactive_indicator:
            p_min = imgui.get_item_rect_min()
            p_max = imgui.get_item_rect_max()
            draw_list = imgui.get_window_draw_list()
            indicator_color = color if is_active else GAMETHEME.colors.text_dim
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
        value_x = x + plate_w - 7.0

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
            value_size = imgui.calc_text_size(value_text)

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
                (value_x - value_size.x, row_y - 1.0),
                imgui.get_color_u32(GAMETHEME.colors.text_main),
                value_text,
            )
