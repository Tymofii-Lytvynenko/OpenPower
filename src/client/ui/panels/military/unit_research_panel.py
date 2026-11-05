from __future__ import annotations

from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.containers import WindowManager
from src.client.ui.core.gml_widgets import GMLWidgets
from src.client.ui.core.panel_close_intent import PanelCloseIntent
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.core.testability import semantic_region
from src.client.ui.components.shared.dirty_close_confirmation import (
    CloseDecision,
    DirtyCloseConfirmation,
    SaveConfirmationPreferences,
)
from src.client.ui.panels.military.presenter import MilitaryPresenter
from src.shared.research_funding import (
    linked_research_funding_group,
    redistribute_linked_funding,
)
from src.shared.actions import ActionUpdateResearchFunding


_RESEARCH_CATEGORIES = (
    ("ground", "GROUND", "togGround", "frmGroundFinancing"),
    ("air", "AIR", "togAir", "frmAirFinancing"),
    ("naval", "NAVAL", "togNaval", "frmNavalFinancing"),
    ("strategic", "STRATEGIC", "togStrategic", "frmStrategicFinancing"),
)
_RESEARCH_METRICS = (
    ("Gun Range", "GunRange"),
    ("Gun Precision", "GunPrecision"),
    ("Gun Damage", "GunDamage"),
    ("Missile Range", "MissileRange"),
    ("Missile Precision", "MissilePrecision"),
    ("Missile Damage", "MissileDamage"),
    ("Missile Payload", "MissilePayload"),
    ("Speed", "Speed"),
    ("Sensors", "Sensors"),
    ("Armor", "Armor"),
    ("Stealth", "Stealth"),
    ("Countermeasures", "Countermeasures"),
)
_DETAIL_TABS = (
    ("technology", "TECHNOLOGY", "Tab1"),
    ("progress", "PROGRESS", "Tab2"),
    ("funding", "FUNDING", "Tab3"),
)
_STRATEGIC_TRACKS = (
    ("strategic_program", "PROGRAM"),
    ("strategic_weapons", "WEAPONS"),
    ("strategic_defense", "DEFENSE"),
)
_FUNDING_COLOR = (0.28, 0.66, 0.35, 1.0)
_PROGRESS_COLOR = (0.88, 0.70, 0.22, 1.0)
_UNAVAILABLE_COLOR = (0.48, 0.54, 0.60, 1.0)


