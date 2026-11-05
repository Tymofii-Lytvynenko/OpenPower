from contextlib import contextmanager
from typing import Literal
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.ui_anchor_registry import UIAnchorRegistry
from src.client.ui.core.window_placement import (
    WindowPlacement,
    WindowPlacementPolicy,
    resolve_window_placement,
)
from src.client.ui.core.window_lifecycle import WindowLifecycle
from src.client.ui.core.window_setup import WindowRequest, WindowSetupPolicy
from src.client.ui.core.popup_containers import PopupManager


class WindowManager:
    """
    Context manager for creating ImGui windows.
    """
    _close_requests: set[str] = set()
    _placements: dict[str, WindowPlacement] = {}
    _frame_placements: dict[str, WindowPlacement] = {}
    _setup_policy = WindowSetupPolicy(WindowPlacementPolicy())
    _lifecycle = WindowLifecycle()
    popup = staticmethod(PopupManager.popup)
    centered_modal = staticmethod(PopupManager.centered_modal)

    @classmethod
    def begin_frame(cls) -> None:
        """Forget last frame's visible windows before collecting current geometry."""
        cls._frame_placements.clear()
        UIAnchorRegistry.begin_frame()

    @classmethod
    def visible_frame_placements(cls) -> tuple[WindowPlacement, ...]:
        """Return positions for windows recorded during the current frame."""
        return tuple(cls._frame_placements.values())

    @classmethod
    def request_close(cls, test_id: str) -> None:
        """Use the same close path for shortcuts and title-bar buttons."""
        cls._close_requests.add(test_id)
    
    @staticmethod
    @contextmanager
    def window(title: str, x: float = 0, y: float = 0, w: float = 300, h: float = 400, 
               closable: bool = True, flags=0, test_id: str | None = None,
               gml_template: str | None = None, padding: tuple[float, float] | None = None,
               follow_position: bool = False, size_override: tuple[float, float] | None = None,
               horizontal_anchor: Literal["left", "right"] = "left",
               horizontal_margin: float = 0.0, fit_layout_width: bool = False,
               avoid_overlaps: bool = False, placement_margin: float = 8.0,
               bottom_clearance: float = 0.0, top_clearance: float = 0.0):
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
        with WindowManager._window_context(request) as opened:
            yield opened

    @staticmethod
    @contextmanager
    def _window_context(request: WindowRequest):
        setup = WindowManager._setup_policy.prepare(
            request,
            placements=WindowManager._placements,
            frame_placements=WindowManager._frame_placements,
        )
        presentation = WindowManager._lifecycle.prepare_presentation(request, setup)
        with WindowManager._lifecycle.frame(request, setup, presentation) as (expanded, opened):
            WindowManager._update_placement(
                setup.window_key,
                (setup.viewport_width, setup.viewport_height),
                live_placement=setup.live_placement,
                follow_position=request.follow_position,
                opened=opened,
            )
            with WindowManager._lifecycle.body(
                request,
                setup,
                presentation,
                expanded=expanded,
                opened=opened,
                close_requests=WindowManager._close_requests,
            ) as visible:
                yield visible

    @staticmethod
    def _update_placement(window_key, viewport_size, *, live_placement, follow_position, opened) -> None:
        viewport_width, viewport_height = viewport_size
        if viewport_width > 0 and viewport_height > 0:
            # ImGui can restore an old absolute position from imgui.ini before the
            # in-memory placement cache has a chance to re-anchor the panel.
            actual_position = imgui.get_window_pos()
            actual_size = imgui.get_window_size()
            visible_placement = resolve_window_placement(
                (float(actual_position.x), float(actual_position.y)),
                (float(actual_size.x), float(actual_size.y)),
                (float(viewport_width), float(viewport_height)),
            )
            if (visible_placement.width, visible_placement.height) != (actual_size.x, actual_size.y):
                imgui.set_window_size(
                    (visible_placement.width, visible_placement.height),
                    imgui.Cond_.always,
                )
            if (visible_placement.x, visible_placement.y) != (actual_position.x, actual_position.y):
                imgui.set_window_pos(
                    (visible_placement.x, visible_placement.y),
                    imgui.Cond_.always,
                )
        if live_placement and not follow_position and viewport_width > 0 and viewport_height > 0:
            actual_position = imgui.get_window_pos()
            actual_size = imgui.get_window_size()
            WindowManager._placements[window_key] = WindowPlacement(
                float(viewport_width),
                float(viewport_height),
                float(actual_position.x),
                float(actual_position.y),
                float(actual_size.x),
                float(actual_size.y),
            )
        if opened and viewport_width > 0 and viewport_height > 0:
            actual_position = imgui.get_window_pos()
            actual_size = imgui.get_window_size()
            active_placement = WindowPlacement(
                float(viewport_width),
                float(viewport_height),
                float(actual_position.x),
                float(actual_position.y),
                float(actual_size.x),
                float(actual_size.y),
            )
            WindowManager._frame_placements[window_key] = active_placement
