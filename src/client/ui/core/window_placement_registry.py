from dataclasses import dataclass

from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.window_placement import WindowPlacement, resolve_window_placement


@dataclass(frozen=True, slots=True)
class WindowPlacementUpdate:
    window_key: str
    viewport_size: tuple[float, float]
    live_placement: bool
    follow_position: bool
    opened: bool


class WindowPlacementRegistry:
    """Track persistent and currently visible ImGui window placements."""

    def __init__(self) -> None:
        self._placements: dict[str, WindowPlacement] = {}
        self._frame_placements: dict[str, WindowPlacement] = {}

    @property
    def placements(self) -> dict[str, WindowPlacement]:
        return self._placements

    @property
    def frame_placements(self) -> dict[str, WindowPlacement]:
        return self._frame_placements

    def begin_frame(self) -> None:
        self._frame_placements.clear()

    def visible_frame_placements(self) -> tuple[WindowPlacement, ...]:
        return tuple(self._frame_placements.values())

    def update(self, request: WindowPlacementUpdate, imgui_api=imgui) -> None:
        self._constrain_visible_geometry(request.viewport_size, imgui_api)
        if self._should_remember_placement(request):
            self._remember_current_placement(
                self._placements,
                request.window_key,
                request.viewport_size,
                imgui_api,
            )
        if request.opened and self._has_valid_viewport(request.viewport_size):
            self._remember_current_placement(
                self._frame_placements,
                request.window_key,
                request.viewport_size,
                imgui_api,
            )

    def _constrain_visible_geometry(self, viewport_size: tuple[float, float], imgui_api) -> None:
        if not self._has_valid_viewport(viewport_size):
            return
        viewport_width, viewport_height = viewport_size
        # ImGui can restore an old absolute position from imgui.ini before the cache re-anchors it.
        actual_position = imgui_api.get_window_pos()
        actual_size = imgui_api.get_window_size()
        visible = resolve_window_placement(
            (float(actual_position.x), float(actual_position.y)),
            (float(actual_size.x), float(actual_size.y)),
            (float(viewport_width), float(viewport_height)),
        )
        if (visible.width, visible.height) != (actual_size.x, actual_size.y):
            imgui_api.set_window_size((visible.width, visible.height), imgui_api.Cond_.always)
        if (visible.x, visible.y) != (actual_position.x, actual_position.y):
            imgui_api.set_window_pos((visible.x, visible.y), imgui_api.Cond_.always)

    @staticmethod
    def _should_remember_placement(request: WindowPlacementUpdate) -> bool:
        return (
            request.live_placement
            and not request.follow_position
            and WindowPlacementRegistry._has_valid_viewport(request.viewport_size)
        )

    @staticmethod
    def _has_valid_viewport(viewport_size: tuple[float, float]) -> bool:
        return viewport_size[0] > 0 and viewport_size[1] > 0

    @staticmethod
    def _remember_current_placement(
        placements: dict[str, WindowPlacement],
        window_key: str,
        viewport_size: tuple[float, float],
        imgui_api,
    ) -> None:
        actual_position = imgui_api.get_window_pos()
        actual_size = imgui_api.get_window_size()
        placements[window_key] = WindowPlacement(
            float(viewport_size[0]),
            float(viewport_size[1]),
            float(actual_position.x),
            float(actual_position.y),
            float(actual_size.x),
            float(actual_size.y),
        )