class UnitResearchPanel:
    def __init__(self):
        self._presenter = MilitaryPresenter()
        self._selected_branch = "ground"
        self._selected_tab = "technology"
        self._draft_country_tag = ""
        self._funding_baseline: dict[str, float] = {}
        self._funding_draft: dict[str, float] = {}
        self._pending_funding_by_country: dict[str, dict[str, float]] = {}
        self._pending_result_cursors: dict[str, int] = {}
        self._pending_player_ids: dict[str, str] = {}
        self._close_intent = PanelCloseIntent()
        self.request_close = self._close_intent.request
        self._close_confirmation = DirtyCloseConfirmation(
            "unit_research.close",
            "Apply research funding changes before closing?",
        )
        self._local_save_confirmation_preferences = SaveConfirmationPreferences()

    def render(self, state, context: PanelRenderContext) -> bool:
        navigation_close = self._close_intent.consume()
        target_tag = str(context.target_tag or "").strip().upper()
        if not self._close_confirmation.pending:
            tracks = self._presenter.research_tracks_for_country(state, target_tag)
            tracks_by_branch = self._tracks_by_branch(tracks)
            if not self._has_changes and target_tag != self._draft_country_tag:
                self._sync_funding_draft(target_tag, tracks_by_branch)

        draft_tag = self._draft_country_tag or target_tag
        draft_tracks = self._presenter.research_tracks_for_country(state, draft_tag)
        tracks_by_branch = self._tracks_by_branch(draft_tracks)
        self._reconcile_funding_snapshot(draft_tag, tracks_by_branch, state)
        if not self._has_changes and draft_tag not in self._pending_funding_by_country:
            self._sync_funding_draft(draft_tag, tracks_by_branch)
        preferences = context.save_confirmation_preferences or self._local_save_confirmation_preferences
        can_apply = bool(
            context.is_own_country
            and context.net_client is not None
            and target_tag == draft_tag
        )
        keep_open = True
        viewport = imgui.get_io().display_size
        if viewport.x <= 0 or viewport.y <= 0:
            viewport = imgui.get_main_viewport().size
        x = max(0.0, (float(viewport.x) - 607.0) / 2.0)
        y = max(0.0, (float(viewport.y) - 455.0) / 2.0)
        with WindowManager.window(
            "UNIT RESEARCH", x=x, y=y, w=607, h=455,
            test_id="unit_research.panel",
            gml_template="Unit_Research_Window",
        ) as is_open:
            close_decision = None
            if not is_open or navigation_close:
                if self._has_changes:
                    close_decision = self._close_confirmation.request_close(
                        preferences,
                        can_apply=can_apply,
                    )
                else:
                    keep_open = False

            if is_open and not navigation_close:
                ui = GMLWidgets("Unit_Research_Window")
                self._draw_frames(ui)
                self._render_title_controls(ui, tracks_by_branch, context, can_apply, state)
                self._render_categories(ui)
                self._render_funding_controls(ui, tracks_by_branch, context, can_apply)
                self._render_program_view(ui, tracks_by_branch)
                self._render_detail_tabs(ui, tracks_by_branch, context, can_apply)

            if close_decision is not None:
                self._finish_close(close_decision, state, context, draft_tag)
                keep_open = False
            elif keep_open:
                close_decision = self._close_confirmation.render(
                    preferences,
                    can_apply=can_apply,
                )
                if close_decision is not None:
                    self._finish_close(close_decision, state, context, draft_tag)
                    keep_open = False

        return keep_open

    @staticmethod
    def _draw_frames(ui: GMLWidgets) -> None:
        for frame in (
            "frmDetails",
            "frmMain",
            "frmView",
            "frmView/frmModel",
            "frmMain/frmGroundFinancing",
            "frmMain/frmAirFinancing",
            "frmMain/frmNavalFinancing",
            "frmMain/frmStrategicFinancing",
        ):
            ui.frame(frame)

    def _render_title_controls(self, ui, tracks_by_branch, context, can_apply: bool, state) -> None:
        if ui.button(
            "frmTitle/btnApply",
            "✓",
            "unit_research.apply",
            enabled=self._has_changes and can_apply,
            dynamic_enabled=True,
            tooltip="Apply the drafted research funding changes.",
        ):
            self._apply_funding_draft(tracks_by_branch, context, state)

    def _render_categories(self, ui: GMLWidgets) -> None:
        with semantic_region("unit_research.branch_navigation", "Research categories"):
            for branch, label, toggle_slot, _ in _RESEARCH_CATEGORIES:
                changed, _ = ui.toggle(
                    f"frmMain/{toggle_slot}",
                    self._selected_branch == branch,
                    f"unit_research.branch.{branch}",
                    icon=label,
                    color=(0.29, 0.52, 0.73, 1.0),
                )
                if changed:
                    self._selected_branch = branch

    def _render_funding_controls(
        self,
        ui: GMLWidgets,
        tracks_by_branch: dict[str, dict],
        context: PanelRenderContext,
        can_apply: bool,
    ) -> None:
        can_edit = can_apply
        for branch, _, _, frame in _RESEARCH_CATEGORIES:
            row = tracks_by_branch.get(branch)
            ratio = self._funding_draft.get(branch, 0.0)
            is_pending = branch in self._pending_funding_by_country.get(self._draft_country_tag, {})
            slot = f"frmMain/{frame}/frmFinancing"
            changed, ratio = ui.meter_slider(
                slot,
                ratio,
                f"unit_research.funding.{branch}",
                _FUNDING_COLOR,
                enabled=can_edit,
                tooltip=f"Set the {branch} research funding ratio.",
            )
            if changed:
                self._stage_funding(branch, ratio)

            ui.text(
                f"frmMain/{frame}/lblNextAdvancement",
                f"{ratio:.0%}" if row or is_pending else "NEW",
                tooltip=("Research funding was sent; waiting for the authoritative state update."
                         if is_pending else
                         "Draft research funding; Apply sends changed branches." if self._has_changes
                         else "OpenPower stores funding per research branch."),
                test_id=f"unit_research.funding_value.{branch}",
            )

    def _render_program_view(
        self,
        ui: GMLWidgets,
        tracks_by_branch: dict[str, dict],
    ) -> None:
        with semantic_region("unit_research.model_view", "Research program details"):
            branch = self._selected_branch
            row = tracks_by_branch.get(branch)
            focus = str(row.get("focus") or self._branch_label(branch)) if row else "No research track"
            level = max(0, int(row.get("research_level") or 0)) if row else None
            progress = self._ratio(row.get("progress")) if row else None
            funding = self._funding_draft.get(branch, 0.0) if branch in self._funding_draft else None

            ui.text_at("frmView/frmModel", f"{self._branch_label(branch)} RESEARCH", offset=(14.0, 13.0), max_width=265.0)
            if branch == "strategic":
                level_status = str(level) if level is not None else "N/A"
                progress_status = f"{progress:.0%}" if progress is not None else "N/A"
                funding_status = f"{funding:.0%}" if funding is not None else "N/A"
                ui.text_at("frmView/frmModel", f"Focus: {focus}", offset=(14.0, 33.0), max_width=265.0)
                ui.text_at("frmView/frmModel", f"Level: {level_status}  Progress: {progress_status}", offset=(14.0, 53.0), max_width=265.0)
                ui.text_at("frmView/frmModel", f"Branch funding: {funding_status}", offset=(14.0, 73.0), max_width=265.0)
                ui.text_at("frmView/frmModel", "STRATEGIC TRACKS", offset=(14.0, 95.0), max_width=265.0)
                next_y = 113.0
                for track_branch, label in _STRATEGIC_TRACKS:
                    track = tracks_by_branch.get(track_branch)
                    track_level = max(0, int(track.get("research_level") or 0)) if track else None
                    track_progress = self._ratio(track.get("progress")) if track else None
                    track_text = (
                        f"{label}: LEVEL {track_level}  {track_progress:.0%}"
                        if track_level is not None and track_progress is not None
                        else f"{label}: NO TRACK"
                    )
                    ui.text_at(
                        "frmView/frmModel",
                        track_text,
                        offset=(14.0, next_y),
                        max_width=265.0,
                    )
                    next_y += 17.0
                ui.text_at(
                    "frmView/frmModel",
                    "3D preview unavailable.",
                    offset=(14.0, 170.0),
                    max_width=265.0,
                    color=_UNAVAILABLE_COLOR,
                    tooltip="OpenPower has no equivalent unit-model assets.",
                )
            else:
                level_status = str(level) if level is not None else "N/A"
                progress_status = f"{progress:.0%}" if progress is not None else "N/A"
                funding_status = f"{funding:.0%}" if funding is not None else "N/A"
                ui.text_at("frmView/frmModel", f"Focus: {focus}", offset=(14.0, 37.0), max_width=265.0)
                ui.text_at("frmView/frmModel", f"Research level: {level_status}", offset=(14.0, 59.0), max_width=265.0)
                ui.text_at("frmView/frmModel", f"Branch progress: {progress_status}", offset=(14.0, 81.0), max_width=265.0)
                ui.text_at("frmView/frmModel", f"Branch funding: {funding_status}", offset=(14.0, 103.0), max_width=265.0)
                ui.text_at(
                    "frmView/frmModel",
                    "Per-stat metrics unavailable.",
                    offset=(14.0, 127.0),
                    max_width=265.0,
                )
                ui.text_at(
                    "frmView/frmModel",
                    "3D preview unavailable.",
                    offset=(14.0, 147.0),
                    max_width=265.0,
                    color=_UNAVAILABLE_COLOR,
                    tooltip="OpenPower has no equivalent unit-model assets.",
                )

    def _render_detail_tabs(
        self,
        ui: GMLWidgets,
        tracks_by_branch: dict[str, dict],
        context: PanelRenderContext,
        can_apply: bool,
    ) -> None:
        tab_slot = "frmDetails/tabResearch"
        tab_rect = ui.rect(tab_slot)
        if tab_rect is None:
            return

        # GTabbed creates three 101x17 selectors in the bottom strip; those
        # generated buttons are not represented as child nodes in layout_catalog.gml.
        for index, (tab_id, label, _) in enumerate(_DETAIL_TABS):
            if ui.button_at(
                tab_slot,
                label,
                f"unit_research.tab.{tab_id}",
                offset=(index * 100.0, tab_rect.height - 17.0),
                size=(101.0, 17.0),
                padding=(1.0, 0.0),
            ):
                self._selected_tab = tab_id
            if self._selected_tab == tab_id:
                minimum = imgui.get_item_rect_min()
                maximum = imgui.get_item_rect_max()
                imgui.get_window_draw_list().add_line(
                    (minimum.x, maximum.y - 1.0),
                    (maximum.x, maximum.y - 1.0),
                    imgui.get_color_u32(_FUNDING_COLOR),
                    2.0,
                )

        selected = next((tab for tab in _DETAIL_TABS if tab[0] == self._selected_tab), _DETAIL_TABS[0])
        self._render_detail_page(ui, tracks_by_branch, context, can_apply, selected)

    def _render_detail_page(
        self,
        ui: GMLWidgets,
        tracks_by_branch: dict[str, dict],
        context: PanelRenderContext,
        can_apply: bool,
        tab: tuple[str, str, str],
    ) -> None:
        tab_id, label, page = tab
        with semantic_region(f"unit_research.detail.{tab_id}", f"{label.title()} research details"):
            branch = self._selected_branch
            page_root = f"frmDetails/tabResearch/{page}/frmInner"
            if tab_id == "progress":
                unavailable = "Per-characteristic progress is not tracked in OpenPower."
            elif tab_id == "funding":
                unavailable = "Funding is controlled per branch in the left panel."
            else:
                unavailable = "Per-characteristic technology ceilings are not tracked in OpenPower."

            can_edit = can_apply
            for index, (label, metric_id) in enumerate(_RESEARCH_METRICS):
                strategic_track = _STRATEGIC_TRACKS[index] if branch == "strategic" and index < len(_STRATEGIC_TRACKS) else None
                track_branch, track_label = strategic_track if strategic_track else ("", "")
                track = tracks_by_branch.get(track_branch) if track_branch else None
                display_label = track_label if strategic_track else (
                    "Missile Prec." if tab_id == "progress" and metric_id == "MissilePrecision" else label
                )
                ui.text(
                    f"{page_root}/lbl{metric_id}",
                    display_label,
                    tooltip=(
                        f"OpenPower tracks {track_label.lower()} research as a separate branch."
                        if strategic_track else unavailable
                    ),
                )
                meter_slot = f"{page_root}/frm{metric_id}"
                if strategic_track and tab_id == "technology" and track is not None:
                    ui.meter(meter_slot, 0.0, _UNAVAILABLE_COLOR)
                    level = max(0, int(track.get("research_level") or 0))
                    meter_rect = ui.rect(meter_slot)
                    if meter_rect is not None:
                        ui.text_at(
                            meter_slot,
                            f"LEVEL {level}",
                            offset=(3.0, 0.0),
                            max_width=meter_rect.width - 6.0,
                        )
                    continue

                if strategic_track and tab_id == "progress" and track is not None:
                    progress = self._ratio(track.get("progress"))
                    ui.meter(meter_slot, progress, _PROGRESS_COLOR)
                    ui.text(f"{meter_slot}/lblValue", f"{progress:.0%}")
                    continue

                if strategic_track and tab_id == "funding":
                    funding = self._funding_draft.get(track_branch, 0.0)
                    is_pending = track_branch in self._pending_funding_by_country.get(self._draft_country_tag, {})
                    changed, funding = ui.meter_slider(
                        meter_slot,
                        funding,
                        f"unit_research.funding.{track_branch}",
                        _FUNDING_COLOR,
                        enabled=can_edit,
                        tooltip=f"Set {track_label.lower()} research funding.",
                    )
                    if changed:
                        self._stage_funding(track_branch, funding)
                    meter_rect = ui.rect(meter_slot)
                    if meter_rect is not None:
                        value_label = f"{funding:.0%}" if track or is_pending else "NEW"
                        ui.text_at(
                            meter_slot,
                            value_label,
                            offset=(max(0.0, meter_rect.width - 34.0), 0.0),
                            max_width=34.0,
                            tooltip=("Research funding was sent; waiting for the authoritative state update."
                                     if is_pending else None),
                            test_id=f"unit_research.detail_funding_value.{track_branch}",
                        )
                    continue

                ui.meter(meter_slot, 0.0, _UNAVAILABLE_COLOR)
                if tab_id == "progress":
                    ui.text(f"{meter_slot}/lblValue", "N/A", tooltip=unavailable)
                else:
                    meter_rect = ui.rect(meter_slot)
                    if meter_rect is not None:
                        ui.text_at(
                            meter_slot,
                            "N/A",
                            offset=(max(0.0, meter_rect.width - 28.0), 0.0),
                            max_width=28.0,
                            color=_UNAVAILABLE_COLOR,
                            tooltip=unavailable,
                        )

    @staticmethod
    def _branch_label(branch: str) -> str:
        return next((label for key, label, _, _ in _RESEARCH_CATEGORIES if key == branch), branch.upper())

    @staticmethod
    def _ratio(value: object) -> float:
        try:
            return max(0.0, min(1.0, float(value or 0.0)))
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _tracks_by_branch(rows: list[dict]) -> dict[str, dict]:
        return {
            str(row.get("branch") or "").strip().lower(): row
            for row in rows
            if str(row.get("branch") or "").strip()
        }

    def _sync_funding_draft(self, country_tag: str, tracks_by_branch: dict[str, dict]) -> None:
        branches = self._funding_branches()
        values = {
            branch: self._ratio(
                tracks_by_branch.get(branch, {}).get("funding_ratio")
            )
            for branch in branches
        }
        values.update(self._pending_funding_by_country.get(country_tag, {}))
        self._draft_country_tag = country_tag
        self._funding_baseline = values.copy()
        self._funding_draft = values.copy()

    @staticmethod
    def _funding_branches() -> tuple[str, ...]:
        return tuple(dict.fromkeys((
            *(branch for branch, _, _, _ in _RESEARCH_CATEGORIES),
            *(branch for branch, _ in _STRATEGIC_TRACKS),
        )))

    def _stage_funding(self, branch: str, ratio: float) -> None:
        # REFERENCE GCursorMeter::UpdateCursors redistributes a changed cursor's delta
        # across unlocked cursors; share the same policy with the authority handler.
        self._funding_draft = redistribute_linked_funding(
            self._funding_draft,
            branch,
            ratio,
            linked_research_funding_group(branch),
        )

    @property
    def _has_changes(self) -> bool:
        return any(
            abs(self._funding_draft.get(branch, 0.0) - baseline) > 0.0001
            for branch, baseline in self._funding_baseline.items()
        )

    def _apply_funding_draft(self, tracks_by_branch, context, state) -> None:
        if not self._has_changes or context.net_client is None:
            return
        country_tag = self._draft_country_tag
        pending = self._pending_funding_by_country.setdefault(country_tag, {})
        is_new_pending_batch = not pending
        changed_values = {}
        for branch in self._funding_branches():
            value = self._funding_draft.get(branch, 0.0)
            baseline = self._funding_baseline.get(branch, 0.0)
            if abs(value - baseline) <= 0.0001:
                continue
            row = tracks_by_branch.get(branch)
            try:
                priority = max(1, int((row or {}).get("priority") or 1))
            except (TypeError, ValueError, OverflowError):
                priority = 1
            context.net_client.send_action(ActionUpdateResearchFunding(
                context.net_client.player_id,
                country_tag,
                branch,
                value,
                priority,
            ))
            changed_values[branch] = value
        if changed_values:
            pending.update(changed_values)
            if is_new_pending_batch:
                results = getattr(getattr(state, "journal", None), "command_results", [])
                self._pending_result_cursors[country_tag] = len(results)
                self._pending_player_ids[country_tag] = str(context.net_client.player_id or "")
        self._funding_baseline = self._funding_draft.copy()

    def _discard_funding_draft(self, country_tag: str, tracks_by_branch: dict[str, dict]) -> None:
        self._sync_funding_draft(country_tag, tracks_by_branch)

    def _finish_close(self, decision, state, context, country_tag: str) -> None:
        tracks = self._presenter.research_tracks_for_country(state, country_tag)
        tracks_by_branch = self._tracks_by_branch(tracks)
        if decision is CloseDecision.APPLY:
            self._apply_funding_draft(tracks_by_branch, context, state)
        else:
            self._discard_funding_draft(country_tag, tracks_by_branch)

    def _reconcile_funding_snapshot(self, country_tag: str, tracks_by_branch, state) -> None:
        pending = self._pending_funding_by_country.get(country_tag)
        if not pending:
            return

        snapshot_values = {
            branch: self._ratio(tracks_by_branch.get(branch, {}).get("funding_ratio"))
            for branch in self._funding_branches()
        }
        results = getattr(getattr(state, "journal", None), "command_results", [])
        cursor = self._pending_result_cursors.get(country_tag, len(results))
        player_id = self._pending_player_ids.get(country_tag, "")
        rejected = any(
            str(result.get("action_type") or "") == "ActionUpdateResearchFunding"
            and str(result.get("player_id") or "") == player_id
            and str(result.get("status") or "").lower() == "rejected"
            for result in results[cursor:]
        )
        if rejected:
            for branch in pending:
                self._funding_baseline[branch] = snapshot_values[branch]
            self._clear_pending_funding(country_tag)
            return

        # The network snapshot can lag one or more frames behind the submitted action.
        for branch, expected in list(pending.items()):
            if abs(snapshot_values[branch] - expected) <= 0.0001:
                self._funding_baseline[branch] = snapshot_values[branch]
                pending.pop(branch)

        for branch, actual in snapshot_values.items():
            if branch in pending:
                continue
            baseline = self._funding_baseline.get(branch, actual)
            draft = self._funding_draft.get(branch, actual)
            if abs(draft - baseline) <= 0.0001:
                self._funding_baseline[branch] = actual
                self._funding_draft[branch] = actual

        if not pending:
            self._clear_pending_funding(country_tag)

    def _clear_pending_funding(self, country_tag: str) -> None:
        self._pending_funding_by_country.pop(country_tag, None)
        self._pending_result_cursors.pop(country_tag, None)
        self._pending_player_ids.pop(country_tag, None)
