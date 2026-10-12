from __future__ import annotations

import math

from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.primitives import UIPrimitives as Prims
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

    def __init__(self):
        self.identity_type = "language"
        self._details_key = None

    def render(self, state, context):
        tag = str(context.target_tag or "").strip().upper()
        Prims.header("Languages and religions", show_bg=False)
        imgui.text_wrapped("Population shares are gameplay estimates. Use Details to inspect their source.")
        for kind, title in (("language", "Languages"), ("religion", "Religions")):
            if kind == "religion":
                imgui.same_line()
            if imgui.button(title, test_id=f"identity.tab.{kind}"):
                self.identity_type = kind
                self._details_key = None
        imgui.text_disabled(f"Showing: {self.identity_type.title()} groups")
        frame = state.tables.get("country_identity_groups")
        rows = [] if frame is None else [
            row for row in frame.iter_rows(named=True)
            if str(row.get("country_id") or "").upper() == tag
            and row.get("identity_type") == self.identity_type
        ]
        rows.sort(key=lambda row: (-self._share(row.get("population_share")), str(row.get("display_name") or "")))
        can_edit = context.is_own_country and context.net_client is not None
        if not can_edit:
            imgui.text_disabled("Viewing another country. Policy changes require control of this country.")
        if not rows:
            imgui.text_disabled(f"No {self.identity_type} profile is available for {tag}.")
        elif imgui.begin_table("identity_groups", 4, imgui.TableFlags_.row_bg):
            imgui.table_setup_column("Group", imgui.TableColumnFlags_.width_stretch)
            imgui.table_setup_column("Share", imgui.TableColumnFlags_.width_fixed, 65)
            imgui.table_setup_column("Status", imgui.TableColumnFlags_.width_fixed, 115)
            imgui.table_setup_column("Source", imgui.TableColumnFlags_.width_fixed, 64)
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
                status = str(row.get("legal_status") or "legal").casefold()
                aggregate = bool(row.get("is_other_bucket"))
                imgui.begin_disabled(not can_edit or aggregate)
                imgui.set_next_item_width(-1)
                changed, index = imgui.combo("##status", IDENTITY_STATUSES.index(status) if status in IDENTITY_STATUSES else 1,
                                             [value.title() for value in IDENTITY_STATUSES], test_id=f"{widget_key}.status")
                imgui.end_disabled()
                if imgui.is_item_hovered(imgui.HoveredFlags_.allow_when_disabled):
                    imgui.set_tooltip("Other is an aggregate of unspecified groups; its status cannot be changed." if aggregate else STATUS_HELP.get(status, "Unknown policy status."))
                if changed and can_edit and not aggregate:
                    context.net_client.send_action(ActionSetCountryIdentityPolicy(
                        context.net_client.player_id, tag, self.identity_type, identity_id, IDENTITY_STATUSES[index]))
                imgui.table_next_column()
                if imgui.small_button("Details", test_id=f"{widget_key}.details"):
                    self._details_key = key
            imgui.end_table()
        selected = next((row for row in rows if (tag, self.identity_type, str(row.get("identity_id") or "")) == self._details_key), None)
        if selected is not None:
            imgui.separator()
            imgui.text_wrapped(f"Source details: {selected.get('display_name') or selected.get('identity_id')}")
            year = selected.get("source_year") or 0
            imgui.text(f"Source year: {year if year else 'Not recorded'}")
            imgui.text_wrapped(f"Reference: {selected.get('source_reference') or 'Not recorded'}")
            imgui.text_wrapped(f"Method / note: {selected.get('source_note') or 'Normalized bundled gameplay estimate; methodology not recorded.'}")
            if selected.get("is_other_bucket"):
                imgui.text_wrapped("Other combines unspecified groups. Its legal status is read-only.")
        if context.net_client is not None:
            results = getattr(getattr(state, "journal", None), "command_results", [])
            result = next((row for row in reversed(results)
                           if str(row.get("player_id") or "") == str(context.net_client.player_id)
                           and row.get("action_type") == "ActionSetCountryIdentityPolicy"), None)
            if result:
                imgui.text_wrapped(f"Latest policy result: {result.get('status')} · {result.get('reason', '')}")

    @staticmethod
    def _share(value):
        try:
            number = float(value)
        except (ValueError, TypeError, OverflowError):
            return 0.0
        return min(100.0, max(0.0, number)) if math.isfinite(number) else 0.0
