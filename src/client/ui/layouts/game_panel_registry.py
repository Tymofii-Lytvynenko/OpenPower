from __future__ import annotations

from imgui_bundle import icons_fontawesome_6

from src.client.ui.components.hud.panel_manager import PanelManager, PanelSpec
from src.client.ui.core.theme import GAMETHEME
from src.client.ui.panels.budget_panel import BudgetPanel
from src.client.ui.panels.data_insp_panel import DataInspectorPanel
from src.client.ui.panels.demographics_panel import DemographicsPanel
from src.client.ui.panels.economic_health_panel import EconomicHealthPanel
from src.client.ui.panels.economy_panel import EconomyPanel
from src.client.ui.panels.military.battle_overview_panel import BattleOverviewPanel
from src.client.ui.panels.military.covert_ops_panel import CovertOpsPanel
from src.client.ui.panels.military.strategic_warfare_panel import StrategicWarfarePanel
from src.client.ui.panels.military.unit_design_panel import UnitDesignPanel
from src.client.ui.panels.military.unit_list_panel import UnitListPanel
from src.client.ui.panels.military.unit_market_panel import UnitMarketPanel
from src.client.ui.panels.military.unit_production_panel import UnitProductionPanel
from src.client.ui.panels.military.unit_research_panel import UnitResearchPanel
from src.client.ui.panels.military.war_list_panel import WarListPanel
from src.client.ui.panels.military_panel import MilitaryPanel
from src.client.ui.panels.politics.constitutional_form_panel import ConstitutionalFormPanel
from src.client.ui.panels.politics.internal_laws_panel import InternalLawsPanel
from src.client.ui.panels.politics.treaties_panel import TreatiesPanel
from src.client.ui.panels.politics.treaty_editor_panel import TreatyEditorPanel
from src.client.ui.panels.politics_panel import PoliticsPanel
from src.client.ui.panels.region_inspector import RegionInspectorPanel
from src.client.ui.panels.resources_panel import ResourcesPanel
from src.client.ui.panels.service.console_panel import ConsolePanel
from src.client.ui.panels.service.mail_panel import MailPanel
from src.client.ui.panels.service.news_panel import NewsPanel
from src.client.ui.panels.service.objectives_panel import ObjectivesPanel
from src.client.ui.panels.service.tooltip_help_panel import TooltipHelpPanel
from src.client.ui.panels.trade_panel import TradePanel


