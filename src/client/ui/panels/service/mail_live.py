"""Source-sized inbox composed from OpenPower messages and domain dispatches."""

from __future__ import annotations

from src.client.ui.components.hud.main_bar_geometry import main_bar_bounds
from src.client.ui.core.containers import WindowManager
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.core.theme import GAMETHEME
from src.client.ui.core.gml_widgets import GMLWidgets
from src.client.ui.layouts.gml_layout import get_gml_layout
from src.client.ui.layouts.gml_rows import gml_row
from src.client.ui.panels.service.feed_presenter import FeedPresenter
from src.client.ui.panels.service.journal_dispatches import journal_dispatches
from src.client.ui.panels.service.mail_inbox_state import MailInboxState
from src.client.ui.panels.shared.panel_widgets import draw_empty_state
from src.shared.actions import ActionRespondTreaty
from src.shared.treaties import normalize_country_tags


class LiveMailPanel:
    """Keep REFERENCE's inbox geometry while routing current OpenPower mail items."""

    def __init__(
        self,
        open_treaty_cb=None,
        open_dispatch_cb=None,
        mail_inbox_state: MailInboxState | None = None,
        close_mail_cb=None,
    ) -> None:
        self._inbox_state = mail_inbox_state or MailInboxState()
        self._presenter = FeedPresenter(self._inbox_state)
        self._open_treaty_cb = open_treaty_cb
        self._open_dispatch_cb = open_dispatch_cb
        self._close_mail_cb = close_mail_cb
        self._message_detail: dict | None = None
        self._message_detail_pending = False
        self._proposal_detail: dict | None = None

    def render(self, state, context: PanelRenderContext) -> bool:
        viewport = imgui.get_main_viewport()
        bounds = main_bar_bounds(
            float(viewport.size.x),
            float(viewport.size.y),
            float(viewport.pos.x),
            float(viewport.pos.y),
        )
        layout = get_gml_layout("Mail_Window")
        x = bounds.x + 190.0
        y = bounds.y - bounds.height - layout.height + 10.0
        viewport_left = float(viewport.pos.x)
        viewport_top = float(viewport.pos.y)
        # Preserve GML dimensions while keeping the source-anchored window reachable on compact viewports.
        x = min(max(x, viewport_left), max(viewport_left, viewport_left + viewport.size.x - layout.width))
        y = min(max(y, viewport_top), max(viewport_top, viewport_top + viewport.size.y - layout.height))
        with WindowManager.window(
            "MAIL",
            x=x,
            y=y,
            w=layout.width,
            h=layout.height,
            closable=False,
            flags=imgui.WindowFlags_.no_title_bar,
            test_id="mail.panel",
            padding=(0.0, 0.0),
        ) as is_open:
            if not is_open:
                return False
            if (
                imgui.is_window_focused()
                and imgui.is_key_pressed(imgui.Key.escape, False)
                and not imgui.is_popup_open("", imgui.PopupFlags_.any_popup_id)
            ):
                return False
            self._render_content(state, context)
            return True

    def _render_content(self, state, context: PanelRenderContext) -> None:
        country_tag = str(context.target_tag or "").upper()
        items = self._items_for_country(state, country_tag)
        ui_root = "Mail_Window/frmInner"
        ui = GMLWidgets(ui_root)
        child_open = imgui.begin_child(
            "mail_list",
            (475.0, 180.0),
            True,
            test_id="mail.items",
            gml_id=f"{ui_root}/lstMail",
        )
        if child_open:
            if not items:
                draw_empty_state("No cabinet mail is available for the selected country yet.")
            else:
                for item in items:
                    self._render_mail_row(item, items, country_tag, context)
        imgui.dummy((0.0, 0.0))
        imgui.end_child()

        if ui.button("btnDeleteAll", "DELETE ALL", "mail.delete_all"):
            self._dismiss_items(items, country_tag)
            self._close_if_empty(items)

        self._render_message_detail()
        self._render_proposal_detail(context, country_tag)

    def _items_for_country(self, state, country_tag: str) -> list[dict]:
        items: list[dict] = []
        for dispatch in journal_dispatches(
            state,
            country_tag,
            self._inbox_state.dismissed_region_event_ids(country_tag),
        ):
            if not self._inbox_state.is_dismissed("dispatch", dispatch.get("id")):
                items.append({"inbox_kind": "dispatch", **dispatch})

        for message in self._presenter.messages_for_country(state, country_tag):
            items.append({"inbox_kind": "message", **message})

        for proposal in self._pending_for_country(state, country_tag):
            if not self._inbox_state.is_dismissed("proposal", proposal.get("id")):
                items.append({"inbox_kind": "proposal", **proposal})
        return items

    def _render_mail_row(
        self,
        item: dict,
        items: list[dict],
        country_tag: str,
        context: PanelRenderContext,
    ) -> None:
        item_id = str(item.get("id") or "")
        kind = str(item["inbox_kind"])
        subject = str(item.get("subject") or item.get("title") or "Untitled dispatch")
        identity = MailInboxState.key(kind, item_id)
        with gml_row("lstMailItem", identity) as row:
            row.text(
                "txtMail",
                subject,
                test_id=f"mail.item.{identity}.subject",
                tooltip=subject,
            )
            if row.button(
                "btnView",
                "VIEW",
                self._view_test_id(item),
                tooltip="Open this message",
            ):
                self._view_item(item, context)
                # REFERENCE consumes a mail row after its view callback runs.
                self._dismiss_item(item, country_tag)
                self._close_if_empty(items)
            if row.button(
                "btnDelete",
                "DELETE",
                f"mail.item.{identity}.delete",
                tooltip="Dismiss this inbox item for this game session",
            ):
                self._dismiss_item(item, country_tag)
                self._close_if_empty(items)

    def _dismiss_item(self, item: dict, country_tag: str) -> None:
        kind = str(item["inbox_kind"])
        item_id = item.get("id")
        self._inbox_state.dismiss(kind, item_id)
        if kind == "dispatch" and item.get("kind") == "region_control":
            payload = item.get("payload") or {}
            self._inbox_state.dismiss_region_events(country_tag, payload.get("event_ids", ()))

    @staticmethod
    def _view_test_id(item: dict) -> str:
        kind = str(item["inbox_kind"])
        item_id = str(item.get("id") or "")
        if kind == "dispatch":
            return f"mail.dispatch.{item_id}"
        if kind == "proposal":
            return f"mail.treaty.{item_id}.view"
        return f"mail.message.{item_id}.view"

    def _view_item(self, item: dict, context: PanelRenderContext) -> None:
        kind = str(item["inbox_kind"])
        if kind == "dispatch" and self._open_dispatch_cb is not None:
            self._open_dispatch_cb(item)
        elif kind == "proposal":
            self._proposal_detail = item
            imgui.open_popup("MailTreatyProposal")
        else:
            subject = str(item.get("subject") or "Untitled dispatch")
            body = str(item.get("body") or "")
            if context.on_notice is not None and body.strip():
                context.on_notice(subject, body)
            else:
                self._message_detail = item
                self._message_detail_pending = True

    def _render_message_detail(self) -> None:
        if self._message_detail is None:
            return
        message = self._message_detail
        if self._message_detail_pending:
            # Open after the row's scoped ImGui ID stack has unwound so begin_popup resolves the same ID.
            imgui.open_popup("MailMessageDetails")
            self._message_detail_pending = False
        if not imgui.begin_popup("MailMessageDetails", test_id="mail.message.details"):
            self._message_detail = None
            return

        imgui.text_colored(
            GAMETHEME.colors.text_main,
            str(message.get("subject") or "Untitled dispatch"),
            test_id="mail.message.details.subject",
        )
        created_at = str(message.get("created_at") or "")
        if created_at:
            imgui.text_disabled(created_at)
        imgui.separator()
        imgui.push_text_wrap_pos(0.0)
        imgui.text_unformatted(
            str(message.get("body") or ""),
            test_id="mail.message.details.body",
        )
        imgui.pop_text_wrap_pos()
        if imgui.button(
            "Close##mail_message_details",
            test_id="mail.message.details.close",
        ):
            imgui.close_current_popup()
            self._message_detail = None
        imgui.end_popup()

    def _render_proposal_detail(self, context: PanelRenderContext, country_tag: str) -> None:
        proposal = self._proposal_detail
        if proposal is None:
            return
        if imgui.begin_popup("MailTreatyProposal", test_id="mail.treaty.proposal.details"):
            proposal_id = str(proposal.get("id") or "")
            imgui.text(str(proposal.get("title") or proposal_id))
            imgui.text_disabled(str(proposal.get("terms") or "No additional terms."))
            if self._open_treaty_cb is not None and imgui.button(
                f"DETAILS##mail-{proposal_id}",
                test_id=f"mail.treaty.{proposal_id}.details",
            ):
                self._open_treaty_cb(proposal_id)

            required = set(normalize_country_tags(proposal.get("required_responses")))
            accepted = set(normalize_country_tags(proposal.get("accepted_members")))
            can_respond = (
                context.net_client is not None
                and context.is_own_country
                and country_tag in required
                and country_tag not in accepted
            )
            if can_respond:
                if imgui.button(f"ACCEPT##mail-{proposal_id}", (110.0, 24.0),
                                test_id=f"mail.treaty.{proposal_id}.accept"):
                    context.net_client.send_action(
                        ActionRespondTreaty(context.net_client.player_id, proposal_id, country_tag, True)
                    )
                imgui.same_line()
                if imgui.button(f"REJECT##mail-{proposal_id}", (110.0, 24.0),
                                test_id=f"mail.treaty.{proposal_id}.reject"):
                    context.net_client.send_action(
                        ActionRespondTreaty(context.net_client.player_id, proposal_id, country_tag, False)
                    )
            imgui.end_popup()

    def _dismiss_items(self, items: list[dict], country_tag: str) -> None:
        self._inbox_state.dismiss_many({
            (str(item["inbox_kind"]), str(item.get("id") or ""))
            for item in items
        })
        for item in items:
            if item["inbox_kind"] == "dispatch" and item.get("kind") == "region_control":
                payload = item.get("payload") or {}
                self._inbox_state.dismiss_region_events(country_tag, payload.get("event_ids", ()))

    def _close_if_empty(self, items: list[dict]) -> None:
        # Keep the inbox open while its fallback detail popup depends on the parent window.
        if self._message_detail is not None:
            return
        if items and all(
            self._inbox_state.is_dismissed(item["inbox_kind"], item.get("id"))
            for item in items
        ) and self._close_mail_cb is not None:
            self._close_mail_cb()

    @staticmethod
    def _pending_for_country(state, country_tag: str) -> list[dict]:
        pending = state.tables.get("pending_treaties")
        if pending is None or pending.is_empty() or "required_responses" not in pending.columns:
            return []
        return [
            row for row in pending.to_dicts()
            if country_tag in set(normalize_country_tags(row.get("required_responses")))
        ]
