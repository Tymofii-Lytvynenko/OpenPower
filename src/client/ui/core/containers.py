from contextlib import contextmanager
from typing import Literal
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.testability import active_telemetry
from src.client.ui.core.ui_anchor_registry import UIAnchorRegistry
from src.client.ui.core.window_placement import (
    WindowPlacement,
    WindowPlacementPolicy,
)
from src.client.ui.core.window_lifecycle import WindowLifecycle
from src.client.ui.core.window_setup import WindowRequest, WindowSetupPolicy
from src.client.ui.core.popup_containers import PopupManager
from src.client.ui.core.window_placement_registry import (
    WindowPlacementRegistry,
    WindowPlacementUpdate,
)
from src.client.ui.layouts.gml_layout import gml_style, resolve_gml_layout


class WindowManager:
    """
    Context manager for creating ImGui windows.
    """
    _close_requests: set[str] = set()
    _placement_registry = WindowPlacementRegistry()
    _placements = _placement_registry.placements
    _frame_placements = _placement_registry.frame_placements
    _setup_policy = WindowSetupPolicy(WindowPlacementPolicy())
    _lifecycle = WindowLifecycle()
    popup = staticmethod(PopupManager.popup)
    centered_modal = staticmethod(PopupManager.centered_modal)

    @classmethod
    def begin_frame(cls) -> None:
        """Forget last frame's visible windows before collecting current geometry."""
        cls._placement_registry.begin_frame()
        UIAnchorRegistry.begin_frame()

    @classmethod
    def visible_frame_placements(cls) -> tuple[WindowPlacement, ...]:
        """Return positions for windows recorded during the current frame."""
        return cls._placement_registry.visible_frame_placements()

    @classmethod
    def request_close(cls, test_id: str) -> None:
        """Use the same close path for shortcuts and title-bar buttons."""
        cls._close_requests.add(test_id)
    
    @classmethod
    @contextmanager
    def window(
        cls,
        title: str,
        x: float = 0,
        y: float = 0,
        w: float = 300,
        h: float = 400,
        closable: bool = True,
        flags=0,
        test_id: str | None = None,
        gml_template: str | None = None,
        padding: tuple[float, float] | None = None,
        follow_position: bool = False,
        size_override: tuple[float, float] | None = None,
        horizontal_anchor: Literal["left", "right"] = "left",
        horizontal_margin: float = 0.0,
        fit_layout_width: bool = False,
        avoid_overlaps: bool = False,
        placement_margin: float = 8.0,
        bottom_clearance: float = 0.0,
        top_clearance: float = 0.0,
    ):
        """
        Creates a standard panel window.
        Yields 'True' if the window is open and expanded.
        """
        request = WindowRequest(
            title=title,
            x=x,
            y=y,
            w=w,
            h=h,
            closable=closable,
            flags=flags,
            test_id=test_id,
            gml_template=gml_template,
            padding=padding,
            follow_position=follow_position,
            size_override=size_override,
            horizontal_anchor=horizontal_anchor,
            horizontal_margin=horizontal_margin,
            fit_layout_width=fit_layout_width,
            avoid_overlaps=avoid_overlaps,
            placement_margin=placement_margin,
            bottom_clearance=bottom_clearance,
            top_clearance=top_clearance,
        )
        with cls._window_context(request) as opened:
            yield opened

    @classmethod
    @contextmanager
    def _window_context(cls, request: WindowRequest):
        setup = cls._setup_policy.prepare(
            request,
            placements=cls._placements,
            frame_placements=cls._frame_placements,
            imgui_api=imgui,
            telemetry_provider=active_telemetry,
            layout_resolver=resolve_gml_layout,
        )
        presentation = cls._lifecycle.prepare_presentation(
            request,
            setup,
            imgui_api=imgui,
            style_factory=gml_style,
        )
        with cls._lifecycle.frame(
            request,
            setup,
            presentation,
            imgui_api=imgui,
        ) as (expanded, opened):
            cls._update_placement(
                WindowPlacementUpdate(
                    window_key=setup.window_key,
                    viewport_size=(setup.viewport_width, setup.viewport_height),
                    live_placement=setup.live_placement,
                    follow_position=request.follow_position,
                    opened=opened,
                )
            )
            with cls._lifecycle.body(
                request,
                setup,
                presentation,
                expanded=expanded,
                opened=opened,
                close_requests=cls._close_requests,
                imgui_api=imgui,
            ) as visible:
                yield visible

    @classmethod
    def _update_placement(cls, request: WindowPlacementUpdate) -> None:
        cls._placement_registry.update(request, imgui_api=imgui)
