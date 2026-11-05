"""Scrollable source notification frame shared by detailed dispatch reports."""
from collections import deque

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.gml_widgets import GMLWidgets
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.window_placement import center_window
from src.client.ui.layouts.gml_layout import gml_child_frame


class TextNotificationDialog:
    def __init__(self):
        self._message = ""
        self._pending: deque[str] = deque()

    def show(self, message: str) -> None:
        self.enqueue(message)

    def enqueue(self, message: str) -> None:
        body = str(message or "").strip()
        if not body:
            return
        if self._message:
            self._pending.append(body)
        else:
            self._message = body

    def _dismiss(self) -> None:
        self._message = self._pending.popleft() if self._pending else ""

    def render(self) -> None:
        if not self._message:
            return
        size = imgui.get_io().display_size
        x, y = center_window((size.x, size.y), (358, 248))
        flags = (imgui.WindowFlags_.no_title_bar | imgui.WindowFlags_.no_scrollbar
                 | imgui.WindowFlags_.no_scroll_with_mouse)
        with WindowManager.window(
            "Dispatch report", x=x, y=y,
            w=358, h=248, flags=flags, gml_template="Region_Control_Change_Window",
            test_id="dispatch.report.dialog",
        ) as opened:
            if not opened:
                self._dismiss()
                return
            ui = GMLWidgets("Region_Control_Change_Window")
            with gml_child_frame(ui.path("frmClip"), padding=(0, 0), bordered=False) as visible:
                if visible:
                    imgui.text_wrapped(self._message, test_id="dispatch.report.content")
            if ui.button("btnOk", "OK", "dispatch.report.ok"):
                self._dismiss()
