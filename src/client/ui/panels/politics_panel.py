from src.client.ui.core.instrumented_imgui import imgui

from src.client.ui.core.theme import GAMETHEME
from src.client.ui.core.gml_widgets import GMLWidgets
from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.panels.politics.presenter import PoliticsPresenter
from src.client.ui.layouts.main_pillar_positions import main_pillar_position


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
        x, y = main_pillar_position("politics")
        with WindowManager.window(
            "POLITICS", x=x, y=y, w=240, h=520, test_id="politics.panel",
            flags=imgui.WindowFlags_.no_resize | imgui.WindowFlags_.no_scrollbar | imgui.WindowFlags_.no_scroll_with_mouse,
        ) as is_open:
            if not is_open:
                return False
            self._render_content(state, context.target_tag, context.is_own_country)
            return True

    def _render_content(self, state, target_tag, is_own):
        summary = self._presenter.build_summary(state, target_tag)
        ui = GMLWidgets("Politic_Window/frmInner")
        ui.text("frmConstitutionalForm/lblTitle", "CONSTITUTIONAL FORM")
        ui.text("frmConstitutionalForm/txtValue", summary.government_type,
                tooltip=f"{summary.government_type}\nCapital: {summary.capital_name}")
        if ui.button("frmConstitutionalForm/btnMoreConstitutionalForm", "more",
                     "politics.open_constitution", enabled=self._open_constitution_cb is not None):
            self._open_constitution_cb()
        ui.text("frmIdeology/lblTitle", "IDEOLOGY")
        ui.meter("frmIdeology/frmIdeologyCursor", summary.ideology_balance,
                 GAMETHEME.colors.accent, cursor=True)
        ui.text("frmIdeology/lblLeft", "Left", color=GAMETHEME.colors.text_dim)
        ui.text("frmIdeology/lblRight", "Right", color=GAMETHEME.colors.text_dim, right=True)
        if ui.button("frmIdeology/btnInternalLaws", "INTERNAL LAWS", "politics.open_laws",
                     enabled=is_own and self._open_laws_cb is not None):
            self._open_laws_cb()
        for section, label, value, color in (
            ("frmApproval", "APPROVAL", summary.approval_pct,
             GAMETHEME.colors.positive if summary.approval_pct > 40 else GAMETHEME.colors.negative),
            ("frmStability", "STABILITY", summary.stability_pct,
             GAMETHEME.colors.positive if summary.stability_pct > 50 else GAMETHEME.colors.warning),
            ("frmCorruption", "CORRUPTION", summary.corruption_pct,
             GAMETHEME.colors.negative if summary.corruption_pct > 30 else GAMETHEME.colors.positive),
        ):
            ui.text(f"{section}/lblTitle", label)
            ui.text(f"{section}/txtValue", f"{value:.0f}%")
            ui.meter(f"{section}/frmGradient", value / 100.0, color)
        # The simulation has no REFERENCE political-pressure field; keep its slot explicit.
        ui.text("frmPressure/lblTitle", "POLITICAL PRESSURE")
        ui.text("frmPressure/txtValue", "N/A", color=GAMETHEME.colors.text_dim,
                tooltip="Political pressure is not available in the current simulation.")
        ui.meter("frmPressure/frmGradient", 0.0, GAMETHEME.colors.text_dim)
        if ui.button("btnTreaties", "TREATIES" if is_own else "DIPLOMATIC ACTIONS",
                     "politics.open_treaties", enabled=self._open_treaties_cb is not None,
                     tooltip=f"Active treaties: {summary.active_treaties}\nPending proposals: {summary.pending_treaties}"):
            self._open_treaties_cb()
