"""Treaty browser and response controls for authoritative diplomacy state."""

from __future__ import annotations

from modules.base.systems.world.treaty_diplomacy import DiplomacySystem
from modules.base.systems.world.treaty_proposal_policy import (
    country_diplomacy_restriction,
)
from src.client.renderers.flag_renderer import FlagRenderer
from src.client.services.journal_cursor import JournalCursor
from src.client.ui.core.containers import WindowManager
from src.client.ui.core.gml_widgets import GMLWidgets
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.core.primitives import UIPrimitives as Prims
from src.client.ui.core.theme import GAMETHEME
from src.client.ui.layouts.gml_layout import gml_child_frame
from src.client.ui.layouts.gml_rows import gml_row
from src.client.ui.layouts.main_pillar_positions import main_pillar_position
from src.client.ui.panels.politics.presenter import PoliticsPresenter
from src.client.ui.panels.politics.recognition_presenter import RecognitionPresenter
from src.client.ui.panels.politics.treaty_detail_lifecycle import TreatyDetailLifecycle
from src.client.ui.panels.politics.treaty_filters import (
    matches_treaty_filter as _matches_treaty_filter,
)
from src.client.ui.panels.politics.treaty_filters import (
    treaty_filter_options as _treaty_filter_options,
)
from src.client.ui.panels.politics.treaty_participant_dialog import (
    TreatyParticipantDialog,
)
from src.client.ui.panels.shared.panel_data import resolve_country_name
from src.client.ui.panels.shared.panel_widgets import (
    draw_empty_state,
    draw_required_tables,
)
from src.shared.actions import (
    ActionCastRecognitionVote,
    ActionJoinTreaty,
    ActionLeaveTreaty,
    ActionRespondTreaty,
    ActionUpdateTreatyParticipants,
)
from src.shared.treaties import (
    decode_conditions,
    normalize_country_tags,
    treaty_definition,
)


def _selectable_table_entry(
    label: str,
    selected: bool,
    test_id: str,
    tooltip: str | None = None,
) -> bool:
    # ImGui expands selectable hitboxes 5 px beyond the first table column's left edge.
    imgui.set_cursor_pos_x(imgui.get_cursor_pos_x() + 5.0)
    available_width = max(1.0, float(imgui.get_content_region_avail().x))
    # Long labels must not make the row selectable over the adjacent table columns.
    changed = imgui.selectable(
        label,
        selected,
        size=(available_width, 0.0),
        test_id=test_id,
    )[0]
    if tooltip:
        imgui.set_item_tooltip(tooltip)
    return changed


def _format_ratio_condition(value) -> str:
    ratio = _condition_number(value, 0.0)
    return "No limit" if ratio <= 0.0 else f"≤ {ratio:.2f}×"


