from __future__ import annotations

from src.client.ui.components.shared.dirty_close_confirmation import (
    CloseDecision,
    DirtyCloseConfirmation,
    SaveConfirmationPreferences,
)
from src.client.ui.components.shared.generic_message_dialog import GenericMessageDialog
from src.client.ui.components.shared.generic_question_dialog import (
    GenericQuestionDialog,
)
from src.client.ui.core.containers import WindowManager
from src.client.ui.core.gml_widgets import GMLWidgets
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.panel_close_intent import PanelCloseIntent
from src.client.ui.layouts.gml_layout import gml_child_frame
from src.client.ui.layouts.gml_rows import gml_row
from src.client.ui.panels.migration_presenter import MigrationPresenter
from src.client.ui.panels.politics.identity_policy_draft import IdentityPolicyDraft
from src.client.ui.panels.politics.identity_policy_view import IdentityPolicyView
from src.client.ui.panels.politics.law_policy_draft import LawPolicyDraft, law_choices
from src.client.ui.panels.politics.party_policy_draft import (
    PartyPolicyDraft,
    party_policy_context,
)
from src.client.ui.panels.politics.political_overview_presenter import (
    PoliticalOverviewPresenter,
)
from src.client.ui.panels.shared.panel_widgets import draw_empty_state


