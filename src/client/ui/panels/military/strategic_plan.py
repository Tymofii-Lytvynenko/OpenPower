"""Presentation-only strategic drafts, validated against the latest snapshot."""
from __future__ import annotations

from dataclasses import dataclass, field

from src.shared.actions import ActionLaunchStrategicStrike


@dataclass
class StrategicPlan:
    country: str = ""
    target_country: str = ""
    target_region: int | None = None
    target_mode: str = "military"
    authorization_context: str = ""
    selected_weapons: set[str] = field(default_factory=set)
    assignments: dict[str, int] = field(default_factory=dict)
    payload_levels: dict[str, int] = field(default_factory=dict)

    def actions(self, state, presenter, player_id: str, *, multiple=False):
        weapons = {str(row.get("id")): row for row in
                   presenter.strategic_inventory_for_country(state, self.country)}
        actions, reasons = [], []
        if not self.selected_weapons:
            return [], ["Select at least one weapon system."]
        total_cost = 0.0
        for weapon_id in sorted(self.selected_weapons):
            weapon = weapons.get(weapon_id)
            if weapon is None:
                reasons.append(f"{weapon_id}: weapon system is unavailable.")
                continue
            region_id = self.assignments.get(weapon_id) if multiple else self.target_region
            preview = presenter.strategic_launch_preview(
                state, self.country, weapon, region_id, self.authorization_context,
            )
            reasons.extend(f"{weapon_id}: {reason}" for reason in preview["reasons"])
            if region_id is None:
                continue
            payload = int(self.payload_levels.get(weapon_id, weapon.get("payload_level") or 1))
            if not 1 <= payload <= max(1, int(weapon.get("payload_cap") or 1)):
                reasons.append(f"{weapon_id}: selected payload is no longer available.")
            total_cost += max(0.0, float(weapon.get("launch_cost") or 0.0))
            actions.append(ActionLaunchStrategicStrike(
                player_id, self.country, int(region_id), str(weapon.get("weapon_type") or "icbm"),
                target_country_tag=str(preview["target_country_id"]), target_mode=self.target_mode,
                weapon_id=weapon_id, payload_level=payload,
                authorization_context=self.authorization_context,
                origin_region_id=int(weapon.get("origin_region_id") or 0),
            ))
        countries = state.tables.get("countries")
        owner = next((row for row in countries.to_dicts() if str(row.get("id")) == self.country), {}) if countries is not None else {}
        if total_cost > float(owner.get("money_reserves") or 0.0):
            reasons.append("The country cannot fund the complete launch plan.")
        # Return no partial batch: stale inventory or authorization must never
        # silently turn a reviewed multi-target plan into a different attack.
        return ([] if reasons else actions), reasons
