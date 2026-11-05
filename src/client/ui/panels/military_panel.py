from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.theme import GAMETHEME
from src.client.ui.core.gml_widgets import GMLWidgets
from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.panels.military.presenter import MilitaryPresenter
from src.client.ui.layouts.main_pillar_positions import main_pillar_position


class MilitaryPanel:
    def __init__(
        self,
        open_unit_list_cb=None,
        open_production_cb=None,
        open_research_cb=None,
        open_design_cb=None,
        open_market_cb=None,
        open_covert_cb=None,
        open_wars_cb=None,
        open_battle_cb=None,
        open_strategic_cb=None,
        open_reserves_cb=None,
    ):
        self._presenter = MilitaryPresenter()
        self._open_unit_list_cb = open_unit_list_cb
        self._open_reserves_cb = open_reserves_cb
        self._open_production_cb = open_production_cb
        self._open_research_cb = open_research_cb
        self._open_design_cb = open_design_cb
        self._open_market_cb = open_market_cb
        self._open_covert_cb = open_covert_cb
        self._open_wars_cb = open_wars_cb
        self._open_battle_cb = open_battle_cb
        self._open_strategic_cb = open_strategic_cb

    def render(self, state, context: PanelRenderContext) -> bool:
        # Use Composition for Window Management
        x, y = main_pillar_position("military")
        with WindowManager.window(
            "MILITARY", x=x, y=y, w=250, h=520, test_id="military.panel",
            flags=imgui.WindowFlags_.no_resize | imgui.WindowFlags_.no_scrollbar | imgui.WindowFlags_.no_scroll_with_mouse,
        ) as is_open:
            if not is_open:
                return False
            self._render_content(state, context.target_tag, context.is_own_country)
            return True

    def _render_content(self, state, target_tag, is_own):
        summary = self._presenter.build_summary(state, target_tag)
        ui = GMLWidgets("Military_Window/frmInner")
        conventional = "frmConventionalWarfare"
        strategic = "frmStrategicWeapons"
        ui.text(f"{conventional}/lblTitle", "CONVENTIONAL FORCES", max_width=165)
        if ui.button(f"{conventional}/btnConventionalForcesMore", "more", "military.open_battle",
                     enabled=self._open_battle_cb is not None,
                     tooltip=f"Moving units: {summary.moving_units}\nActive wars: {summary.active_wars}\nCovert cells: {summary.covert_cells}"):
            self._open_battle_cb()
        ui.text(f"{conventional}/lblSoldiers", "UNITS", test_id="military.units_header")
        slots = {"LAND": ("lblLand", "lblLandNb", "lblLandRank"),
                 "AIR": ("lblAir", "lblAirNb", "lblAirRank"),
                 "NAVAL": ("lblNaval", "lblNavalNb", "lblNavalRank"),
                 "STRATEGIC": ("lblSoldier", "lblSoldiersNb", "lblSoldiersRank")}
        for bucket in summary.branches:
            label, value, count = slots[bucket.label]
            ui.text(f"{conventional}/{label}", "STRAT." if bucket.label == "STRATEGIC" else bucket.label,
                    color=GAMETHEME.colors.text_dim, tooltip=bucket.label)
            ui.text(f"{conventional}/{value}", f"{bucket.strength:,}".replace(",", " "), right=True)
            ui.text(f"{conventional}/{count}", bucket.unit_count)
        for slot, label, test_id, callback in (
            ("btnBuy", "BUY", "military.open_market", self._open_market_cb),
            ("btnBuild", "BUILD", "military.open_production", self._open_production_cb),
            ("btnResearch", "RESEARCH", "military.open_research", self._open_research_cb),
            ("btnDesign", "DESIGN", "military.open_design", self._open_design_cb),
        ):
            if ui.button(f"{conventional}/{slot}", label, test_id, enabled=is_own and callback is not None):
                callback()
        # OpenPower exposes both deployed and reserve lists in the deployment row.
        for offset, label, test_id, callback in (
            ((-49.0, 0.0), "UNIT LIST", "military.open_unit_list", self._open_unit_list_cb),
            ((52.0, 0.0), "RESERVES", "military.open_reserves", self._open_reserves_cb),
        ):
            if ui.button_at(f"{conventional}/btnDeploy", label, test_id, offset=offset,
                            enabled=is_own and callback is not None):
                callback()
        ui.text(f"{strategic}/lblTitle", "STRATEGIC FORCES", max_width=165)
        if ui.button_at(f"{strategic}/lblTitle", "more", "military.open_strategic",
                        offset=(169.0, 0.0), size=(37.0, 12.0),
                        enabled=is_own and self._open_strategic_cb is not None):
            self._open_strategic_cb()
        ui.text(f"{strategic}/frmNuclearProgress", f"{summary.strategic_ready} / {summary.strategic_total}",
                max_width=96, tooltip=f"{summary.strategic_ready} ready / {summary.strategic_total} total")
        if ui.button(f"{strategic}/btnBuild", "BUILD", "military.open_strategic_build",
                     enabled=is_own and self._open_production_cb is not None):
            self._open_production_cb()
        ui.text(f"{strategic}/lblMissileDefense", "MISSILE DEFENSE")
        ui.text(f"{strategic}/txtMissileDefenseStatus", f"{summary.missile_defense_pct:.0f}%")
        ui.meter(f"{strategic}/frmAmdsProgress/btnUnfilled", summary.missile_defense_pct / 100.0,
                 GAMETHEME.colors.positive, max_width=96)
        if ui.button(f"{strategic}/btnResearch", "RESEARCH", "military.open_missile_research",
                     enabled=is_own and self._open_research_cb is not None):
            self._open_research_cb()
        for slot, label, test_id, callback, allowed in (
            ("btnCovertActions", "COVERT ACTIONS", "military.open_covert", self._open_covert_cb, is_own),
            ("btnStrategicWarfare", "STRATEGIC WARFARE", "military.open_strategic_warfare", self._open_strategic_cb, is_own),
            ("btnWarList", "WAR LIST", "military.open_war_list", self._open_wars_cb, True),
        ):
            if ui.button(slot, label, test_id, enabled=allowed and callback is not None):
                callback()
