import math
from typing import Callable

import polars as pl
from src.client.ui.core.instrumented_imgui import imgui

from src.client.ui.core.theme import GAMETHEME
from src.client.ui.core.primitives import UIPrimitives as Prims
from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext


class DemographicsPanel:
    def __init__(
        self,
        open_migration_policy_cb: Callable[[], None] | None = None,
        open_social_programs_cb: Callable[[], None] | None = None,
    ) -> None:
        self._open_migration_policy_cb = open_migration_policy_cb
        self._open_social_programs_cb = open_social_programs_cb

    def open_migration_policy(self) -> bool:
        if self._open_migration_policy_cb is None:
            return False
        self._open_migration_policy_cb()
        return True

    def open_social_programs(self) -> bool:
        if self._open_social_programs_cb is None:
            return False
        self._open_social_programs_cb()
        return True

    def render(self, state, context: PanelRenderContext) -> bool:
        with WindowManager.window("DEMOGRAPHICS", x=10, y=350, w=240, h=480) as is_open:
            if not is_open:
                return False
            self._render_content(state, context.target_tag, context.is_own_country)
            return True

    def _render_content(self, state, target_tag, is_own):
        # --- 1. Aggregation Logic ---
        total_pop = 0
        pop_14 = 0
        pop_15_64 = 0
        pop_65 = 0
        
        if "regions" in state.tables:
            try:
                df = state.tables["regions"]
                # Filter by active target (could be foreign)
                target_regions = df.filter(pl.col("owner") == target_tag)
                
                if not target_regions.is_empty():
                    pop_14 = target_regions.select(pl.col("pop_14")).sum().item()
                    pop_15_64 = target_regions.select(pl.col("pop_15_64")).sum().item()
                    pop_65 = target_regions.select(pl.col("pop_65")).sum().item()
                    total_pop = pop_14 + pop_15_64 + pop_65
            except Exception as e:
                print(f"[Demographics] Error: {e}")

        # Calculate percentages
        pct_14 = (pop_14 / total_pop * 100) if total_pop > 0 else 0
        pct_15_64 = (pop_15_64 / total_pop * 100) if total_pop > 0 else 0
        pct_65 = (pop_65 / total_pop * 100) if total_pop > 0 else 0

        # --- 2. Render UI ---
        
        # Total Population
        Prims.header("POPULATION SUMMARY")

        imgui.text("Total:")
        imgui.same_line()
        # Right align the number
        Prims.right_align_text(f"{total_pop:,}", GAMETHEME.colors.accent)
        
        imgui.dummy((0, 5))

        # Age Structure
        Prims.header("AGE STRUCTURE", show_bg=False)
        
        Prims.meter(f"Youth: {pop_14:,}", pct_14, (0.4, 0.7, 1.0, 1.0))
        Prims.meter(f"Working: {pop_15_64:,}", pct_15_64, (0.3, 0.8, 0.4, 1.0))
        Prims.meter(f"Elderly: {pop_65:,}", pct_65, (0.8, 0.4, 0.4, 1.0))

        # Development Metrics
        Prims.header("DEVELOPMENT")
        
        human_dev_index = self._human_development_index(state, target_tag)

        Prims.meter("HDI Score", human_dev_index, GAMETHEME.colors.info)
        
        imgui.dummy((0, 15))
        
        # Action Buttons
        if is_own:
            if self._open_migration_policy_cb is not None and imgui.button("MIGRATION POLICY", (-1, 30)):
                self.open_migration_policy()
            if self._open_social_programs_cb is not None and imgui.button("SOCIAL PROGRAMS", (-1, 30)):
                self.open_social_programs()
        else:
            imgui.text_disabled("Internal Policies Restricted")

    @staticmethod
    def _human_development_index(state, target_tag: str) -> float:
        # The loader merges countries_dem.tsv into countries rather than exposing a separate runtime table.
        countries = state.tables.get("countries")
        if countries is None or not {"id", "human_dev"}.issubset(countries.columns):
            return 0.0

        row = countries.filter(
            pl.col("id").cast(pl.String, strict=False) == str(target_tag)
        ).select("human_dev").head(1)
        if row.is_empty():
            return 0.0

        value = row.item()
        try:
            score = float(value)
        except (TypeError, ValueError, OverflowError):
            return 0.0
        if not math.isfinite(score):
            return 0.0
        return max(0.0, min(1.0, score))
