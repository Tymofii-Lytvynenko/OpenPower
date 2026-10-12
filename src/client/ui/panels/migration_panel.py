from __future__ import annotations

from typing import Protocol

from src.client.ui.core.instrumented_imgui import imgui

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.panels.migration_presenter import MigrationCountrySummary, MigrationPresenter
from src.shared.actions import ActionUpdateMigrationPolicy


class MigrationPolicyUI(Protocol):
    def separator(self) -> None: ...

    def text(self, value: str) -> None: ...

    def combo(
        self,
        label: str,
        current_item: int,
        items: tuple[str, ...],
    ) -> tuple[bool, int]: ...

    def slider_float(
        self,
        label: str,
        value: float,
        minimum: float,
        maximum: float,
        format: str,
    ) -> tuple[bool, float]: ...

    def button(self, label: str) -> bool: ...


class MigrationPanel:
    """Displays migration read models and dispatches semantic policy intents only."""

    _MIGRATION_POSTURES = ("open", "managed", "restricted")
    _BORDER_POSTURES = ("open", "managed", "closed")

    def __init__(
        self,
        presenter: MigrationPresenter | None = None,
        *,
        imgui_api: MigrationPolicyUI | None = None,
    ) -> None:
        self._presenter = presenter or MigrationPresenter()
        self._policy_ui = imgui_api if imgui_api is not None else imgui
        self._draft_country = ""
        self._migration_index = 1
        self._border_index = 1
        self._entry_rate = 0.5
        self._exit_rate = 0.5
        self._asylum_rate = 0.25
        self._family_reunification_rate = 0.5
        self._skilled_worker_preference = 0.0
        self._enforcement_strength = 0.5

    def render(self, state, context: PanelRenderContext) -> bool:
        with WindowManager.window("MIGRATION", x=740, y=120, w=520, h=560) as is_open:
            if not is_open:
                return False
            country = self._presenter.present_country(state, context.target_tag)
            if country is None:
                imgui.text_disabled("No migration profile is available for this country.")
                return True

            self._render_country_summary(country)
            if context.selected_region_id is not None:
                self._render_region_summary(state, context.selected_region_id)
            self._render_policy_controls(state, context, country)
            return True

    def _render_country_summary(self, summary: MigrationCountrySummary) -> None:
        imgui.text(f"Country {summary.country_id} · {summary.migration_policy} migration · {summary.border_policy} border")
        imgui.separator()
        imgui.text(
            f"Recent 30-day flows: +{summary.gross_inflow:,} / -{summary.gross_outflow:,} "
            f"(net {summary.net_flow:+,}; {summary.recent_trend})"
        )
        imgui.text(
            f"Working-age change {summary.working_age_delta:+,} · services "
            f"{summary.service_pressure:.0%} · political pressure {summary.political_pressure:.0%} · "
            f"law pressure {summary.law_pressure:.0%}"
        )
        imgui.text(
            f"Entry / exit {summary.entry_rate:.0%} / {summary.exit_rate:.0%} · "
            f"asylum {summary.asylum_rate:.0%} · family reunification "
            f"{summary.family_reunification_rate:.0%}"
        )
        imgui.text(
            f"Skilled-worker preference {summary.skilled_worker_preference:.0%} · "
            f"enforcement {summary.enforcement_strength:.0%}"
        )
        imgui.separator()
        imgui.text("Top routes and latest reasons")
        if not summary.top_routes:
            imgui.text_disabled("No recorded routes in the current state.")
        for route in summary.top_routes:
            imgui.text_wrapped(
                f"{route.origin_region_id} → {route.destination_region_id}: "
                f"{route.population_count:,} · {route.status} · {route.reason_label}"
            )
        for status, count in summary.status_counts:
            if count:
                imgui.text_disabled(f"{status.title()}: {count}")

    def _render_region_summary(self, state, region_id: int) -> None:
        region = self._presenter.present_region(state, region_id)
        if region is None:
            return
        imgui.separator()
        capacity_text = "unknown" if region.capacity_pressure is None else f"{region.capacity_pressure:.0%}"
        imgui.text(
            f"Selected region {region.region_id}: net {region.net_migration:+,} · "
            f"incoming {region.incoming_population:,} · pending {region.pending_population:,} · "
            f"capacity load {capacity_text}"
        )
        for reason in region.recent_reasons:
            imgui.text_disabled(reason)

    def _render_policy_controls(
        self,
        state,
        context: PanelRenderContext,
        summary: MigrationCountrySummary,
    ) -> None:
        client = context.net_client
        can_edit = bool(context.is_own_country and client is not None)
        if not can_edit:
            return
        if self._draft_country != summary.country_id:
            self._draft_country = summary.country_id
            self._migration_index = self._index_or_default(self._MIGRATION_POSTURES, summary.migration_policy)
            self._border_index = self._index_or_default(self._BORDER_POSTURES, summary.border_policy)
            self._entry_rate = summary.entry_rate
            self._exit_rate = summary.exit_rate
            self._asylum_rate = summary.asylum_rate
            self._family_reunification_rate = summary.family_reunification_rate
            self._skilled_worker_preference = summary.skilled_worker_preference
            self._enforcement_strength = summary.enforcement_strength

        self._policy_ui.separator()
        self._policy_ui.text("Policy controls")
        _, self._migration_index = self._policy_ui.combo(
            "Migration posture", self._migration_index, self._MIGRATION_POSTURES
        )
        _, self._border_index = self._policy_ui.combo(
            "Border posture", self._border_index, self._BORDER_POSTURES
        )
        _, self._entry_rate = self._policy_ui.slider_float("Entry rate", self._entry_rate, 0.0, 1.0, "%.2f")
        _, self._exit_rate = self._policy_ui.slider_float("Exit rate", self._exit_rate, 0.0, 1.0, "%.2f")
        _, self._asylum_rate = self._policy_ui.slider_float("Asylum rate", self._asylum_rate, 0.0, 1.0, "%.2f")
        _, self._family_reunification_rate = self._policy_ui.slider_float(
            "Family reunification rate", self._family_reunification_rate, 0.0, 1.0, "%.2f"
        )
        _, self._skilled_worker_preference = self._policy_ui.slider_float(
            "Skilled worker preference", self._skilled_worker_preference, 0.0, 1.0, "%.2f"
        )
        _, self._enforcement_strength = self._policy_ui.slider_float(
            "Enforcement strength", self._enforcement_strength, 0.0, 1.0, "%.2f"
        )
        if self._policy_ui.button("Apply migration policy"):
            client.send_action(ActionUpdateMigrationPolicy(
                player_id=client.player_id,
                country_tag=summary.country_id,
                migration_policy=self._MIGRATION_POSTURES[self._migration_index],
                border_policy=self._BORDER_POSTURES[self._border_index],
                entry_rate=self._entry_rate,
                exit_rate=self._exit_rate,
                asylum_rate=self._asylum_rate,
                family_reunification_rate=self._family_reunification_rate,
                skilled_worker_preference=self._skilled_worker_preference,
                enforcement_strength=self._enforcement_strength,
                effective_at_minute=max(0, int(state.time.total_minutes)),
            ))

    @staticmethod
    def _index_or_default(options: tuple[str, ...], selected: str) -> int:
        try:
            return options.index(str(selected).strip().lower())
        except ValueError:
            return 1
