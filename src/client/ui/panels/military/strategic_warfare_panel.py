from __future__ import annotations

from src.client.ui.core.instrumented_imgui import imgui
import polars as pl

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.core.primitives import UIPrimitives as Prims
from src.client.ui.panels.military.presenter import MilitaryPresenter
from src.client.ui.panels.shared.panel_widgets import draw_empty_state, draw_required_tables
from src.shared.actions import ActionLaunchStrategicStrike, ActionProduceStrategicWeapon


class StrategicWarfarePanel:
    def __init__(self):
        self._presenter = MilitaryPresenter()
        self._selected_payloads: dict[str, int] = {}
        self._selected_authorization_contexts: dict[str, str] = {}

    def render(self, state, context: PanelRenderContext) -> bool:
        with WindowManager.window("STRATEGIC WARFARE", x=840, y=180, w=500, h=360) as is_open:
            if not is_open:
                return False
            self._render_content(state, context)
            return True

    def _render_content(self, state, context: PanelRenderContext) -> None:
        country_tag = str(context.target_tag or "").strip().upper()
        draw_required_tables(state, ("strategic_weapons", "strategic_launch_orders", "missile_defense_layers"))
        imgui.separator()

        rows = self._presenter.strategic_inventory_for_country(state, country_tag)
        profiles = self._presenter.strategic_payload_profiles(state)
        if not rows:
            draw_empty_state("No strategic inventory is available for the selected country.")
        for row in rows:
            ready = int(row.get("ready") or 0)
            total = int(row.get("quantity") or 0)
            defense = float(row.get("defense_rating") or 0.0) * 100.0
            weapon_id = str(row.get("id") or "")
            imgui.text(f"{row.get('weapon_class') or row.get('weapon_type') or 'Strategic system'} · {weapon_id}")
            imgui.same_line()
            Prims.right_align_text(f"{ready}/{total} ready")
            imgui.text_disabled(
                f"Range {float(row.get('range_km') or 0.0):,.0f} km · "
                f"Payload cap {int(row.get('payload_cap') or 0)} · "
                f"Defense rating {defense:.0f}%"
            )
            if not bool(row.get("research_permitted")):
                imgui.text_disabled("Unavailable: complete the strategic program and weapon research first.")
                continue
            payload_cap = max(1, int(row.get("payload_cap") or 1))
            payload_level = min(payload_cap, max(1, self._selected_payloads.get(weapon_id, int(row.get("payload_level") or 1))))
            yield_kt, radius_km = profiles.get(payload_level, (0.0, 0.0))
            preview = f"Level {payload_level}: {yield_kt:,.0f} kt · {radius_km:g} km"
            if imgui.begin_combo(f"Payload profile##{weapon_id}", preview):
                for level, (profile_yield, profile_radius) in sorted(profiles.items()):
                    if level > payload_cap:
                        continue
                    label = f"Level {level}: {profile_yield:,.0f} kt · {profile_radius:g} km##payload-{weapon_id}-{level}"
                    if imgui.selectable(label, level == payload_level)[0]:
                        payload_level = level
                imgui.end_combo()
            self._selected_payloads[weapon_id] = payload_level

            region_id = context.selected_region_id
            target = None
            regions = state.tables.get("regions")
            if region_id is not None and regions is not None and "id" in regions.columns:
                matches = regions.filter(pl.col("id") == int(region_id))
                target = None if matches.is_empty() else matches.to_dicts()[0]
            target_country = str((target or {}).get("owner") or "").strip().upper()
            authorization_contexts = self._presenter.strategic_authorization_contexts(state)
            authorization_context = self._selected_authorization_contexts.get(country_tag, "")
            if authorization_context not in authorization_contexts:
                authorization_context = ""
            if authorization_contexts and imgui.begin_combo(
                f"Launch authorization##{weapon_id}", authorization_context or "Select configured context",
            ):
                for option in authorization_contexts:
                    if imgui.selectable(option, option == authorization_context)[0]:
                        authorization_context = option
                imgui.end_combo()
            self._selected_authorization_contexts[country_tag] = authorization_context

            target_defense = None
            if target is not None and target_country and target_country != country_tag:
                target_defense = self._presenter.strategic_defense_estimate_for_region(
                    state, target_country, int(region_id),
                )
            if target_defense is None:
                imgui.text_disabled("Select an enemy region to preview target coverage and interception chance.")
            else:
                imgui.text("TARGET DEFENSE ESTIMATE")
                target_name = str(target.get("name") or target.get("id") or region_id)
                imgui.text_disabled(f"Selected target: {target_name} · {target_country} · region {int(region_id)}")
                imgui.text_disabled(
                    f"Configured interception estimate {float(target_defense.get('interception_probability') or 0.0) * 100:.1f}%"
                )
                covered_layers = target_defense.get("covered_layers") or []
                if not covered_layers:
                    imgui.text_disabled("No configured defense layer is available for this target.")
                for layer in covered_layers:
                    if layer.get("covered") and layer.get("researched_and_operational"):
                        coverage = "covers target"
                    elif not layer.get("researched_and_operational"):
                        coverage = "inactive or unresearched"
                    else:
                        coverage = "outside coverage"
                    coverage_details = []
                    region_ids = layer.get("coverage_region_ids") or []
                    if region_ids:
                        coverage_details.append("regions " + ", ".join(str(int(item)) for item in region_ids))
                    coverage_radius = float(layer.get("coverage_radius_km") or 0.0)
                    if coverage_radius > 0.0:
                        coverage_details.append(f"radius {coverage_radius:,.0f} km")
                    range_km = float(layer.get("range_km") or 0.0)
                    if range_km > 0.0:
                        coverage_details.append(f"range {range_km:,.0f} km")
                    configured_coverage = "; ".join(coverage_details) or "no configured area"
                    imgui.text_disabled(
                        f"{layer.get('layer')} · {coverage} · "
                        f"first {float(layer.get('effective_first_attempt_probability') or 0.0) * 100:.0f}% · "
                        f"second {float(layer.get('effective_second_attempt_probability') or 0.0) * 100:.0f}% · "
                        f"layer estimate {float(layer.get('layer_interception_probability') or 0.0) * 100:.0f}% · "
                        f"coverage {configured_coverage}"
                    )

            launch_preview = self._presenter.strategic_launch_preview(
                state, country_tag, row, None if region_id is None else int(region_id), authorization_context,
            )
            imgui.text_disabled(
                f"Launch authorization: {launch_preview['authorization']} · "
                f"Estimated resolution: {int(launch_preview['flight_minutes'])} min"
            )
            for reason in launch_preview["reasons"]:
                imgui.text_disabled(reason)
            if (
                context.is_own_country and context.net_client is not None and target is not None
                and target_country and target_country != country_tag and launch_preview["can_launch"]
            ):
                if imgui.button(f"STRIKE MILITARY##{weapon_id}"):
                    context.net_client.send_action(ActionLaunchStrategicStrike(
                        context.net_client.player_id, country_tag, int(region_id),
                        str(row.get("weapon_type") or "icbm"), target_country_tag=target_country,
                        target_mode="military", weapon_id=weapon_id, payload_level=payload_level,
                        authorization_context=authorization_context,
                        origin_region_id=int(row.get("origin_region_id") or 0),
                    ))
                imgui.same_line()
                if imgui.button(f"STRIKE CIVILIAN##{weapon_id}"):
                    context.net_client.send_action(ActionLaunchStrategicStrike(
                        context.net_client.player_id, country_tag, int(region_id),
                        str(row.get("weapon_type") or "icbm"), target_country_tag=target_country,
                        target_mode="civilian", weapon_id=weapon_id, payload_level=payload_level,
                        authorization_context=authorization_context,
                        origin_region_id=int(row.get("origin_region_id") or 0),
                    ))
            elif row.get("pending_order_status"):
                imgui.text_disabled(f"Pending launch · target region {row.get('pending_target_region_id')}")

            production = self._presenter.strategic_production_preview(state, country_tag, row)
            if production["can_produce"]:
                imgui.text_disabled(
                    f"Production: ${float(production['cost_per_weapon']):,.0f} · "
                    f"{int(production['production_minutes'])} min per weapon"
                )
                if context.is_own_country and context.net_client is not None and imgui.button(f"PRODUCE ONE##{weapon_id}"):
                    context.net_client.send_action(ActionProduceStrategicWeapon(
                        context.net_client.player_id, country_tag, weapon_id, 1,
                    ))
            else:
                for reason in production["reasons"]:
                    imgui.text_disabled(reason)

        imgui.dummy((0.0, 6.0))
        imgui.text("MISSILE DEFENSE")
        defenses = self._presenter.missile_defense_for_country(state, country_tag)
        if not defenses:
            imgui.text_disabled("No missile-defense layers are fielded.")
        for layer in defenses:
            status = "operational" if layer.get("operational") and layer.get("researched") else "inactive or unresearched"
            probability = float(layer.get("first_attempt_probability") or (0.6 if layer.get("layer") == "long_range" else 0.5))
            imgui.text_disabled(
                f"{layer.get('layer')} · {status} · readiness {float(layer.get('readiness') or 0.0) * 100:.0f}% · "
                f"range {float(layer.get('range_km') or 0.0):,.0f} km · first attempt {probability * 100:.0f}%"
            )

        imgui.dummy((0.0, 6.0))
        imgui.text("WEAPON PRODUCTION")
        production_orders = self._presenter.strategic_production_orders_for_country(state, country_tag)
        if not production_orders:
            imgui.text_disabled("No strategic weapon production orders.")
        for order in production_orders[:8]:
            imgui.text(
                f"{order.get('weapon_id')} · {int(order.get('quantity') or 0)} · {order.get('status')}"
            )
            imgui.text_disabled(str(order.get("reason") or ""))

        imgui.dummy((0.0, 6.0))
        imgui.text("RECENT STRIKES")
        orders = self._presenter.strategic_orders_for_country(state, country_tag)
        if not orders:
            imgui.text_disabled("No known launch orders.")
        for order in orders[:8]:
            owner = str(order.get("country_id") or "Unknown")
            imgui.text(f"{owner} · {order.get('target_mode')} · {order.get('status')}")
            imgui.text_disabled(str(order.get("reason") or ""))
        impacts = self._presenter.strategic_impacts_for_country(state, country_tag)
        for impact in impacts[:8]:
            nature = "collateral" if bool(impact.get("collateral")) else "intended"
            imgui.text_disabled(
                f"Region {int(impact.get('region_id') or 0)} · {impact.get('category')} · "
                f"{float(impact.get('severity') or 0.0) * 100:.1f}% · {nature}"
            )
