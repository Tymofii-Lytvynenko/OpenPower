from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable

from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.testability import semantic_region

# The source creates this transient Tooltip_Window at runtime and resizes it to 400px wide.
TUTORIAL_GUIDE_WIDTH = 400.0
TUTORIAL_GUIDE_MIN_WIDTH = 260.0
TUTORIAL_GUIDE_BODY_Y = 58.0
TUTORIAL_GUIDE_BUTTON_HEIGHT = 28.0
TUTORIAL_GUIDE_BOTTOM_PADDING = 22.0
TUTORIAL_GUIDE_HORIZONTAL_PADDING = 56.0


@dataclass(frozen=True, slots=True)
class TutorialGuideLayout:
    status_y: float | None
    buttons_y: float
    stack_buttons: bool
    window_height: float


def resolve_tutorial_guide_layout(
    body_height: float,
    status_height: float | None = None,
    window_width: float = TUTORIAL_GUIDE_WIDTH,
) -> TutorialGuideLayout:
    """Size the tutorial frame around its wrapped body, optional status, and controls."""
    body_bottom = TUTORIAL_GUIDE_BODY_Y + max(0.0, body_height)
    if status_height is None:
        status_y = None
        buttons_y = body_bottom + 16.0
    else:
        status_y = body_bottom + 10.0
        buttons_y = status_y + max(0.0, status_height) + 12.0
    stack_buttons = window_width < 360.0
    controls_height = (
        TUTORIAL_GUIDE_BUTTON_HEIGHT * 3.0 + 12.0
        if stack_buttons
        else TUTORIAL_GUIDE_BUTTON_HEIGHT
    )
    window_height = buttons_y + controls_height + TUTORIAL_GUIDE_BOTTOM_PADDING
    return TutorialGuideLayout(status_y, buttons_y, stack_buttons, window_height)


@dataclass(frozen=True, slots=True)
class TutorialStep:
    title: str
    body: str
    required_panel_states: tuple[tuple[str, bool], ...] = ()
    arrow_target: str | None = None
    auto_advance: bool = True
    fallback_arrow_target: str | None = None
    advance_on_interaction: str | None = None


