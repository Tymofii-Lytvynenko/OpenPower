from imgui_bundle import imgui

from src.client.ui.core.theme import GAMETHEME
from src.client.ui.core.primitives import UIPrimitives as Prims
from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.panels.politics.presenter import PoliticsPresenter


class PoliticsPanel:
    def __init__(
        self,
        open_constitution_cb=None,
        open_laws_cb=None,
        open_treaties_cb=None,
    ):
        self._presenter = PoliticsPresenter()
        self._open_constitution_cb = open_constitution_cb
        self._open_laws_cb = open_laws_cb
        self._open_treaties_cb = open_treaties_cb

    def render(self, state, context: PanelRenderContext) -> bool:
        # Composition: WindowManager handles the Begin/End
        with WindowManager.window("POLITICS", x=10, y=100, w=240, h=520) as is_open:
            if not is_open:
                return False
            self._render_content(state, context.target_tag, context.is_own_country)
            return True

    def _render_content(self, state, target_tag, is_own):
        summary = self._presenter.build_summary(state, target_tag)

        # --- 2. Render Widgets ---
        Prims.header("CONSTITUTIONAL FORM")
        imgui.text(summary.government_type)
        imgui.text_disabled(summary.capital_name)
        if self._open_constitution_cb and imgui.button("DETAILS", (imgui.get_content_region_avail().x, 0)):
            self._open_constitution_cb()
        imgui.dummy((0, 5))

        # Ideology Slider
        Prims.header("IDEOLOGY", show_bg=False)
        imgui.push_style_color(imgui.Col_.slider_grab, GAMETHEME.colors.accent)
        imgui.push_style_color(imgui.Col_.frame_bg, GAMETHEME.colors.bg_popup)

        imgui.begin_disabled()
        imgui.slider_float("##ideology", summary.ideology_balance, 0.0, 1.0, "")
        imgui.end_disabled()
        
        imgui.pop_style_color(2)
        
        imgui.text_disabled("Left")
        imgui.same_line()
        Prims.right_align_text("Right", GAMETHEME.colors.text_dim)
        
        imgui.dummy((0, 5))
        
        # Internal Laws Button
        if is_own:
            if imgui.button("INTERNAL LAWS", (imgui.get_content_region_avail().x, 0)) and self._open_laws_cb:
                self._open_laws_cb()
        else:
            imgui.text_disabled("Internal Laws Restricted")

        imgui.dummy((0, 8))

        # Metrics
        Prims.header("APPROVAL", show_bg=False)
        col = GAMETHEME.colors.positive if summary.approval_pct > 40 else GAMETHEME.colors.negative
        Prims.meter("", summary.approval_pct, col)

        Prims.header("STABILITY", show_bg=False)
        col = GAMETHEME.colors.positive if summary.stability_pct > 50 else GAMETHEME.colors.warning
        Prims.meter("", summary.stability_pct, col)

        Prims.header("CORRUPTION", show_bg=False)
        col = GAMETHEME.colors.negative if summary.corruption_pct > 30 else GAMETHEME.colors.positive
        Prims.meter("", summary.corruption_pct, col)
        
        imgui.dummy((0, 10))
        imgui.text_disabled(f"Active treaties: {summary.active_treaties}")
        imgui.text_disabled(f"Pending proposals: {summary.pending_treaties}")
        imgui.dummy((0, 6))
        
        if is_own:
            if imgui.button("TREATIES", (-1, 35)) and self._open_treaties_cb:
                self._open_treaties_cb()
        else:
            if imgui.button("DIPLOMATIC ACTIONS", (-1, 35)) and self._open_treaties_cb:
                self._open_treaties_cb()
