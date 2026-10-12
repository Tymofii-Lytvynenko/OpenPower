from __future__ import annotations

import json

from src.client.ui.core.instrumented_imgui import imgui

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.panels.military.presenter import MilitaryPresenter
from src.client.ui.panels.shared.panel_widgets import draw_empty_state, draw_required_tables


class UnitDesignPanel:
    def __init__(self):
        self._presenter = MilitaryPresenter()

    def render(self, state, context: PanelRenderContext) -> bool:
        with WindowManager.window("UNIT DESIGN", x=650, y=210, w=500, h=420) as is_open:
            if not is_open:
                return False
            self._render_content(state, context.target_tag)
            return True

    def _render_content(self, state, country_tag: str) -> None:
        draw_required_tables(state, ("unit_designs",))
        imgui.separator()

        designs = self._presenter.designs_for_country(state, country_tag)
        if not designs:
            draw_empty_state("No reusable unit designs are available.")
            return

        for row in designs:
            imgui.text(str(row.get("display_name") or "Design"))
            imgui.same_line()
            imgui.text_disabled(str(row.get("branch") or "").upper())
            imgui.text_disabled("Fixed role definition")
            imgui.text_disabled(
                f"Role {str(row.get('class_name') or 'generic')} · "
                f"Domain {str(row.get('domain') or 'land')} · "
                f"Research level {int(row.get('research_level') or 0)} · "
                f"Cost ${float(row.get('cost') or 0.0):,.0f} · "
                f"Annual upkeep ${float(row.get('maintenance_cost') or 0.0):,.0f} per strength"
            )
            imgui.text_disabled("Design-adjustable capabilities are bounded by the role catalog")
            imgui.text_disabled(
                f"Quality {float(row.get('quality') or 0.0) * 100:.0f}% | "
                f"Speed {float(row.get('speed') or 0.0) * 100:.0f}% | "
                f"Firepower {float(row.get('firepower') or 0.0) * 100:.0f}%"
            )
            capabilities = self._decode_mapping(row.get("capabilities_json"))
            if capabilities:
                labels = (
                    ("speed", "Speed"), ("maneuverability", "Maneuverability"), ("sensors", "Sensors"),
                    ("gun_range", "Gun range"), ("gun_precision", "Gun precision"), ("gun_damage", "Gun damage"),
                    ("missile_payload", "Missile payload"), ("missile_range", "Missile range"),
                    ("missile_precision", "Missile precision"), ("missile_damage", "Missile damage"),
                    ("stealth", "Stealth"), ("countermeasures", "Countermeasures"), ("armor", "Armor"),
                )
                values = [f"{label} {float(capabilities[key]):g}" for key, label in labels if key in capabilities]
                imgui.text_wrapped(" · ".join(values))
            targets = self._decode_list(row.get("valid_targets_json"))
            vulnerabilities = self._decode_list(row.get("vulnerabilities_json"))
            imgui.text_wrapped(f"Fixed targets: {', '.join(targets) or 'neutral'}")
            imgui.text_wrapped(f"Fixed counter vulnerabilities: {', '.join(vulnerabilities) or 'none configured'}")
            requirements = self._decode_mapping(row.get("research_requirements_json"))
            if requirements:
                imgui.text_disabled("Research: " + ", ".join(f"{key} ≥ {value}" for key, value in sorted(requirements.items())))
            imgui.separator()

    def _decode_mapping(self, value):
        try:
            parsed = json.loads(str(value or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _decode_list(self, value):
        try:
            parsed = json.loads(str(value or "[]"))
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
        return [str(item) for item in parsed] if isinstance(parsed, list) else []
