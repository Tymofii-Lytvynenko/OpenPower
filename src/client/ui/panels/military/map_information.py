"""Read-only map information adapted to the current snapshot's visibility."""
from dataclasses import dataclass

import polars as pl

from src.client.ui.panels.shared.panel_data import resolve_country_name, resolve_region_name
from src.client.ui.panels.shared.unit_categories import unit_category


def _row(state, table, identity):
    frame = state.tables.get(table)
    if frame is None or frame.is_empty() or "id" not in frame.columns or identity is None:
        return None
    # Project only the selected row; copying the full army every rendered frame
    # makes a small informational overlay unexpectedly expensive in large worlds.
    selected = frame.filter(pl.col("id") == identity)
    return selected.row(0, named=True) if selected.height else None


@dataclass(frozen=True)
class UnitComposition:
    quantities: dict[str, int | None]
    fractions: dict[str, float]


def selected_unit_composition(state, unit_id, viewer):
    row = _row(state, "units", unit_id)
    if row is None or int(row.get("strength") or 0) <= 0:
        return None
    quantities = dict.fromkeys("IGNA")
    fractions = dict.fromkeys("IGNA", 0.0)
    category = unit_category(row.get("unit_type"))
    # Raw foreign snapshot rows are not a substitute for an authorized observation.
    # REFERENCE uses noisy intelligence here; OpenPower has no per-group equivalent yet.
    if row.get("owner") == viewer and category:
        quantities = dict.fromkeys("IGNA", 0)
        value = row.get("strength" if category == "I" else "equipment_quantity")
        quantities[category] = max(0, int(value)) if value is not None else None
        fractions[category] = 1.0
    return UnitComposition(quantities, fractions)


@dataclass(frozen=True)
class RegionControl:
    name: str
    political_tag: str
    political_name: str
    military_tag: str
    military_name: str


def region_control(state, region_id):
    row = _row(state, "regions", region_id)
    if row is None:
        return None
    political = str(row.get("owner") or "").strip().upper()
    military = str(row.get("controller") or political).strip().upper()
    if not political or not military:
        return None
    return RegionControl(resolve_region_name(state, region_id), political,
                         resolve_country_name(state, political), military,
                         resolve_country_name(state, military))
