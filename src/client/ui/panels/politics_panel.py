import polars as pl
from imgui_bundle import imgui

from src.client.ui.core.theme import GAMETHEME
from src.client.ui.core.primitives import UIPrimitives as Prims
from src.client.ui.core.containers import WindowManager

class PoliticsPanel:
    def render(self, state, **kwargs) -> bool:
        target_tag = kwargs.get("target_tag", "")
        is_own = kwargs.get("is_own_country", False)
        
        # Composition: WindowManager handles the Begin/End
        with WindowManager.window("POLITICS", x=10, y=100, w=240, h=520) as is_open:
            if not is_open: return False
            self._render_content(state, target_tag, is_own)
            return True

    def _render_content(self, state, target_tag, is_own):
        # --- 1. Fetch Data ---
        stability = 50.0
        corruption = 50.0
        approval = 50.0
        
        if "countries" in state.tables:
            try:
                df = state.tables["countries"]
                row = df.filter(pl.col("id") == target_tag)
                if not row.is_empty():
                    stability = float(row["gvt_stability"][0])
                    corruption = float(row["gvt_corruption"][0])
                    approval = float(row["gvt_approval"][0])
            except Exception:
                pass

        # --- 2. Render Widgets ---
        Prims.header("CONSTITUTIONAL FORM")
        imgui.text("Multi-party democracy")
        imgui.dummy((0, 5))

        # Ideology Slider
        Prims.header("IDEOLOGY", show_bg=False)
        imgui.push_style_color(imgui.Col_.slider_grab, GAMETHEME.colors.accent)
        imgui.push_style_color(imgui.Col_.frame_bg, GAMETHEME.colors.bg_popup)
        
        if not is_own: imgui.begin_disabled()
        imgui.slider_float("##ideology", 0.5, 0.0, 1.0, "")
        if not is_own: imgui.end_disabled()
        
        imgui.pop_style_color(2)
        
        imgui.text_disabled("Left")
        imgui.same_line()
        Prims.right_align_text("Right", GAMETHEME.colors.text_dim)
        
        imgui.dummy((0, 5))
        
        # Internal Laws Button
        if is_own:
            if imgui.button("INTERNAL LAWS", (imgui.get_content_region_avail().x, 0)): pass 
        else:
            imgui.text_disabled("Internal Laws Restricted")

        imgui.dummy((0, 8))

        # Metrics
        Prims.header("APPROVAL", show_bg=False)
        col = GAMETHEME.colors.positive if approval > 40 else GAMETHEME.colors.negative
        Prims.meter("", approval, col) 

        Prims.header("STABILITY", show_bg=False)
        col = GAMETHEME.colors.positive if stability > 50 else GAMETHEME.colors.warning
        Prims.meter("", stability, col) 

        Prims.header("CORRUPTION", show_bg=False)
        col = GAMETHEME.colors.negative if corruption > 30 else GAMETHEME.colors.positive
        Prims.meter("", corruption, col) 
        
        imgui.dummy((0, 10))
        
        if is_own:
            if imgui.button("TREATIES", (-1, 35)): pass
        else:
            if imgui.button("DIPLOMATIC ACTIONS", (-1, 35)): pass