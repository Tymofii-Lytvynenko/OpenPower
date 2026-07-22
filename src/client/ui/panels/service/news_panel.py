from __future__ import annotations

from imgui_bundle import imgui

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.core.theme import GAMETHEME
from src.client.ui.panels.service.feed_presenter import FeedPresenter
from src.client.ui.panels.shared.panel_widgets import draw_empty_state


class NewsPanel:
    def __init__(self):
        self._presenter = FeedPresenter()
        self._selected_news_id: str = ""

    def render(self, state, context: PanelRenderContext) -> bool:
        with WindowManager.window("NEWS LOG", x=1180, y=130, w=600, h=460) as is_open:
            if not is_open:
                return False
            self._render_content(state, context.target_tag)
            return True

    def _render_content(self, state, country_tag: str) -> None:
        news_items = self._presenter.news_for_country(state, country_tag)
        if not news_items:
            draw_empty_state("No news bulletins are available yet.")
            return

        if self._selected_news_id not in {str(row.get("id") or "") for row in news_items}:
            self._selected_news_id = str(news_items[0].get("id") or "")

        imgui.columns(2, "news_columns", True)
        imgui.set_column_width(0, 260.0)
        imgui.begin_child("news_list", (0.0, -1.0), True)
        for row in news_items:
            news_id = str(row.get("id") or "")
            headline = str(row.get("headline") or "Untitled bulletin")
            severity = str(row.get("severity") or "info").upper()
            if imgui.selectable(f"{headline}##{news_id}", self._selected_news_id == news_id)[0]:
                self._selected_news_id = news_id
            imgui.text_disabled(severity)
            imgui.separator()
        imgui.end_child()

        imgui.next_column()
        selected = next((row for row in news_items if str(row.get("id") or "") == self._selected_news_id), news_items[0])
        imgui.text_colored(GAMETHEME.colors.text_main, str(selected.get("headline") or "Untitled bulletin"))
        imgui.text_disabled(str(selected.get("created_at") or ""))
        imgui.separator()
        imgui.push_text_wrap_pos(0.0)
        imgui.text(str(selected.get("body") or ""))
        imgui.pop_text_wrap_pos()
        imgui.columns(1)
