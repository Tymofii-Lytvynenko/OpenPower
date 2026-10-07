from __future__ import annotations

from imgui_bundle import imgui

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.panels.military.presenter import (
    MilitaryPresenter,
    battle_balance_estimate_label,
    battle_mode_label,
    battle_status_label,
)
from src.client.ui.panels.shared.panel_data import resolve_region_name
from src.client.ui.panels.shared.panel_widgets import draw_empty_state, draw_required_tables
from src.shared.actions import ActionSetBattleStrategy


class BattleOverviewPanel:
    def __init__(self):
        self._presenter = MilitaryPresenter()

    def render(self, state, context: PanelRenderContext) -> bool:
        with WindowManager.window("BATTLE OVERVIEW", x=800, y=250, w=560, h=500) as is_open:
            if not is_open:
                return False
            self._render_content(state, context)
            return True

    def _render_content(self, state, context: PanelRenderContext) -> None:
        draw_required_tables(state, ("battles",))
        imgui.separator()

        viewer_country = self._viewer_country(state, context)
        battles = self._presenter.battles_for_country(state, viewer_country)
        if not battles:
            draw_empty_state("No active battles are tracked in the current state.")
            return

        for row in battles:
            battle_id = str(row.get("id") or "Battle")
            model = self._presenter.battle_status(state, battle_id, viewer_country)
            region_name = resolve_region_name(state, int(row.get("region_id") or 0))
            balance_estimate = battle_balance_estimate_label(
                model.balance if model else float(row.get("balance") or 0.0)
            )
            balance_ratio = max(0.0, min(1.0, model.balance if model else float(row.get("balance") or 0.0)))
            imgui.text(battle_id)
            imgui.same_line()
            imgui.text_disabled(region_name)
            mode = model.mode_label if model else battle_mode_label(row.get("mode") or "positional")
            status = model.status_label if model else battle_status_label(row.get("status") or "inactive")
            round_number = model.round if model else int(row.get("round") or 0)
            imgui.text(f"{mode} | Round {round_number} | {balance_estimate} | Status {status}")
            side_a = model.side_a_strength if model else float(row.get("side_a_strength") or 0.0)
            side_b = model.side_b_strength if model else float(row.get("side_b_strength") or 0.0)
            imgui.text(f"Forces {side_a:.0f} : {side_b:.0f}")
            if context.on_focus_request is not None and imgui.button(f"Focus##{battle_id}"):
                context.on_focus_request(int(row.get("region_id") or 0))
            if model:
                if str(model.status or "").strip().lower() == "concluded":
                    imgui.text(f"Outcome {model.outcome_label}")
                imgui.text(f"Losses {model.side_a_losses} : {model.side_b_losses}")
                distribution = model.readiness_distribution
                imgui.text(
                    "Readiness "
                    f"parked {distribution.get('parked', 0)} | "
                    f"ready {distribution.get('ready', 0)} | "
                    f"fortified {distribution.get('fortified', 0)}"
                )
                imgui.text(f"A: {', '.join(model.side_a_countries) or '—'}")
                imgui.text(f"B: {', '.join(model.side_b_countries) or '—'}")
                for participant in model.participants:
                    imgui.text_disabled(
                        f"{participant.country_id} [{participant.role}] {participant.weighted_strength:.0f}"
                    )
                force_groups = self._presenter.battle_force_summary(state, battle_id, viewer_country)
                for group in force_groups:
                    positions = group["relative_positions"]
                    position_text = ""
                    if positions:
                        anchor_lat = float(row.get("anchor_latitude") or 0.0)
                        anchor_lon = float(row.get("anchor_longitude") or 0.0)
                        mean_lat = sum(point[0] for point in positions) / len(positions)
                        mean_lon = sum(point[1] for point in positions) / len(positions)
                        position_text = f" · Δ{mean_lat - anchor_lat:+.1f},{mean_lon - anchor_lon:+.1f}°"
                    imgui.text_disabled(
                        f"{group['side']} {group['country_id']} · {group['unit_type']} "
                        f"×{group['unit_count']} · {group['strength']:,}{position_text}"
                    )
                    if (
                        context.is_own_country and context.net_client is not None
                        and group["country_id"] == str(context.target_tag or "").upper()
                    ):
                        actions = (
                            ("attack", "ATTACK"), ("defend", "DEFEND"), ("back_off", "BACK OFF"),
                            ("retreat", "RETREAT"), ("reorganize", "REORGANIZE"),
                            ("attack_preset", "ATTACK PRESET"), ("defend_preset", "DEFEND PRESET"),
                        )
                        for index, (strategy, label) in enumerate(actions):
                            if index:
                                if index % 3 == 0:
                                    imgui.new_line()
                                else:
                                    imgui.same_line()
                            if imgui.small_button(f"{label} {group['unit_type']}##{battle_id}-{group['unit_type']}-{strategy}"):
                                context.net_client.send_action(ActionSetBattleStrategy(
                                    context.net_client.player_id, battle_id, strategy,
                                    group["country_id"], group["unit_type"],
                                ))
                        imgui.new_line()
                postures = self._presenter.battle_postures_for_country(state, battle_id, viewer_country)
                if postures:
                    imgui.text_disabled("Your force postures")
                    for posture in postures:
                        imgui.text_disabled(
                            f"{posture['unit_type']} {posture['unit_id']} · {posture['strategy']} / {posture['status']} · "
                            f"by {posture['issuer_player_id']} at t={posture['effective_at_minute']} · "
                            f"attack {posture['attack_modifier']:.2f}, risk {posture['attack_risk_modifier']:.2f}, "
                            f"defense {posture['defense_modifier']:.2f}, readiness {posture['readiness_modifier']:.2f}, "
                            f"holding {posture['holding_modifier']:.2f}, counterattack {posture['counterattack_modifier']:.2f}, "
                            f"casualties {posture['casualty_modifier']:.2f} · {posture['reason']}"
                        )
                        next_at = posture.get("next_action_at_minute")
                        next_time = f" at t={next_at}" if next_at else ""
                        imgui.text_disabled(f"Next: {posture['next_action']}{next_time}")
                command_history = self._presenter.battle_command_history(state, battle_id, viewer_country)
                if command_history:
                    imgui.text_disabled("Recent command history")
                    for command in command_history:
                        force_names = ", ".join(
                            f"{force['unit_type']} {force['unit_id']}"
                            for force in command["affected_forces"]
                        ) or "no forces"
                        effect_text = "; ".join(
                            f"{effect['unit_id']}: attack {effect['attack_modifier']:.2f}, risk {effect['attack_risk_modifier']:.2f}, "
                            f"defense {effect['defense_modifier']:.2f}, readiness {effect['readiness_modifier']:.2f}, "
                            f"holding {effect['holding_modifier']:.2f}, counterattack {effect['counterattack_modifier']:.2f}, "
                            f"casualties {effect['casualty_modifier']:.2f}"
                            for effect in command["expected_effects"]
                        ) or "no applied projection"
                        imgui.text_disabled(
                            f"t={command['effective_at_minute']} · {command['strategy']} · {force_names} · "
                            f"{command['status']} · {command['reason'] or effect_text}"
                        )
                loss_groups = self._presenter.battle_loss_summary(state, battle_id, viewer_country)
                if loss_groups:
                    imgui.text_disabled("Recorded losses by force type")
                    for loss in loss_groups:
                        imgui.text_disabled(
                            f"{loss['side']} {loss['country_id']} · {loss['unit_type']} · "
                            f"{loss['losses']:,} lost"
                        )
                if model.occupation:
                    imgui.text_disabled(
                        f"Occupation: {model.occupation.get('controller_country_id', '')} "
                        f"garrison {model.occupation.get('garrison_strength', 0)} "
                        f"resistance {float(model.occupation.get('resistance', 0.0) or 0.0):.1f} "
                        f"status {model.occupation.get('occupation_status', 'active')}"
                    )
            if hasattr(imgui, "progress_bar"):
                imgui.progress_bar(balance_ratio, (0.0, 12.0), "")
            imgui.separator()

    def _viewer_country(self, state, context: PanelRenderContext) -> str:
        client = context.net_client
        player_id = str(getattr(client, "player_id", "") or "")
        player_map = state.globals.get("player_country_map", {})
        mapped_country = player_map.get(player_id, "") if isinstance(player_map, dict) else ""
        country = mapped_country or state.globals.get("player_tag", "")
        if not country and context.is_own_country:
            country = context.target_tag
        return str(country or "").strip().upper()
