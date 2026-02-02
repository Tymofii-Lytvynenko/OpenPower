import polars as pl
from imgui_bundle import imgui
from src.client.ui.core.theme import GAMETHEME
from src.client.ui.core.primitives import UIPrimitives as Prims
from src.client.ui.core.containers import WindowManager

class DemographicsPanel:
    def render(self, state, **kwargs) -> bool:
        target_tag = kwargs.get("target_tag", "")
        
        with WindowManager.window("DEMOGRAPHICS", x=10, y=350, w=240, h=480) as is_open:
            if not is_open: return False

            # Aggregation
            pop_14, pop_15_64, pop_65 = 0, 0, 0
            if "regions" in state.tables:
                try:
                    df = state.tables["regions"].filter(pl.col("owner") == target_tag)
                    if not df.is_empty():
                        pop_14 = df.select(pl.col("pop_14")).sum().item()
                        pop_15_64 = df.select(pl.col("pop_15_64")).sum().item()
                        pop_65 = df.select(pl.col("pop_65")).sum().item()
                except: pass

            total = pop_14 + pop_15_64 + pop_65
            if total == 0: total = 1 # avoid div/0

            Prims.header("POPULATION")
            Prims.right_align_text(f"{total:,}", GAMETHEME.colors.accent)
            
            imgui.dummy((0, 10))
            Prims.header("AGE STRUCTURE", show_bg=False)
            Prims.meter("Youth", (pop_14 / total) * 100, (0.4, 0.7, 1.0, 1.0))
            Prims.meter("Working", (pop_15_64 / total) * 100, (0.3, 0.8, 0.4, 1.0))
            Prims.meter("Elderly", (pop_65 / total) * 100, (0.8, 0.4, 0.4, 1.0))

            return True