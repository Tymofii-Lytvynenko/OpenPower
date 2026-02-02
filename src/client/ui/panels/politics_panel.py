import polars as pl
from imgui_bundle import imgui

from src.client.ui.core.theme import GAMETHEME
from src.client.ui.core.primitives import UIPrimitives as Prims
from src.client.ui.core.containers import WindowManager

class PoliticsPanel:
    def render(self, state, **kwargs) -> bool:
        target_tag = kwargs.get("target_tag", "")
        is_own = kwargs.get("is_own_country", False)

        with WindowManager.window("POLITICS", x=10, y=100, w=240, h=520) as is_open:
            if not is_open: return False
            self._render_content(state, target_tag, is_own)
            return True

    def _render_content(self, state, target_tag, is_own):
        stability = 50.0
        corruption = 50.0
        approval = 50.0

        if "countries" in state.tables:
            try:
                row = state.tables["countries"].filter(pl.col("id") == target_tag)
                if not row.is_empty():
                    stability = float(row["gvt_stability"][0])
                    corruption = float(row["gvt_corruption"][0])
                    approval = float(row["gvt_approval"][0])
            except: pass

        Prims.header("IDEOLOGY")
        if not is_own: imgui.begin_disabled()
        imgui.slider_float("##ideo", 0.5, 0.0, 1.0, "")
        if not is_own: imgui.end_disabled()
        
        imgui.text_disabled("Left")
        imgui.same_line()
        Prims.right_align_text("Right", GAMETHEME.colors.text_dim)

        imgui.dummy((0, 10))

        Prims.header("METRICS", show_bg=False)
        Prims.meter("Approval", approval, GAMETHEME.colors.positive if approval > 40 else GAMETHEME.colors.negative)
        Prims.meter("Stability", stability, GAMETHEME.colors.positive if stability > 50 else GAMETHEME.colors.warning)
        Prims.meter("Corruption", corruption, GAMETHEME.colors.negative if corruption > 30 else GAMETHEME.colors.positive)

        imgui.dummy((0, 20))
        if is_own:
            if imgui.button("INTERNAL LAWS", (-1, 35)): pass