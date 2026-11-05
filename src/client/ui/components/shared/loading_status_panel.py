"""Reusable loading and failure feedback rendered by the startup view."""
from __future__ import annotations

from collections.abc import Callable

from src.client.ui.core.composer import UIComposer
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.theme import GAMETHEME


class LoadingStatusPanel:
    def render(self, ui: UIComposer, task, error: Exception | None,
               screen_size: tuple[int, int], on_return: Callable[[], None]) -> None:
        screen_w, screen_h = screen_size
        error_message = str(error) if error is not None else None
        has_error = error_message is not None
        if not has_error:
            panel_height = 150
        else:
            error_line_count = max(1, (len(error_message) + 47) // 48)
            panel_height = min(max(150, 120 + error_line_count * 14), screen_h - 40)
        if ui.begin_centered_panel(
            "Loader", screen_w, screen_h, w=400, h=panel_height,
            test_id="loading.error.panel" if has_error else "loading.progress.panel",
            force_size=has_error,
        ):
            if has_error:
                # A completed failure must not retain progress UI that implies work is ongoing.
                imgui.text_colored(
                    GAMETHEME.colors.error,
                    "OPERATION FAILED",
                    test_id="loading.error.heading",
                )
                imgui.separator()
                imgui.text_wrapped(error_message, test_id="loading.error.details")
                if imgui.button("RETURN TO START", test_id="loading.error.return"):
                    on_return()
            else:
                ui.draw_title("PROCESSING")
                ui.draw_progress_bar(task.progress, task.status_text)

            ui.end_panel()
