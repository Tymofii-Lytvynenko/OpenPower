"""Treaty browser and response controls for authoritative diplomacy state."""

from __future__ import annotations

from imgui_bundle import imgui

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.core.primitives import UIPrimitives as Prims
from src.client.ui.panels.politics.presenter import PoliticsPresenter
from src.client.ui.panels.shared.panel_widgets import draw_empty_state, draw_required_tables
from src.shared.actions import ActionJoinTreaty, ActionLeaveTreaty, ActionRespondTreaty
from src.shared.treaties import normalize_country_tags


class LiveTreatiesPanel:
    """Renders real agreements and lets the addressed country resolve proposals."""

    def __init__(self, open_editor_cb=None) -> None:
        self._presenter = PoliticsPresenter()
        self._open_editor_cb = open_editor_cb
        self._selected_treaty_id = ""
        self._selected_pending_id = ""

    def render(self, state, context: PanelRenderContext) -> bool:
        with WindowManager.window("Treaties", x=300, y=150, w=760, h=480) as is_open:
            if not is_open:
                return False
            self._render_content(state, context)
            return True

    def _render_content(self, state, context: PanelRenderContext) -> None:
        draw_required_tables(state, ("countries_treaties", "pending_treaties", "countries_relations"))
        country_tag = str(context.target_tag or "").upper()
        active = self._presenter.active_treaties_for_country(state, country_tag)
        pending = self._presenter.pending_treaties_for_country(state, country_tag)

        imgui.text("ACTIVE TREATIES")
        self._render_active_table(active)
        imgui.separator()
        imgui.text("PENDING PROPOSALS")
        self._render_pending_table(pending)
        imgui.separator()
        self._render_actions(state, context, country_tag, active, pending)

    def _render_active_table(self, active: list[dict]) -> None:
        if not active:
            draw_empty_state("No active treaties involve the selected country.")
            return
        if imgui.begin_table("active_treaties", 3, imgui.TableFlags_.borders_inner | imgui.TableFlags_.row_bg, (0.0, 130.0)):
            imgui.table_setup_column("NAME", imgui.TableColumnFlags_.width_stretch)
            imgui.table_setup_column("TYPE", imgui.TableColumnFlags_.width_stretch)
            imgui.table_setup_column("MEMBERS", imgui.TableColumnFlags_.width_fixed, 75)
            imgui.table_headers_row()
            for treaty in active:
                treaty_id = str(treaty.get("id") or "")
                imgui.table_next_row()
                imgui.table_next_column()
                if imgui.selectable(f"{treaty.get('name') or treaty_id}##active-{treaty_id}", self._selected_treaty_id == treaty_id)[0]:
                    self._selected_treaty_id = treaty_id
                imgui.table_next_column()
                imgui.text(str(treaty.get("type") or "").replace("_", " ").title())
                imgui.table_next_column()
                imgui.text(str(treaty.get("members_count") or ""))
            imgui.end_table()

    def _render_pending_table(self, pending: list[dict]) -> None:
        if not pending:
            draw_empty_state("No treaty proposal is awaiting a response.")
            return
        if imgui.begin_table("pending_treaties", 3, imgui.TableFlags_.borders_inner | imgui.TableFlags_.row_bg, (0.0, 130.0)):
            imgui.table_setup_column("NAME", imgui.TableColumnFlags_.width_stretch)
            imgui.table_setup_column("TYPE", imgui.TableColumnFlags_.width_stretch)
            imgui.table_setup_column("RESPONSES", imgui.TableColumnFlags_.width_fixed, 85)
            imgui.table_headers_row()
            for proposal in pending:
                proposal_id = str(proposal.get("id") or "")
                responses = normalize_country_tags(proposal.get("accepted_members"))
                required = normalize_country_tags(proposal.get("required_responses"))
                imgui.table_next_row()
                imgui.table_next_column()
                if imgui.selectable(f"{proposal.get('title') or proposal_id}##pending-{proposal_id}", self._selected_pending_id == proposal_id)[0]:
                    self._selected_pending_id = proposal_id
                imgui.table_next_column()
                imgui.text(str(proposal.get("treaty_type") or "").replace("_", " ").title())
                imgui.table_next_column()
                imgui.text(f"{len(responses)}/{len(required) + 1}")
            imgui.end_table()

    def _render_actions(self, state, context: PanelRenderContext, country_tag: str, active: list[dict], pending: list[dict]) -> None:
        if self._open_editor_cb and context.is_own_country and imgui.button("NEW TREATY", (180.0, 28.0)):
            self._open_editor_cb()
        selected_pending = next((row for row in pending if str(row.get("id") or "") == self._selected_pending_id), None)
        selected_active = next((row for row in active if str(row.get("id") or "") == self._selected_treaty_id), None)
        if context.net_client is None or not context.is_own_country:
            return
        if selected_pending is not None:
            required = set(normalize_country_tags(selected_pending.get("required_responses")))
            if country_tag in required:
                imgui.same_line()
                if imgui.button("ACCEPT", (120.0, 28.0)):
                    context.net_client.send_action(ActionRespondTreaty(context.net_client.player_id, self._selected_pending_id, country_tag, True))
                imgui.same_line()
                if imgui.button("REJECT", (120.0, 28.0)):
                    context.net_client.send_action(ActionRespondTreaty(context.net_client.player_id, self._selected_pending_id, country_tag, False))
        if selected_active is not None:
            imgui.same_line()
            if imgui.button("LEAVE", (120.0, 28.0)):
                context.net_client.send_action(ActionLeaveTreaty(context.net_client.player_id, self._selected_treaty_id, country_tag))
            if bool(selected_active.get("open_to_new_members")):
                imgui.same_line()
                if imgui.button("JOIN", (120.0, 28.0)):
                    context.net_client.send_action(ActionJoinTreaty(context.net_client.player_id, self._selected_treaty_id, country_tag))
