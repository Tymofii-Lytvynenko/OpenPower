from __future__ import annotations

from imgui_bundle import imgui

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.panels.military.presenter import MilitaryPresenter
from src.client.ui.panels.shared.panel_widgets import draw_empty_state, draw_required_tables


class CovertOpsPanel:
    def __init__(self):
        self._presenter = MilitaryPresenter()

    def render(self, state, context: PanelRenderContext) -> bool:
        with WindowManager.window("COVERT OPS", x=720, y=190, w=460, h=350) as is_open:
            if not is_open:
                return False
            self._render_content(state, context.target_tag)
            return True

    def _render_content(self, state, country_tag: str) -> None:
        draw_required_tables(state, ("covert_cells", "covert_missions", "covert_findings"))
        imgui.separator()

        cells = self._presenter.covert_cells_for_country(state, country_tag)
        if not cells:
            draw_empty_state("No covert cells are registered for the selected country.")
        for row in cells:
            imgui.text(str(row.get("cell_name") or "Cell"))
            imgui.same_line()
            imgui.text_disabled(str(row.get("target_country_id") or ""))
            imgui.text(
                f"{str(row.get('skill_level') or 'Recruit')} · {str(row.get('status') or 'unknown')} | "
                f"Readiness {float(row.get('readiness') or 0.0) * 100:.0f}% | "
                f"Concealment {float(row.get('concealment') or 0.0) * 100:.0f}% | "
                f"Upkeep {float(row.get('upkeep') or 0.0):.2f}/day"
            )
            imgui.text_disabled(
                f"Assignment {str(row.get('assignment') or 'unassigned')} · "
                f"Last known: {str(row.get('last_known_status') or 'unknown')}"
            )
            imgui.separator()

        imgui.dummy((0.0, 6.0))
        imgui.text("KNOWN OPERATIONS")
        missions = self._presenter.covert_missions_for_country(state, country_tag)
        if not missions:
            imgui.text_disabled("No pending or discovered operations.")
        for row in missions[:12]:
            mission_type = str(row.get("mission_type") or "unknown").replace("_", " ").title()
            result = str(row.get("result") or row.get("status") or "unknown").replace("_", " ")
            progress = max(0.0, min(1.0, float(row.get("preparation_progress") or 0.0)))
            confidence = max(0.0, min(1.0, float(row.get("confidence") or 0.0)))
            imgui.text(f"{mission_type} · {result}")
            imgui.text_disabled(
                f"Target {str(row.get('target_country_id') or 'unknown')} · "
                f"Preparation {progress * 100:.0f}% · Confidence {confidence * 100:.0f}%"
            )
            if not bool(row.get("attributed_to_owner")) and str(row.get("owner_country_id") or "") == "Unknown":
                imgui.text_disabled("Operation detected; attribution remains unknown.")

        if str(country_tag or "").strip().upper():
            findings = self._presenter.covert_findings_for_country(state, country_tag)
            imgui.dummy((0.0, 6.0))
            imgui.text("INTELLIGENCE FINDINGS")
            if not findings:
                imgui.text_disabled("No intelligence findings are available.")
            for row in findings[:8]:
                source = str(row.get("source_country_id") or "").strip().upper()
                provenance = "Collected directly" if source == str(country_tag or "").strip().upper() else f"Shared by {source or 'ally'}"
                imgui.text(
                    f"{str(row.get('category') or 'unknown').title()} · "
                    f"{str(row.get('information_status') or 'unknown')} · "
                    f"Confidence {float(row.get('confidence') or 0.0) * 100:.0f}% · "
                    f"Freshness {float(row.get('freshness') or 0.0) * 100:.0f}%"
                )
                imgui.text_disabled(provenance)
