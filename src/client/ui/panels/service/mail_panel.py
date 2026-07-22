from __future__ import annotations

from imgui_bundle import imgui

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.core.theme import GAMETHEME
from src.client.ui.panels.service.feed_presenter import FeedPresenter
from src.client.ui.panels.shared.panel_widgets import draw_empty_state


class MailPanel:
    def __init__(self):
        self._presenter = FeedPresenter()
        self._selected_message_id: str = ""

    def render(self, state, context: PanelRenderContext) -> bool:
        with WindowManager.window("MAIL", x=1220, y=100, w=540, h=420) as is_open:
            if not is_open:
                return False
            self._render_content(state, context.target_tag)
            return True

    def _render_content(self, state, country_tag: str) -> None:
        messages = self._presenter.messages_for_country(state, country_tag)
        if not messages:
            draw_empty_state("No cabinet mail is available for the selected country yet.")
            return

        if self._selected_message_id not in {str(row.get("id") or "") for row in messages}:
            self._selected_message_id = str(messages[0].get("id") or "")

        imgui.columns(2, "mail_columns", True)
        imgui.set_column_width(0, 245.0)
        imgui.begin_child("mail_list", (0.0, -1.0), True)
        for row in messages:
            message_id = str(row.get("id") or "")
            subject = str(row.get("subject") or "Untitled dispatch")
            category = str(row.get("category") or "system").upper()
            unread = not bool(row.get("is_read", False))
            label = f"{'[NEW] ' if unread else ''}{subject}##{message_id}"

            if imgui.selectable(label, self._selected_message_id == message_id)[0]:
                self._selected_message_id = message_id

            imgui.text_disabled(category)
            imgui.separator()
        imgui.end_child()

        imgui.next_column()
        selected = next((row for row in messages if str(row.get("id") or "") == self._selected_message_id), messages[0])
        imgui.text_colored(GAMETHEME.colors.text_main, str(selected.get("subject") or "Untitled dispatch"))
        imgui.text_disabled(str(selected.get("created_at") or ""))
        imgui.separator()
        imgui.push_text_wrap_pos(0.0)
        imgui.text(str(selected.get("body") or ""))
        imgui.pop_text_wrap_pos()
        imgui.columns(1)

# The original mail renderer remains import-compatible while proposals become actionable.
from src.client.ui.panels.service.mail_live import LiveMailPanel
MailPanel = LiveMailPanel
