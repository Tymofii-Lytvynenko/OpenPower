from __future__ import annotations

import math

from imgui_bundle import icons_fontawesome_6
from src.client.ui.core.instrumented_imgui import imgui

from src.client.renderers.flag_renderer import FlagRenderer
from src.shared.actions import ActionRespondToRandomEvent, ActionSetRandomEventControls
from src.client.ui.core.containers import WindowManager
from src.client.ui.core.gml_widgets import GMLWidgets
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.core.primitives import UIPrimitives
from src.client.ui.core.theme import GAMETHEME, with_alpha
from src.client.ui.panels.service.event_feed_presenter import (
    EventCategory,
    EventFeedItem,
    EventFeedPresenter,
)
from src.client.ui.panels.shared.panel_widgets import draw_empty_state


class NewsPanel:
    _FILTERS = (
        (EventCategory.POLITICAL, "togFilterPolitic", icons_fontawesome_6.ICON_FA_BUILDING_COLUMNS, "Political events"),
        (EventCategory.ECONOMIC, "togFilterEconomic", icons_fontawesome_6.ICON_FA_SACK_DOLLAR, "Economic events"),
        (EventCategory.MILITARY, "togFilterMilitary", icons_fontawesome_6.ICON_FA_PERSON_MILITARY_RIFLE, "Military events"),
        (EventCategory.DEMOGRAPHIC, "togFilterDemographic", icons_fontawesome_6.ICON_FA_USERS, "Demographic events"),
    )

    _CATEGORY_COLORS = {
        EventCategory.GENERAL: GAMETHEME.colors.info,
        EventCategory.DEMOGRAPHIC: GAMETHEME.colors.demographics,
        EventCategory.MILITARY: GAMETHEME.colors.military,
        EventCategory.POLITICAL: GAMETHEME.colors.politics,
        EventCategory.ECONOMIC: GAMETHEME.colors.economy,
    }

    def __init__(self):
        self._presenter = EventFeedPresenter()
        self._flag_renderer = FlagRenderer()
        self._enabled_filters = {category for category, *_ in self._FILTERS}
        self._selected_event_id: str | None = None

    def render(self, state, context: PanelRenderContext) -> bool:
        viewport = imgui.get_io().display_size
        width, height = 488.0, 199.0
        x = max(0.0, (float(viewport.x) - width) / 2.0)
        y = max(0.0, (float(viewport.y) - height) / 2.0)
        with WindowManager.window(
            "EVENT FEED",
            x=x,
            y=y,
            w=width,
            h=height,
            closable=False,
            flags=imgui.WindowFlags_.no_title_bar,
            padding=(6.0, 4.0),
            test_id="news.panel",
            follow_position=True,
        ) as is_open:
            if not is_open:
                return False
            self._render_content(state, context)
            return True

    def _render_content(self, state, context: PanelRenderContext) -> None:
        ui = GMLWidgets("Event_Log/frmInner")
        all_items = self._presenter.items(state)
        counts = {category: 0 for category in EventCategory}
        for item in all_items:
            counts[item.category] += 1

        # Event_Log has no source title frame; the HUD news toggle is its close affordance.
        imgui.push_style_var(imgui.StyleVar_.window_padding, (4.0, 4.0))
        try:
            # The source list starts one GML item-spacing below the content origin.
            imgui.dummy((0.0, 0.0))
            child_open = imgui.begin_child(
                "event_feed_pool",
                (446.0, 185.0),
                True,
                test_id="news.events",
            )
            visible_items = [
                item for item in all_items
                if item.category is EventCategory.GENERAL or item.category in self._enabled_filters
            ]
            if self._selected_event_id not in {item.id for item in visible_items}:
                self._selected_event_id = None
            if child_open:
                if visible_items:
                    for item in visible_items:
                        self._render_item(item, context)
                else:
                    draw_empty_state("No events match the selected filters.")
            imgui.dummy((0.0, 0.0))
            imgui.end_child()
        finally:
            imgui.pop_style_var()

        self._render_filters(ui, counts)
        if ui.button_at(
            "btnGoto",
            icons_fontawesome_6.ICON_FA_GEAR,
            "news.random_event_settings",
            offset=(0.0, -63.0),
            size=(27.0, 21.0),
            tooltip="Random event controls",
            padding=(1.0, 0.0),
        ):
            imgui.open_popup("NewsRandomEventControls")

        if imgui.begin_popup("NewsRandomEventControls", test_id="news.controls.popup"):
            self._render_event_controls(state, context)
            imgui.end_popup()

        selected = next(
            (item for item in visible_items if item.id == self._selected_event_id),
            None,
        )
        if ui.button(
            "btnGoto",
            icons_fontawesome_6.ICON_FA_LOCATION_CROSSHAIRS,
            "news.goto",
            enabled=selected is not None and selected.region_id is not None,
            tooltip="Focus the selected event's region",
            dynamic_enabled=True,
        ) and selected is not None and selected.region_id is not None:
            if context.on_focus_request is not None:
                context.on_focus_request(int(selected.region_id))

    def _render_item(self, item: EventFeedItem, context: PanelRenderContext) -> None:
        row_height = 54.0 if item.response_options and item.status == "active" else 30.0
        available_width = imgui.get_content_region_avail().x
        local_start = imgui.get_cursor_pos()
        screen_start = imgui.get_cursor_screen_pos()
        color = self._CATEGORY_COLORS[item.category]
        draw_list = imgui.get_window_draw_list()
        is_selected = self._selected_event_id == item.id

        if is_selected:
            draw_list.add_rect_filled(
                screen_start,
                (screen_start.x + available_width, screen_start.y + row_height),
                imgui.get_color_u32(with_alpha(GAMETHEME.colors.accent, 0.22)),
            )

        draw_list.add_rect_filled(
            screen_start,
            (screen_start.x + 3.0, screen_start.y + row_height),
            imgui.get_color_u32(color),
        )

        content_x = local_start.x + 9.0
        content_y = local_start.y + 5.0
        if item.country_tag:
            imgui.set_cursor_pos((content_x, content_y + 1.0))
            self._flag_renderer.draw_flag(item.country_tag, 27.0, 18.0)
        else:
            draw_list.add_text(
                (screen_start.x + 15.0, screen_start.y + 7.0),
                imgui.get_color_u32(GAMETHEME.colors.text_dim),
                icons_fontawesome_6.ICON_FA_GLOBE,
            )

        tag = item.country_tag or "WORLD"
        tag_x = content_x + 35.0
        tag_offset = tag_x - local_start.x
        draw_list.add_text(
            (screen_start.x + tag_offset, screen_start.y + 7.0),
            imgui.get_color_u32(color),
            tag,
        )
        tag_width = max(34.0, imgui.calc_text_size(tag).x + 8.0)
        summary_x = tag_offset + tag_width
        summary_width = max(0.0, available_width - summary_x - 8.0)
        summary = UIPrimitives.fit_text(item.summary, summary_width)
        draw_list.add_text(
            (screen_start.x + summary_x, screen_start.y + 7.0),
            imgui.get_color_u32(GAMETHEME.colors.text_main),
            summary,
        )

        imgui.set_cursor_pos(local_start)
        response_actions_visible = bool(
            item.response_options and item.status == "active" and context.net_client is not None
        )
        selection_height = row_height - 20.0 if response_actions_visible else row_height
        if imgui.invisible_button(
            f"##event_feed_item_{item.id}",
            (available_width, selection_height),
            test_id=f"news.item.{item.id}",
        ):
            self._selected_event_id = item.id
        if imgui.is_item_hovered():
            self._render_item_tooltip(item)

        if response_actions_visible:
            imgui.set_cursor_pos((local_start.x + 44.0, local_start.y + 31.0))
            for option_index, (response_id, cost) in enumerate(item.response_options):
                if option_index:
                    imgui.same_line()
                if imgui.small_button(
                    f"{response_id} · {cost:,.0f}##{item.id}-{response_id}",
                    test_id=f"news.response.{item.id}.{response_id}",
                ):
                    context.net_client.send_action(
                        ActionRespondToRandomEvent(
                            player_id=context.net_client.player_id,
                            event_id=item.id.removeprefix("instance:"),
                            response_id=response_id,
                            country_tag=item.country_tag,
                        )
                    )

        separator_y = screen_start.y + row_height
        draw_list.add_line(
            (screen_start.x + 8.0, separator_y),
            (screen_start.x + available_width, separator_y),
            imgui.get_color_u32(with_alpha(GAMETHEME.colors.text_dim, 0.16)),
        )
        imgui.set_cursor_pos((local_start.x, local_start.y + row_height + 3.0))

    def _render_filters(self, ui: GMLWidgets, counts: dict[EventCategory, int]) -> None:
        for category, component_id, icon, tooltip in self._FILTERS:
            is_enabled = category in self._enabled_filters
            changed, is_enabled = ui.toggle(
                component_id,
                is_enabled,
                test_id=f"news.filter.{category.value}",
                icon=icon,
                color=self._CATEGORY_COLORS[category],
                tooltip=f"{tooltip}: {counts[category]}",
            )
            if changed:
                if is_enabled:
                    self._enabled_filters.add(category)
                else:
                    self._enabled_filters.discard(category)

    @staticmethod
    def _render_event_controls(state, context: PanelRenderContext) -> None:
        client = context.net_client
        if client is None:
            return

        enabled = NewsPanel._read_bool(state.globals.get("random_events_enabled"), True)
        if imgui.button(
            f"Random events: {'ON' if enabled else 'OFF'}",
            test_id="news.rules.enabled",
        ):
            client.send_action(
                ActionSetRandomEventControls(
                    player_id=client.player_id,
                    enabled=not enabled,
                )
            )
        imgui.same_line()
        multiplier = NewsPanel._read_frequency_multiplier(
            state.globals.get("random_event_frequency_multiplier")
        )
        if imgui.small_button("−##event_frequency_down", test_id="news.rules.frequency.down"):
            client.send_action(
                ActionSetRandomEventControls(
                    player_id=client.player_id,
                    frequency_multiplier=max(0.0, round(multiplier - 0.25, 2)),
                )
            )
        imgui.same_line()
        imgui.text(f"Frequency {multiplier:.2f}×")
        imgui.same_line()
        if imgui.small_button("+##event_frequency_up", test_id="news.rules.frequency.up"):
            client.send_action(
                ActionSetRandomEventControls(
                    player_id=client.player_id,
                    frequency_multiplier=min(4.0, round(multiplier + 0.25, 2)),
                )
            )
        seed = NewsPanel._read_seed(
            state.globals.get("random_event_seed"), state.determinism.seed
        )
        imgui.same_line()
        if imgui.small_button("−##event_seed_down", test_id="news.rules.seed.down"):
            client.send_action(
                ActionSetRandomEventControls(
                    player_id=client.player_id,
                    seed=max(0, seed - 1),
                )
            )
        imgui.same_line()
        imgui.text(f"Seed {seed}")
        imgui.same_line()
        if imgui.small_button("+##event_seed_up", test_id="news.rules.seed.up"):
            client.send_action(
                ActionSetRandomEventControls(
                    player_id=client.player_id,
                    seed=min((1 << 63) - 1, seed + 1),
                )
            )

        imgui.separator()
        controls = state.tables.get("random_event_controls")
        if controls is None or controls.is_empty():
            return
        for control in controls.sort("category").iter_rows(named=True):
            category = str(control.get("category") or "")
            category_enabled = NewsPanel._read_bool(control.get("enabled"), True)
            imgui.same_line()
            if imgui.small_button(
                f"{category.title()}: {'ON' if category_enabled else 'OFF'}##event-category-{category}",
                test_id=f"news.rules.category.{category}",
            ):
                client.send_action(
                    ActionSetRandomEventControls(
                        player_id=client.player_id,
                        category=category,
                        category_enabled=not category_enabled,
                    )
                )

    @staticmethod
    def _read_bool(value: object, default: bool) -> bool:
        return value if isinstance(value, bool) else default

    @staticmethod
    def _read_frequency_multiplier(value: object) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError, OverflowError):
            return 1.0
        return max(0.0, min(4.0, parsed)) if math.isfinite(parsed) else 1.0

    @staticmethod
    def _read_seed(value: object, fallback: int) -> int:
        try:
            parsed = int(value) if value is not None else int(fallback)
        except (TypeError, ValueError, OverflowError):
            parsed = int(fallback)
        return max(0, min((1 << 63) - 1, parsed))

    @staticmethod
    def _render_item_tooltip(item: EventFeedItem) -> None:
        imgui.begin_tooltip()
        imgui.text(item.headline)
        if item.body:
            imgui.separator()
            imgui.push_text_wrap_pos(imgui.get_font_size() * 30.0)
            imgui.text_unformatted(item.body)
            imgui.pop_text_wrap_pos()
        if item.created_at:
            imgui.text_disabled(item.created_at)
        imgui.end_tooltip()
