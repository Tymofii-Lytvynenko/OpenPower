from __future__ import annotations

from collections.abc import Callable
from collections import deque
from dataclasses import dataclass

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.layouts.gml_layout import active_gml_layout, gml_child_frame
from src.client.ui.layouts.gml_message_geometry import (
    apply_gml_message_geometry,
    measure_gml_message_geometry,
)


@dataclass(frozen=True, slots=True)
class MessageDialogContent:
    title: str
    message: str
    severity: str = "info"


class GenericMessageDialog:
    """Reusable GML-sized message surface for OpenPower notices and errors."""

    _COLORS = {
        "info": (0.90, 0.91, 0.92, 1.0),
        "warning": (1.0, 0.78, 0.30, 1.0),
        "error": (1.0, 0.43, 0.38, 1.0),
    }

    def __init__(self) -> None:
        self._content: MessageDialogContent | None = None
        self._on_acknowledge: Callable[[], None] | None = None
        self._pending: deque[tuple[MessageDialogContent, Callable[[], None] | None]] = deque()

    def enqueue(self, title: str, message: str, *, severity: str = "info",
                on_acknowledge: Callable[[], None] | None = None) -> None:
        if not str(message or "").strip():
            return
        if self.is_open:
            # Concurrent server outcomes must not overwrite the active caller's
            # acknowledgement callback or discard another command's failure.
            self._pending.append((MessageDialogContent(title, message, severity), on_acknowledge))
        else:
            self.show(title, message, severity=severity, on_acknowledge=on_acknowledge)

    @property
    def is_open(self) -> bool:
        return self._content is not None

    def show(
        self,
        title: str,
        message: str,
        *,
        severity: str = "info",
        on_acknowledge: Callable[[], None] | None = None,
    ) -> None:
        body = str(message or "").strip()
        if not body:
            return
        normalized_severity = severity.casefold()
        if normalized_severity not in self._COLORS:
            normalized_severity = "info"
        self._content = MessageDialogContent(
            str(title or "Message").strip() or "Message",
            body,
            normalized_severity,
        )
        self._on_acknowledge = on_acknowledge

    def dismiss(self) -> None:
        self._content = None
        self._on_acknowledge = None
        self._advance_pending()

    def _advance_pending(self) -> None:
        if self._pending:
            content, callback = self._pending.popleft()
            self.show(content.title, content.message, severity=content.severity,
                      on_acknowledge=callback)

    def acknowledge(self) -> None:
        callback = self._on_acknowledge
        self._content = None
        self._on_acknowledge = None
        if callback is not None:
            callback()
        # A caller may open its next notice from the acknowledgement callback.
        # Promoting the queue first would let that callback overwrite a notice.
        if not self.is_open:
            self._advance_pending()

    def render(self) -> bool:
        content = self._content
        if content is None:
            return False

        viewport = imgui.get_main_viewport()
        geometry = measure_gml_message_geometry(
            "Generic_Message_Window",
            f"{content.title}\n{content.message}",
            float(viewport.size.y),
        )
        width = geometry.window_width
        height = geometry.window_height
        x = float(viewport.pos.x + (viewport.size.x - width) / 2.0)
        y = float(viewport.pos.y + (viewport.size.y - height) / 2.0)
        flags = (
            imgui.WindowFlags_.no_title_bar
            | imgui.WindowFlags_.no_resize
            | imgui.WindowFlags_.no_collapse
            | imgui.WindowFlags_.no_saved_settings
            | imgui.WindowFlags_.no_scrollbar
            | imgui.WindowFlags_.no_scroll_with_mouse
        )
        imgui.set_next_window_focus()
        with WindowManager.window(
            "##generic_message_dialog",
            x=x,
            y=y,
            w=width,
            h=height,
            flags=flags,
            test_id="generic_message.dialog",
            gml_template="Generic_Message_Window",
            size_override=(width, height),
        ) as is_open:
            if not is_open:
                self.dismiss()
                return False

            apply_gml_message_geometry(active_gml_layout(), geometry)

            imgui.push_style_color(
                imgui.Col_.text,
                self._COLORS[content.severity],
            )
            # Server reasons can exceed the source label's height. Scrolling
            # within that slot preserves access to the fixed acknowledgement.
            with gml_child_frame("Generic_Message_Window/lblMessage", padding=(0, 0),
                                 bordered=False) as body_open:
                if body_open:
                    imgui.text_wrapped(
                        f"{content.title}\n{content.message}",
                        test_id="generic_message.content",
                    )
            imgui.pop_style_color()

            if imgui.button(
                "OK",
                test_id="generic_message.ok",
                gml_id="Generic_Message_Window/btnOk",
            ):
                self.acknowledge()
        return self.is_open