def build_game_panel_specs(panel_manager: PanelManager) -> list[PanelSpec]:
    """Builds the declarative panel registry for the in-game HUD."""

    def open_panel(panel_id: str) -> None:
        panel_manager.set_visible(panel_id, True)

    return [
        PanelSpec(
            id="POL",
            title="Politics",
            category="politics",
            factory=lambda: PoliticsPanel(
                open_constitution_cb=lambda: open_panel("CONSTITUTIONAL_FORM"),
                open_laws_cb=lambda: open_panel("INTERNAL_LAWS"),
                open_treaties_cb=lambda: open_panel("TREATIES"),
            ),
            icon=icons_fontawesome_6.ICON_FA_BUILDING_COLUMNS,
            color=GAMETHEME.colors.politics,
        ),
        PanelSpec(
            id="MIL",
            title="Military",
            category="military",
            factory=lambda: MilitaryPanel(
                open_unit_list_cb=lambda: open_panel("UNIT_LIST"),
                open_production_cb=lambda: open_panel("UNIT_PRODUCTION"),
                open_research_cb=lambda: open_panel("UNIT_RESEARCH"),
                open_design_cb=lambda: open_panel("UNIT_DESIGN"),
                open_market_cb=lambda: open_panel("UNIT_MARKET"),
                open_covert_cb=lambda: open_panel("COVERT_OPS"),
                open_wars_cb=lambda: open_panel("WAR_LIST"),
                open_battle_cb=lambda: open_panel("BATTLE_OVERVIEW"),
                open_strategic_cb=lambda: open_panel("STRATEGIC_WARFARE"),
            ),
            icon=icons_fontawesome_6.ICON_FA_PERSON_MILITARY_RIFLE,
            color=GAMETHEME.colors.military,
        ),
        PanelSpec(
            id="ECO",
            title="Economy",
            category="economy",
            factory=lambda: EconomyPanel(
                toggle_resources_cb=lambda: open_panel("RESOURCES"),
                toggle_budget_cb=lambda: open_panel("BUDGET"),
                toggle_health_cb=lambda: open_panel("ECONOMIC_HEALTH"),
                toggle_trade_cb=lambda: open_panel("TRADE"),
            ),
            icon=icons_fontawesome_6.ICON_FA_SACK_DOLLAR,
            color=GAMETHEME.colors.economy,
        ),
        PanelSpec(
            id="DEM",
            title="Demographics",
            category="society",
            factory=DemographicsPanel,
            icon=icons_fontawesome_6.ICON_FA_PEOPLE_GROUP,
            color=GAMETHEME.colors.demographics,
        ),
        PanelSpec(
            id="CONSTITUTIONAL_FORM",
            title="Constitutional Form",
            category="politics",
            factory=ConstitutionalFormPanel,
            show_in_toggle_bar=False,
        ),
        PanelSpec(
            id="INTERNAL_LAWS",
            title="Internal Laws",
            category="politics",
            factory=InternalLawsPanel,
            show_in_toggle_bar=False,
        ),
        PanelSpec(
            id="TREATIES",
            title="Treaties",
            category="politics",
            factory=lambda: TreatiesPanel(open_editor_cb=lambda: open_panel("NEW_TREATY")),
            show_in_toggle_bar=False,
        ),
        PanelSpec(
            id="NEW_TREATY",
            title="New Treaty",
            category="politics",
            factory=TreatyEditorPanel,
            show_in_toggle_bar=False,
        ),
        PanelSpec(
            id="UNIT_LIST",
            title="Unit List",
            category="military",
            factory=UnitListPanel,
            show_in_toggle_bar=False,
        ),
        PanelSpec(
            id="UNIT_PRODUCTION",
            title="Unit Production",
            category="military",
            factory=UnitProductionPanel,
            show_in_toggle_bar=False,
        ),
        PanelSpec(
            id="UNIT_RESEARCH",
            title="Unit Research",
            category="military",
            factory=UnitResearchPanel,
            show_in_toggle_bar=False,
        ),
        PanelSpec(
            id="UNIT_DESIGN",
            title="Unit Design",
            category="military",
            factory=UnitDesignPanel,
            show_in_toggle_bar=False,
        ),
        PanelSpec(
            id="UNIT_MARKET",
            title="Unit Market",
            category="military",
            factory=UnitMarketPanel,
            show_in_toggle_bar=False,
        ),
        PanelSpec(
            id="COVERT_OPS",
            title="Covert Ops",
            category="military",
            factory=CovertOpsPanel,
            show_in_toggle_bar=False,
        ),
        PanelSpec(
            id="WAR_LIST",
            title="War List",
            category="military",
            factory=WarListPanel,
            show_in_toggle_bar=False,
        ),
        PanelSpec(
            id="BATTLE_OVERVIEW",
            title="Battle Overview",
            category="military",
            factory=BattleOverviewPanel,
            show_in_toggle_bar=False,
        ),
        PanelSpec(
            id="STRATEGIC_WARFARE",
            title="Strategic Warfare",
            category="military",
            factory=StrategicWarfarePanel,
            show_in_toggle_bar=False,
        ),
        PanelSpec(
            id="INSPECTOR",
            title="Inspector",
            category="tools",
            factory=RegionInspectorPanel,
            show_in_toggle_bar=False,
        ),
        PanelSpec(
            id="DATA_INSPECTOR",
            title="Data Inspector",
            category="tools",
            factory=DataInspectorPanel,
            show_in_toggle_bar=False,
        ),
        PanelSpec(
            id="RESOURCES",
            title="Resources",
            category="economy",
            factory=ResourcesPanel,
            show_in_toggle_bar=False,
        ),
        PanelSpec(
            id="BUDGET",
            title="Budget",
            category="economy",
            factory=BudgetPanel,
            show_in_toggle_bar=False,
        ),
        PanelSpec(
            id="ECONOMIC_HEALTH",
            title="Economic Health",
            category="economy",
            factory=EconomicHealthPanel,
            show_in_toggle_bar=False,
        ),
        PanelSpec(
            id="TRADE",
            title="Trade",
            category="economy",
            factory=TradePanel,
            show_in_toggle_bar=False,
        ),
        PanelSpec(
            id="MAIL",
            title="Mail",
            category="service",
            factory=MailPanel,
            show_in_toggle_bar=False,
        ),
        PanelSpec(
            id="NEWS_LOG",
            title="News Log",
            category="service",
            factory=NewsPanel,
            show_in_toggle_bar=False,
        ),
        PanelSpec(
            id="OBJECTIVES",
            title="Objectives",
            category="service",
            factory=ObjectivesPanel,
            show_in_toggle_bar=False,
        ),
        PanelSpec(
            id="CONSOLE",
            title="Console",
            category="service",
            factory=ConsolePanel,
            show_in_toggle_bar=False,
        ),
        PanelSpec(
            id="TOOLTIP_HELP",
            title="Tooltip Help",
            category="service",
            hotkey="F1",
            factory=TooltipHelpPanel,
            show_in_toggle_bar=False,
        ),
    ]
