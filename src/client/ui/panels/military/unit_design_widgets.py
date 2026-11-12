"""Reusable OpenPower capability presentation for source-sized design windows."""

from __future__ import annotations

import json

from src.client.services.client_presentation import contribution_for
from src.client.ui.core.gml_widgets import GMLWidgets
from src.client.ui.core.instrumented_imgui import imgui
from src.shared.mod_api import ClientPresentationKeys

DESIGN_METRICS = (
    ("gun_range", "Gun range", "GunRange"),
    ("gun_precision", "Gun precision", "GunPrecision"),
    ("gun_damage", "Gun damage", "GunDamage"),
    ("missile_range", "Missile range", "MissileRange"),
    ("missile_precision", "Missile precision", "MissilePrecision"),
    ("missile_damage", "Missile damage", "MissileDamage"),
    ("missile_payload", "Missile payload", "MissilePayload"),
    ("speed", "Speed", "Speed"),
    ("stealth", "Stealth", "Stealth"),
    ("countermeasures", "Countermeasures", "Countermeasures"),
    ("armor", "Armor", "Armor"),
    ("sensors", "Sensors", "Sensors"),
)


def saved_capabilities(design: dict | None) -> dict[str, float]:
    """Decode numeric capabilities present in a saved design."""
    design = design or {}
    try:
        saved = json.loads(str(design.get("capabilities_json") or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    if not isinstance(saved, dict):
        return {}

    values = {}
    for key, value in saved.items():
        try:
            values[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return values


def capabilities_for_design(design: dict | None, state) -> dict[str, float]:
    """Resolve saved design values, falling back only to its configured role."""
    design = design or {}
    canonical_role = contribution_for(state, ClientPresentationKeys.CANONICAL_ROLE)
    role_profiles = contribution_for(state, ClientPresentationKeys.DEFAULT_ROLE_PROFILES)
    role = canonical_role(design.get("class_name"))
    profile = role_profiles.get(role)
    base = dict(profile.capabilities) if profile is not None else {}
    base.update(saved_capabilities(design))
    return base


def render_capability_rows(
    ui: GMLWidgets,
    frame_slot: str,
    values: dict[str, float],
    state,
    *,
    editable: bool = False,
    test_id_prefix: str = "unit_design.capability",
    visible_keys: set[str] | None = None,
) -> None:
    """Render OpenPower capabilities into the source label and meter slots."""
    capability_bounds = contribution_for(state, ClientPresentationKeys.CAPABILITY_BOUNDS)
    for key, label, component in DESIGN_METRICS:
        if visible_keys is not None and key not in visible_keys:
            continue
        value = values.get(key)
        label_slot = f"{frame_slot}/lbl{component}"
        meter_slot = f"{frame_slot}/frm{component}"
        ui.text(label_slot, label, test_id=f"{test_id_prefix}.{key}.label")
        if value is None:
            continue

        minimum, maximum = capability_bounds[key]
        if editable:
            display_format = "%.2f" if maximum <= 1.0 else "%.0f"
            _, values[key] = imgui.slider_float(
                f"##{test_id_prefix}.{key}",
                float(value),
                float(minimum),
                float(maximum),
                display_format,
                test_id=f"{test_id_prefix}.{key}",
                gml_id=ui.path(meter_slot),
            )
            continue

        fraction = (
            0.0 if maximum <= minimum
            else max(0.0, min(1.0, (float(value) - minimum) / (maximum - minimum)))
        )
        imgui.progress_bar(
            fraction, (0.0, 0.0), f"{float(value):g}",
            gml_id=ui.path(meter_slot),
        )
        if imgui.is_item_hovered():
            imgui.set_tooltip(f"{label}: {float(value):g}")
