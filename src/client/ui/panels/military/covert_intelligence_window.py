"""OpenPower findings and detected incidents supplementary to the source cell list."""
from src.client.ui.core.containers import WindowManager
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.panels.shared.panel_widgets import draw_empty_state


class CovertIntelligenceWindow:
    def __init__(self):
        self.is_open = False

    def render(self, state, context, presenter):
        if not self.is_open:
            return
        with WindowManager.window("Covert intelligence", x=340, y=410, w=620, h=260,
                                  test_id="covert_ops.intelligence") as opened:
            self.is_open = opened
            if not opened:
                return
            if not context.is_own_country:
                imgui.text_wrapped("Select your country to inspect authorized intelligence.")
                return
            missions = presenter.covert_missions_for_country(state, context.target_tag)
            imgui.text("KNOWN OPERATIONS")
            if not missions:
                draw_empty_state("No pending or discovered operations.")
            for row in missions:
                if row.get("_viewer_role") == "framed":
                    imgui.text_wrapped("Detected operation · your country was implicated")
                    imgui.text_disabled(f"Your country was framed · Target {row.get('target_country_id') or 'unknown'}")
                else:
                    imgui.text_wrapped(f"{str(row.get('mission_type') or 'unknown').replace('_', ' ').title()} · "
                                       f"{row.get('result') or row.get('status') or 'unknown'}")
                    imgui.text_disabled(f"Target {row.get('target_country_id') or 'unknown'} · "
                                        f"Attribution {row.get('owner_country_id') or 'unknown'}")
            imgui.separator()
            imgui.text("INTELLIGENCE FINDINGS")
            findings = presenter.covert_findings_for_country(state, context.target_tag)
            if not findings:
                draw_empty_state("No intelligence findings are available.")
            for row in findings:
                source = str(row.get("source_country_id") or "").upper()
                provenance = "Collected directly" if source == context.target_tag else f"Shared by {source or 'ally'}"
                imgui.text_wrapped(f"{str(row.get('category') or 'unknown').title()} · "
                    f"{row.get('information_status') or 'unknown'} · "
                    f"Confidence {float(row.get('confidence') or 0) * 100:.0f}% · "
                    f"Freshness {float(row.get('freshness') or 0) * 100:.0f}%")
                imgui.text_disabled(provenance)
