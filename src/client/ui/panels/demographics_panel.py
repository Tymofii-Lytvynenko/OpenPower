import math
from typing import Callable

import polars as pl
from src.client.ui.core.instrumented_imgui import imgui

from src.client.ui.core.theme import GAMETHEME
from src.client.ui.core.primitives import UIPrimitives as Prims
from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.layouts.main_pillar_positions import main_pillar_position


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
        x, y = main_pillar_position("demographics")
        with WindowManager.window(
            "DEMOGRAPHICS", x=x, y=y, w=240, h=480,
            test_id="demographics.panel",
        ) as is_open:
            if not is_open:
                return False
            self._render_content(state, context.target_tag, context.is_own_country)
            return True

    def _render_content(self, state, target_tag, is_own):
        # --- 1. Aggregation Logic ---
        total_pop, pop_14, pop_15_64, pop_65, has_age_structure = 0, 0, 0, 0, False
        
        if "regions" in state.tables:
            try:
                df = state.tables["regions"]
                # Filter by active target (could be foreign)
                target_regions = df.filter(pl.col("owner") == target_tag)
                
                age_columns = {"pop_14", "pop_15_64", "pop_65"}
                if not target_regions.is_empty() and age_columns.issubset(target_regions.columns):
                    pop_14, pop_15_64, pop_65 = (
                        int(target_regions.select(pl.col(column).fill_null(0).sum()).item() or 0)
                        for column in ("pop_14", "pop_15_64", "pop_65")
                    )
                    total_pop = pop_14 + pop_15_64 + pop_65
                    has_age_structure = True
                elif not target_regions.is_empty() and "population" in target_regions.columns:
                    # Older snapshots expose only total population; do not turn missing cohorts into zero-valued data.
                    total_pop = int(target_regions.select(pl.col("population").fill_null(0).sum()).item() or 0)
            except (pl.exceptions.PolarsError, TypeError, ValueError, OverflowError):
                total_pop, pop_14, pop_15_64, pop_65, has_age_structure = 0, 0, 0, 0, False

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
        
        age_labels = (
            (f"Youth: {pop_14:,}", "Youth: N/A"),
            (f"Working: {pop_15_64:,}", "Working: N/A"),
            (f"Elderly: {pop_65:,}", "Elderly: N/A"),
        )
        for (available_label, fallback_label), value, color in zip(
            age_labels,
            (pct_14, pct_15_64, pct_65),
            ((0.4, 0.7, 1.0, 1.0), (0.3, 0.8, 0.4, 1.0), (0.8, 0.4, 0.4, 1.0)),
        ):
            Prims.meter(available_label if has_age_structure else fallback_label, value, color)

        # Development Metrics
        Prims.header("DEVELOPMENT")
        
        human_dev_index = self._human_development_index(state, target_tag)
        if human_dev_index is None:
            Prims.meter("HDI Score: N/A", 0.0, GAMETHEME.colors.text_dim)
        else:
            # Country HDI is stored as 0..1; this meter expects 0..100 percent.
            Prims.meter(
                f"HDI Score: {human_dev_index:.2f}",
                human_dev_index * 100.0,
                GAMETHEME.colors.info,
            )
        
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
    def _human_development_index(state, target_tag: str) -> float | None:
        # The loader merges countries_dem.tsv into countries rather than exposing a separate runtime table.
        countries = state.tables.get("countries")
        if countries is None or not {"id", "human_dev"}.issubset(countries.columns):
            return None

        row = countries.filter(
            pl.col("id").cast(pl.String, strict=False) == str(target_tag)
        ).select("human_dev").head(1)
        if row.is_empty():
            return None

        value = row.item()
        try:
            score = float(value)
        except (TypeError, ValueError, OverflowError):
            return None
        if not math.isfinite(score):
            return None
        return max(0.0, min(1.0, score))
