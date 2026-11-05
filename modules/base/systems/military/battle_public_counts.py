"""Publish per-category unit quantities for observers without unit identities."""
from collections import defaultdict

import polars as pl

from modules.base.systems.military.capability_catalog import DEFAULT_ROLE_PROFILES, canonical_role


COUNT_SCHEMA = {"battle_id": pl.Utf8, "side": pl.Utf8, "category": pl.Utf8,
                "unit_quantity": pl.Int64, "complete": pl.Boolean, "sampled_at_minute": pl.Int64}


def battle_unit_category(unit_type):
    role = canonical_role(unit_type)
    profile = DEFAULT_ROLE_PROFILES.get(role)
    if profile is None:
        return None
    if profile.domain == "strategic":
        # REFERENCE computes a fifth nuclear category, but Battle_Info_Window only binds I/G/A/N labels.
        return "X"
    return "I" if role == "infantry" else {"land": "G", "air": "A", "naval": "N"}.get(profile.domain)


def public_battle_counts(battles, participants, units):
    """Expose category quantities from the battle snapshot, never unit identities."""
    units_by_id = {str(row.get("id")): row for row in units}
    by_battle_side = defaultdict(list)
    for row in participants:
        by_battle_side[(str(row.get("battle_id")), str(row.get("side") or "").removeprefix("SIDE_"))].append(row)
    result = []
    for battle in sorted(battles, key=lambda row: str(row.get("id"))):
        if battle.get("status") not in {"active", "stalemate"}:
            continue
        for side in ("A", "B"):
            members = by_battle_side[(str(battle["id"]), side)]
            declared = battle.get("attacker_side" if side == "A" else "defender_side") or ()
            countries = set(declared.split(",") if isinstance(declared, str) else declared)
            counts = dict.fromkeys("IGAN", 0)
            complete = bool(members) and bool(countries)
            seen = set()
            for member in members:
                unit_id = str(member.get("unit_id"))
                unit = units_by_id.get(unit_id)
                if unit_id in seen:
                    complete = False
                    continue
                seen.add(unit_id)
                quantity = unit.get("equipment_quantity") if unit is not None else None
                if (unit is None or int(unit.get("strength") or 0) <= 0
                        or unit.get("owner") != member.get("country_id")
                        or unit.get("owner") not in countries
                        or quantity is None or int(quantity) < 0):
                    complete = False
                    continue
                category = battle_unit_category(unit.get("unit_type"))
                if category is None:
                    complete = False
                elif category != "X":
                    # REFERENCE's visible battle counters sum unit quantities by category, not group rows.
                    # OpenPower's equipment quantity is the closest authoritative count contract.
                    counts[category] += int(quantity)
            # Incomplete rosters cannot justify zeroes in an observer's UI.
            for category, count in counts.items():
                result.append(dict(battle_id=str(battle["id"]), side=side, category=category,
                                   unit_quantity=count, complete=complete,
                                   sampled_at_minute=int(battle.get("updated_at_minute") or 0)))
    return pl.DataFrame(result, schema=COUNT_SCHEMA)
