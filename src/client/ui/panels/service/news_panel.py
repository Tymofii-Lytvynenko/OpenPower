from __future__ import annotations

import math

from imgui_bundle import icons_fontawesome_6, imgui

from src.client.renderers.flag_renderer import FlagRenderer
from src.shared.actions import ActionRespondToRandomEvent, ActionSetRandomEventControls
from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.core.theme import GAMETHEME, with_alpha
from src.client.ui.panels.service.event_feed_presenter import (
    EventCategory,
    EventFeedItem,
    EventFeedPresenter,
)
from src.client.ui.panels.shared.panel_widgets import draw_empty_state


class NewsPanel:
    _FILTERS = (
        (EventCategory.GENERAL, icons_fontawesome_6.ICON_FA_GLOBE, "General events"),
        (EventCategory.MILITARY, icons_fontawesome_6.ICON_FA_PERSON_MILITARY_RIFLE, "Military events"),
        (EventCategory.POLITICAL, icons_fontawesome_6.ICON_FA_BUILDING_COLUMNS, "Political events"),
        (EventCategory.ECONOMIC, icons_fontawesome_6.ICON_FA_SACK_DOLLAR, "Economic events"),
    )

    _CATEGORY_COLORS = {
        EventCategory.GENERAL: GAMETHEME.colors.info,
        EventCategory.MILITARY: GAMETHEME.colors.military,
        EventCategory.POLITICAL: GAMETHEME.colors.politics,
        EventCategory.ECONOMIC: GAMETHEME.colors.economy,
    }

    def __init__(self):
        self._presenter = EventFeedPresenter()
        self._flag_renderer = FlagRenderer()
        self._selected_category: EventCategory | None = None

    def render(self, state, context: PanelRenderContext) -> bool:
        with WindowManager.window("EVENT FEED", x=1120, y=120, w=700, h=320) as is_open:
            if not is_open:
                return False
            self._render_content(state, context)
            return True

    def _render_content(self, state, context: PanelRenderContext) -> None:
        self._render_event_controls(state, context)
        all_items = self._presenter.items(state)
        counts = {category: 0 for category in EventCategory}
        for item in all_items:
            counts[item.category] += 1

        rail_width = 44.0
        spacing = imgui.get_style().item_spacing.x
        list_width = max(1.0, imgui.get_content_region_avail().x - rail_width - spacing)

        imgui.push_style_var(imgui.StyleVar_.window_padding, (4.0, 4.0))
        imgui.begin_child("event_feed_pool", (list_width, 0.0), True)
        visible_items = (
            all_items
            if self._selected_category is None
            else [item for item in all_items if item.category is self._selected_category]
        )
        if visible_items:
            for item in visible_items:
                self._render_item(item, context)
        else:
            draw_empty_state("No events match the selected category.")
        imgui.end_child()

        imgui.same_line()
        imgui.begin_child("event_feed_filters", (rail_width, 0.0), True)
        self._render_filters(counts)
        imgui.end_child()
        imgui.pop_style_var()

    def _render_item(self, item: EventFeedItem, context: PanelRenderContext) -> None:
        row_height = 54.0 if item.response_options and item.status == "active" else 30.0
        available_width = imgui.get_content_region_avail().x
        local_start = imgui.get_cursor_pos()
        screen_start = imgui.get_cursor_screen_pos()
        color = self._CATEGORY_COLORS[item.category]
        draw_list = imgui.get_window_draw_list()

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
        draw_list.add_text(
            (screen_start.x + tag_x - local_start.x, screen_start.y + 7.0),
            imgui.get_color_u32(color),
            tag,
        )
        tag_width = max(34.0, imgui.calc_text_size(tag).x + 8.0)
        draw_list.add_text(
            (screen_start.x + tag_x - local_start.x + tag_width, screen_start.y + 7.0),
            imgui.get_color_u32(GAMETHEME.colors.text_main),
            item.summary,
        )

        imgui.set_cursor_pos(local_start)
        imgui.invisible_button(f"##event_feed_item_{item.id}", (available_width, row_height))
        if imgui.is_item_hovered():
            self._render_item_tooltip(item)

        if item.response_options and item.status == "active" and context.net_client is not None:
            imgui.set_cursor_pos((local_start.x + 44.0, local_start.y + 31.0))
            for option_index, (response_id, cost) in enumerate(item.response_options):
                if option_index:
                    imgui.same_line()
                if imgui.small_button(f"{response_id} · {cost:,.0f}##{item.id}-{response_id}"):
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

    def _render_filters(self, counts: dict[EventCategory, int]) -> None:
        button_size = (30.0, 30.0)
        for category, icon, tooltip in self._FILTERS:
            is_active = self._selected_category is category
            color = self._CATEGORY_COLORS[category]
            if is_active:
                imgui.push_style_color(imgui.Col_.button, with_alpha(color, 0.65))
                imgui.push_style_color(imgui.Col_.button_hovered, with_alpha(color, 0.8))

            if imgui.button(f"{icon}##event_filter_{category.value}", button_size):
                self._selected_category = None if is_active else category

            if is_active:
                imgui.pop_style_color(2)

            if imgui.is_item_hovered():
                suffix = "; click again to show all" if is_active else ""
                imgui.set_tooltip(f"{tooltip}: {counts[category]}{suffix}")

    @staticmethod
    def _render_event_controls(state, context: PanelRenderContext) -> None:
        client = context.net_client
        if client is None:
            return

        enabled = NewsPanel._read_bool(state.globals.get("random_events_enabled"), True)
        if imgui.button(f"Random events: {'ON' if enabled else 'OFF'}"):
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
        if imgui.small_button(f"−##event_frequency_down"):
            client.send_action(
                ActionSetRandomEventControls(
                    player_id=client.player_id,
                    frequency_multiplier=max(0.0, round(multiplier - 0.25, 2)),
                )
            )
        imgui.same_line()
        imgui.text(f"Frequency {multiplier:.2f}×")
        imgui.same_line()
        if imgui.small_button(f"+##event_frequency_up"):
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
        if imgui.small_button(f"−##event_seed_down"):
            client.send_action(
                ActionSetRandomEventControls(
                    player_id=client.player_id,
                    seed=max(0, seed - 1),
                )
            )
        imgui.same_line()
        imgui.text(f"Seed {seed}")
        imgui.same_line()
        if imgui.small_button(f"+##event_seed_up"):
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
                f"{category.title()}: {'ON' if category_enabled else 'OFF'}##event-category-{category}"
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
