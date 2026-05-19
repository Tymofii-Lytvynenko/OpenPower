from imgui_bundle import imgui
from src.client.ui.core.theme import GAMETHEME


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
        # Compute the right edge of the content region in window-relative coords.
        # This is reliable even after same_line() following a full-width dummy,
        # where get_content_region_avail().x drops to ~0 and produces a wrong result.
        content_max_x = imgui.get_window_content_region_max().x
        target_x = content_max_x - width
        current_x = imgui.get_cursor_pos_x()
        if target_x > current_x:
            imgui.set_cursor_pos_x(target_x)

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
