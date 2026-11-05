from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
import sys
from typing import Any

from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.testability import semantic_region
from src.client.ui.layouts.gml_layout import (
    GMLLayoutSession,
    GMLWindowLayout,
    gml_style,
    gml_titlebar_close,
    render_gml_title,
    use_gml_layout,
)
from src.client.ui.core.window_setup import WindowRequest, WindowSetup


_GML_WINDOW_SETTINGS_REVISION = "v2"


@dataclass(frozen=True, slots=True)
class WindowPresentation:
    title: str
    flags: Any
    padding: tuple[float, float] | None
    custom_titlebar: bool
    style_scope: Any


class WindowLifecycle:
    """Compose ImGui frame management with optional GML rendering scopes."""

    @staticmethod
    def prepare_presentation(request: WindowRequest, setup: WindowSetup) -> WindowPresentation:
        custom_titlebar = WindowLifecycle._has_custom_titlebar(setup.layout)
        flags = WindowLifecycle._resolve_flags(request.flags, custom_titlebar)
        padding = WindowLifecycle._resolve_padding(request.padding, custom_titlebar)
        title = WindowLifecycle._resolve_imgui_title(request, setup)
        return WindowPresentation(
            title=title,
            flags=flags,
            padding=padding,
            custom_titlebar=custom_titlebar,
            style_scope=gml_style() if setup.layout is not None else None,
        )

    @staticmethod
    def _has_custom_titlebar(layout: GMLWindowLayout | None) -> bool:
        if layout is None:
            return False
        close_component = gml_titlebar_close(layout)
        title_label = layout.component("lblTitle")
        return bool(close_component and title_label)

    @staticmethod
    def _resolve_flags(flags: Any, custom_titlebar: bool) -> Any:
        flags = flags | imgui.WindowFlags_.no_collapse
        if custom_titlebar:
            flags |= imgui.WindowFlags_.no_title_bar
            if flags & imgui.WindowFlags_.menu_bar:
                flags &= ~imgui.WindowFlags_.menu_bar
        return flags

    @staticmethod
    def _resolve_padding(
        padding: tuple[float, float] | None,
        custom_titlebar: bool,
    ) -> tuple[float, float] | None:
        if padding is None and custom_titlebar:
            return (0.0, 0.0)
        return padding

    @staticmethod
    def _resolve_imgui_title(request: WindowRequest, setup: WindowSetup) -> str:
        if setup.layout is None:
            return request.title
        # New GML windows must not inherit stale positions saved under their old visible titles.
        visible_title = request.title.split("##", 1)[0]
        viewport_key = f"{setup.viewport_width:g}x{setup.viewport_height:g}"
        return (
            f"{visible_title}##openpower.gml.{_GML_WINDOW_SETTINGS_REVISION}:"
            f"{setup.window_key}:{viewport_key}"
        )

    @staticmethod
    @contextmanager
    def frame(
        request: WindowRequest,
        setup: WindowSetup,
        presentation: WindowPresentation,
    ):
        expanded, opened = WindowLifecycle._begin_window(request, presentation)
        try:
            yield expanded, opened
        finally:
            WindowLifecycle._end_window(setup, presentation, expanded)

    @staticmethod
    def _begin_window(
        request: WindowRequest,
        presentation: WindowPresentation,
    ) -> tuple[bool, bool]:
        style_scope = presentation.style_scope
        if style_scope is not None:
            style_scope.__enter__()
        try:
            # A failed Begin must still unwind padding and the GML style stack.
            if presentation.padding is not None:
                imgui.push_style_var(imgui.StyleVar_.window_padding, presentation.padding)
            try:
                return imgui.begin(
                    presentation.title,
                    True if request.closable else None,
                    presentation.flags,
                )
            finally:
                if presentation.padding is not None:
                    imgui.pop_style_var()
        except BaseException:
            if style_scope is not None:
                style_scope.__exit__(*sys.exc_info())
            raise

    @staticmethod
    def _end_window(
        setup: WindowSetup,
        presentation: WindowPresentation,
        expanded: bool,
    ) -> None:
        try:
            if setup.layout is not None and expanded:
                # GML screen coordinates can extend past ImGui's cursor bounds.
                imgui.dummy((1.0, 1.0))
        finally:
            try:
                imgui.end()
            finally:
                if presentation.style_scope is not None:
                    presentation.style_scope.__exit__(None, None, None)

    @staticmethod
    @contextmanager
    def body(
        request: WindowRequest,
        setup: WindowSetup,
        presentation: WindowPresentation,
        *,
        expanded: bool,
        opened: bool,
        close_requests: set[str],
    ):
        opened = WindowLifecycle._resolve_open_state(request, opened)
        layout_scope, titlebar_closed = WindowLifecycle._prepare_layout_scope(
            request,
            setup,
            presentation,
            expanded,
        )
        if titlebar_closed:
            opened = False
        opened = WindowLifecycle._apply_close_request(request, setup, opened, close_requests)
        with ExitStack() as scopes:
            if layout_scope is not None:
                scopes.enter_context(layout_scope)
            if request.test_id is not None:
                scopes.enter_context(
                    semantic_region(
                        request.test_id,
                        request.title,
                        visible=opened and expanded,
                    )
                )
            yield opened

    @staticmethod
    def _resolve_open_state(request: WindowRequest, opened: bool) -> bool:
        return opened if request.closable else True

    @staticmethod
    def _prepare_layout_scope(
        request: WindowRequest,
        setup: WindowSetup,
        presentation: WindowPresentation,
        expanded: bool,
    ) -> tuple[Any, bool]:
        if setup.layout is None or not expanded:
            return None, False
        layout_session, window_position = WindowLifecycle._create_layout_session(
            setup.layout,
            request.fit_layout_width,
        )
        titlebar_closed = presentation.custom_titlebar and WindowLifecycle._render_titlebar(
            setup.layout,
            request.title,
            layout_session,
            window_position,
            closable=request.closable,
            test_id=request.test_id,
        )
        return use_gml_layout(layout_session), titlebar_closed

    @staticmethod
    def _apply_close_request(
        request: WindowRequest,
        setup: WindowSetup,
        opened: bool,
        close_requests: set[str],
    ) -> bool:
        if request.closable and setup.window_key in close_requests:
            close_requests.discard(setup.window_key)
            return False
        return opened

    @staticmethod
    def _create_layout_session(layout: GMLWindowLayout, fit_layout_width: bool):
        window_position = imgui.get_window_pos()
        window_size = imgui.get_window_size()
        layout_session = GMLLayoutSession(
            layout,
            (float(window_position.x), float(window_position.y)),
            (
                float(layout.width) if fit_layout_width and window_size.x < layout.width
                else float(window_size.x),
                float(window_size.y),
            ),
        )
        if fit_layout_width and 0.0 < window_size.x < layout.width:
            # Compress only when the viewport is narrower than the source frame.
            layout_session.scale_subtree_x(layout.template, float(window_size.x) / layout.width)
        layout_session.apply_base_window_titlebar_rules()
        return layout_session, window_position

    @staticmethod
    def _render_titlebar(layout, title, layout_session, window_position, *, closable, test_id) -> bool:
        close_clicked = False
        close_component = gml_titlebar_close(layout)
        render_gml_title(layout, title, layout_session)
        if closable and close_component is not None:
            close_rect = layout_session.rect_for(close_component)
            imgui.set_cursor_screen_pos((
                float(window_position.x) + close_rect.x,
                float(window_position.y) + close_rect.y,
            ))
            close_test_id = (
                f"{test_id}.close" if test_id
                else f"gml.{layout.template}.close"
            )
            if imgui.button(
                "×",
                (close_rect.width, close_rect.height),
                test_id=close_test_id,
            ):
                close_clicked = True
            inner_frame = layout.component("frmInner")
            if inner_frame is not None:
                inner_rect = layout_session.rect_for(inner_frame)
                imgui.set_cursor_screen_pos((
                    float(window_position.x) + inner_rect.x,
                    float(window_position.y) + inner_rect.y,
                ))
        return close_clicked
