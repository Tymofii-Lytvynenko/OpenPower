"""Resolve combat rounds and calculate strength from unit state."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable

import polars as pl

from modules.base.systems.military.capability_catalog import canonical_role
from modules.base.systems.military.readiness_policy import ReadinessPolicy
from modules.base.systems.military.war_index import ConflictContext


def normalize_country_tag(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().upper()


@dataclass(frozen=True, slots=True)
class CombatOutcome:
    attacker_losses: int
    defender_losses: int


class CombatResolutionPolicy:
    """Keeps combat deterministic and easy to tune independently from system flow."""

    def resolve(self, attacker_strength: int, defender_strength: int, mode: str = "positional") -> CombatOutcome:
        if attacker_strength <= 0 or defender_strength <= 0:
            return CombatOutcome(0, 0)

        intensity = 1.35 if mode == "assault" else 1.0
        stronger = max(attacker_strength, defender_strength)
        weaker = min(attacker_strength, defender_strength)
        if weaker > 0 and stronger / weaker >= 2.5:
            if attacker_strength >= defender_strength:
                return CombatOutcome(
                    attacker_losses=max(1, int(round(attacker_strength * 0.08 * intensity))),
                    defender_losses=defender_strength,
                )
            return CombatOutcome(
                attacker_losses=attacker_strength,
                defender_losses=max(1, int(round(defender_strength * 0.08 * intensity))),
            )

        total = attacker_strength + defender_strength
        attacker_share = attacker_strength / total
        defender_share = defender_strength / total

        attacker_losses = max(1, int(round(attacker_strength * (0.10 + (defender_share * 0.18)) * intensity)))
        defender_losses = max(1, int(round(defender_strength * (0.12 + (attacker_share * 0.22)) * intensity)))
        return CombatOutcome(attacker_losses=attacker_losses, defender_losses=defender_losses)


class CombatRoundResolver:
    """Resolve combat rounds and evaluate the combat strength of unit groups."""

    def __init__(
        self,
        policy: CombatResolutionPolicy,
        readiness: ReadinessPolicy,
    ) -> None:
        self._policy = policy
        self._readiness = readiness
        self._capability_index: dict[str, dict[str, Any]] = {}

    @property
    def capability_index(self) -> dict[str, dict[str, Any]]:
        return self._capability_index

    def set_capability_index(
        self,
        capability_index: dict[str, dict[str, Any]],
    ) -> None:
        self._capability_index = capability_index

    def load_capability_projections(
        self,
        projection_table: pl.DataFrame | None,
    ) -> None:
        self._capability_index = {} if projection_table is None else {
            str(row.get("unit_id") or ""): self._decode_projection(row)
            for row in projection_table.to_dicts()
        }

    def apply_combat_round(
        self,
        local_units: list[dict[str, Any]],
        conflict: ConflictContext,
        mode: str,
    ) -> str | None:
        side_a_strength = self.total_strength(local_units, conflict.side_a_members)
        side_b_strength = self.total_strength(local_units, conflict.side_b_members)
        raw_a = self.raw_strength(local_units, conflict.side_a_members)
        raw_b = self.raw_strength(local_units, conflict.side_b_members)
        outcome = self._policy.resolve(side_a_strength, side_b_strength, mode)
        # Resolve tactics on readiness-weighted strength, then translate losses
        # back to personnel so a low-readiness modifier does not make a unit
        # impossible to eliminate in a decisive round.
        damageable_by_a = self._eligible_defenders(local_units, conflict.side_a_members, conflict.side_b_members)
        damageable_by_b = self._eligible_defenders(local_units, conflict.side_b_members, conflict.side_a_members)
        losses_a = 0 if not damageable_by_b else int(round(
            outcome.attacker_losses * raw_a / max(1, side_a_strength)
            * self._casualty_modifier(local_units, conflict.side_a_members)
            * self._side_damage_factor(local_units, conflict.side_b_members, conflict.side_a_members)
        ))
        losses_b = 0 if not damageable_by_a else int(round(
            outcome.defender_losses * raw_b / max(1, side_b_strength)
            * self._casualty_modifier(local_units, conflict.side_b_members)
            * self._side_damage_factor(local_units, conflict.side_a_members, conflict.side_b_members)
        ))
        self._distribute_losses(
            local_units,
            conflict.side_a_members,
            losses_a,
            {str(unit.get("id") or "") for unit in damageable_by_b},
        )
        self._distribute_losses(
            local_units,
            conflict.side_b_members,
            losses_b,
            {str(unit.get("id") or "") for unit in damageable_by_a},
        )

        remaining_a = self.total_strength(local_units, conflict.side_a_members)
        remaining_b = self.total_strength(local_units, conflict.side_b_members)
        if remaining_a > 0 and remaining_b > 0:
            return None
        if remaining_a <= 0 and remaining_b <= 0:
            return None
        if remaining_a > 0:
            return self._dominant_country(local_units, conflict.side_a_members)
        return self._dominant_country(local_units, conflict.side_b_members)

    def record_round_casualties(
        self,
        rows: list[dict[str, Any]],
        battle_id: str,
        round_number: int,
        local_units: list[dict[str, Any]],
        conflict: ConflictContext,
        pre_round_strength: dict[str, int],
        now: int,
    ) -> None:
        existing_ids = {str(row.get("id") or "") for row in rows}
        side_a, side_b = set(conflict.side_a_members), set(conflict.side_b_members)
        for unit in sorted(local_units, key=lambda row: str(row.get("id") or "")):
            unit_id = str(unit.get("id") or "")
            losses = max(0, pre_round_strength.get(unit_id, 0) - max(0, int(unit.get("strength") or 0)))
            record_id = f"{battle_id}:{round_number}:{unit_id}"
            if losses <= 0 or record_id in existing_ids:
                continue
            owner = normalize_country_tag(unit.get("owner"))
            side = "SIDE_A" if owner in side_a else "SIDE_B" if owner in side_b else ""
            if not side:
                continue
            rows.append({
                "id": record_id, "battle_id": battle_id, "unit_id": unit_id,
                "country_id": owner, "side": side,
                "unit_type": str(unit.get("unit_type") or "unit"),
                "losses": losses, "round": int(round_number), "created_at_minute": int(now),
            })
            existing_ids.add(record_id)

    def _dominant_country(self, local_units: list[dict[str, Any]], eligible_tags: Iterable[str]) -> str:
        best_tag = ""
        best_strength = -1
        eligible = set(eligible_tags)
        for tag in sorted(eligible):
            strength = self.total_strength(local_units, {tag})
            if strength > best_strength:
                best_strength = strength
                best_tag = tag
        return best_tag

    def winning_country(self, local_units: list[dict[str, Any]], conflict: ConflictContext) -> str:
        remaining_a = self.total_strength(local_units, conflict.side_a_members)
        remaining_b = self.total_strength(local_units, conflict.side_b_members)
        if remaining_a > remaining_b:
            return self._dominant_country(local_units, conflict.side_a_members)
        if remaining_b > remaining_a:
            return self._dominant_country(local_units, conflict.side_b_members)
        return ""

    def total_strength(self, local_units: list[dict[str, Any]], eligible_tags: Iterable[str]) -> int:
        eligible = set(eligible_tags)
        raw_strength = sum(
            max(0, int(row.get("strength") or 0))
            for row in local_units
            if normalize_country_tag(row.get("owner")) in eligible and self._combat_active(row)
        )
        if raw_strength <= 0:
            return 0
        effective_strength = sum(
            max(0, int(row.get("strength") or 0))
            * self._readiness.combat_weight(row.get("readiness_status"))
            * self._bounded_modifier(row, "combat_strength_modifier", 0.0, 1.5)
            * self._bounded_modifier(row, "combat_readiness_modifier", 0.0, 1.5)
            * max(0.5, min(1.0, float(row.get("war_exhaustion_modifier") or 1.0)))
            * max(0.5, min(1.0, self._number(row.get("cohesion")) or 1.0))
            * self._capability_strength_factor(row)
            for row in local_units
            if normalize_country_tag(row.get("owner")) in eligible and self._combat_active(row)
        )
        return max(1, int(round(effective_strength)))

    def _side_can_damage(self, local_units, attacking_tags, defending_tags) -> bool:
        return bool(self._eligible_defenders(local_units, attacking_tags, defending_tags))

    def _eligible_defenders(self, local_units, attacking_tags, defending_tags):
        attacking = set(attacking_tags)
        defending = set(defending_tags)
        attackers = [
            row for row in local_units
            if normalize_country_tag(row.get("owner")) in attacking
            and int(row.get("strength") or 0) > 0
            and self._can_initiate_combat(row)
        ]
        defenders = [
            row for row in local_units
            if normalize_country_tag(row.get("owner")) in defending
            and int(row.get("strength") or 0) > 0
            and self._combat_active(row)
        ]
        return [
            defender for defender in defenders
            if any(self._attacker_can_damage(attacker, defender) for attacker in attackers)
        ]

    def _attacker_can_damage(self, attacker, defender) -> bool:
        profile = self._capability_index.get(str(attacker.get("id") or ""))
        if profile is None:
            return True
        targets = set(profile.get("valid_targets") or [])
        if "generic" in targets or "all" in targets:
            return True
        target_profile = self._capability_index.get(str(defender.get("id") or ""), {})
        role = canonical_role(target_profile.get("role") or defender.get("unit_type"))
        domain = str(target_profile.get("domain") or defender.get("unit_domain") or "land").lower()
        categories = {role, domain, self._target_category(role, domain)}
        return bool(targets.intersection(categories))

    def _side_damage_factor(self, local_units, attacking_tags, defending_tags) -> float:
        attackers = [
            row for row in local_units
            if normalize_country_tag(row.get("owner")) in set(attacking_tags)
            and int(row.get("strength") or 0) > 0
            and self._can_initiate_combat(row)
        ]
        defenders = self._eligible_defenders(local_units, attacking_tags, defending_tags)
        if not attackers or not defenders:
            return 0.0
        eligible_attackers = [
            attacker for attacker in attackers
            if any(self._attacker_can_damage(attacker, defender) for defender in defenders)
        ]
        eligible_raw_strength = sum(max(0, int(row.get("strength") or 0)) for row in eligible_attackers)
        all_raw_strength = sum(max(0, int(row.get("strength") or 0)) for row in attackers)
        if eligible_raw_strength <= 0 or all_raw_strength <= 0:
            return 0.0
        attack_factor = sum(
            max(0, int(row.get("strength") or 0))
            * self._capability_damage_factor(
                row,
                [defender for defender in defenders if self._attacker_can_damage(row, defender)],
            )
            * (
                self._bounded_modifier(row, "combat_counterattack_modifier", 0.0, 1.5)
                if str(row.get("combat_posture") or "hold").strip().lower() == "defend"
                else 1.0
            )
            for row in eligible_attackers
        ) / eligible_raw_strength
        eligible_strength = self.total_strength(eligible_attackers, attacking_tags)
        total_strength = self.total_strength(attackers, attacking_tags)
        participation = min(1.0, eligible_strength / max(1, total_strength))
        protection = sum(
            max(0.5, min(1.5,
                self._bounded_modifier(row, "combat_defense_modifier", 0.5, 1.5)
                * self._bounded_modifier(row, "combat_holding_modifier", 0.5, 1.5)
            ))
            for row in defenders
        ) / len(defenders)
        return max(0.0, min(1.5, attack_factor * participation / protection))

    def _capability_strength_factor(self, unit):
        profile = self._capability_index.get(str(unit.get("id") or ""))
        if profile is None:
            return 1.0
        capabilities = profile.get("capabilities") or {}
        firepower = max(0.0, self._number(capabilities.get("gun_damage"))) + max(0.0, self._number(capabilities.get("missile_damage")))
        precision = max(self._number(capabilities.get("gun_precision")), self._number(capabilities.get("missile_precision")))
        return max(0.75, min(1.5, 1.0 + min(0.4, firepower / 100.0) * max(0.0, min(1.0, precision))))

    def _combat_active(self, unit):
        return str(unit.get("combat_posture") or "hold").strip().lower() != "reorganize"

    def _can_initiate_combat(self, unit):
        return self._combat_active(unit) and str(unit.get("combat_posture") or "hold").strip().lower() not in {"back_off", "retreat"}

    def _capability_damage_factor(self, unit, defenders):
        profile = self._capability_index.get(str(unit.get("id") or ""))
        if profile is None:
            return 1.0
        factor = self._capability_strength_factor(unit)
        targets = set(profile.get("valid_targets") or [])
        if "generic" in targets or "all" in targets:
            return factor
        for defender in defenders:
            if not self._attacker_can_damage(unit, defender):
                continue
            target_profile = self._capability_index.get(str(defender.get("id") or ""), {})
            vulnerabilities = set(target_profile.get("vulnerabilities") or [])
            domain = str(profile.get("domain") or unit.get("unit_domain") or "land").lower()
            if domain in vulnerabilities:
                factor *= 1.1
                break
        return max(0.75, min(1.5, factor))

    def _number(self, value):
        try:
            result = float(value)
        except (TypeError, ValueError, OverflowError):
            return 0.0
        return result if result == result and abs(result) != float("inf") else 0.0

    def _bounded_modifier(self, row, name, minimum, maximum):
        value = row.get(name)
        if value is None:
            return 1.0
        return max(minimum, min(maximum, self._number(value)))

    def _target_category(self, role, domain):
        if role in {"tanks", "infantry_vehicles", "artillery", "air_defense", "mobile_launchers"}:
            return "armor" if role in {"tanks", "infantry_vehicles"} else role
        if domain == "air":
            return "air"
        if domain == "naval":
            return "ships"
        return role

    def _decode_projection(self, row):
        def decode(key, fallback):
            try:
                value = json.loads(str(row.get(key) or fallback))
            except (TypeError, ValueError, json.JSONDecodeError):
                return json.loads(fallback)
            return value
        return {
            "role": canonical_role(row.get("role")),
            "domain": str(row.get("domain") or "land").lower(),
            "valid_targets": decode("valid_targets_json", "[]"),
            "vulnerabilities": decode("vulnerabilities_json", "[]"),
            "capabilities": decode("capabilities_json", "{}"),
        }

    def _casualty_modifier(self, local_units: list[dict[str, Any]], eligible_tags: Iterable[str]) -> float:
        eligible = set(eligible_tags)
        rows = [row for row in local_units if normalize_country_tag(row.get("owner")) in eligible and int(row.get("strength") or 0) > 0 and self._combat_active(row)]
        total = sum(int(row.get("strength") or 0) for row in rows)
        if total <= 0:
            return 1.0
        weighted = sum(
            int(row.get("strength") or 0)
            * self._bounded_modifier(row, "combat_casualty_modifier", 0.5, 1.5)
            * self._bounded_modifier(row, "combat_attack_risk_modifier", 0.5, 1.5)
            for row in rows
        )
        return weighted / total

    def raw_strength(self, local_units: list[dict[str, Any]], eligible_tags: Iterable[str]) -> int:
        eligible = set(eligible_tags)
        return sum(
            max(0, int(row.get("strength") or 0))
            for row in local_units
            if normalize_country_tag(row.get("owner")) in eligible and self._combat_active(row)
        )

    def _distribute_losses(
        self,
        local_units: list[dict[str, Any]],
        eligible_tags: Iterable[str],
        total_losses: int,
        eligible_unit_ids: set[str] | None = None,
    ) -> None:
        remaining_losses = max(0, total_losses)
        if remaining_losses <= 0:
            return

        allowed_ids = None if eligible_unit_ids is None else set(eligible_unit_ids)
        eligible_country_tags = set(eligible_tags)
        eligible_rows = [
            row
            for row in sorted(local_units, key=lambda unit: str(unit.get("id") or ""))
            if normalize_country_tag(row.get("owner")) in eligible_country_tags
            and (allowed_ids is None or str(row.get("id") or "") in allowed_ids)
            and int(row.get("strength") or 0) > 0
            and self._combat_active(row)
        ]
        if not eligible_rows:
            return

        remaining_strength = sum(int(row.get("strength") or 0) for row in eligible_rows)
        for index, row in enumerate(eligible_rows):
            if remaining_losses <= 0:
                break

            strength = max(0, int(row.get("strength") or 0))
            if strength <= 0 or remaining_strength <= 0:
                continue

            if index == len(eligible_rows) - 1:
                row_losses = remaining_losses
            else:
                row_share = strength / remaining_strength
                row_losses = max(1, int(round(total_losses * row_share)))
                row_losses = min(row_losses, remaining_losses)

            applied_losses = min(strength, row_losses)
            row["strength"] = strength - applied_losses
            equipment_quantity = max(0, int(row.get("equipment_quantity") or 0))
            if equipment_quantity > 0:
                row["equipment_quantity"] = int(
                    round(equipment_quantity * row["strength"] / strength)
                )
            remaining_losses -= applied_losses
            remaining_strength -= strength
