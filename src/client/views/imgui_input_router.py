"""Route view input through ImGui before forwarding it to game controls."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class MouseButtonInput:
    x: float
    y: float
    button: int
    modifiers: int


@dataclass(frozen=True)
class MouseMotionInput:
    x: float
    y: float
    dx: float
    dy: float


@dataclass(frozen=True)
class MouseDragInput:
    x: float
    y: float
    dx: float
    dy: float
    buttons: int
    modifiers: int


@dataclass(frozen=True)
class MouseScrollInput:
    x: float
    y: float
    scroll_x: float
    scroll_y: float


class _ImGuiInput(Protocol):
    def on_mouse_press(self, x: float, y: float, button: int, modifiers: int) -> bool: ...

    def on_mouse_motion(self, x: float, y: float, dx: float, dy: float) -> bool: ...

    def on_mouse_release(self, x: float, y: float, button: int, modifiers: int) -> bool: ...

    def on_mouse_drag(
        self,
        x: float,
        y: float,
        dx: float,
        dy: float,
        buttons: int,
        modifiers: int,
    ) -> bool: ...

    def on_mouse_scroll(
        self,
        x: float,
        y: float,
        scroll_x: float,
        scroll_y: float,
    ) -> bool: ...

    def on_key_press(self, symbol: int, modifiers: int) -> bool: ...

    def on_key_release(self, symbol: int, modifiers: int) -> bool: ...

    def on_text(self, text: str) -> bool: ...


class ImGuiInputRouter:
    """Apply ImGui capture and mouse pass-through rules before game input."""

    def __init__(self, right_mouse_button: int, middle_mouse_button: int) -> None:
        self._pass_through_mouse_buttons = frozenset(
            (right_mouse_button, middle_mouse_button)
        )
        self._pass_through_drag_mask = right_mouse_button | middle_mouse_button

    def dispatch_mouse_press(
        self,
        imgui: _ImGuiInput | None,
        event: MouseButtonInput,
        game_handler: Callable[[float, float, int, int], None],
    ) -> None:
        captured = (
            imgui.on_mouse_press(event.x, event.y, event.button, event.modifiers)
            if imgui
            else False
        )
        if captured and event.button not in self._pass_through_mouse_buttons:
            return
        game_handler(event.x, event.y, event.button, event.modifiers)

    def dispatch_mouse_motion(
        self,
        imgui: _ImGuiInput | None,
        event: MouseMotionInput,
        game_handler: Callable[[float, float, float, float], None],
    ) -> None:
        if imgui:
            imgui.on_mouse_motion(event.x, event.y, event.dx, event.dy)
        game_handler(event.x, event.y, event.dx, event.dy)

    def dispatch_mouse_release(
        self,
        imgui: _ImGuiInput | None,
        event: MouseButtonInput,
        game_handler: Callable[[float, float, int, int], None],
    ) -> None:
        captured = (
            imgui.on_mouse_release(event.x, event.y, event.button, event.modifiers)
            if imgui
            else False
        )
        if captured and event.button not in self._pass_through_mouse_buttons:
            return
        game_handler(event.x, event.y, event.button, event.modifiers)

    def dispatch_mouse_drag(
        self,
        imgui: _ImGuiInput | None,
        event: MouseDragInput,
        game_handler: Callable[[float, float, float, float, int, int], None],
    ) -> None:
        captured = (
            imgui.on_mouse_drag(
                event.x,
                event.y,
                event.dx,
                event.dy,
                event.buttons,
                event.modifiers,
            )
            if imgui
            else False
        )
        if captured and not event.buttons & self._pass_through_drag_mask:
            return
        game_handler(
            event.x,
            event.y,
            event.dx,
            event.dy,
            event.buttons,
            event.modifiers,
        )

    def dispatch_mouse_scroll(
        self,
        imgui: _ImGuiInput | None,
        event: MouseScrollInput,
        game_handler: Callable[[float, float, float, float], None],
    ) -> None:
        captured = (
            imgui.on_mouse_scroll(event.x, event.y, event.scroll_x, event.scroll_y)
            if imgui
            else False
        )
        if not captured:
            game_handler(event.x, event.y, event.scroll_x, event.scroll_y)

    def key_press_captured(
        self,
        imgui: _ImGuiInput | None,
        symbol: int,
        modifiers: int,
    ) -> bool:
        return imgui.on_key_press(symbol, modifiers) if imgui else False

    def dispatch_key_release(
        self,
        imgui: _ImGuiInput | None,
        symbol: int,
        modifiers: int,
        game_handler: Callable[[int, int], None],
    ) -> None:
        captured = imgui.on_key_release(symbol, modifiers) if imgui else False
        if not captured:
            game_handler(symbol, modifiers)

    def dispatch_text(
        self,
        imgui: _ImGuiInput | None,
        text: str,
        game_handler: Callable[[str], None],
    ) -> None:
        captured = imgui.on_text(text) if imgui else False
        if not captured:
            game_handler(text)
