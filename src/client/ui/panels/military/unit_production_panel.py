from __future__ import annotations

from imgui_bundle import imgui

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.core.primitives import UIPrimitives as Prims
from src.client.ui.panels.military.presenter import MilitaryPresenter
from src.client.ui.panels.shared.panel_widgets import draw_empty_state, draw_required_tables
from src.shared.actions import (
    ActionCancelForeignUnitOrder,
    ActionCancelProductionOrder,
    ActionDispatchUnitDeployment,
    ActionQueueUnitProduction,
    ActionRequestForeignUnitOrder,
    ActionRespondForeignUnitOrder,
    ActionSetForeignOrderAcceptance,
    ActionSetProductionPaused,
    ActionSetProductionPriority,
)


class UnitProductionPanel:
    def __init__(self):
        self._presenter = MilitaryPresenter()

    def render(self, state, context: PanelRenderContext) -> bool:
        with WindowManager.window("UNIT PRODUCTION", x=560, y=140, w=560, h=420) as is_open:
            if not is_open:
                return False
            self._render_content(state, context)
            return True

    def _render_content(self, state, context: PanelRenderContext) -> None:
        country_tag = str(context.target_tag or "").upper()
        draw_required_tables(state, ("unit_designs", "production_orders", "unit_deployment_orders"))
        imgui.separator()

        designs = self._presenter.designs_for_country(state, country_tag)
        foreign_designs = self._presenter.foreign_designs_for_country(state, country_tag)
        orders = self._presenter.production_orders_for_country(state, country_tag)
        foreign_orders = self._presenter.foreign_orders_for_country(state, country_tag)
        deployments = self._presenter.deployment_orders_for_country(state, country_tag)
        posture = self._presenter.force_posture_text(state, country_tag)
        imgui.text_disabled(posture)
        imgui.dummy((0.0, 6.0))

        Prims.header("AVAILABLE DESIGNS", show_bg=False)
        if not designs:
            draw_empty_state("No design catalog is available for production.")
        else:
            for row in designs[:6]:
                imgui.text(str(row.get("display_name") or "Design"))
                imgui.same_line()
                Prims.right_align_text(
                    f"${float(row.get('cost') or 0.0):,.0f}".replace(",", " ")
                )
                if context.is_own_country and context.net_client is not None:
                    imgui.same_line()
                    if imgui.button(f"BUILD ONE##{row.get('id') or ''}"):
                        context.net_client.send_action(ActionQueueUnitProduction(
                            context.net_client.player_id, country_tag, str(row.get("id") or ""), 1,
                        ))

        imgui.dummy((0.0, 12.0))
        Prims.header("QUEUE", show_bg=False)
        if not orders:
            draw_empty_state("No production orders are queued.")
        for row in orders:
            order_id = str(row.get("id") or "")
            order_status = str(row.get("status") or "queued").lower()
            progress = max(0.0, min(100.0, float(row.get("progress") or 0.0) * 100.0))
            imgui.text(str(row.get("design_id") or "Design"))
            imgui.same_line()
            Prims.right_align_text(f"x{int(row.get('quantity') or 0)} · {order_status.title()}")
            Prims.meter("", progress, (0.35, 0.65, 0.35, 1.0))
            remaining = max(0.0, float(row.get("remaining_work") or 0.0))
            eta = int(row.get("eta_days") or -1)
            eta_label = "unknown" if eta < 0 else f"{eta} days"
            imgui.text_disabled(
                f"Priority {int(row.get('priority') or 1)} · Capacity {float(row.get('assigned_capacity') or 0.0):,.0f} · "
                f"Remaining funding ${remaining:,.0f} · ETA {eta_label}"
            )
            reason = str(row.get("blocking_reason") or "")
            if reason:
                imgui.text_wrapped(reason)
            if context.is_own_country and context.net_client is not None and order_status in {"queued", "paused"}:
                if imgui.small_button(f"{'RESUME' if order_status == 'paused' else 'PAUSE'}##{order_id}"):
                    context.net_client.send_action(ActionSetProductionPaused(
                        context.net_client.player_id, order_id, order_status != "paused",
                    ))
                imgui.same_line()
                if imgui.small_button(f"PRIORITY −##{order_id}"):
                    context.net_client.send_action(ActionSetProductionPriority(
                        context.net_client.player_id, order_id, max(1, int(row.get("priority") or 1) - 1),
                    ))
                imgui.same_line()
                if imgui.small_button(f"PRIORITY +##{order_id}"):
                    context.net_client.send_action(ActionSetProductionPriority(
                        context.net_client.player_id, order_id, min(100, int(row.get("priority") or 1) + 1),
                    ))
                imgui.same_line()
                if imgui.small_button(f"CANCEL##{order_id}"):
                    context.net_client.send_action(ActionCancelProductionOrder(
                        context.net_client.player_id, order_id,
                    ))

        Prims.header("ELIGIBLE FOREIGN DESIGNS", show_bg=False)
        if not foreign_designs:
            draw_empty_state("No foreign designs are currently eligible for inspection.")
        for row in foreign_designs[:6]:
            design_id = str(row.get("id") or "")
            seller = str(row.get("country_id") or "").strip().upper()
            imgui.text(f"{row.get('display_name', 'Design')} · {row.get('seller_name', seller)}")
            imgui.text_disabled(f"{row.get('domain', 'land')} · ${float(row.get('cost') or 0.0):,.0f} per group unit")
            if row.get("seller_accepts_orders"):
                if context.is_own_country and context.net_client is not None and imgui.small_button(f"REQUEST ONE##{design_id}"):
                    context.net_client.send_action(ActionRequestForeignUnitOrder(
                        context.net_client.player_id, country_tag, seller, design_id, 1,
                    ))
            else:
                imgui.text_disabled("Seller has not enabled foreign-order requests.")

        Prims.header("FOREIGN CONTRACTS", show_bg=False)
        if not foreign_orders:
            draw_empty_state("No foreign unit contracts are active or recently completed.")
        for row in foreign_orders[:8]:
            order_id = str(row.get("id") or "")
            buyer = str(row.get("buyer_country_id") or "").strip().upper()
            seller = str(row.get("seller_country_id") or "").strip().upper()
            status = str(row.get("status") or "unknown")
            imgui.text(f"{row.get('design_name', 'Design')} ×{int(row.get('quantity') or 0)} · {status.replace('_', ' ').title()}")
            imgui.text_disabled(f"Buyer {buyer} · Seller {seller} · ${float(row.get('price') or 0.0):,.0f} · {row.get('reason', '')}")
            if context.is_own_country and context.net_client is not None:
                if seller == country_tag and status == "pending_seller_acceptance":
                    if imgui.small_button(f"ACCEPT##{order_id}"):
                        context.net_client.send_action(ActionRespondForeignUnitOrder(context.net_client.player_id, order_id, True))
                    imgui.same_line()
                    if imgui.small_button(f"REJECT##{order_id}"):
                        context.net_client.send_action(ActionRespondForeignUnitOrder(context.net_client.player_id, order_id, False))
                    imgui.same_line()
                if status in {"pending_seller_acceptance", "accepted", "in_production"} and imgui.small_button(f"CANCEL CONTRACT##{order_id}"):
                    context.net_client.send_action(ActionCancelForeignUnitOrder(context.net_client.player_id, order_id))

        profile_table = state.tables.get("seller_acceptance_profiles")
        profile = None if profile_table is None else next((
            row for row in profile_table.to_dicts() if str(row.get("country_id") or "").strip().upper() == country_tag
        ), None)
        is_accepting = bool(profile and profile.get("accepts_foreign_orders"))
        if context.is_own_country and context.net_client is not None and imgui.button(
            "DISABLE FOREIGN ORDERS" if is_accepting else "ENABLE FOREIGN ORDERS"
        ):
            context.net_client.send_action(ActionSetForeignOrderAcceptance(
                context.net_client.player_id, country_tag, not is_accepting,
            ))

        imgui.dummy((0.0, 8.0))
        Prims.header("DEPLOYMENT QUEUE", show_bg=False)
        if not deployments:
            draw_empty_state("Completed groups will appear here until dispatched.")
        for row in deployments:
            deployment_id = str(row.get("id") or "")
            unit_id = str(row.get("unit_id") or "")
            quantity = max(0, int(row.get("quantity") or 0))
            imgui.text(f"{row.get('unit_type', 'unit')} ×{quantity} · {row.get('status', 'queued')}")
            imgui.text_disabled(f"From {row.get('origin_name', 'unknown')} → {row.get('destination_name', 'choose destination')}")
            reason = str(row.get("blocking_reason") or "")
            if reason:
                imgui.text_wrapped(reason)
            dispatchable = str(row.get("status") or "") in {"queued", "blocked"}
            can_dispatch = context.is_own_country and context.net_client is not None and context.selected_region_id is not None and dispatchable
            if can_dispatch:
                if imgui.button(f"DISPATCH GROUP TO SELECTED REGION##{deployment_id}"):
                    context.net_client.send_action(ActionDispatchUnitDeployment(
                        context.net_client.player_id, unit_id, int(context.selected_region_id), 0,
                    ))
                if quantity > 1:
                    imgui.same_line()
                    if imgui.button(f"SPLIT HALF##{deployment_id}"):
                        context.net_client.send_action(ActionDispatchUnitDeployment(
                            context.net_client.player_id, unit_id, int(context.selected_region_id), max(1, quantity // 2),
                        ))
