from __future__ import annotations

from imgui_bundle import icons_fontawesome_6

from src.client.ui.components.hud.panel_manager import PanelManager, PanelSpec
from src.client.ui.core.theme import GAMETHEME
from src.client.ui.panels.budget_panel import BudgetPanel
from src.client.ui.panels.data_insp_panel import DataInspectorPanel
from src.client.ui.panels.demographics_panel import DemographicsPanel
from src.client.ui.panels.economic_health_panel import EconomicHealthPanel
from src.client.ui.panels.economy_panel import EconomyPanel
from src.client.ui.panels.military_panel import MilitaryPanel
from src.client.ui.panels.politics_panel import PoliticsPanel
from src.client.ui.panels.region_inspector import RegionInspectorPanel
from src.client.ui.panels.resources_panel import ResourcesPanel
from src.client.ui.panels.trade_panel import TradePanel


def build_game_panel_specs(panel_manager: PanelManager) -> list[PanelSpec]:
    """Builds the declarative panel registry for the in-game HUD."""
    return [
        PanelSpec(
            id="POL",
            factory=PoliticsPanel,
            icon=icons_fontawesome_6.ICON_FA_BUILDING_COLUMNS,
            color=GAMETHEME.colors.politics,
        ),
        PanelSpec(
            id="MIL",
            factory=MilitaryPanel,
            icon=icons_fontawesome_6.ICON_FA_PERSON_MILITARY_RIFLE,
            color=GAMETHEME.colors.military,
        ),
        PanelSpec(
            id="ECO",
            factory=lambda: EconomyPanel(
                toggle_resources_cb=lambda: panel_manager.toggle("RESOURCES"),
                toggle_budget_cb=lambda: panel_manager.toggle("BUDGET"),
                toggle_health_cb=lambda: panel_manager.toggle("ECONOMIC_HEALTH"),
                toggle_trade_cb=lambda: panel_manager.toggle("TRADE"),
            ),
            icon=icons_fontawesome_6.ICON_FA_SACK_DOLLAR,
            color=GAMETHEME.colors.economy,
        ),
        PanelSpec(
            id="DEM",
            factory=DemographicsPanel,
            icon=icons_fontawesome_6.ICON_FA_PEOPLE_GROUP,
            color=GAMETHEME.colors.demographics,
        ),
        PanelSpec(
            id="INSPECTOR",
            factory=RegionInspectorPanel,
            show_in_toggle_bar=False,
        ),
        PanelSpec(
            id="DATA_INSPECTOR",
            factory=DataInspectorPanel,
            show_in_toggle_bar=False,
        ),
        PanelSpec(
            id="RESOURCES",
            factory=ResourcesPanel,
            show_in_toggle_bar=False,
        ),
        PanelSpec(
            id="BUDGET",
            factory=BudgetPanel,
            show_in_toggle_bar=False,
        ),
        PanelSpec(
            id="ECONOMIC_HEALTH",
            factory=EconomicHealthPanel,
            show_in_toggle_bar=False,
        ),
        PanelSpec(
            id="TRADE",
            factory=TradePanel,
            show_in_toggle_bar=False,
        ),
    ]
