import polars as pl
from src.client.ui.core.instrumented_imgui import imgui

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.core.theme import GAMETHEME
from src.client.ui.panels.politics.recognition_presenter import RecognitionPresenter


class RegionInspectorPanel:
    def __init__(self) -> None:
        self._recognition_presenter = RecognitionPresenter()

    def render(self, state, context: PanelRenderContext) -> bool:
        with WindowManager.window("INSPECTOR", x=400, y=200, w=300, h=400) as is_open:
            if not is_open:
                return False

            if context.selected_region_id is None:
                imgui.text_disabled("Select a region...")
                return True

            self._render_details(
                state,
                context.selected_region_id,
                context.on_focus_request,
                context.target_tag,
            )
            return True

    def _render_details(self, state, region_id, on_focus, country_tag: str = ""):
        if "regions" not in state.tables:
            return

        row_df = state.tables["regions"].filter(pl.col("id") == region_id)
        if row_df.is_empty():
            imgui.text_colored(GAMETHEME.colors.error, "Invalid Region ID")
            return

        row = row_df.row(0, named=True)
        imgui.text_colored(GAMETHEME.colors.accent, row.get("name", "Unknown"))

        imgui.separator()
        imgui.text(f"ID: {region_id}")
        imgui.text(f"Owner: {row.get('owner', 'N/A')}")
        if "controller" in row:
            imgui.text(f"Controller: {row.get('controller', row.get('owner', 'N/A'))}")
        recognition = self._recognition_presenter.for_region(state, int(region_id), country_tag)
        if recognition is not None:
            imgui.separator()
            imgui.text("UN Recognition")
            imgui.text(f"Claimant: {recognition['claimant_id']}")
            imgui.text(f"Former owner: {recognition['former_owner_id']}")
            imgui.text(f"Case: {recognition['status'].replace('_', ' ').title()}")
            imgui.text(
                f"Yes votes: {recognition['yes_votes']} / "
                f"{recognition['eligible_count']} eligible"
            )
            if recognition["recognized_count"]:
                imgui.text(f"Recognizing countries: {recognition['recognized_count']}")
            if recognition["country_status"]:
                imgui.text(f"Selected country: {recognition['country_status'].replace('_', ' ').title()}")
        occupations = state.tables.get("occupations")
        if occupations is not None and not occupations.is_empty() and "region_id" in occupations.columns:
            occupation = occupations.filter(pl.col("region_id") == int(region_id))
            if not occupation.is_empty():
                occupation_row = occupation.to_dicts()[0]
                imgui.separator()
                imgui.text("Military occupation")
                imgui.text(f"Controller: {occupation_row.get('controller_country_id', row.get('controller', 'N/A'))}")
                imgui.text(f"Garrison: {int(occupation_row.get('garrison_strength') or 0)}")
                imgui.text(f"Resistance: {float(occupation_row.get('resistance') or 0.0):.1f}")
                imgui.text(f"Status: {occupation_row.get('occupation_status', 'active')}")
                imgui.text(f"Started: {int(occupation_row.get('started_at_minute') or 0)}")
                imgui.text(f"Contested: {'Yes' if bool(occupation_row.get('contested')) else 'No'}")
        imgui.text(f"Biome: {row.get('biome', 'N/A')}")

        if on_focus and imgui.button("Center Camera"):
            on_focus(region_id)
