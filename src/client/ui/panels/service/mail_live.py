"""Mail view with actionable treaty proposals."""

from __future__ import annotations

import polars as pl
from imgui_bundle import imgui

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.core.theme import GAMETHEME
from src.client.ui.panels.service.feed_presenter import FeedPresenter
from src.client.ui.panels.shared.panel_widgets import draw_empty_state
from src.shared.actions import ActionRespondTreaty
from src.shared.treaties import normalize_country_tags


class LiveMailPanel:
    """Keeps the treaty inbox in the mail surface referenced by the ruleset."""

    def __init__(self) -> None:
        self._presenter = FeedPresenter()
        self._selected_message_id = ""

    def render(self, state, context: PanelRenderContext) -> bool:
        with WindowManager.window("MAIL", x=1220, y=100, w=540, h=420) as is_open:
            if not is_open:
                return False
            self._render_content(state, context)
            return True

    def _render_content(self, state, context: PanelRenderContext) -> None:
        country_tag = str(context.target_tag or "").upper()
        messages = self._presenter.messages_for_country(state, country_tag)
        pending = self._pending_for_country(state, country_tag)
        if not messages and not pending:
            draw_empty_state("No cabinet mail is available for the selected country yet.")
            return

        imgui.begin_child("mail_messages", (0.0, 200.0), True)
        if messages:
            for row in messages:
                message_id = str(row.get("id") or "")
                unread = not bool(row.get("is_read", False))
                label = f"{'[NEW] ' if unread else ''}{row.get('subject') or 'Untitled dispatch'}##{message_id}"
                if imgui.selectable(label, self._selected_message_id == message_id)[0]:
                    self._selected_message_id = message_id
                imgui.text_disabled(str(row.get("category") or "system").upper())
                imgui.separator()
        imgui.end_child()

        if messages:
            selected = next((row for row in messages if str(row.get("id") or "") == self._selected_message_id), messages[0])
            imgui.text_colored(GAMETHEME.colors.text_main, str(selected.get("subject") or "Untitled dispatch"))
            imgui.text_wrapped(str(selected.get("body") or ""))

        if pending:
            imgui.separator()
            imgui.text("TREATY PROPOSALS")
            for proposal in pending:
                self._render_proposal(proposal, context, country_tag)

    def _render_proposal(self, proposal: dict, context: PanelRenderContext, country_tag: str) -> None:
        proposal_id = str(proposal.get("id") or "")
        imgui.text(f"{proposal.get('title') or proposal_id} ({str(proposal.get('treaty_type') or '').replace('_', ' ').title()})")
        imgui.text_disabled(str(proposal.get("terms") or "No additional terms."))
        required = set(normalize_country_tags(proposal.get("required_responses")))
        accepted = set(normalize_country_tags(proposal.get("accepted_members")))
        if context.net_client is not None and context.is_own_country and country_tag in required and country_tag not in accepted:
            if imgui.button(f"ACCEPT##mail-{proposal_id}", (110.0, 24.0)):
                context.net_client.send_action(ActionRespondTreaty(context.net_client.player_id, proposal_id, country_tag, True))
            imgui.same_line()
            if imgui.button(f"REJECT##mail-{proposal_id}", (110.0, 24.0)):
                context.net_client.send_action(ActionRespondTreaty(context.net_client.player_id, proposal_id, country_tag, False))

    def _pending_for_country(self, state, country_tag: str) -> list[dict]:
        pending = state.tables.get("pending_treaties")
        if pending is None or pending.is_empty() or "required_responses" not in pending.columns:
            return []
        return [
            row for row in pending.to_dicts()
            if country_tag in set(normalize_country_tags(row.get("required_responses")))
        ]