_GUIDES: dict[str, tuple[str, tuple[TutorialStep, ...]]] = {
    "interface": (
        "INTERFACE TUTORIAL",
        (
            TutorialStep(
                "Explore the globe",
                "Drag with the right mouse button to rotate the globe. Use the mouse wheel to zoom, and left-click a region to select it.",
                arrow_target="world.viewport",
            ),
            TutorialStep(
                "Navigate with the mini map",
                "Click or drag on the mini map to move the main view to another part of the world.",
                arrow_target="mini_map.map",
                fallback_arrow_target="world.viewport",
                advance_on_interaction="mini_map.navigate",
            ),
            TutorialStep(
                "Zoom with the mini map",
                "Use the mini map's zoom bar to change the view scale. You can also zoom with the mouse wheel.",
                arrow_target="mini_map.zoom",
                fallback_arrow_target="world.viewport",
                advance_on_interaction="mini_map.zoom",
            ),
            TutorialStep(
                "Read the map",
                "Use the map controls and context menu to inspect the geographic view and the thematic layers available in OpenPower.",
                arrow_target="world.viewport",
            ),
            TutorialStep(
                "Select a country",
                "Click a country on the globe or choose it from the country selector in the main bar. The selected country drives the panels and actions you can use.",
                arrow_target="hud.country",
            ),
            TutorialStep(
                "Open a domain panel",
                "The buttons at the lower left open Politics, Military, Economy, and Demographics. Each domain keeps its own tools and details.",
                arrow_target="hud.panel.pol",
            ),
            TutorialStep(
                "Use the main bar",
                "Use the bottom main bar to open Relations and inspect the current country's diplomatic context.",
                (("RELATIONS", True),),
                arrow_target="hud.relations",
            ),
            TutorialStep(
                "Inspect Relations",
                "Choose two countries to inspect their directed relationship and its recorded history.",
                (("RELATIONS", True),),
                auto_advance=False,
            ),
            TutorialStep(
                "Move the window",
                "Drag the Relations title bar to reposition the window, then continue.",
                (("RELATIONS", True),),
                auto_advance=False,
            ),
            TutorialStep(
                "Close Relations",
                "Close the Relations window using its title bar.",
                (("RELATIONS", False),),
                arrow_target="relations.panel.close",
            ),
            TutorialStep(
                "Open Country Information",
                "Open More Info from the main bar to inspect the selected country.",
                (("COUNTRY_MORE_INFO", True),),
                arrow_target="hud.more_info",
            ),
            TutorialStep(
                "Close Country Information",
                "Close Country Information to return to the main bar.",
                (("COUNTRY_MORE_INFO", False),),
                arrow_target="country_more_info.panel.close",
            ),
            TutorialStep(
                "Advisor settings",
                "The advisor button opens settings for the automation and recommendations supported by OpenPower.",
                arrow_target="hud.advisor",
            ),
            TutorialStep(
                "History",
                "Open History to inspect recorded changes and graphs for countries and their indicators.",
                arrow_target="hud.history",
            ),
            TutorialStep(
                "Messages",
                "Mail contains dispatches and other messages that may lead to further details or actions.",
                arrow_target="hud.mail",
            ),
            TutorialStep(
                "World events",
                "The news ticker reports recent events. When a bulletin has a location, select it to focus the map.",
                arrow_target="hud.ticker",
            ),
            TutorialStep(
                "Event details",
                "Open the event feed to inspect recorded events and focus their locations when available.",
                arrow_target="hud.ticker",
            ),
            TutorialStep(
                "Event filters",
                "The event feed can filter political, economic, military and demographic events.",
                arrow_target="hud.ticker",
            ),
            TutorialStep(
                "Event feed",
                "Use the news button to open or close the event feed.",
                arrow_target="hud.news",
            ),
            TutorialStep(
                "Game date",
                "The main bar shows the current game date and time. If the speed controls are open, use the clock button to show the date again.",
                arrow_target="hud.date",
                fallback_arrow_target="hud.clock",
            ),
            TutorialStep(
                "Time controls",
                "Use the clock button to show the pause and game-speed controls.",
                arrow_target="hud.clock",
            ),
            TutorialStep(
                "Ready to play",
                "F1 opens controls and these guided tours. This guide does not recreate the source game's scripted tutorial scenario.",
            ),
        ),
    ),
    "military": (
        "MILITARY TUTORIAL",
        (
            TutorialStep(
                "Open Military",
                "Use the Military button at the lower left. The panel summarizes conventional forces and the strategic programs supported by OpenPower.",
                (("MIL", True),),
                arrow_target="hud.panel.mil",
            ),
            TutorialStep(
                "Inspect forces",
                "Open the unit list to inspect your groups. Close it before continuing; foreign forces expose only aggregate information.",
                (("MIL", True), ("UNIT_LIST", True)),
                arrow_target="military.open_unit_list",
            ),
            TutorialStep(
                "Fund research",
                "Close the unit list, then open Unit Research to review supported branches and authoritative funding actions.",
                (("UNIT_LIST", False), ("UNIT_RESEARCH", True)),
                arrow_target="military.open_research",
            ),
            TutorialStep(
                "Create designs",
                "Close Unit Research, then open Unit Design to inspect supported roles and capability profiles.",
                (("UNIT_RESEARCH", False), ("UNIT_DESIGN", True)),
                arrow_target="military.open_design",
            ),
            TutorialStep(
                "Place production orders",
                "Close Unit Design, then open Unit Production to review a design, quantity, and the OpenPower estimate.",
                (("UNIT_DESIGN", False), ("UNIT_PRODUCTION", True)),
                arrow_target="military.open_production",
            ),
            TutorialStep(
                "Train and deploy reserves",
                "Close Unit Production, then open Reserves to inspect eligible groups and their supported deployment actions.",
                (("UNIT_PRODUCTION", False), ("UNIT_RESERVES", True)),
                arrow_target="military.open_reserves",
            ),
            TutorialStep(
                "Manage units",
                "Close Reserves, then reopen the unit list to review guarded training, sale, disband, merge, and split actions.",
                (("UNIT_RESERVES", False), ("UNIT_LIST", True)),
                arrow_target="military.open_unit_list",
            ),
            TutorialStep(
                "Review conflicts",
                "Close the unit list, then open War List to inspect current OpenPower conflict data and supported actions.",
                (("UNIT_LIST", False), ("WAR_LIST", True)),
                arrow_target="military.open_war_list",
            ),
        ),
    ),
}


