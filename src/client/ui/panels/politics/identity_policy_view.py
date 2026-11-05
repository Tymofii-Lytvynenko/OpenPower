from __future__ import annotations

import math

from src.client.ui.components.shared.generic_message_dialog import GenericMessageDialog
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.primitives import UIPrimitives as Prims
from src.client.ui.layouts.gml_rows import gml_row
from src.client.ui.panels.shared.panel_widgets import draw_empty_state
from src.shared.actions import ActionSetCountryIdentityPolicy

IDENTITY_STATUSES = ("official", "legal", "restricted", "illegal")
STATUS_HELP = {
    "official": "Official recognition. The group remains recognized by state policy.",
    "legal": "Legal recognition without official status.",
    "restricted": "Restrictions increase policy pressure and gradually change population shares.",
    "illegal": "Prohibition creates stronger policy pressure and faster changes in population shares.",
}


class IdentityPolicyView:
    """Reusable identity table; commands remain owned by the supplied session context."""

    def __init__(self, notice=None, draft=None):
        self._notice = notice if notice is not None else GenericMessageDialog()
        self._draft = draft
        self.identity_type = "language"
        self._details_key = None
        self._details_row = None

    def render(self, state, context, *, compact=False):
        tag = str(context.target_tag or "").strip().upper()
        if not compact:
            Prims.header("Languages and religions", show_bg=False)
            imgui.text_wrapped("Population shares are gameplay estimates. Use Details to inspect their source.")
            self.render_tabs()
            imgui.text_disabled(f"Showing: {self.identity_type.title()} groups")
        frame = state.tables.get("country_identity_groups")
        rows = [] if frame is None else [
            row for row in frame.iter_rows(named=True)
            if str(row.get("country_id") or "").upper() == tag
            and row.get("identity_type") == self.identity_type
        ]
        rows.sort(key=lambda row: (-self._share(row.get("population_share")), str(row.get("display_name") or "")))
        can_edit = context.is_own_country and context.net_client is not None
        if not can_edit and not compact:
            imgui.text_disabled("Viewing another country. Policy changes require control of this country.")
        if not rows:
            draw_empty_state(f"No {self.identity_type} profile is available for {tag}.")
        elif compact:
            self._render_source_rows(rows, context, tag, can_edit)
        elif imgui.begin_table("identity_groups", 4, imgui.TableFlags_.row_bg):
            imgui.table_setup_column("Group", imgui.TableColumnFlags_.width_stretch)
            imgui.table_setup_column("Share", imgui.TableColumnFlags_.width_fixed, 50 if compact else 65)
            imgui.table_setup_column("Status", imgui.TableColumnFlags_.width_fixed, 100 if compact else 115)
            imgui.table_setup_column("Source", imgui.TableColumnFlags_.width_fixed, 48 if compact else 64)
            imgui.table_headers_row()
            for row in rows:
                identity_id = str(row.get("identity_id") or "")
                key = (tag, self.identity_type, identity_id)
                widget_key = f"identity.{tag}.{self.identity_type}.{identity_id}"
                imgui.table_next_row()
                imgui.table_next_column()
                imgui.text_wrapped(str(row.get("display_name") or identity_id))
                imgui.table_next_column()
                imgui.text(f"{self._share(row.get('population_share')):.1f}%")
                imgui.table_next_column()
                status = self._draft.status(row) if self._draft is not None else str(row.get("legal_status") or "legal").casefold()
                aggregate = bool(row.get("is_other_bucket"))
                imgui.begin_disabled(not can_edit or aggregate)
                imgui.set_next_item_width(-1)
                changed, index = imgui.combo("##status", IDENTITY_STATUSES.index(status) if status in IDENTITY_STATUSES else 1,
                                             [value.title() for value in IDENTITY_STATUSES], test_id=f"{widget_key}.status")
                imgui.end_disabled()
                if imgui.is_item_hovered(imgui.HoveredFlags_.allow_when_disabled):
                    imgui.set_tooltip("Other is an aggregate of unspecified groups; its status cannot be changed." if aggregate else STATUS_HELP.get(status, "Unknown policy status."))
                if changed and can_edit and not aggregate:
                    self.request_policy(rows, row, IDENTITY_STATUSES[index], context)
                imgui.table_next_column()
                if imgui.small_button("Details", test_id=f"{widget_key}.details"):
                    self._details_key = key
            imgui.end_table()
        selected = next((row for row in rows if (tag, self.identity_type, str(row.get("identity_id") or "")) == self._details_key), None)
        self._details_row = selected if compact else None
        if selected is not None and not compact:
            imgui.separator()
            imgui.text_wrapped(f"Source details: {selected.get('display_name') or selected.get('identity_id')}")
            year = selected.get("source_year") or 0
            imgui.text(f"Source year: {year if year else 'Not recorded'}")
            imgui.text_wrapped(f"Reference: {selected.get('source_reference') or 'Not recorded'}")
            imgui.text_wrapped(f"Method / note: {selected.get('source_note') or 'Normalized bundled gameplay estimate; methodology not recorded.'}")
            if selected.get("is_other_bucket"):
                imgui.text_wrapped("Other combines unspecified groups. Its legal status is read-only.")
        if context.net_client is not None and not compact:
            results = getattr(getattr(state, "journal", None), "command_results", [])
            result = next((row for row in reversed(results)
                           if str(row.get("player_id") or "") == str(context.net_client.player_id)
                           and row.get("action_type") == "ActionSetCountryIdentityPolicy"), None)
            if result:
                imgui.text_wrapped(f"Latest policy result: {result.get('status')} · {result.get('reason', '')}")

    def _render_source_rows(self, rows, context, tag, can_edit):
        for row in rows:
            identity = str(row.get("identity_id") or "")
            widget = f"identity.{tag}.{self.identity_type}.{identity}"
            with gml_row("lstInternalLawsGroups", widget) as ui:
                display_name = str(row.get("display_name") or identity)
                if ui.hitbox(
                    "lblName",
                    widget + ".details",
                    tooltip=display_name + "\nClick for population source details",
                ):
                    self._details_key = (tag, self.identity_type, identity)
                ui.text("lblName", display_name)
                ui.text("lblPerc", f"{self._share(row.get('population_share')):.1f}%", right=True, test_id=widget + ".share")
                status = self._draft.status(row) if self._draft is not None else str(row.get("legal_status") or "legal").casefold()
                aggregate = bool(row.get("is_other_bucket"))
                imgui.begin_disabled(not can_edit or aggregate)
                changed, index = imgui.combo("##status", IDENTITY_STATUSES.index(status) if status in IDENTITY_STATUSES else -1,
                                             [value.title() for value in IDENTITY_STATUSES],
                                             test_id=widget + ".status", gml_id=ui.path("cboStatus"))
                imgui.end_disabled()
                if imgui.is_item_hovered(imgui.HoveredFlags_.allow_when_disabled):
                    imgui.set_tooltip("Other is an aggregate; its status is read-only." if aggregate else STATUS_HELP.get(status, "Unknown policy status."))
                if changed and can_edit and not aggregate:
                    self.request_policy(rows, row, IDENTITY_STATUSES[index], context)

    def render_tabs(self, ui=None):
        for index, (kind, title) in enumerate((("religion", "Religions"), ("language", "Languages"))):
            if ui is None:
                if index:
                    imgui.same_line()
                clicked = imgui.button(title, test_id=f"identity.tab.{kind}")
            else:
                # GML tab pages occupy the list above the bottom tab strip.
                clicked = ui.button_at("frmInner/frmDemographicGroups/tabGroups", title,
                                       f"identity.tab.{kind}", offset=(index * 100, 89), size=(101, 16))
            if clicked:
                self.identity_type = kind
                self._details_key = None

    def render_notices(self):
        if self._details_row is not None:
            from src.client.ui.core.containers import WindowManager
            with WindowManager.window("Identity source details", x=670, y=80, w=420, h=230,
                                      test_id="identity.source.details") as opened:
                if not opened:
                    self._details_key = None
                    self._details_row = None
                else:
                    row = self._details_row
                    imgui.text_wrapped(str(row.get("display_name") or row.get("identity_id")))
                    imgui.text(f"Source year: {row.get('source_year') or 'Not recorded'}")
                    imgui.text_wrapped(f"Reference: {row.get('source_reference') or 'Not recorded'}")
                    imgui.text_wrapped(str(row.get("source_note") or "Methodology not recorded."))
        self._notice.render()

    def request_policy(self, rows, target, status, context):
        if not context.is_own_country or context.net_client is None or target.get("is_other_bucket"):
            return False
        if self._draft is not None:
            reason = self._draft.choose(rows, target, status)
            if reason:
                (context.on_notice or self._notice.enqueue)("Internal laws", reason, severity="warning")
            return not reason
        # The combo reads the snapshot every frame, so refusing the intent also
        # restores its old value. The server remains authoritative if data changes.
        if status in {"restricted", "illegal"} and not any(
            row.get("identity_id") != target.get("identity_id")
            and str(row.get("legal_status") or "").strip().casefold() in {"official", "legal"}
            and self._share(row.get("population_share")) > 0
            for row in rows
        ):
            (context.on_notice or self._notice.enqueue)(
                "Internal laws",
                f"At least one other {self.identity_type} group must remain legally recognized.",
                severity="warning",
            )
            return False
        context.net_client.send_action(ActionSetCountryIdentityPolicy(
            context.net_client.player_id, str(context.target_tag or "").strip().upper(),
            self.identity_type, str(target.get("identity_id") or ""), status))
        return True

    @staticmethod
    def _share(value):
        try:
            number = float(value)
        except (ValueError, TypeError, OverflowError):
            return 0.0
        return min(100.0, max(0.0, number)) if math.isfinite(number) else 0.0
