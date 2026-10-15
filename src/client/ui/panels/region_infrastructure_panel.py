from __future__ import annotations

from src.client.ui.core.instrumented_imgui import imgui

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.panels.infrastructure_presenter import InfrastructurePresenter
from src.shared.actions import ActionCancelInfrastructureProject, ActionInvestRegionalInfrastructure


class RegionInfrastructurePanel:
    """Displays a selected region and sends only semantic server actions."""

    def __init__(self, presenter: InfrastructurePresenter | None = None) -> None:
        self.presenter = presenter or InfrastructurePresenter()

    def render(self, state, context: PanelRenderContext) -> bool:
        with WindowManager.window("REGIONAL INFRASTRUCTURE", x=650, y=120, w=440, h=560) as is_open:
            if not is_open:
                return False
            region_id = context.selected_region_id
            if region_id is None:
                imgui.text_disabled("Select a region to inspect its infrastructure.")
                return True

            summary = self.presenter.build_region_summary(state, region_id)
            imgui.text(f"Region {summary.region_id} · Owner {summary.owner or 'Unowned'}")
            imgui.separator()
            for category in summary.categories:
                imgui.text(f"{category.category.title()}: level {category.level:.2f} / {category.maximum:.2f}")
                imgui.text(
                    f"Capacity {category.capacity:.0%} · condition {category.condition:.0%} · "
                    f"monthly maintenance need {category.maintenance_need:,.0f}"
                )
                if category.project_status:
                    imgui.text(
                        f"Project: {category.project_status} ({category.project_progress:.0%})"
                    )
                    if category.project_reason:
                        imgui.text_wrapped(category.project_reason)
                if category.last_source_type:
                    imgui.text(
                        f"Last change: {category.last_source_type} · "
                        f"minute {category.last_change_minute}"
                    )
                self._render_action(state, context, summary.owner, category)
                imgui.separator()
            effects = dict(summary.downstream_effects)
            imgui.text(
                "Regional effects — transport "
                f"{effects.get('transport_access', 0.0):.0%}, utilities "
                f"{effects.get('utilities_capacity', 0.0):.0%}, industrial "
                f"{effects.get('industrial_access', 0.0):.0%}, telecom "
                f"{effects.get('telecom_capacity', 0.0):.0%}"
            )
            return True

    @staticmethod
    def _render_action(state, context, owner: str, category) -> None:
        client = context.net_client
        if not context.is_own_country or client is None or owner.strip().upper() != context.target_tag.strip().upper():
            return
        active = category.project_status in {"in_progress", "paused"}
        if active:
            if category.project_id and imgui.small_button(f"Cancel##{category.category}"):
                client.send_action(
                    ActionCancelInfrastructureProject(client.player_id, category.project_id)
                )
            return

        if category.capacity + 0.000001 < category.level / max(0.000001, category.maximum):
            repair_target = min(
                category.level,
                category.capacity + 0.05,
            )
            if repair_target > category.capacity and imgui.small_button(f"Repair##{category.category}"):
                client.send_action(
                    ActionInvestRegionalInfrastructure(
                        client.player_id,
                        context.target_tag,
                        int(context.selected_region_id),
                        category.category,
                        repair_target,
                    )
                )
            return

        target = min(category.maximum, category.level + 0.05)
        if target > category.level and imgui.small_button(f"Invest +0.05##{category.category}"):
            client.send_action(
                ActionInvestRegionalInfrastructure(
                    client.player_id,
                    context.target_tag,
                    int(context.selected_region_id),
                    category.category,
                    target,
                )
            )