def _condition_number(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class LiveTreatiesPanel:
    """Renders real agreements and lets the addressed country resolve proposals."""

    def __init__(self, open_editor_cb=None) -> None:
        self._presenter = PoliticsPresenter()
        self._recognition_presenter = RecognitionPresenter()
        self._diplomacy = DiplomacySystem()
        self._flags = FlagRenderer()
        self._open_editor_cb = open_editor_cb
        self._selected_treaty_id = ""
        self._selected_pending_id = ""
        self._show_details = False
        self._details_needs_focus = False
        self._participant_dialog = TreatyParticipantDialog()
        self._editing_treaty_id = ""
        self._filter_member_tag = ""
        self._filter_type_key = ""
        self._requested_treaty_id = ""
        self._detail_lifecycle = None
        self._participant_result_cursor = None
        self._pending_participant_sides = None

    def request_treaty(self, treaty_id: str) -> None:
        self._requested_treaty_id = str(treaty_id)

    def show_treaty(self, state, treaty_id: str) -> bool:
        """Resolve an external selection before opening its detail window."""
        treaty = self._find_row(state, "countries_treaties", treaty_id)
        pending = self._find_row(state, "pending_treaties", treaty_id)
        if treaty is None and pending is None:
            return False
        # A stale active selection would otherwise take precedence over the
        # proposal addressed by the external request.
        self._selected_treaty_id = treaty_id if treaty is not None else ""
        self._selected_pending_id = treaty_id if pending is not None else ""
        self._show_details = True
        self._details_needs_focus = True
        self._detail_lifecycle = TreatyDetailLifecycle(
            treaty_id, proposal=pending is not None,
            initial_events=getattr(getattr(state, "journal", None), "domain_events", []),
        )
        return True

    def render(self, state, context: PanelRenderContext) -> bool:
        self._resolve_participant_update(state, context)
        if self._requested_treaty_id:
            if not self.show_treaty(state, self._requested_treaty_id):
                self._selected_treaty_id = self._requested_treaty_id
                self._selected_pending_id = ""
                self._show_details = True
                self._detail_lifecycle = None
            self._requested_treaty_id = ""
        self._update_detail_lifecycle(state, context)
        if not self._show_details:
            x, y = main_pillar_position("treaties")
            with WindowManager.window(
                "Treaties", x=x, y=y, w=760, h=480, test_id="treaties.panel"
            ) as is_open:
                if not is_open:
                    self._participant_dialog.dismiss()
                    return False
                self._render_content(state, context)
        if not self._participant_dialog.is_open:
            self._render_details_window(state, context)
        editing_treaty = self._find_row(state, "countries_treaties", self._editing_treaty_id)
        ineligible = (
            self._diplomacy.ineligible_treaty_members(state, editing_treaty)
            if editing_treaty is not None
            else frozenset()
        )
        updated_sides = self._participant_dialog.render(state, ineligible_tags=ineligible)
        if updated_sides is not None and context.net_client is not None and self._editing_treaty_id:
            side_a, side_b = updated_sides
            self._pending_participant_sides = (
                frozenset(side_a),
                frozenset(side_b),
            )
            context.net_client.send_action(
                ActionUpdateTreatyParticipants(
                    player_id=context.net_client.player_id,
                    treaty_id=self._editing_treaty_id,
                    side_a_country_tags=sorted(side_a),
                    side_b_country_tags=sorted(side_b),
                )
            )
        return True

    def _resolve_participant_update(self, state, context: PanelRenderContext) -> None:
        journal = getattr(state, "journal", None)
        records = list(getattr(journal, "command_results", []))
        if self._participant_result_cursor is None:
            self._participant_result_cursor = JournalCursor(records)
            return

        player_id = str(getattr(context.net_client, "player_id", ""))
        fresh = self._participant_result_cursor.consume(records)
        for result in fresh:
            actor = str(result.get("actor_id") or result.get("player_id") or "")
            if (
                actor != player_id
                or str(result.get("action_type") or "") != "ActionUpdateTreatyParticipants"
            ):
                continue
            status = str(result.get("status") or "").casefold()
            if status in {"rejected", "failed"}:
                pending_sides = self._pending_participant_sides
                treaty = self._find_row(state, "countries_treaties", self._editing_treaty_id)
                if pending_sides is not None and treaty is not None:
                    side_a, side_b = pending_sides
                    proposed_treaty = {
                        **treaty,
                        "members": sorted(side_a | side_b),
                        "side_a": sorted(side_a),
                        "side_b": sorted(side_b),
                    }
                    self._participant_dialog.mark_ineligible(
                        self._diplomacy.ineligible_treaty_members(state, proposed_treaty)
                    )
                self._participant_dialog.resolve_result(applied=False)
                self._pending_participant_sides = None
            elif status in {"accepted", "applied", "succeeded"}:
                self._participant_dialog.resolve_result(applied=True)
                self._pending_participant_sides = None

        if self._pending_participant_sides is None:
            return
        treaty = self._find_row(state, "countries_treaties", self._editing_treaty_id)
        if treaty is None:
            return
        current_sides = (
            frozenset(normalize_country_tags(treaty.get("side_a"))),
            frozenset(normalize_country_tags(treaty.get("side_b"))),
        )
        if current_sides == self._pending_participant_sides:
            self._participant_dialog.resolve_result(applied=True)
            self._pending_participant_sides = None

    def _update_detail_lifecycle(self, state, context: PanelRenderContext) -> None:
        if not self._show_details:
            return

        treaty = self._find_row(state, "countries_treaties", self._selected_treaty_id)
        proposal = self._find_row(state, "pending_treaties", self._selected_pending_id)
        row = treaty or proposal
        events = getattr(getattr(state, "journal", None), "domain_events", [])
        if self._detail_lifecycle is None:
            self._detail_lifecycle = TreatyDetailLifecycle(
                self._selected_treaty_id or self._selected_pending_id,
                proposal=bool(self._selected_pending_id),
                initial_events=events,
            )

        lifecycle = self._detail_lifecycle
        message = lifecycle.update(row, events)
        if lifecycle.message:
            self._participant_dialog.dismiss()
            self._editing_treaty_id = ""
        if message and context.on_notice:
            # A queued acknowledgement belongs to this inspection. It must not
            # close another treaty opened before the player reaches that notice.
            def close_inspected_treaty():
                self._close_details_if_current(lifecycle)

            context.on_notice("Treaty details", message, on_acknowledge=close_inspected_treaty)

    def _render_content(self, state, context: PanelRenderContext) -> None:
        if not draw_required_tables(
            state, ("countries_treaties", "pending_treaties")
        ):
            return
        country_tag = str(context.target_tag or "").upper()
        active = self._presenter.active_treaties_for_country(state, country_tag)
        pending = self._presenter.pending_treaties_for_country(state, country_tag)
        ui = GMLWidgets("Treaties_Window/frmInner")
        rows = active + pending
        member_options, type_options = _treaty_filter_options(state, rows)
        member_tags = [tag for tag, _ in member_options]
        type_keys = [key for key, _ in type_options]
        if self._filter_member_tag not in member_tags:
            self._filter_member_tag = ""
        if self._filter_type_key not in type_keys:
            self._filter_type_key = ""
        ui.text("frmFilters/lblTitle", "FILTERS")
        ui.text("frmFilters/lblMember", "MEMBER")
        ui.text("frmFilters/lblType", "TYPE")
        member_index = member_tags.index(self._filter_member_tag) + 1 if self._filter_member_tag else 0
        _, member_index = imgui.combo(
            "##treaty_member", member_index, ["All members", *(label for _, label in member_options)],
            gml_id=ui.path("frmFilters/cboCountry"), test_id="treaties.filter_member")
        self._filter_member_tag = member_tags[member_index - 1] if member_index > 0 else ""
        type_index = type_keys.index(self._filter_type_key) + 1 if self._filter_type_key else 0
        _, type_index = imgui.combo(
            "##treaty_type", type_index, ["All types", *(label for _, label in type_options)],
            gml_id=ui.path("frmFilters/cboType"), test_id="treaties.filter_type")
        self._filter_type_key = type_keys[type_index - 1] if type_index > 0 else ""
        active = [row for row in active if _matches_treaty_filter(row, self._filter_member_tag, self._filter_type_key)]
        pending = [row for row in pending if _matches_treaty_filter(row, self._filter_member_tag, self._filter_type_key)]
        for section, title in (("frmActiveTreaties", "ACTIVE TREATIES"),
                               ("frmPendingTreaties", "PENDING PROPOSALS")):
            ui.text(f"{section}/lblTitle", title)
        with gml_child_frame(ui.path("frmActiveTreaties/lstTreaties"), bordered=False) as opened:
            if opened:
                self._render_active_table(active)
        with gml_child_frame(ui.path("frmPendingTreaties/lstTreaties"), bordered=False) as opened:
            if opened and imgui.begin_tab_bar("treaty_activity"):
                if imgui.begin_tab_item("Proposals")[0]:
                    self._render_pending_table(pending)
                    self._render_actions(state, context, country_tag, active, pending)
                    imgui.end_tab_item()
                if imgui.begin_tab_item("Recognition")[0]:
                    self._render_recognition(state, context, country_tag)
                    imgui.end_tab_item()
                imgui.end_tab_bar()
        if ui.button("btnNew", "NEW TREATY", "treaties.new_treaty",
                     enabled=context.is_own_country and self._open_editor_cb is not None):
            reason = country_diplomacy_restriction(state.tables.get("country_governments"), country_tag)
            if reason:
                if context.on_notice:
                    context.on_notice("New treaty", reason)
            else:
                self._open_editor_cb()
        if ui.button("btnView", "VIEW DETAILS", "treaties.view_selected",
                     enabled=bool(self._selected_treaty_id or self._selected_pending_id)):
            self._show_details = True
            self._details_needs_focus = True
            self._detail_lifecycle = None

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
                treaty_name = str(treaty.get("name") or treaty_id)
                imgui.table_next_row()
                imgui.table_next_column()
                selected = _selectable_table_entry(
                    f"{treaty_name}##active-{treaty_id}",
                    self._selected_treaty_id == treaty_id,
                    f"treaties.active.{treaty_id}",
                    treaty_name,
                )
                if selected:
                    self._selected_treaty_id = treaty_id
                    self._selected_pending_id = ""
                    self._detail_lifecycle = None
                imgui.table_next_column()
                imgui.text(
                    str(treaty.get("type") or "").replace("_", " ").title(),
                    test_id=f"treaties.active.{treaty_id}.type",
                )
                imgui.table_next_column()
                imgui.text(
                    str(treaty.get("members_count") or ""),
                    test_id=f"treaties.active.{treaty_id}.members",
                )
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
                proposal_title = str(proposal.get("title") or proposal_id)
                responses = normalize_country_tags(proposal.get("accepted_members"))
                required = normalize_country_tags(proposal.get("required_responses"))
                imgui.table_next_row()
                imgui.table_next_column()
                selected = _selectable_table_entry(
                    f"{proposal_title}##pending-{proposal_id}",
                    self._selected_pending_id == proposal_id,
                    f"treaties.pending.{proposal_id}",
                    proposal_title,
                )
                if selected:
                    self._selected_pending_id = proposal_id
                    self._selected_treaty_id = ""
                    self._detail_lifecycle = None
                imgui.table_next_column()
                imgui.text(
                    str(proposal.get("treaty_type") or "").replace("_", " ").title(),
                    test_id=f"treaties.pending.{proposal_id}.type",
                )
                imgui.table_next_column()
                imgui.text(
                    f"{len(responses)}/{len(required) + 1}",
                    test_id=f"treaties.pending.{proposal_id}.responses",
                )
            imgui.end_table()

    def _render_actions(self, state, context: PanelRenderContext, country_tag: str, active: list[dict], pending: list[dict]) -> None:
        selected_active = next((row for row in active if str(row.get("id") or "") == self._selected_treaty_id), None)
        if context.net_client is None or not context.is_own_country:
            return
        if selected_active is not None:
            if imgui.button("LEAVE", (120.0, 28.0)):
                context.net_client.send_action(ActionLeaveTreaty(context.net_client.player_id, self._selected_treaty_id, country_tag))
            if bool(selected_active.get("open_to_new_members")):
                imgui.same_line()
                if imgui.button("JOIN", (120.0, 28.0)):
                    context.net_client.send_action(ActionJoinTreaty(context.net_client.player_id, self._selected_treaty_id, country_tag))

    def _render_details_window(self, state, context: PanelRenderContext) -> None:
        if not self._show_details:
            return

        treaty = self._find_row(state, "countries_treaties", self._selected_treaty_id)
        proposal = self._find_row(state, "pending_treaties", self._selected_pending_id)
        row = treaty or proposal
        lifecycle = self._detail_lifecycle
        if lifecycle is None:
            return

        if self._details_needs_focus:
            imgui.set_next_window_focus()
            self._details_needs_focus = False
        viewport = imgui.get_io().display_size
        viewport_width, viewport_height = float(viewport.x), float(viewport.y)
        centered_x = max(0.0, (viewport_width - 634.0) / 2.0)
        treaty_x, _ = main_pillar_position("treaties")
        # The wider detail frame covers the list's text column instead of leaving a clipped strip underneath.
        details_x = 0.0 if viewport_width < 1000.0 else min(centered_x, float(treaty_x))
        centered_y = max(0.0, (viewport_height - 448.0) / 2.0)
        # Reserve the bottom HUD's 96 px plus its 8 px viewport margin on compact screens.
        hud_clearance_y = max(0.0, viewport_height - 448.0 - 104.0)
        details_y = min(centered_y, hud_clearance_y)
        with WindowManager.window(
            "Treaty Details", x=details_x, y=details_y, w=634, h=448,
            test_id="treaties.details.dialog",
        ) as is_open:
            if not is_open:
                self._show_details = False
                return
            if not draw_required_tables(
                state, ("countries_treaties", "pending_treaties")
            ):
                return

            row = row or lifecycle.last_row or {}
            ui = GMLWidgets("Treaty_Details_Window/frmInner")
            ui.frame("frmMain")
            name = str(row.get("name") or row.get("title") or row.get("id") or "Treaty")
            treaty_type = str(
                row.get("type") or row.get("treaty_type") or "Unknown"
            ).replace("_", " ").title()
            status = str(row.get("status") or "Unknown").replace("_", " ").title()
            if lifecycle.message:
                # Cached proposal data predates the event and must not imply it
                # is still pending after the server has accepted or removed it.
                status = "Accepted" if lifecycle.message == "The treaty has been accepted." else "Unavailable"

            ui.text("frmMain/lblType", "TYPE", test_id="treaties.details.type.label")
            ui.combo_at(
                "frmMain/cboType",
                "##treaties.details.type",
                0,
                [treaty_type],
                "treaties.details.type.value",
                enabled=False,
            )
            ui.text("frmMain/lblName", "NAME", test_id="treaties.details.name.label")
            ui.frame("frmMain/edtName")
            ui.text_at(
                "frmMain/edtNameOver",
                name,
                offset=(4.0, 2.0),
                test_id="treaties.details.title",
            )
            ui.text("frmMain/lblName1", "STATUS", test_id="treaties.details.status.label")
            ui.text_at(
                "frmMain/picStatus",
                "●",
                color=(0.35, 0.78, 0.42, 1.0) if status.casefold() == "active" else (0.7, 0.62, 0.32, 1.0),
            )
            ui.text_at(
                "frmMain/txtStatus",
                status,
                offset=(16.0, 0.0),
                test_id="treaties.details.status.value",
            )
            ui.text("frmMain/lblSideA", "SIDE A", test_id="treaties.details.side_a.label")
            ui.text("frmMain/lblSideB", "SIDE B", test_id="treaties.details.side_b.label")
            self._render_conditions(ui, row)

            member_tags = set(normalize_country_tags(row.get("members")))
            side_a = set(normalize_country_tags(row.get("side_a")))
            side_b = set(normalize_country_tags(row.get("side_b")))
            if not side_a and not side_b:
                side_a = member_tags
            else:
                side_a.update(member_tags - side_b)
            self._render_details_member_list(ui, state, "lstCountriesA", sorted(side_a))
            self._render_details_member_list(ui, state, "lstCountriesB", sorted(side_b))

            ui.frame("frmMain/frmDescription")
            detail_lines = []
            if lifecycle.message:
                detail_lines.append(lifecycle.message)
            else:
                terms = str(row.get("terms") or "").strip()
                if terms:
                    detail_lines.extend(("TERMS", terms))
                effects = self._find_effects(state, str(row.get("id") or ""))
                if effects:
                    detail_lines.append("RECORDED EFFECTS")
                    for effect in effects:
                        description = str(effect.get("detail") or effect.get("effect") or "")
                        value = effect.get("value")
                        value_text = "" if value is None else f" ({value})"
                        detail_lines.append(f"• {description}{value_text}")
            if not detail_lines:
                detail_lines.append("No additional treaty details are recorded.")
            detail_test_id = (
                "treaties.details.lifecycle"
                if lifecycle.message
                else "treaties.details.description"
            )
            with gml_child_frame(
                ui.path("frmMain/frmDescription/txtDetail"),
                padding=(3.0, 2.0),
                bordered=False,
            ) as opened:
                if opened:
                    imgui.text_wrapped("\n".join(detail_lines), test_id=detail_test_id)

            is_open_to_new_members = bool(row.get("open_to_new_members"))
            ui.text(
                "frmMain/lblOpen",
                "OPEN TO NEW MEMBERS" if is_open_to_new_members else "CLOSED TO NEW MEMBERS",
                test_id="treaties.details.open_to_new_members.label",
            )
            ui.toggle(
                "frmMain/togOpen",
                is_open_to_new_members,
                "treaties.details.open_to_new_members",
                icon="",
                color=(0.35, 0.78, 0.42, 1.0),
                enabled=False,
            )

            if proposal is not None and not lifecycle.message:
                self._render_proposal_response_actions(ui, proposal, context)
            elif not lifecycle.message and self._can_edit_participants(treaty, context):
                if ui.button(
                    "frmMain/frmModify/btnModify",
                    "Members",
                    "treaties.details.edit_participants",
                ):
                    self._open_participant_editor(treaty, state)

            self._render_eligibility_list(treaty, state, context)
            self._render_pressure_fallback(ui)

            if ui.button("frmMain/btnCancel", "Close", "treaties.details.close"):
                self._show_details = False

    @staticmethod
    def _render_conditions(ui: GMLWidgets, treaty: dict) -> None:
        """Show saved admission conditions in their source GML slots without enabling edits."""
        ui.frame("frmConditions")
        conditions = decode_conditions(treaty.get("conditions_json"))
        allow_wars = bool(conditions.get("allow_members_at_war"))
        ui.text(
            "frmConditions/lblTitle",
            "CONDITIONS",
            tooltip=(
                "OpenPower-only admission setting: members may be at war. "
                f"Current value: {'Yes' if allow_wars else 'No'}."
            ),
            test_id="treaties.details.conditions.label",
        )

        relation = _condition_number(conditions.get("minimum_relation"), -100.0)
        relation_text = "No limit" if relation <= -100.0 else f"≥ {relation:.0f}"
        distance = _condition_number(conditions.get("maximum_geographic_distance_km"), 0.0)
        geography_text = "No limit" if distance <= 0.0 else f"≤ {distance:.0f} km"
        government = str(conditions.get("government_type") or "").strip()
        government_text = government.replace("_", " ").title() if government else "No limit"

        condition_values = (
            ("lblRelations", "cboRelations", relation_text, "minimum_relation"),
            ("lblGeographicProximity", "cboGeographicProximity", geography_text, "maximum_geographic_distance_km"),
            ("lblPoliticalStr", "cboPoliticalStrength", government_text, "government_type"),
            ("lblEconomicStr", "cboEconomicStrength", _format_ratio_condition(conditions.get("max_economic_strength_ratio")), "max_economic_strength_ratio"),
            ("lblMilitaryStr", "cboMilitaryStrength", _format_ratio_condition(conditions.get("max_military_strength_ratio")), "max_military_strength_ratio"),
            ("lblResearchLvl", "cboResearchLevel", _format_ratio_condition(conditions.get("max_research_ratio")), "max_research_ratio"),
        )
        for label_slot, combo_slot, value, condition_key in condition_values:
            label = {
                "lblRelations": "RELATIONS",
                "lblGeographicProximity": "GEOGRAPHIC PROXIMITY",
                "lblPoliticalStr": "POLITICAL STRENGTH",
                "lblEconomicStr": "ECONOMIC STRENGTH",
                "lblMilitaryStr": "MILITARY STRENGTH",
                "lblResearchLvl": "RESEARCH LEVEL",
            }[label_slot]
            label_path = f"frmConditions/{label_slot}"
            if label_slot == "lblGeographicProximity":
                # This source caption is typed as a graph, so automatic label placement misses its GML x offset.
                ui.text_at(label_path, label, max_width=130.0, font_size=11.0)
            else:
                ui.text(label_path, label)
            ui.combo_at(
                f"frmConditions/{combo_slot}",
                f"##treaties.details.condition.{condition_key}",
                0,
                [value],
                f"treaties.details.condition.{condition_key}",
                enabled=False,
            )
    def _render_proposal_response_actions(
        self,
        ui: GMLWidgets,
        proposal: dict,
        context: PanelRenderContext,
    ) -> None:
        country_tag = str(context.target_tag or "").strip().upper()
        required = set(normalize_country_tags(proposal.get("required_responses")))
        if (
            context.net_client is None
            or not context.is_own_country
            or country_tag not in required
        ):
            return

        proposal_id = str(proposal.get("id") or self._selected_pending_id)
        if ui.button(
            "frmMain/frmModify/btnModify",
            "ACCEPT",
            "treaties.details.accept",
        ):
            context.net_client.send_action(
                ActionRespondTreaty(
                    context.net_client.player_id,
                    proposal_id,
                    country_tag,
                    True,
                )
            )
        if ui.button(
            "frmMain/frmModify/btnRefuse",
            "REJECT",
            "treaties.details.reject",
        ):
            context.net_client.send_action(
                ActionRespondTreaty(
                    context.net_client.player_id,
                    proposal_id,
                    country_tag,
                    False,
                )
            )

    @staticmethod
    def _render_pressure_fallback(ui: GMLWidgets) -> None:
        """Preserve the treaty-pressure slots without inventing pressure data."""
        ui.frame("frmPressure")
        ui.text("frmPressure/lblTitle", "PRESSURE", test_id="treaties.details.pressure.label")
        ui.text(
            "frmPressure/txtValue",
            "N/A",
            color=GAMETHEME.colors.text_dim,
            test_id="treaties.details.pressure.value",
        )
        ui.meter("frmPressure/frmGradient", 0.0, GAMETHEME.colors.text_dim)
        with gml_child_frame(
            ui.path("frmPressure/lstPressure"),
            padding=(4.0, 2.0),
            bordered=False,
        ) as opened:
            if opened:
                imgui.text_wrapped(
                    "OpenPower does not track REFERENCE treaty pressure-country totals.",
                    test_id="treaties.details.pressure.unavailable",
                )
        ui.button(
            "frmPressure/btnSponsor",
            "SPONSOR",
            "treaties.details.sponsor.unavailable",
            enabled=False,
            tooltip="OpenPower has no separate treaty-pressure membership action.",
        )

    def _render_details_member_list(
        self,
        ui: GMLWidgets,
        state,
        slot: str,
        country_tags: list[str],
    ) -> None:
        with gml_child_frame(ui.path(f"frmMain/{slot}"), padding=(4.0, 2.0)) as opened:
            if not opened:
                return
            if not country_tags:
                imgui.text_disabled("No members recorded.")
                return
            for tag in country_tags:
                self._flags.draw_flag(tag, 22.0, 13.0)
                imgui.same_line()
                imgui.text(f"{resolve_country_name(state, tag)} ({tag})")

    def _open_participant_editor(
        self,
        treaty: dict,
        state,
        *,
        remove_ineligible: bool = False,
    ) -> None:
        definition = treaty_definition(treaty.get("type"))
        members = set(normalize_country_tags(treaty.get("members")))
        side_a = set(normalize_country_tags(treaty.get("side_a")))
        side_b = set(normalize_country_tags(treaty.get("side_b")))
        sponsor = str(treaty.get("source_country_id") or "").upper()
        if not side_a and not side_b:
            side_a = members
        if definition is not None and not definition.two_sided:
            side_a = members
            side_b = set()
        ineligible = self._diplomacy.ineligible_treaty_members(state, treaty)
        self._editing_treaty_id = str(treaty.get("id") or "")
        self._participant_dialog.open(
            side_a=side_a,
            side_b=side_b,
            two_sided=bool(definition and definition.two_sided),
            protected_a={sponsor} if sponsor else set(),
            protected_b=set(),
            ineligible_tags=ineligible,
        )
        if remove_ineligible:
            self._participant_dialog.remove_ineligible()

    def _render_eligibility_list(self, treaty: dict | None, state, context) -> None:
        if treaty is None:
            return
        ui = GMLWidgets("Treaty_Details_Window/frmInner")
        ui.text("frmEligibleCountries/lblTitle", "ELIGIBLE COUNTRIES")
        eligible = self._diplomacy.eligible_treaty_countries(state, treaty)
        with gml_child_frame(ui.path("frmEligibleCountries/lstEligibleCountries"), bordered=True) as opened:
            if opened:
                tags = sorted(eligible)
                if not tags:
                    imgui.text_disabled("No eligible countries.")
                for row_index, row_start in enumerate(range(0, len(tags), 5)):
                    with gml_row("lstTreatyEligibleCountryItem", row_index) as row_ui:
                        for column, tag in enumerate(tags[row_start:row_start + 5]):
                            flag_slot = "picFlag" if column == 0 else f"picFlag{column}"
                            code_slot = "txtCode" if column == 0 else f"txtCode{column}"
                            name = resolve_country_name(state, tag)
                            row_ui.picture(
                                flag_slot,
                                lambda width, height, country=tag: self._flags.draw_flag(country, width, height),
                            )
                            row_ui.text(
                                code_slot,
                                tag,
                                tooltip=name,
                                test_id=f"treaties.eligible.{tag}",
                            )
        ineligible = self._diplomacy.ineligible_treaty_members(state, treaty)
        if ui.button(
            "frmEligibleCountries/btnRemoveNotEligible",
            "REMOVE NOT ELIGIBLE",
            "treaties.details.remove_ineligible",
            enabled=bool(ineligible) and self._can_edit_participants(treaty, context),
            dynamic_enabled=True,
        ):
            self._open_participant_editor(treaty, state, remove_ineligible=True)
            if context.on_notice:
                context.on_notice(
                    "Treaty eligibility",
                    "Removed ineligible members from the draft: "
                    + ", ".join(sorted(ineligible))
                    + ". Apply the participant changes to save.",
                )

    def _close_details_if_current(self, lifecycle) -> None:
        if self._detail_lifecycle is lifecycle:
            self._show_details = False

    @staticmethod
    def _can_edit_participants(treaty: dict | None, context: PanelRenderContext) -> bool:
        if treaty is None or context.net_client is None or not context.is_own_country:
            return False
        definition = treaty_definition(treaty.get("type"))
        sponsor = str(treaty.get("source_country_id") or "").strip().upper()
        return bool(
            definition
            and definition.multi_member
            and str(treaty.get("status") or "active") == "active"
            and sponsor == str(context.target_tag or "").strip().upper()
        )

    @staticmethod
    def _find_row(state, table_name: str, record_id: str) -> dict | None:
        table = state.tables.get(table_name)
        if table is None or table.is_empty() or not record_id:
            return None
        return next(
            (row for row in table.to_dicts() if str(row.get("id") or "") == record_id),
            None,
        )

    @staticmethod
    def _find_effects(state, treaty_id: str) -> list[dict]:
        table = state.tables.get("treaty_effects")
        if table is None or table.is_empty() or "treaty_id" not in table.columns:
            return []
        return [row for row in table.to_dicts() if str(row.get("treaty_id") or "") == treaty_id]

    def _render_recognition(self, state, context: PanelRenderContext, country_tag: str) -> None:
        cases = self._recognition_presenter.cases_for_country(state, country_tag)
        imgui.text("UN RECOGNITION COUNCIL")
        if not cases:
            draw_empty_state("No completed annexation is awaiting or has received a recognition vote.")
            return

        for case in cases:
            imgui.push_id(str(case["id"]))
            imgui.text(
                f"Region {case['region_id']} · {case['claimant_id']} / former owner {case['former_owner_id']}"
            )
            imgui.text(
                f"{case['status'].replace('_', ' ').title()} · "
                f"Yes {case['yes_votes']} / No {case['no_votes']} / Abstain {case['abstain_votes']} "
                f"of {len(case['eligible_voters'])} eligible"
            )
            if case["my_status"]:
                imgui.text(f"Your country's status: {case['my_status'].replace('_', ' ').title()}")
            elif case["my_vote"]:
                imgui.text(f"Your current vote: {case['my_vote'].title()}")
            elif case["status"] == "pending" and country_tag in case["eligible_voters"]:
                imgui.text(f"Voting deadline: {case['days_remaining']} game days remaining")

            client = context.net_client
            can_vote = (
                case["status"] == "pending"
                and case["days_remaining"] > 0
                and country_tag in case["eligible_voters"]
                and context.is_own_country
                and client is not None
            )
            if can_vote:
                for index, vote in enumerate(("yes", "no", "abstain")):
                    if index:
                        imgui.same_line()
                    if imgui.small_button(f"{vote.title()}##{vote}"):
                        client.send_action(
                            ActionCastRecognitionVote(
                                player_id=client.player_id,
                                case_id=case["id"],
                                country_tag=country_tag,
                                vote=vote,
                            )
                        )
            if case["reason"]:
                imgui.text_disabled(case["reason"])
            imgui.separator()
            imgui.pop_id()
