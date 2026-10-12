from __future__ import annotations

from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.core.primitives import UIPrimitives as Prims
from src.client.ui.panels.migration_presenter import MigrationPresenter
from src.client.ui.panels.politics.political_overview_presenter import PoliticalOverviewPresenter
from src.client.ui.panels.politics.identity_policy_view import IdentityPolicyView


class InternalLawsPanel:
    """Composes identity policy with authoritative political and migration summaries."""

    def __init__(self, open_politics_cb=None, open_migration_cb=None):
        self._identity = IdentityPolicyView()
        self._politics = PoliticalOverviewPresenter()
        self._migration = MigrationPresenter()
        self._open_politics = open_politics_cb
        self._open_migration = open_migration_cb

    def render(self, state, context: PanelRenderContext) -> bool:
        with WindowManager.window("INTERNAL LAWS", x=260, y=60, w=620, h=640) as is_open:
            if not is_open:
                return False
            imgui.text(f"Country: {context.target_tag}")
            self._identity.render(state, context)
            overview = self._politics.build(state, context.target_tag)
            Prims.header("Civil and family laws", show_bg=False)
            if not overview.laws:
                imgui.text_disabled("No civil or family law records are available.")
            for law in overview.laws:
                imgui.text_wrapped(f"{law.title}: {law.value} ({law.status})")
            for transition in overview.pending_law_transitions:
                imgui.text_wrapped(f"Pending: {transition.law_id} -> {transition.target_value}")

            Prims.header("Political parties", show_bg=False)
            if not overview.parties:
                imgui.text_disabled("No party records are available.")
            for party in overview.parties:
                support = "Unknown support" if party.support_pct is None else f"{party.support_pct:.1f}% support"
                status = "Ruling" if party.is_ruling else "Eligible" if party.eligible else "Ineligible" if party.eligible is False else "Eligibility unknown"
                imgui.text_wrapped(f"{party.display_name} · {support} · {status}")
            imgui.begin_disabled(self._open_politics is None)
            if imgui.button("Open political overview", test_id="laws.open_politics") and self._open_politics:
                self._open_politics()
            imgui.end_disabled()

            Prims.header("Human migration", show_bg=False)
            policy_table = state.tables.get("migration_policies")
            tag = str(context.target_tag or "").strip().upper()
            has_policy = policy_table is not None and any(
                str(row.get("country_id") or "").upper() == tag
                for row in policy_table.iter_rows(named=True)
            )
            summary = self._migration.present_country(state, tag) if has_policy else None
            if summary is None:
                imgui.text_disabled("No migration policy records are available.")
            else:
                imgui.text_wrapped(f"Migration: {summary.migration_policy.title()} · Border: {summary.border_policy.title()}")
                imgui.text_wrapped(f"Entry / exit policy: {summary.entry_rate:.0%} / {summary.exit_rate:.0%}")
                imgui.text_wrapped(f"Last 30 days: +{summary.gross_inflow:,} / -{summary.gross_outflow:,} · net {summary.net_flow:+,}")
            imgui.begin_disabled(self._open_migration is None)
            if imgui.button("Manage migration policy", test_id="laws.open_migration") and self._open_migration:
                self._open_migration()
            imgui.end_disabled()
            return True
