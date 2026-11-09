from contextlib import contextmanager

from src.client.ui.core.instrumented_imgui import imgui


class PopupManager:
    """Provide scoped ImGui popup and centered modal containers."""

    @staticmethod
    @contextmanager
    def popup(title: str):
        is_open = imgui.begin_popup(title)
        # A context manager must yield when a popup is closed, or entering it raises RuntimeError.
        try:
            yield is_open
        finally:
            if is_open:
                imgui.end_popup()

    @staticmethod
    @contextmanager
    def centered_modal(name: str, sw: float, sh: float, w: float = 300, h: float = 400):
        pos_x = (sw - w) / 2
        pos_y = (sh - h) / 2

        imgui.set_next_window_pos((pos_x, pos_y))
        imgui.set_next_window_size((w, h))

        flags = imgui.WindowFlags_.no_title_bar | imgui.WindowFlags_.no_move

        is_open = imgui.begin(name, None, flags)
        # Preserve context-manager semantics while letting callers skip closed modal contents.
        try:
            yield is_open
        finally:
            if is_open:
                imgui.end()