class TutorialGuideContent:
    """Presents concise OpenPower guides for the two single-player tutorial entries."""

    def __init__(self) -> None:
        self._guide_id: str | None = None
        self._step_index = 0

    @property
    def is_open(self) -> bool:
        return self._guide_id in _GUIDES

    @property
    def title(self) -> str:
        return _GUIDES[self._guide_id][0] if self.is_open else "TUTORIAL"

    @property
    def arrow_target(self) -> str | None:
        if not self.is_open:
            return None
        return _GUIDES[self._guide_id][1][self._step_index].arrow_target

    @property
    def arrow_targets(self) -> tuple[str, ...]:
        if not self.is_open:
            return ()
        step = _GUIDES[self._guide_id][1][self._step_index]
        return tuple(target for target in (step.arrow_target, step.fallback_arrow_target) if target)

    def window_size(
        self,
        panel_visible_cb: Callable[[str], bool] | None = None,
        window_width: float = TUTORIAL_GUIDE_WIDTH,
    ) -> tuple[float, float]:
        if not self.is_open:
            return window_width, 180.0

        step = _GUIDES[self._guide_id][1][self._step_index]
        layout, _, _ = self._resolve_layout(step, panel_visible_cb, window_width)
        return window_width, layout.window_height

    def open(self, guide_id: str) -> None:
        if guide_id not in _GUIDES:
            raise ValueError(f"Unknown tutorial guide: {guide_id}")
        self._guide_id = guide_id
        self._step_index = 0

    def close(self) -> None:
        self._guide_id = None
        self._step_index = 0

    def on_interaction(self, interaction: str) -> None:
        if not self.is_open:
            return
        steps = _GUIDES[self._guide_id][1]
        if steps[self._step_index].advance_on_interaction != interaction:
            return
        # Only the active step consumes a gesture; earlier clicks must not
        # silently complete a later tutorial goal.
        if self._step_index < len(steps) - 1:
            self._step_index += 1

    def advance_if_ready(self, panel_visible_cb: Callable[[str], bool]) -> None:
        if not self.is_open:
            return
        steps = _GUIDES[self._guide_id][1]
        step = steps[self._step_index]
        if not step.auto_advance or not step.required_panel_states or not self._requirements_satisfied(step, panel_visible_cb):
            return
        if self._step_index == len(steps) - 1:
            self.close()
        else:
            self._step_index += 1

    def render(
        self,
        on_close: Callable[[], None],
        panel_visible_cb: Callable[[str], bool] | None = None,
        test_id_prefix: str = "main_menu",
        window_width: float = TUTORIAL_GUIDE_WIDTH,
    ) -> None:
        if not self.is_open:
            return

        guide_id = self._guide_id
        steps = _GUIDES[guide_id][1]
        step = steps[self._step_index]
        layout, status, can_advance = self._resolve_layout(
            step, panel_visible_cb, window_width
        )
        wrap_width = max(1.0, window_width - TUTORIAL_GUIDE_HORIZONTAL_PADDING)
        with semantic_region(f"{test_id_prefix}.tutorial.{guide_id}.content", step.title):
            imgui.set_cursor_pos((12.0, 14.0))
            imgui.text_colored(
                (0.72, 0.83, 0.96, 1.0),
                _GUIDES[guide_id][0],
                test_id=f"{test_id_prefix}.tutorial.title.{guide_id}",
            )
            imgui.set_cursor_pos((12.0, 34.0))
            imgui.text_colored(
                (0.72, 0.83, 0.96, 1.0),
                f"{self._step_index + 1} / {len(steps)}  ·  {step.title}",
                test_id=f"{test_id_prefix}.tutorial.step.{guide_id}.{self._step_index + 1}",
            )
            imgui.separator()
            imgui.set_cursor_pos((12.0, 58.0))
            imgui.push_text_wrap_pos(imgui.get_cursor_pos_x() + wrap_width)
            try:
                imgui.text_wrapped(
                    step.body,
                    test_id=f"{test_id_prefix}.tutorial.body.{guide_id}.{self._step_index + 1}",
                )
            finally:
                imgui.pop_text_wrap_pos()

            if status is not None:
                imgui.set_cursor_pos((12.0, layout.status_y))
                imgui.push_text_wrap_pos(imgui.get_cursor_pos_x() + wrap_width)
                try:
                    imgui.text_colored(
                        (0.45, 0.88, 0.53, 1.0) if can_advance else (0.92, 0.73, 0.38, 1.0),
                        status,
                        test_id=f"{test_id_prefix}.tutorial.requirement.{guide_id}.{self._step_index + 1}",
                    )
                finally:
                    imgui.pop_text_wrap_pos()

            imgui.set_cursor_pos((12.0, layout.buttons_y))
            self._render_navigation_controls(
                layout,
                window_width,
                can_advance,
                on_close,
                test_id_prefix,
                len(steps),
            )

    @staticmethod
    def _requirements_satisfied(
        step: TutorialStep,
        panel_visible_cb: Callable[[str], bool] | None,
    ) -> bool:
        if panel_visible_cb is None or not step.required_panel_states:
            return True
        return all(
            bool(panel_visible_cb(panel_id)) is expected_visible
            for panel_id, expected_visible in step.required_panel_states
        )

    @classmethod
    def _status_text(
        cls,
        step: TutorialStep,
        panel_visible_cb: Callable[[str], bool],
    ) -> str:
        return (
            "Ready"
            if cls._requirements_satisfied(step, panel_visible_cb)
            else "Waiting for the requested panel state"
        )

    def _resolve_layout(
        self,
        step: TutorialStep,
        panel_visible_cb: Callable[[str], bool] | None,
        window_width: float,
    ) -> tuple[TutorialGuideLayout, str | None, bool]:
        can_advance = self._requirements_satisfied(step, panel_visible_cb)
        status = (
            self._status_text(step, panel_visible_cb)
            if step.required_panel_states and panel_visible_cb is not None
            else None
        )
        wrap_width = max(1.0, window_width - TUTORIAL_GUIDE_HORIZONTAL_PADDING)
        body_height = float(imgui.calc_text_size(step.body, wrap_width=wrap_width).y)
        status_height = (
            float(imgui.calc_text_size(status, wrap_width=wrap_width).y)
            if status is not None
            else None
        )
        return (
            resolve_tutorial_guide_layout(body_height, status_height, window_width),
            status,
            can_advance,
        )

    def _render_navigation_controls(
        self,
        layout: TutorialGuideLayout,
        window_width: float,
        can_advance: bool,
        on_close: Callable[[], None],
        test_id_prefix: str,
        step_count: int,
    ) -> None:
        if layout.stack_buttons:
            button_width = max(1.0, window_width - 24.0)
            if imgui.button(
                "BACK TO MENU", (button_width, TUTORIAL_GUIDE_BUTTON_HEIGHT),
                test_id=f"{test_id_prefix}.tutorial.close",
            ):
                on_close()
            imgui.set_cursor_pos((12.0, layout.buttons_y + 34.0))
            if self._render_previous_button(button_width, test_id_prefix):
                self._step_index -= 1
            imgui.set_cursor_pos((12.0, layout.buttons_y + 68.0))
            next_clicked = self._render_next_button(
                button_width, can_advance, test_id_prefix, step_count
            )
        else:
            if imgui.button(
                "BACK TO MENU", (124.0, TUTORIAL_GUIDE_BUTTON_HEIGHT),
                test_id=f"{test_id_prefix}.tutorial.close",
            ):
                on_close()
            imgui.same_line()
            if self._render_previous_button(108.0, test_id_prefix):
                self._step_index -= 1
            imgui.same_line()
            next_clicked = self._render_next_button(
                108.0, can_advance, test_id_prefix, step_count
            )

        if next_clicked:
            if self._step_index == step_count - 1:
                on_close()
            else:
                self._step_index += 1

    def _render_previous_button(self, width: float, test_id_prefix: str) -> bool:
        imgui.begin_disabled(self._step_index == 0)
        try:
            return imgui.button(
                "PREVIOUS", (width, TUTORIAL_GUIDE_BUTTON_HEIGHT),
                test_id=f"{test_id_prefix}.tutorial.previous",
            )
        finally:
            imgui.end_disabled()

    def _render_next_button(
        self,
        width: float,
        can_advance: bool,
        test_id_prefix: str,
        step_count: int,
    ) -> bool:
        next_label = "FINISH" if self._step_index == step_count - 1 else "NEXT"
        imgui.begin_disabled(not can_advance)
        try:
            return imgui.button(
                next_label, (width, TUTORIAL_GUIDE_BUTTON_HEIGHT),
                test_id=f"{test_id_prefix}.tutorial.next",
            )
        finally:
            imgui.end_disabled()