class InternalLawsPanel:
    """Compose OpenPower read models within the source section rectangles."""

    def __init__(self, open_politics_cb=None, open_migration_cb=None):
        self._law_notice = GenericMessageDialog()
        self._party_question = GenericQuestionDialog("laws.constitution.question")
        self._party_draft = PartyPolicyDraft()
        self._identity_draft = IdentityPolicyDraft()
        self._identity = IdentityPolicyView(self._law_notice, self._identity_draft)
        self._politics = PoliticalOverviewPresenter()
        self._migration = MigrationPresenter()
        self._open_politics = open_politics_cb
        self._open_migration = open_migration_cb
        self._law_draft = LawPolicyDraft()
        self._close_confirmation = DirtyCloseConfirmation("laws.close", "Apply law drafts before closing?")
        self._local_preferences = SaveConfirmationPreferences()
        self._close_intent = PanelCloseIntent()

    def request_close(self):
        self._close_intent.request()

    def render(self, state, context):
        if not self._close_confirmation.pending and not self._close_intent.pending and not self._party_question.is_open:
            self._law_draft.select_country(context.target_tag)
            self._identity_draft.select_country(context.target_tag)
            self._party_draft.select_country(context.target_tag)
        preferences = context.save_confirmation_preferences or self._local_preferences
        can_apply = bool(context.is_own_country and context.net_client is not None
                         and str(context.target_tag or "").upper() == self._law_draft.country)
        navigation_close = False if self._party_question.is_open else self._close_intent.consume()
        decision = None
        with WindowManager.window("INTERNAL LAWS", x=260, y=60, test_id="laws.panel", padding=(0, 0)) as is_open:
            if not is_open or navigation_close:
                if not self._has_changes:
                    return False
                decision = self._close_confirmation.request_close(preferences, can_apply=can_apply)
            else:
                self._render_content(state, context)
        if decision is None:
            decision = self._close_confirmation.render(preferences, can_apply=can_apply)
        keep_open = True
        if decision is not None:
            keep_open = self._finish_close(decision, state, context)
        self._party_question.render()
        self._identity.render_notices()
        return keep_open

    def _finish_close(self, decision, state, context):
        if decision is CloseDecision.DISCARD:
            self._discard_drafts()
            return False
        reason = self._apply_drafts(state, context)
        if reason:
            # Closing must not hide a rejected stale draft or its explanation.
            (context.on_notice or self._law_notice.enqueue)("Internal laws", reason, severity="warning")
            return True
        return False

    @property
    def _has_changes(self):
        return bool(self._law_draft.pending or self._identity_draft.pending or self._party_draft.pending)

    def _discard_drafts(self):
        self._law_draft.pending.clear()
        self._identity_draft.pending.clear()
        self._party_draft.pending.clear()

    def _apply_drafts(self, state, context):
        actions = []
        for draft in (self._law_draft, self._identity_draft, self._party_draft):
            prepared, reason = draft.prepare(state, context)
            if reason:
                return reason
            actions.extend(prepared)
        # Preflight every model before sending any intent. Gameplay acceptance
        # still belongs to the server and is independent for each command.
        self._discard_drafts()
        for action in actions:
            context.net_client.send_action(action)
        return ""

    def _choose_party(self, state, context, party, eligible, form):
        previous = self._party_draft.checkpoint()
        self._party_draft.choose(party, eligible, form)
        target = self._party_draft.transition_target(state)
        if target is None:
            return
        fingerprint = self._party_draft.fingerprint()
        message = (f"Change to {target[1]}?\nPending laws may be cancelled.\n"
                   "The election schedule will be replaced.\nApply will send the order.")
        def accept():
            if not self._party_draft.confirm_transition(target[0], fingerprint):
                (context.on_notice or self._law_notice.enqueue)("Internal laws", "The party draft changed. Choose the status again.", severity="warning")
        if not self._party_question.show(message, accept, lambda: self._party_draft.restore(previous)):
            self._party_draft.restore(previous)

    def _render_content(self, state, context):
        ui = GMLWidgets("Internal_Laws")
        ui.text("frmInner/frmDemographicGroups/lblTitle", "DEMOGRAPHIC GROUPS")
        page = "Tab2" if self._identity.identity_type == "language" else "Tab1"
        with gml_child_frame(f"Internal_Laws/frmInner/frmDemographicGroups/tabGroups/{page}/lstGroups"):
            imgui.push_style_var(imgui.StyleVar_.cell_padding, (1, 0))
            imgui.push_style_var(imgui.StyleVar_.frame_padding, (1, 0))
            try:
                self._identity.render(state, context, compact=True)
            finally:
                imgui.pop_style_var(2)
        self._identity.render_tabs(ui)
        overview = self._politics.build(state, context.target_tag)
        ui.text("frmInner/frmLaws/lblTitle", "CIVIL AND FAMILY LAWS")
        with gml_child_frame("Internal_Laws/frmInner/frmLaws/lstLaws"):
            self._render_laws(state, context, overview)
        ui.text("frmInner/frmOrganizations/lblTitle", "POLITICAL PARTIES")
        with gml_child_frame("Internal_Laws/frmInner/frmOrganizations/lstOrganization"):
            if not overview.parties:
                draw_empty_state("No party records available.")
            government, rule = party_policy_context(state, self._party_draft.country)
            for party in overview.parties:
                with gml_row("lstInternalLawsGroups", party.party_id) as row_ui:
                    row_ui.text("lblName", party.display_name)
                    row_ui.text("lblPerc", "—" if party.support_pct is None else f"{party.support_pct:.1f}%", right=True)
                    editable = bool(context.is_own_country and context.net_client is not None and rule
                                    and rule.get("party_policy_editable") and not party.is_ruling and party.eligible is not None)
                    status = self._party_draft.status(party)
                    choices = ["Ruling"] if party.is_ruling else ["Eligible", "Ineligible"] if party.eligible is not None else ["Unknown"]
                    imgui.begin_disabled(not editable)
                    changed, index = imgui.combo("##party-status", 0 if party.is_ruling or status is None or status else 1,
                                                 choices, gml_id=row_ui.path("cboStatus"),
                                                 test_id="laws.party." + party.party_id + ".status")
                    imgui.end_disabled()
                    if changed and editable:
                        self._choose_party(state, context, party, index == 0, government["government_form_id"])
                    if not editable and imgui.is_item_hovered(imgui.HoveredFlags_.allow_when_disabled):
                        imgui.set_tooltip("The ruling party cannot be prohibited." if party.is_ruling else "Party-policy authority is unavailable for this government form.")
            imgui.begin_disabled(self._open_politics is None)
            if imgui.button("Open political overview", test_id="laws.open_politics") and self._open_politics:
                self._open_politics()
            imgui.end_disabled()
        self._render_migration(state, context, ui)
        if ui.button("frmTitle/btnApply", "A", "laws.apply", enabled=self._has_changes and context.is_own_country,
                     tooltip="Apply drafted law changes", dynamic_enabled=True):
            reason = self._apply_drafts(state, context)
            if reason:
                (context.on_notice or self._law_notice.enqueue)("Internal laws", reason, severity="warning")

    def _render_laws(self, state, context, overview):
        if not overview.laws:
            draw_empty_state("No law records available.")
        table = state.tables.get("country_laws")
        rows = {} if table is None else {str(row.get("law_id") or ""): row for row in table.iter_rows(named=True)
                                        if str(row.get("country_id") or "").upper() == self._law_draft.country}
        for law in overview.laws:
            row = rows.get(law.law_id, {})
            choices = law_choices(row)
            with gml_row("lstInternalLawsLawsItem", law.law_id) as ui:
                ui.text("lblName", law.title)
                draft = self._law_draft.pending.get(law.law_id)
                value = draft.target_value if draft else law.value
                imgui.begin_disabled(not choices or not context.is_own_country or context.net_client is None)
                changed, index = imgui.combo("##law-" + law.law_id,
                                             choices.index(value) if value in choices else -1 if choices else 0,
                                             list(choices) if choices else [value],
                                             test_id="laws.value." + law.law_id, gml_id=ui.path("cboStatus"))
                imgui.end_disabled()
                if changed and choices:
                    self._law_draft.choose(row, choices[index])
        if self._has_changes and imgui.button("Discard policy draft", test_id="laws.discard"):
            self._discard_drafts()
        for transition in overview.pending_law_transitions:
            imgui.text_wrapped(f"Pending: {transition.law_id} -> {transition.target_value}")

    def _render_migration(self, state, context, ui):
        prefix = "frmInner/frmHumanMigration/"
        ui.text(prefix + "lblTitle", "HUMAN MIGRATION")
        ui.text(prefix + "lblImmigration", "Immigration")
        ui.text(prefix + "lblEmigration", "Emigration")
        table = state.tables.get("migration_policies")
        tag = str(context.target_tag or "").strip().upper()
        available = table is not None and any(str(row.get("country_id") or "").upper() == tag for row in table.iter_rows(named=True))
        summary = self._migration.present_country(state, tag) if available else None
        ui.text(prefix + "txtImmigrationValue", self._format_migration_rate(summary.entry_rate if summary else None), right=True)
        ui.text(prefix + "txtEmigrationValue", self._format_migration_rate(summary.exit_rate if summary else None), right=True)
        # The source slots open the richer authoritative OpenPower editor;
        # two invented boolean statuses would misrepresent its migration model.
        for slot, title, test_id in (("cboImmigrationStatus", "Entry policy", "laws.open_migration"),
                                     ("cboEmigrationStatus", "Exit policy", "laws.open_emigration")):
            rect = ui.rect(prefix + slot)
            size = (rect.width, rect.height) if rect is not None else (140.0, 16.0)
            if ui.button_at(prefix + slot, title, test_id, size=size,
                            enabled=self._open_migration is not None) and self._open_migration:
                self._open_migration()

    @staticmethod
    def _format_migration_rate(rate: float | None) -> str:
        return "—" if rate is None else f"{rate:.1%}"
