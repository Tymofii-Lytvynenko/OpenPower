from __future__ import annotations

from imgui_bundle import imgui

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.panels.politics.political_overview_presenter import PoliticalOverviewPresenter
from src.client.ui.panels.politics.presenter import PoliticsPresenter
from src.shared.actions import ActionSetElectionOverride


class PoliticalOverviewPanel:
    def __init__(self) -> None:
        self._presenter = PoliticalOverviewPresenter()
        self._legacy_presenter = PoliticsPresenter()
        self._override_durations: dict[tuple[str, str], int] = {}

    def render(self, state, context: PanelRenderContext) -> bool:
        with WindowManager.window("POLITICAL OVERVIEW", x=260, y=120, w=520, h=640) as is_open:
            if not is_open:
                return False
            self._render_content(state, context)
            return True

    def _render_content(self, state, context: PanelRenderContext) -> None:
        overview = self._presenter.build(state, context.target_tag)
        legacy = self._legacy_presenter.build_summary(state, context.target_tag)
        election = self._election_summary(overview.election_eligible, overview.days_to_next_election)

        imgui.text("GOVERNMENT")
        imgui.separator()
        imgui.text(f"Form: {overview.government_form}")
        imgui.text(f"Ruling authority: {overview.ruling_party}")
        imgui.text(f"Election: {election}")
        self._render_election_overrides(overview, context)
        self._render_recent_elections(overview)
        imgui.text(f"Capital: {legacy.capital_name}")
        imgui.text(f"Martial law: {'Active' if legacy.martial_law else 'Inactive'}")
        imgui.text(f"Election risk: {legacy.election_risk_pct:.1f}%")
        imgui.text(f"Free-market balance: {legacy.ideology_balance * 100.0:.1f}%")

        imgui.spacing()
        imgui.text("PUBLIC INDICATORS")
        imgui.separator()
        imgui.text(f"Approval: {self._percent(overview.approval_pct)}")
        imgui.text(f"Stability: {self._percent(overview.stability_pct)}")
        imgui.text(f"Corruption: {self._percent(overview.corruption_pct)}")
        imgui.text(f"Crisis: {overview.crisis_status}")

        imgui.spacing()
        imgui.text("PARTIES AND FACTIONS")
        imgui.separator()
        if overview.parties:
            for party in overview.parties:
                support = self._percent(party.support_pct)
                suffix = " — ruling" if party.is_ruling else ""
                imgui.text(f"{party.display_name}: {support}{suffix}")
        else:
            imgui.text_disabled("No party records are available.")

        imgui.spacing()
        imgui.text("ACTIVE LAWS")
        imgui.separator()
        if overview.laws:
            for law in overview.laws:
                imgui.text(f"{law.title}: {law.value} ({law.status})")
        else:
            imgui.text_disabled("No law records are available.")
        for transition in overview.pending_law_transitions:
            imgui.text_disabled(
                f"Pending {transition.law_id}: {transition.target_value} "
                f"at minute {transition.effective_at_minute}"
            )

        imgui.spacing()
        imgui.text("RECENT POLITICAL CAUSES")
        imgui.separator()
        if overview.recent_causes:
            for cause in overview.recent_causes:
                imgui.text(f"{cause.event_type}: {cause.reason}")
        else:
            imgui.text_disabled("No recorded political causes are available.")

    def _render_election_overrides(self, overview, context: PanelRenderContext) -> None:
        imgui.spacing()
        imgui.text("ELECTION OVERRIDES")
        imgui.separator()
        if not overview.election_override_options:
            imgui.text_disabled("No election override rules are configured for this government.")
            return

        for option in overview.election_override_options:
            key = (overview.country_id, option.override_type)
            duration_days = self._override_durations.get(key, option.default_duration_days)
            duration_days = min(
                option.maximum_duration_days,
                max(option.minimum_duration_days, duration_days),
            )
            if option.minimum_duration_days < option.maximum_duration_days:
                _, duration_days = imgui.slider_int(
                    f"{option.override_type.title()} duration (days)##{overview.country_id}-{option.override_type}",
                    duration_days,
                    option.minimum_duration_days,
                    option.maximum_duration_days,
                )
            self._override_durations[key] = duration_days

            cost = "Unavailable" if option.cost is None else f"{option.cost:,.2f}"
            imgui.text(
                f"Cost: {cost} · Approval: {option.approval_delta:+.1f} · "
                f"Stability: {option.stability_delta:+.1f}"
            )
            client = context.net_client
            if not option.available:
                imgui.text_disabled(option.unavailable_reason)
            elif not context.is_own_country:
                imgui.text_disabled("Select your own country to issue this action.")
            elif client is None:
                imgui.text_disabled("The authoritative game connection is unavailable.")
            elif imgui.small_button(
                f"Apply {option.override_type.title()}##{overview.country_id}-{option.override_type}"
            ):
                client.send_action(
                    ActionSetElectionOverride(
                        player_id=client.player_id,
                        country_tag=overview.country_id,
                        override_type=option.override_type,
                        duration_days=duration_days,
                    )
                )

    def _render_recent_elections(self, overview) -> None:
        imgui.text("RECENT ELECTION RECORDS")
        if not overview.recent_elections:
            imgui.text_disabled("No election results or override records are available.")
            return
        for election in overview.recent_elections:
            if election.status == "resolved":
                turnout = self._percent(election.turnout_pct)
                summary = f"Resolved: {election.winner_party_id or 'Unavailable'} · turnout {turnout}"
            else:
                summary = (
                    f"{election.status.title()} at minute {election.scheduled_at_minute}"
                )
            if election.override_type:
                summary += f" · {election.override_type}"
            imgui.text(summary)
            if election.reason:
                imgui.text_disabled(election.reason)

    def _election_summary(self, eligible: bool | None, days: int | None) -> str:
        if eligible is None:
            return "Unavailable"
        if not eligible:
            return "Not scheduled for this government form"
        if days is None:
            return "Unscheduled"
        return "Due" if days == 0 else f"In {days} game days"

    def _percent(self, value: float | None) -> str:
        return "Unavailable" if value is None else f"{value:.1f}%"
