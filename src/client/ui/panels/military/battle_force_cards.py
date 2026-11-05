"""Compose observed unit groups and owner-only commands in the battle stage."""
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.panels.shared.panel_widgets import draw_empty_state


def render_battle_force_cards(
    groups, ally, enemy, country, *, active, command, losses=(), postures=(),
    selected_force=None, on_select=None,
):
    if not imgui.begin_table("battle_forces", 2, imgui.TableFlags_.borders_inner):
        return
    cards = _merge_force_losses(groups, losses)
    orders = _posture_counts(postures)
    for tag in (ally, enemy):
        imgui.table_next_column()
        imgui.text(f"FORCES: {tag or 'Unknown'}")
        selected = [group for group in cards if group["country_id"] == tag]
        if not selected:
            draw_empty_state("No observed unit groups are available.")
        for group in selected:
            key = f"{group['country_id']}.{group['unit_type']}"
            with_card = imgui.begin_child("force." + key, (0, 112), child_flags=imgui.ChildFlags_.borders)
            if with_card:
                selected_force_key = (group["country_id"], group["unit_type"])
                unit_label = "unit" if group["unit_count"] == 1 else "units"
                label = (
                    f"{group['country_id']} · {group['unit_type']} · "
                    f"{group['unit_count']} {unit_label} · {group['strength']:,} personnel"
                )
                if imgui.selectable(
                    label,
                    selected_force == selected_force_key,
                    size=(max(1.0, float(imgui.get_content_region_avail().x)), 0.0),
                    test_id=f"battle.inspection.force.{key}",
                )[0] and on_select is not None:
                    on_select(selected_force_key)
                if group["losses"]:
                    imgui.text_disabled(
                        f"Recorded casualties: {group['losses']:,} personnel",
                        test_id=f"battle.inspection.loss.{key}",
                    )
                if group["country_id"] == country:
                    posture_lines = orders.get((group["country_id"], group["unit_type"]), ())
                    if posture_lines:
                        imgui.text_disabled(
                            "Orders: " + " · ".join(
                                f"{strategy.replace('_', ' ').title()} ×{count}"
                                for strategy, count in posture_lines
                            ),
                            test_id=f"battle.inspection.posture.{key}",
                        )
                    imgui.text_disabled("FORCE ORDERS")
                    imgui.begin_disabled(not active)
                    for strategy in ("attack", "defend", "back_off", "reorganize"):
                        if imgui.small_button(strategy.replace("_", " ").title(),
                                              test_id=f"battle.inspection.force.{key}.{strategy}"):
                            command(strategy, group["unit_type"])
                        imgui.same_line()
                    imgui.new_line()
                    imgui.end_disabled()
            imgui.end_child()
    imgui.end_table()


def _merge_force_losses(groups, losses):
    merged = {}
    for group in groups:
        key = _force_key(group)
        merged[key] = {**group, "losses": 0}
    for loss in losses:
        key = _force_key(loss)
        if not key[1] or not key[2]:
            continue
        group = merged.setdefault(key, {
            "side": key[0], "country_id": key[1], "unit_type": key[2],
            "unit_count": 0, "strength": 0, "relative_positions": [], "losses": 0,
        })
        group["losses"] += max(0, int(loss.get("losses") or 0))
    return [merged[key] for key in sorted(merged)]


def _posture_counts(postures):
    counts = {}
    for posture in postures:
        key = (
            str(posture.get("country_id") or "").strip().upper(),
            str(posture.get("unit_type") or "").strip().lower().replace(" ", "_"),
            str(posture.get("strategy") or "hold").strip().lower().replace(" ", "_"),
        )
        if not key[0] or not key[1]:
            continue
        counts[key] = counts.get(key, 0) + 1
    by_force = {}
    for (country, unit_type, strategy), count in sorted(counts.items()):
        by_force.setdefault((country, unit_type), []).append((strategy, count))
    return by_force


def _force_key(group):
    return (
        str(group.get("side") or "").strip().upper(),
        str(group.get("country_id") or "").strip().upper(),
        str(group.get("unit_type") or "unit").strip().lower().replace(" ", "_"),
    )
