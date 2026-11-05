from __future__ import annotations

from imgui_bundle import icons_fontawesome_6

from src.client.ui.components.shared.dirty_close_confirmation import (
    CloseDecision,
    DirtyCloseConfirmation,
    SaveConfirmationPreferences,
)
from src.client.ui.components.shared.generic_message_dialog import GenericMessageDialog
from src.client.ui.components.shared.generic_question_dialog import GenericQuestionDialog
from src.client.ui.core.containers import WindowManager
from src.client.ui.core.gml_widgets import GMLWidgets
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.panels.politics.presenter import PoliticsPresenter
from src.client.ui.panels.shared.panel_data import resolve_region_name, safe_text
from src.shared.actions import ActionSetCountryCapital, ActionSetGovernmentForm
from modules.base.systems.world.authority_policy import foreign_government_change_restriction
from src.shared.region_control import region_controlled_by_country

# REFERENCE exposes this override only for government types 8 and 9, its two electoral forms.
_REFERENCE_ELECTORAL_FORM_IDS = frozenset({"multi-party democracy", "single-party democracy"})


class ConstitutionalFormPanel:
    """Render constitutional controls in their source GML positions."""

    def __init__(self):
        self._presenter = PoliticsPresenter()
        self._draft_country = ""
        self._pending_capital_region_id: int | None = None
        self._pending_government_form_id: str | None = None
        self._expected_government_form_id: str | None = None
        self._pending_martial_law: bool | None = None
        self._submitted_government_form_id: str | None = None
        self._submitted_expected_form_id: str | None = None
        self._submitted_target_martial_law: bool | None = None
        self._submitted_expected_martial_law: bool | None = None
        self._submitted_form_country = ""
        self._submitted_result_start = 0
        self._close_confirmation = DirtyCloseConfirmation(
            "constitutional_form.close",
            "Apply constitutional changes before closing?",
        )
        self._local_preferences = SaveConfirmationPreferences()
        self._notice = GenericMessageDialog()
        self._foreign_question = GenericQuestionDialog("constitutional_form.foreign.confirmation")

    def render(self, state, context: PanelRenderContext) -> bool:
        if self._foreign_question.is_open:
            self._foreign_question.render()
            self._notice.render()
            return True
        country = str(context.target_tag or "").strip().upper()
        if not self._close_confirmation.pending and country != self._draft_country:
            self._draft_country = country
            self._pending_capital_region_id = None
            self._pending_government_form_id = None
            self._expected_government_form_id = None
            self._pending_martial_law = None
            self._clear_government_form_submission()
        self._reconcile_government_form_submission(state, context, country)

        preferences = context.save_confirmation_preferences or self._local_preferences
        can_apply = self._can_edit_form(state, context)
        decision = None
        with WindowManager.window(
            "CONSTITUTIONAL FORM",
            x=260,
            y=120,
            test_id="constitutional_form.panel",
            padding=(0, 0),
        ) as is_open:
            if not is_open:
                if not self._has_pending_change(state, country):
                    self._notice.render()
                    return False
                decision = self._close_confirmation.request_close(
                    preferences,
                    can_apply=can_apply,
                )
            else:
                self._render_content(state, context)

        if decision is None:
            decision = self._close_confirmation.render(
                preferences,
                can_apply=can_apply,
            )
        if decision is None:
            self._foreign_question.render()
            self._notice.render()
            return True
        if decision is CloseDecision.DISCARD:
            self._clear_pending_changes()
            self._notice.render()
            return False

        reason = self._request_apply(state, context)
        if self._foreign_question.is_open:
            self._foreign_question.render()
            self._notice.render()
            return True
        if reason:
            self._notify(context, reason)
            self._notice.render()
            return True
        self._notice.render()
        return False

    def _render_content(self, state, context: PanelRenderContext) -> None:
        country = str(context.target_tag or "").strip().upper()
        can_apply = self._can_edit_form(state, context)
        summary = self._presenter.build_summary(state, country)
        martial_law = (
            self._pending_martial_law
            if self._pending_martial_law is not None
            else summary.martial_law
        )
        current_form_id = self._current_government_form_id(state, country, summary.government_type)
        current_capital_id = self._current_capital_id(state, country)
        capital_options = self._capital_options(state, country, current_capital_id)
        if not any(region_id == current_capital_id for region_id, _ in capital_options):
            capital_options.insert(0, (current_capital_id, summary.capital_name))
        option_ids = [region_id for region_id, _ in capital_options]
        option_names = [name for _, name in capital_options]
        selected_capital_id = (
            self._pending_capital_region_id
            if self._pending_capital_region_id is not None
            else current_capital_id
        )
        selected_capital_index = next(
            (index for index, region_id in enumerate(option_ids) if region_id == selected_capital_id),
            0,
        )
        can_edit_capital = bool(
            context.is_own_country
            and can_apply
            and any(region_id != current_capital_id for region_id in option_ids)
        )
        ui = GMLWidgets("Constitutional_Form")

        for frame in (
            "frmInner",
            "frmInner/frmConstitutionalForm",
            "frmInner/frmCapital",
            "frmInner/frmNextElection",
        ):
            ui.frame(frame)

        form_options = self._government_form_options(
            state, country, current_form_id, summary.government_type
        )
        if self._pending_government_form_id and all(
            form_id.casefold() != self._pending_government_form_id.casefold()
            for form_id, _ in form_options
        ):
            form_options.append((
                self._pending_government_form_id,
                self._form_display_name(state, self._pending_government_form_id),
            ))
        form_ids = [form_id for form_id, _ in form_options]
        form_names = [name for _, name in form_options]
        selected_form_id = self._pending_government_form_id or current_form_id
        selected_form = self._selected_form_index(form_ids, selected_form_id)
        can_edit_form = bool(
            can_apply
            and self._submitted_government_form_id is None
            and any(form_id.casefold() != current_form_id.casefold() for form_id in form_ids)
        )
        form_changed, selected_form = ui.combo_at(
            "frmInner/frmConstitutionalForm/cboConstitutionalForm",
            "##constitutional-form",
            selected_form,
            form_names,
            "constitutional_form.government_form",
            enabled=can_edit_form,
        )
        if form_changed and 0 <= selected_form < len(form_ids):
            selected_form_id = form_ids[selected_form]
            self._stage_government_form(
                current_form_id,
                selected_form_id,
                form_names[selected_form],
            )

        ui.text("frmInner/frmCapital/lblTitle", "CAPITAL")
        capital_changed, selected_capital_index = ui.combo_at(
            "frmInner/frmCapital/cboCapital",
            "##constitutional-capital",
            selected_capital_index,
            option_names,
            "constitutional_form.capital",
            enabled=can_edit_capital,
        )
        if capital_changed and 0 <= selected_capital_index < len(option_ids):
            self._pending_capital_region_id = option_ids[selected_capital_index]

        ui.text("frmInner/frmNextElection/lblTitle", "NEXT ELECTION")
        ui.text("frmInner/frmNextElection/lblElectionDate", summary.next_election)
        military_form = self._military_override_form(form_options, current_form_id)
        can_override = bool(
            can_edit_form
            and not martial_law
            and current_form_id.casefold() in _REFERENCE_ELECTORAL_FORM_IDS
            and self._is_election_eligible_form(state, current_form_id)
            and selected_form_id.casefold() == current_form_id.casefold()
            and military_form is not None
        )
        if can_override and military_form is not None:
            override_tooltip = f"Select {military_form[1]}; apply it through the validated government-form action."
        elif selected_form_id.casefold() != current_form_id.casefold():
            override_tooltip = "Apply or discard the staged form before using Override."
        elif martial_law:
            override_tooltip = "End martial law before using Override."
        elif not context.is_own_country:
            override_tooltip = "Override is available only for your country."
        elif not self._is_election_eligible_form(state, current_form_id):
            override_tooltip = "The current government form has no scheduled election."
        elif current_form_id.casefold() not in _REFERENCE_ELECTORAL_FORM_IDS:
            override_tooltip = "Override is available for single-party and multi-party democracies."
        elif military_form is None:
            override_tooltip = "No unique eligible military-led successor is defined by the current rules."
        else:
            override_tooltip = self._foreign_change_tooltip(state, context)
        override_clicked = ui.button(
            "frmInner/frmNextElection/btnOverride",
            "Override",
            "constitutional_form.override",
            enabled=can_override,
            tooltip=override_tooltip,
        )
        # REFERENCE stages the military form here and submits it through its regular Save action.
        if override_clicked and military_form is not None:
            self._stage_government_form(current_form_id, military_form[0])

        martial_law_label = "END MARTIAL LAW" if martial_law else "DECLARE MARTIAL LAW"
        can_edit_martial_law = bool(
            context.is_own_country
            and can_apply
            and self._submitted_government_form_id is None
        )
        martial_law_clicked = ui.button(
            "frmInner/btnDeclareMartialLaw",
            martial_law_label,
            "constitutional_form.martial_law",
            enabled=can_edit_martial_law,
            tooltip=(
                "Stage this change, then apply it with the title-bar checkmark."
                if can_edit_martial_law
                else "Only the controlled country's martial-law status can be changed."
            ),
        )
        if martial_law_clicked:
            self._pending_martial_law = not martial_law

        has_change = self._has_pending_change(state, country)
        if not can_apply:
            apply_tooltip = self._foreign_change_tooltip(state, context)
        elif context.net_client is None:
            apply_tooltip = "Connect to a game session before applying constitutional changes."
        elif not has_change:
            apply_tooltip = "Choose a government form, capital region, or martial-law status to apply."
        else:
            apply_tooltip = "Apply the selected constitutional changes."
        apply_clicked = ui.button(
            "frmTitle/btnApply",
            icons_fontawesome_6.ICON_FA_CHECK,
            "constitutional_form.apply",
            enabled=has_change and can_apply,
            dynamic_enabled=True,
            tooltip=apply_tooltip,
        )
        if apply_clicked:
            reason = self._request_apply(state, context)
            if reason:
                self._notify(context, reason)

    def _request_apply(self, state, context: PanelRenderContext) -> str:
        if context.net_client is None:
            return "Connect to a game session before applying constitutional changes."
        if not context.is_own_country:
            if not self._can_edit_form(state, context):
                return self._foreign_change_tooltip(state, context)
            if not self._foreign_question.show(
                "Apply these constitutional changes to the foreign country?",
                lambda: self._apply_confirmed_foreign_change(state, context),
                lambda: None,
            ):
                return "A foreign constitutional change is already awaiting confirmation."
            return ""
        return self._apply_changes(state, context)

    def _apply_confirmed_foreign_change(self, state, context: PanelRenderContext) -> None:
        reason = self._apply_changes(state, context, confirmed_foreign_change=True)
        if reason:
            self._notify(context, reason)

    def _apply_changes(
        self,
        state,
        context: PanelRenderContext,
        *,
        confirmed_foreign_change: bool = False,
    ) -> str:
        country = str(self._draft_country or "").strip().upper()
        current_capital_id = self._current_capital_id(state, country)
        target_region_id = self._pending_capital_region_id
        summary = self._presenter.build_summary(state, country)
        current_form_id = self._current_government_form_id(state, country, summary.government_type)
        target_form_id = self._pending_government_form_id or current_form_id
        target_martial_law = (
            self._pending_martial_law
            if self._pending_martial_law is not None
            else summary.martial_law
        )
        capital_changed = target_region_id is not None and target_region_id != current_capital_id
        form_changed = target_form_id.casefold() != current_form_id.casefold()
        martial_law_changed = target_martial_law != summary.martial_law
        if not capital_changed and not form_changed and not martial_law_changed:
            self._clear_pending_changes()
            return ""
        if context.net_client is None:
            return "Connect to a game session before applying constitutional changes."
        foreign_change = not context.is_own_country
        if foreign_change:
            restriction = self._foreign_change_tooltip(state, context)
            if restriction:
                return restriction
            if not confirmed_foreign_change:
                return "Confirm this foreign government-form change before applying it."
            if capital_changed or martial_law_changed:
                return "Foreign constitutional changes can only change the government form."

        if capital_changed:
            context.net_client.send_action(
                ActionSetCountryCapital(
                    player_id=context.net_client.player_id,
                    country_tag=country,
                    expected_capital_region_id=current_capital_id,
                    target_region_id=target_region_id,
                )
            )
        if form_changed or martial_law_changed:
            expected_form_id = self._expected_government_form_id or current_form_id
            self._submitted_government_form_id = target_form_id
            self._submitted_expected_form_id = expected_form_id
            self._submitted_target_martial_law = target_martial_law
            self._submitted_expected_martial_law = summary.martial_law
            self._submitted_form_country = country
            self._submitted_result_start = len(state.journal.command_results)
            context.net_client.send_action(
                ActionSetGovernmentForm(
                    player_id=context.net_client.player_id,
                    country_tag=country,
                    expected_form_id=expected_form_id,
                    target_form_id=target_form_id,
                    expected_martial_law=summary.martial_law,
                    target_martial_law=target_martial_law,
                    confirmed_foreign_change=confirmed_foreign_change,
                )
            )
        self._pending_capital_region_id = None
        if not form_changed:
            self._pending_government_form_id = None
            self._expected_government_form_id = None
        return ""

    def _can_edit_form(self, state, context: PanelRenderContext) -> bool:
        if context.net_client is None:
            return False
        if context.is_own_country:
            return True
        return not foreign_government_change_restriction(
            state, context.net_client.player_id, context.target_tag
        )

    def _foreign_change_tooltip(self, state, context: PanelRenderContext) -> str:
        if context.net_client is None:
            return "Connect to a game session before applying constitutional changes."
        return foreign_government_change_restriction(
            state, context.net_client.player_id, context.target_tag
        )

    def _has_pending_change(self, state, country: str) -> bool:
        capital_pending = (
            self._pending_capital_region_id is not None
            and self._pending_capital_region_id != self._current_capital_id(state, country)
        )
        summary = self._presenter.build_summary(state, country)
        current_form_id = self._current_government_form_id(state, country, summary.government_type)
        selected_form = self._pending_government_form_id or current_form_id
        submission_waiting = bool(
            self._submitted_government_form_id
            and self._submitted_form_country == country
            and self._submitted_government_form_id.casefold()
            == selected_form.casefold()
            and (
                self._pending_martial_law is None
                or self._submitted_target_martial_law == self._pending_martial_law
            )
        )
        form_pending = bool(
            self._pending_government_form_id
            and self._pending_government_form_id.casefold() != current_form_id.casefold()
            and not submission_waiting
        )
        martial_law_pending = (
            self._pending_martial_law is not None
            and self._pending_martial_law != summary.martial_law
            and not submission_waiting
        )
        return capital_pending or form_pending or martial_law_pending

    def _reconcile_government_form_submission(self, state, context, country: str) -> None:
        submitted_form = self._submitted_government_form_id
        if not submitted_form or self._submitted_form_country != country:
            return

        summary = self._presenter.build_summary(state, country)
        current_form = self._current_government_form_id(state, country, summary.government_type)
        current_martial_law = summary.martial_law
        target_martial_law = self._submitted_target_martial_law
        form_confirmed = current_form.casefold() == submitted_form.casefold()
        martial_law_confirmed = (
            target_martial_law is None or current_martial_law == target_martial_law
        )
        if form_confirmed and martial_law_confirmed:
            self._clear_government_form_submission()
            self._pending_government_form_id = None
            self._expected_government_form_id = None
            self._pending_martial_law = None
            return

        form_changed_elsewhere = (
            current_form.casefold() != (self._submitted_expected_form_id or "").casefold()
            and not form_confirmed
        )
        martial_law_changed_elsewhere = (
            self._submitted_expected_martial_law is not None
            and current_martial_law != self._submitted_expected_martial_law
            and not martial_law_confirmed
        )
        if form_changed_elsewhere or martial_law_changed_elsewhere:
            self._clear_government_form_submission()
            self._pending_government_form_id = None
            self._expected_government_form_id = None
            self._pending_martial_law = None
            reason = (
                "The government form changed while this request was pending. Review the current form."
                if form_changed_elsewhere
                else "Martial law changed while this request was pending. Review its current status."
            )
            self._notify(context, reason)
            return

        results = state.journal.command_results[self._submitted_result_start:]
        rejection = next(
            (
                result for result in results
                if str(result.get("action_type") or "") == "ActionSetGovernmentForm"
                and str(result.get("country_id") or "").strip().upper() == country
                and str(result.get("target_form_id") or "").casefold() == submitted_form.casefold()
                and result.get("target_martial_law", target_martial_law) == target_martial_law
                and str(result.get("status") or "").casefold() == "rejected"
            ),
            None,
        )
        if rejection is not None:
            reason = str(rejection.get("reason") or "The government form change was rejected.")
            self._clear_government_form_submission()
            self._pending_government_form_id = None
            self._expected_government_form_id = None
            self._pending_martial_law = None
            self._notify(context, reason)

    def _clear_government_form_submission(self) -> None:
        self._submitted_government_form_id = None
        self._submitted_expected_form_id = None
        self._submitted_target_martial_law = None
        self._submitted_expected_martial_law = None
        self._submitted_form_country = ""
        self._submitted_result_start = 0

    @staticmethod
    def _current_capital_id(state, country: str) -> int:
        governments = state.tables.get("country_governments")
        if governments is None or "country_id" not in governments.columns:
            return 0
        government = next(
            (
                row for row in governments.iter_rows(named=True)
                if str(row.get("country_id") or "").strip().upper() == country
            ),
            None,
        )
        try:
            return int(government.get("capital_region_id") or 0) if government else 0
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _capital_options(state, country: str, current_capital_id: int) -> list[tuple[int, str]]:
        regions = state.tables.get("regions")
        if regions is None or not {"id", "owner"}.issubset(regions.columns):
            return []

        options: dict[int, str] = {}
        for region in regions.iter_rows(named=True):
            try:
                region_id = int(region.get("id") or 0)
            except (TypeError, ValueError):
                continue
            if region_id <= 0:
                continue
            if region_id == current_capital_id or region_controlled_by_country(state, region, country):
                options[region_id] = resolve_region_name(state, region_id)
        return sorted(options.items(), key=lambda item: (item[1].casefold(), item[0]))

    @staticmethod
    def _government_form_options(
        state,
        country: str,
        current_form: str,
        current_label: str,
    ) -> list[tuple[str, str]]:
        table = state.tables.get("government_form_rules")
        parties_table = state.tables.get("political_parties")
        government_table = state.tables.get("country_governments")
        if table is None or table.is_empty() or parties_table is None or government_table is None:
            return [(current_form or current_label, current_label or "Unavailable")]

        government = next(
            (
                row for row in government_table.iter_rows(named=True)
                if str(row.get("country_id") or "").strip().upper() == country
            ),
            None,
        )
        parties = [
            row for row in parties_table.iter_rows(named=True)
            if str(row.get("country_id") or "").strip().upper() == country
        ]
        if government is None or not parties:
            return [(current_form or current_label, current_label or "Unavailable")]

        crisis_active = str(government.get("crisis_status") or "none").strip().casefold() not in {
            "", "none", "resolved"
        }
        crises = state.tables.get("political_crises")
        if crises is not None and {"country_id", "status"}.issubset(crises.columns):
            crisis_active = crisis_active or any(
                str(row.get("country_id") or "").strip().upper() == country
                and str(row.get("status") or "").strip().casefold()
                in {"pending", "active", "open", "escalated"}
                for row in crises.iter_rows(named=True)
            )
        eligible_count = sum(bool(row.get("eligible")) for row in parties)

        rows = sorted(
            table.to_dicts(),
            key=lambda row: str(row.get("government_form_id") or "").casefold(),
        )
        options: list[tuple[str, str]] = []
        for row in rows:
            form_id = safe_text(row.get("government_form_id"), "").strip()
            if not form_id:
                continue
            minimum = row.get("minimum_eligible_parties")
            maximum = row.get("maximum_eligible_parties")
            is_current = form_id.casefold() == current_form.casefold()
            valid_limits = (
                type(minimum) is int and type(maximum) is int
                and minimum >= 1 and maximum >= 0
            )
            valid_count = valid_limits and eligible_count >= minimum and (
                maximum == 0 or eligible_count <= maximum
            )
            if is_current or (not crisis_active and valid_count):
                options.append((form_id, safe_text(row.get("display_name"), form_id)))

        if all(form_id.casefold() != current_form.casefold() for form_id, _ in options):
            options.append((current_form, current_label or current_form or "Unavailable"))
        return sorted(options, key=lambda item: (item[1].casefold(), item[0].casefold()))

    @staticmethod
    def _current_government_form_id(state, country: str, current_label: str) -> str:
        governments = state.tables.get("country_governments")
        if governments is None or "country_id" not in governments.columns:
            return current_label.casefold()
        government = next(
            (
                row for row in governments.iter_rows(named=True)
                if str(row.get("country_id") or "").strip().upper() == country
            ),
            None,
        )
        if government is None:
            return current_label.casefold()
        form_id = safe_text(government.get("government_form_id"), "").strip()
        if form_id:
            return form_id
        label = safe_text(government.get("government_type"), current_label).strip().casefold()
        rules = state.tables.get("government_form_rules")
        if rules is not None and not rules.is_empty():
            match = next(
                (
                    row for row in rules.iter_rows(named=True)
                    if safe_text(row.get("display_name"), "").strip().casefold() == label
                ),
                None,
            )
            if match is not None:
                return safe_text(match.get("government_form_id"), label)
        return label

    @staticmethod
    def _form_display_name(state, form_id: str) -> str:
        rules = state.tables.get("government_form_rules")
        if rules is not None and not rules.is_empty():
            row = next(
                (
                    item for item in rules.iter_rows(named=True)
                    if safe_text(item.get("government_form_id"), "").casefold() == form_id.casefold()
                ),
                None,
            )
            if row is not None:
                return safe_text(row.get("display_name"), form_id)
        return form_id

    @staticmethod
    def _military_override_form(
        form_options: list[tuple[str, str]], current_form: str
    ) -> tuple[str, str] | None:
        current = str(current_form or "").casefold()
        candidates = [
            (form_id, display_name)
            for form_id, display_name in form_options
            if form_id.casefold() != current
            and "military" in f"{form_id} {display_name}".casefold()
        ]
        return candidates[0] if len(candidates) == 1 else None

    @staticmethod
    def _is_election_eligible_form(state, form_id: str) -> bool:
        rules = state.tables.get("government_form_rules")
        if rules is None:
            return False
        row = next(
            (
                item for item in rules.iter_rows(named=True)
                if safe_text(item.get("government_form_id"), "").casefold() == form_id.casefold()
            ),
            None,
        )
        return bool(row and row.get("election_eligible") is True)

    def _stage_government_form(
        self,
        current_form: str,
        target_form: str,
        target_display_name: str = "",
    ) -> bool:
        target = str(target_form or "").strip()
        if not target:
            return False
        if target.casefold() == current_form.casefold():
            self._pending_government_form_id = None
            self._expected_government_form_id = None
        else:
            if self._pending_government_form_id is None:
                self._expected_government_form_id = current_form
            self._pending_government_form_id = target
            if "military" not in f"{target} {target_display_name}".casefold():
                self._pending_martial_law = False
        return True

    @staticmethod
    def _selected_form_index(options: list[str], current_form: str) -> int:
        current = str(current_form or "").casefold()
        return next((index for index, name in enumerate(options) if name.casefold() == current), 0)

    def _clear_pending_changes(self) -> None:
        self._pending_capital_region_id = None
        self._pending_government_form_id = None
        self._expected_government_form_id = None
        self._pending_martial_law = None

    def _notify(self, context: PanelRenderContext, reason: str) -> None:
        if context.on_notice is not None:
            context.on_notice("Constitutional form", reason, severity="warning")
        else:
            self._notice.enqueue("Constitutional form", reason, severity="warning")
