"""Generate evidence-tagged REFERENCE UI inventories from the supplied local sources."""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from utils.reference_audit_navigation import reachable_windows
from utils.reference_audit_output import write_csv_tables
from utils.reference_paths import resolve_reference_file
from utils.reference_cpp_parser import cpp_functions, find_matching as _find_matching
from utils.reference_gml_validation import _validate_gml, _walk
from utils.reference_source_index import _source_index
from utils.reference_audit_geometry import (
    _layout_geometry_crosswalk as _build_layout_geometry_crosswalk,
    _route_evidence_snapshot,
)

from src.client.ui.components.reference_credit_roster import (
    REFERENCE_CREDIT_SUPPLEMENTAL_TEXT,
    REFERENCE_STEAM_CREDIT_GROUPS,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_REPOSITORY = "docs/ui/reference/source_links.md"
FUNCTIONAL_MATRIX_SUITE_NAMES = (
    "unit-design-create-matrix",
    "covert-create-matrix",
    "covert-train-matrix",
    "covert-mission-matrix",
    "treaty-create-matrix",
    "treaty-details-matrix",
    "resources-close-apply-matrix",
    "budget-close-apply-matrix",
    "resources-close-discard-matrix",
    "budget-remember-discard-matrix",
    "budget-remember-apply-matrix",
    "main-menu-options-matrix",
    "main-menu-credits-matrix",
    "main-menu-credits-close-matrix",
    "politics-close-matrix",
    "military-close-matrix",
    "unit-list-close-matrix",
    "war-list-close-matrix",
    "unit-list-design-details-matrix",
    "unit-production-design-details-matrix",
)
WINDOW_SPECIALS = {
    "Main_Bar", "Event_Log", "Internal_Laws", "Constitutional_Form",
    "Strategic_Warfare", "Unit_Design_New", "Unit_Buy_Used_Window",
    "Trade_Detailed_Window", "Mini_Map", "Country_Profile_Window",
    "Party_Selection_Window", "Main_Menu", "Scenarios_Window",
    "Start_Single_Player",
}
PANEL_ALIASES: dict[str, tuple[str, str]] = {
    "Politic_Window": ("POL", "verified_openpower"),
    "Economic_Window": ("ECO", "verified_openpower"),
    "Military_Window": ("MIL", "verified_openpower"),
    "Budget_Window": ("BUDGET", "verified_openpower"),
    "Economic_Health_Window": ("ECONOMIC_HEALTH", "verified_openpower"),
    "Resources_Window": ("RESOURCES", "verified_openpower"),
    "Increase_Production_Window": ("RESOURCES", "partial"),
    "Constitutional_Form": ("CONSTITUTIONAL_FORM", "partial"),
    "Internal_Laws": ("INTERNAL_LAWS", "verified_openpower"),
    "Treaties_Window": ("TREATIES", "verified_openpower"),
    "Treaty_Details_Window": ("TREATIES", "verified_openpower"),
    "Relations_Window": ("RELATIONS", "verified_openpower"),
    "Covert_Actions_Cell_Creation": ("COVERT_OPS", "verified_openpower"),
    "Covert_Actions_Cell_Training": ("COVERT_OPS", "verified_openpower"),
    "Covert_Actions_New_Mission": ("COVERT_OPS", "verified_openpower"),
    "Add_Remove_Window": ("TREATIES", "verified_openpower"),
    "Advisor_Advise_Window": ("OBJECTIVES", "partial"),
    "Advisor_Window": ("OBJECTIVES", "partial"),
    "Advisor_Settings_Window": ("ADVISOR_SETTINGS", "partial"),
    "Strategic_Warfare": ("STRATEGIC_WARFARE", "partial"),
    "Options_Window": ("SETTINGS", "partial"),
    "Trade_Window": ("TRADE", "partial"),
    "Trade_Detailed_Window": ("TRADE", "partial"),
    "Country_Information_Window": ("COUNTRY_MORE_INFO", "partial"),
    "Unit_Design_New": ("UNIT_DESIGN", "partial"),
    "Unit_New_Design": ("UNIT_DESIGN", "partial"),
    "Unit_List_Window_New": ("UNIT_LIST", "partial"),
    "Unit_Buy_Used_Window": ("UNIT_MARKET", "partial"),
    "Unit_Production_Window": ("UNIT_PRODUCTION", "partial"),
    "Unit_Research_Window": ("UNIT_RESEARCH", "partial"),
    "Unit_Ground_Deployment_Window": ("UNIT_RESERVES", "partial"),
    "Covert_Actions_Window": ("COVERT_OPS", "partial"),
    "War_List_Window": ("WAR_LIST", "partial"),
    "History_Window": ("HISTORY", "partial"),
    "Mail_Window": ("MAIL", "verified_openpower"),
    "Event_Log": ("NEWS_LOG", "verified_openpower"),
    "Objectives_Window": ("OBJECTIVES", "partial"),
}
LAYOUT_SURFACES: dict[str, tuple[str, str]] = {
    "Battle_Overview_Small_Unit_Info": ("BattleOverviewPanel/BattleInspectionWindows", "partial"),
    "Credits_Window": ("ProjectCreditsContent: REFERENCE roster and OpenPower package attribution", "partial"),
    "Connecting_Window": ("MultiplayerConnectionWorkflowUnavailable", "verified_unavailable"),
    "Game_Lobby": ("MultiplayerLobbyWorkflowUnavailable", "verified_unavailable"),
    "Game_Over_Window": ("GameLayout/GameOverDialog + ObjectivesPanel sandbox outcomes", "partial"),
    "History_Marker": ("HistoryPanel/TrendGraphMarker", "partial"),
    "History_Tooltip_Window": ("HistoryPanel/TrendGraphTooltip", "partial"),
    "Host_Multiplayer_Game": ("MainMenuContent/HostMultiplayerGameWindow settings draft", "partial"),
    "Mini_Map": ("GameLayout/MiniMapPanel", "partial"),
    "Country_Profile_Window": ("NewGameView/CountryProfileWindow", "partial"),
    "System_Bar_Window": ("GameLayout/SystemBar", "partial"),
    "Thematic_Map_Legend": ("GameLayout/ThematicMapLegend", "verified_openpower"),
    "Context_Menu": ("GameLayout/ContextMenu", "verified_openpower"),
    "Generic_Question_Window": ("InternalLawsPanel/GenericQuestionDialog", "partial"),
    "Main_Bar": ("GameLayout/CentralBar", "verified_openpower"),
    "Main_Menu": ("MainMenuView", "verified_openpower"),
    "Save_Confirmation_Window": ("DirtyCloseConfirmation", "verified_openpower"),
    "Save_Game_Window": ("GameLayout/SaveGameDialog", "verified_openpower"),
    "Load_Saved_Game": ("GameLayout/SaveGameDialog", "verified_openpower"),
    "Battle_Summary_Window": ("GameLayout/BattleSummaryDialog", "partial"),
    "Battle_Window": ("GameLayout/BattleInspectionWindows", "partial"),
    "Battle_Info_Window": ("GameLayout/BattleInspectionWindows", "verified_openpower"),
    "Small_Unit_Info_Window": ("GameView/MapInformationWindows", "partial"),
    "Sphere_Control_Window": ("GameView/MapInformationWindows", "verified_openpower"),
    "Unit_Attack_Confirm_Window": ("GameLayout/UnitAttackConfirmation", "verified_openpower"),
    "Region_Control_Change_Window": ("GameLayout/TextNotificationDialog", "verified_openpower"),
    "Covert_Actions_Mission_Outcome": ("GameLayout/CovertOutcomeDialog", "partial"),
    "Covert_Actions_Mission_Outcome_Attacked": ("GameLayout/CovertOutcomeDialog", "partial"),
    "Strategic_Target_Country_Window": ("StrategicWarfarePanel/StrategicPlanner", "partial"),
    "Strategic_Target_Multiple_Countries_Window": ("StrategicWarfarePanel/StrategicPlanner", "partial"),
    "Strategic_Missile_List_Window": ("StrategicWarfarePanel/StrategicPlanner", "partial"),
    "Strategic_Select_Target_Window": ("StrategicWarfarePanel/StrategicPlanner", "partial"),
    "Strategic_Launch_Window": ("StrategicWarfarePanel/StrategicPlanner", "partial"),
    "Split_Group_Window": ("GameLayout/UnitReorganizationWindows", "verified_openpower"),
    "Unit_Split_Window": ("GameLayout/UnitReorganizationWindows", "verified_openpower"),
    "Unit_List_Window": ("GameLayout/UnitReorganizationWindows", "partial"),
    "Party_Selection_Window": ("NewGameView/PartySelectionWindow", "verified_openpower"),
    "Scenarios_Window": ("NewGameView/CampaignScenarioSelectionWindow", "partial"),
    "Start_Single_Player": ("NewGameView/SinglePlayerSetupWindow", "partial"),
    "Submenu_Single": ("MainMenuContent/SinglePlayerSubmenu", "verified_openpower"),
    "Submenu_Multi": ("MainMenuContent/MultiplayerSubmenu", "partial"),
    "Join_Multiplayer_Game": ("MainMenuContent/JoinMultiplayerWindow", "partial"),
    "Generic_Input_Window": ("JoinMultiplayerWindow/GenericInputDialog", "partial"),
    "Server_Info_Window": ("JoinMultiplayerWindow/ServerInfoWindow", "partial"),
    "Player_Options_Window": ("UnusedSourceTemplate/NoRuntimeRoute", "verified_unavailable"),
    "Political_Parties_Window": ("UnusedSourceTemplate/NoRuntimeRoute", "verified_unavailable"),
    "Strategic_Alert_Window": ("UnusedSourceTemplate/NoRuntimeRoute", "verified_unavailable"),
    "Strategic_News_Window": ("UnusedSourceTemplate/NoRuntimeRoute", "verified_unavailable"),
    "Tooltip_Window": ("ImGuiTooltip/TutorialGuideContent", "partial"),
    "Tutorial_Arrow_Window": ("GuidedTutorialWindow/TutorialArrowWindow 50x50 vector pointer; source Picture_Normal 783 artwork unavailable", "partial"),
    "Tutorial_Window": ("MainMenuContent/TutorialGuideContent", "partial"),
    "Unit_Movement_Denial": ("GameLayout/UnitOrderFeedback", "partial"),
    "frmBaseWindow": ("RGAPILoginUnavailable/NoOpenPowerAuthenticationRoute", "verified_unavailable"),
    "frmTest": ("REFERENCEDeveloperTestWindow/IntentionallyNotShipped", "verified_unavailable"),
}
INACTIVE_SOURCE_TEMPLATE_WINDOWS = frozenset({
    "Strategic_Alert_Window",
    "Strategic_News_Window",
})
STATE_MACHINE_MENU_ROUTES = (
    {
        "source_window": "Main_Menu",
        "source_widget_path": "Main_Menu/frmInner/btnSingle",
        "target_window": "Submenu_Single",
        "event": "OnMouseClick",
        "context": "disconnected state; in_pCaller == m_pObjSingleBtn",
        "passed_context": "SendEvent(FSM::EEvents::SPMenuBtn) -> GInSubMenuSP::OnEnter -> SubmenuSingle()->Show()",
        "source_file": "Client/Source/reference_main_menu.cpp",
        "source_line": 91,
        "action_source_file": "Client/Source/reference_fsm_disconnected.cpp",
        "action_source_line": 114,
    },
    {
        "source_window": "Main_Menu",
        "source_widget_path": "Main_Menu/frmInner/btnMulti",
        "target_window": "Submenu_Multi",
        "event": "OnMouseClick",
        "context": "disconnected state; in_pCaller == m_pObjMultiBtn",
        "passed_context": "SendEvent(FSM::EEvents::MPMenuBtn) -> GInSubMenuMP::OnEnter -> SubmenuMulti()->Show()",
        "source_file": "Client/Source/reference_main_menu.cpp",
        "source_line": 104,
        "action_source_file": "Client/Source/reference_fsm_disconnected.cpp",
        "action_source_line": 151,
    },
    {
        "source_window": "Join_Multiplayer_Game",
        "source_widget_path": "Join_Multiplayer_Game/frmInner/btnHostInJoinMenu",
        "target_window": "Host_Multiplayer_Game",
        "event": "OnMouseClick",
        "context": "in_pCaller == m_pObjHostBtn",
        "passed_context": (
            "StartMultiplayerGame -> StartMultiplayerBtn -> GInJoinWindow enters "
            "GInHostWindow -> GInHostWindow::OnEnter spawns Host_Multiplayer_Game"
        ),
        "source_file": "Client/Source/reference_join_multiplayer_game_window.cpp",
        "source_line": 121,
        "action_source_file": "Client/Source/reference_fsm_disconnected.cpp",
        "action_source_line": 189,
    },
)
UNIMPLEMENTED_WINDOW_GAPS: dict[str, dict[str, str]] = {}
PARTIALLY_IMPLEMENTED_WINDOW_GAPS: dict[str, dict[str, str]] = {
    "Options_Window": {
        "reason": "MainMenuContent uses the source 462x329 Options_Window frame with GML-positioned Profile, Graphics, and Sound tabs plus an OpenPower extension tab. Profile autosave controls bind to persisted OpenPower settings and the scheduled ActionSaveGame path; unsupported player, AI, audio, renderer, and atlas controls stay unavailable in their GML slots. The admin-only ban-list command stays hidden because OpenPower has no multiplayer admin workflow. Supported OpenPower display, localization, and reduce-motion values remain staged in the extension tab until Confirm; Back and title close discard them.",
        "action_required": "Keep the GML frame and Apply/Cancel draft behavior covered. Preserve the verified autosave settings and save path; keep the remaining REFERENCE-only values unavailable until OpenPower has an authoritative field or matching action.",
        "missing_action": "REFERENCE-only player, AI, audio, renderer, atlas-detail, and multiplayer admin ban-list controls",
        "current_implementation": "MainMenuContent composes REFERENCEOptionsWindowContent inside the 462x329 Options_Window GML canvas: three source-sized tabs, source-slot autosave settings persisted by GameSettingsService and executed by AutosaveScheduler through ActionSaveGame, unsupported source controls explicitly unavailable, a fourth OpenPower extension tab for staged display/language/geography-name/reduce-motion settings, and source-anchored close/Confirm/Cancel controls",
    },
    "Credits_Window": {
        "reason": "MainMenuContent renders the 568x580 Credits_Window GML layout and scrollable ProjectCreditsContent. The 57-entry public Steam Edition roster follows the GML role/name rows: the Art team section uses lblTitle5, and 2D Art, Animation, Modeling, and Textures align with their names. The public credit listing appends (www.multimediarts.net) to Eric Vigneault; it is rendered in GML row lblTitle35/Text 101405 as an inferred continuation. The REFERENCE manual places © GolemLabs 2004 after its credits list, and GML exposes a final full-width row lblTitle91/Text 102121; the footer mapping is inferred pending the reference localization bundle.",
        "action_required": "Keep the source-sized credits frame, corrected role/name alignment, both explicitly inferred supplemental rows, and return path covered. Confirm tokens 101405 and 102121 against the reference localization bundle; retain OpenPower package attribution after the source roster.",
        "missing_action": "Confirm the inferred URL continuation at token 101405/lblTitle35 and copyright footer mapping at token 102121/lblTitle91 against the reference REFERENCE localization bundle",
        "current_implementation": "MainMenuContent/Credits with the 568x580 Credits_Window layout, full local 57-entry public Steam Edition roster aligned to GML role/name rows, an Art team section heading, inferred (www.multimediarts.net) and © GolemLabs 2004 text in GML slots lblTitle35 and lblTitle91, and scrollable OpenPower package attribution",
    },
    "Host_Multiplayer_Game": {
        "reason": "HostMultiplayerGameWindow renders the source 341x342 GML frame and all visible host settings controls. Server name, password, port, player limit, time limit, dedicated-server flag, game speed, nuclear setting, and five objective drafts are editable locally; Cancel returns to the server browser. The source-localized default server name and captions are unavailable. OpenPower has no authoritative multiplayer host service, so Start remains disabled and no setup draft reaches the simulation.",
        "action_required": "Keep the source frame, settings draft, disabled Start state, and return-to-browser route covered. Enable Start only after OpenPower can validate and launch an authoritative multiplayer session; retain the missing source-localized default and labels as explicit gaps.",
        "missing_action": "Authoritative host-server startup, lobby player assignment, and source-localized host captions/default server name",
        "current_implementation": "MainMenuContent/HostMultiplayerGameWindow with the source 341x342 Host_Multiplayer_Game GML slots and local host settings draft",
    },
    "Advisor_Advise_Window": {
        "reason": "OpenPower stores advisor recommendations as campaign state and presents review/acknowledgement through ObjectivesPanel with a source-sized GenericQuestionDialog for decisions. The source advice popup's layout, daily advice stream, and scheduled callback behavior are not equivalent.",
        "action_required": "Keep recommendation listing, accept/decline action results, acknowledgement callbacks, and decision-dialog geometry covered. Add the source advice cadence only if OpenPower exposes matching advisor events and schedule data.",
        "missing_action": "Exact REFERENCE advisor advice popup and scheduled recommendation semantics",
        "current_implementation": "ObjectivesPanel recommendations and GameLayout/GenericQuestionDialog with ActionResolveAdvisorRecommendation",
    },
    "Advisor_Window": {
        "reason": "OpenPower exposes campaign objectives, AI priorities, and delegated scopes in ObjectivesPanel, with advisor preferences in AdvisorSettingsPanel. The source Advisor_Window plan builder and its staged plan-part editor have no one-to-one OpenPower plan model.",
        "action_required": "Keep advisor recommendation review and supported sphere-delegation actions covered. Add staged advisor plan parts only when OpenPower defines an equivalent plan model and authoritative actions.",
        "missing_action": "Source Advisor_Window plan-part builder and exact localized advice flow",
        "current_implementation": "ObjectivesPanel/Advisor priorities and delegation controls; AdvisorSettingsPanel preferences",
    },
    "Battle_Summary_Window": {
        "reason": "BattleSummaryDialog now follows the 283x306 source frame, with defender countries and outcomes on pane A, attackers on pane B, and per-category casualty slots. OpenPower's casualty records count personnel; they are not the source engine's abstract category-loss totals, and category values remain unavailable when no detailed records exist.",
        "action_required": "Keep source pane ordering, flag/code country rows, outcome mapping, and category-slot binding covered. Show an em dash when category casualty records are unavailable; do not substitute an aggregate battle total for infantry or infer missing categories.",
        "missing_action": "Exact REFERENCE battle-category loss accounting and source localization",
        "current_implementation": "GameLayout/BattleSummaryDialog with source-order defender/attacker panes, GML-sized flag/code lists, and OpenPower personnel casualties grouped by unit category",
    },
    "Battle_Overview_Small_Unit_Info": {
        "reason": "OpenPower battle overview and inspection surfaces report the battle groups, observed force categories, and command state supported by current battle records. The source's compact per-unit roster window and source-specific unit breakdowns do not have a direct data contract.",
        "action_required": "Keep supported battle summaries, observed counts, and inspection actions covered. Show unavailable data explicitly when the battle snapshot does not include per-unit composition.",
        "missing_action": "Exact compact battle unit roster and unavailable source force breakdowns",
        "current_implementation": "BattleOverviewPanel and GameLayout/BattleInspectionWindows",
    },
    "Game_Over_Window": {
        "reason": "GameLayout/GameOverDialog presents terminal non-sandbox campaign outcomes from OpenPower campaign state and returns to the main menu through the existing local stop-game lifecycle. Ongoing and sandbox campaigns remain in ObjectivesPanel. REFERENCE ranking formulas, localized result copy, and exact deadline presentation have no matching OpenPower contract.",
        "action_required": "Keep the conditional result dialog, source-sized layout, terminal objective list, title-close route, and Main Menu route scenario-covered. Preserve sandbox continuation in ObjectivesPanel; add source-only ranking or deadline semantics only when OpenPower has matching data.",
        "missing_action": "Exact REFERENCE ranking/result formulas, localized result copy, and source deadline presentation",
        "current_implementation": "GameLayout/GameOverDialog for terminal non-sandbox outcomes; ObjectivesPanel for ongoing and sandbox outcomes",
    },
    "History_Marker": {
        "reason": "HistoryPanel plots persisted OpenPower observations and draws per-sample trend markers. Its series, subject, and time-range controls use the source History_Window layout, but marker filtering and source localization differ.",
        "action_required": "Keep historical series selection, trend marker rendering, and chart bounds covered; add source marker semantics only where OpenPower stores matching observations.",
        "missing_action": "Exact REFERENCE history marker display filters and localization",
        "current_implementation": "HistoryPanel GML-bound trend graph markers",
    },
    "History_Tooltip_Window": {
        "reason": "HistoryPanel provides hover tooltips for indicator values, chart limits, and trend context. The transient source marker-info window does not share an exact tooltip data or localization contract.",
        "action_required": "Keep chart hover values tied to the selected OpenPower series and show no fabricated values for missing samples.",
        "missing_action": "Source marker tooltip layout and localized historical fields",
        "current_implementation": "HistoryPanel hover tooltips over OpenPower trend data",
    },
    "Tooltip_Window": {
        "reason": "OpenPower uses native ImGui hover tooltips throughout the panels and an OpenPower-authored tutorial guide for the tutorial entry. The source transient Tooltip_Window is dynamically resized and repositioned by tutorial code; it is not a separate persistent OpenPower panel.",
        "action_required": "Keep hover help attached to its owning control and retain the tested OpenPower guide. Recreate the transient source frame only with an equivalent tutorial runtime.",
        "missing_action": "Exact transient REFERENCE tooltip frame and scripted tutorial positioning",
        "current_implementation": "Shared ImGui hover tooltips and MainMenuContent/TutorialGuideContent",
    },
    "Tutorial_Window": {
        "reason": "The two tutorial entries show tested OpenPower interface and military guides. They do not implement the source tutorial state machine, scenario-specific progression, or event-gated lessons.",
        "action_required": "Keep both guide routes and their navigation covered; add source progression only when OpenPower has the corresponding tutorial game type and scripted events.",
        "missing_action": "REFERENCE tutorial scenario, progression state machine, and event-gated lesson behavior",
        "current_implementation": "MainMenuContent/TutorialGuideContent with interface and military guides",
    },
    "Tutorial_Arrow_Window": {
        "reason": "GuidedTutorialWindow now uses a source-sized 50x50 TutorialArrowWindow that targets live interface and military controls. The supplied workspace does not include the source Picture_Normal 783 sprite, so Python draws a vector arrow.",
        "action_required": "Use the reference Picture_Normal 783 artwork if its atlas becomes available; keep current-frame target geometry, foreground ordering, and guide-close visibility covered.",
        "missing_action": "reference REFERENCE Tutorial_Arrow_Window sprite artwork",
        "current_implementation": "GuidedTutorialWindow/TutorialArrowWindow with a 50x50 foreground vector pointer",
    },
    "Unit_Movement_Denial": {
        "reason": "OpenPower reports rejected movement through UnitOrderFeedback and the GML-sized GenericMessageDialog, including the unit count and authoritative denial reason. The source's separate denial-list window and per-unit list are represented as aggregated feedback.",
        "action_required": "Keep refusal reasons tied to authoritative unit-order results and retain the tested dismissal route. Add per-unit rows only when the server returns stable denied-unit identities.",
        "missing_action": "Per-unit movement-denial list and source-specific message layout",
        "current_implementation": "GameLayout/UnitOrderFeedback to GenericMessageDialog",
    },
    "Objectives_Window": {
        "reason": "ObjectivesPanel now uses the exact 354x336 Objectives_Window GML root and presents OpenPower campaign outcomes, objective records, advisor priorities, recommendation review/acknowledgement, and delegation controls. The source objective rows, progress formulas, localization, and end-of-game presentation do not map one-to-one to OpenPower campaign state.",
        "action_required": "Keep the 354x336 GML window geometry, F5/SystemBar entry, objective data, advisor recommendation actions, and viewport containment covered. Add source-only progress or end-game behavior only when matching OpenPower state and lifecycle events exist.",
        "missing_action": "Exact REFERENCE objective progress formulas, source localization, and automatic end-game workflow",
        "current_implementation": "PanelSpec/OBJECTIVES with the 354x336 Objectives_Window GML frame, OpenPower campaign objectives and advisor review actions",
    },
    "Strategic_Warfare": {
        "reason": "The Python StrategicWarfarePanel now uses the exact 274x362 Strategic_Warfare GML root and retains OpenPower's strategic inventory, missile-defense summaries, production, strike history, and target planner. The source window's compact country/attack-type/strength controls and launch workflow do not map one-to-one to OpenPower's authorization, payload-profile, target-defense, and guarded launch model.",
        "action_required": "Keep the 274x362 GML window geometry, source title frame, OpenPower planner route, authoritative strategic actions, and viewport containment covered. Preserve OpenPower authorization and launch validation; only add source controls when they have a supported OpenPower contract.",
        "missing_action": "Exact REFERENCE strategic country/attack-strength form and source localization/artwork",
        "current_implementation": "PanelSpec/STRATEGIC_WARFARE with the 274x362 Strategic_Warfare GML window and OpenPower strategic inventory/planner",
    },
    "Trade_Window": {
        "reason": "TradePanel uses the exact 630x245 Trade_Window GML frame for its offer-list page, then switches to the existing source-sized Trade_Detailed_Window for the bilateral OpenPower proposal editor and deal lifecycle. OpenPower creates, responds to, counteroffers, and withdraws trade deals through its authoritative action model; the supplied source mirror has no caller for GTradeWindow's list window.",
        "action_required": "Keep the GML-sized offers page and detailed editor transition covered together with create, accept, reject, counteroffer, and withdraw journeys. Preserve the OpenPower trade-deal action model where the source workflow has no mapped caller or equivalent valuation contract.",
        "missing_action": "Exact REFERENCE trade-list callback and source trade valuation/localization semantics",
        "current_implementation": "PanelSpec/TRADE with the 630x245 Trade_Window offers page and GML-bound Trade_Detailed_Window editor",
    },
    "Country_Profile_Window": {
        "reason": "NewGameView.CountryProfileWindow uses the 271x359 GML layout in the singleplayer setup route. It presents the OpenPower desired profile choices and ranked country suggestions using current OpenPower GDP, government approval, and military personnel, then updates the parent setup selection on confirm. The separate REFERENCE lobby profile route depends on RGAPI server state, which OpenPower does not currently provide.",
        "action_required": "Keep the singleplayer profile open, recommendation, confirm, and cancel route covered. Preserve the lobby route as unsupported until OpenPower has a multiplayer lobby and authoritative country-profile workflow.",
        "missing_action": "REFERENCE multiplayer lobby country-profile workflow and exact source scoring/localization",
        "current_implementation": "NewGameView/CountryProfileWindow with the 271x359 Country_Profile_Window GML layout and OpenPower country metrics",
    },
    "Mini_Map": {
        "reason": "GameLayout.MiniMapPanel follows the 228x155 GML root at the bottom-right viewport edge. Its map raster uses OpenPower's packed region map and active map-mode colors, draws the live camera center, and binds the source home, magnifier, map, and zoom-track slots. Map clicks recenter the globe or planar viewport, Home focuses the controlled country, the magnifier toggles global unit display, and the zoom track updates the active camera. The source realistic/strategic frame assets and exact Earth mini-map rendering are not available in OpenPower; the Python panel renders a compact region-color map instead.",
        "action_required": "Keep the 228x155 GML anchor, source control geometry, camera focus, Home, unit-display toggle, and zoom mapping covered at compact and wide viewports. Replace the compact region raster with source-equivalent map art only when matching OpenPower-renderable assets or rendering data are available.",
        "missing_action": "REFERENCE realistic/strategic map frame art and exact background Earth rendering",
        "current_implementation": "GameLayout/MiniMapPanel with the 228x155 Mini_Map GML layout, bottom-right anchoring, OpenPower region raster, viewport focus/zoom, Home, and unit-display toggle",
    },
    "Scenarios_Window": {
        "reason": "CampaignScenarioSelectionWindow uses the exact 560x354 GML root and source slots for the custom campaign list, scenario metadata, detail tabs, and Start/Cancel controls. Scenario availability, country allowlists, descriptions, objectives, duration, sandbox continuation and enabled rules come from OpenPower campaign_scenarios. The REFERENCE Politics/Economy/Military difficulty presets have no equivalent OpenPower setting and remain explicitly marked N/A. The Continue action leads into OpenPower's country/party setup stage before the authoritative campaign action.",
        "action_required": "Keep scenario list, detail tabs, GML geometry, and cancel/continue navigation covered. Add an REFERENCE difficulty preset only if an authoritative OpenPower rules model is introduced; preserve the two-stage selection because OpenPower requires a country and player party before campaign start.",
        "missing_action": "REFERENCE sphere difficulty presets and source localization/artwork",
        "current_implementation": "CampaignScenarioSelectionWindow with the 560x354 Scenarios_Window layout and OpenPower scenario metadata",
    },
    "Start_Single_Player": {
        "reason": "SinglePlayerSetupWindow uses the exact 346x341 GML root and source country combo, profile, party, control, objective, and Start slots. Country eligibility, party options, scenario rules and fixed objectives use OpenPower state; selecting a country defaults to its ruling party, and campaign start remains guarded until a country is chosen. OpenPower does not expose separate human/computer sphere assignments or editable REFERENCE objective goals, so control cells identify the OpenPower mapping and objectives remain scenario-defined.",
        "action_required": "Keep country/profile/party navigation, fixed scenario objective display, start guard, and GML slot geometry covered. Add editable sphere control or objective choices only when OpenPower exposes matching rules and authoritative actions.",
        "missing_action": "REFERENCE human/computer sphere assignments and editable objective-goal semantics",
        "current_implementation": "SinglePlayerSetupWindow with the 346x341 Start_Single_Player layout, OpenPower country/profile/party data and ActionStartCampaign route",
    },
    "System_Bar_Window": {
        "reason": "SystemBar uses the exact 577x38 GML root at the upper-right viewport edge, including the source 22x23 toggle and six 28x18 shortcut buttons with separate 57x15 labels. F3/F4/F5/F10 reach OpenPower save, load, objectives, and a resumable in-game menu overlay. The F10 overlay uses the active-game 273x223 Main_Menu geometry and source runtime button positions; the disconnected menu retains its separate 273x196 geometry. The main toggle reproduces the source 0.26-second delay and 0.5-second linear slide between full and collapsed positions. F1 opens expanded OpenPower-authored HUD help while the source button only displays its tooltip text; F2 remains disabled because OpenPower has no multiplayer lobby workflow. Source texture IDs and localized caption tokens are unavailable, so the frame and keycaps use OpenPower styling and captions remain English. OpenPower mail/news/history stay on the central bar, F9 console and F6 history remain keyboard shortcuts, and Settings remains in the main menu.",
        "action_required": "Keep the F10 overlay runtime geometry and GML shortcut slot journey passing at all supported viewports. Implement F2 only with an authoritative multiplayer lobby workflow; restore source tooltip, texture, and localization parity only when their behavior/resources are available.",
        "missing_action": "Multiplayer lobby workflow, source tooltip content, source frame/keycap artwork, and localization resources",
        "current_implementation": "SystemBar with the 577x38 System_Bar_Window GML layout, right-edge collapsed toggle, OpenPower shortcut callbacks, and resumable in-game menu overlay",
    },
    "Constitutional_Form": {
        "reason": "ConstitutionalFormPanel follows the 352x153 GML frame and source-anchored form, capital, election, martial-law, and title controls. Its inherited GBaseWindow::OnCreate hides togLockWindow and moves btnApply into that title slot; the Python panel preserves both source runtime behaviors. Domestic capital changes use ActionSetCountryCapital with authoritative country, stale-state, and regional-control checks. The form selector stages compatible OpenPower government rules and dispatches ActionSetGovernmentForm; the server validates control, expected form, political-crisis state, party-count limits, and election rules, then updates elections, dependent schedules, history, and the domain event. Martial-law toggles are staged with constitutional drafts and applied through ActionSetGovernmentForm with stale-state checks, history, and a domain event. Leaving a military form clears stored martial law on legacy form-only requests. The source btnOverride callback stages the military-led state for supported multi-party/single-party democratic forms; OpenPower keeps this domestic-only and regular Apply submits it through ActionSetGovernmentForm. Foreign form changes are available only for a non-hostile country when at least 75% of its political regions are controlled by the player; Apply requires GenericQuestionDialog confirmation. OpenPower uses the region-count share as its authoritative native proxy because the published REFERENCE repository omits the proportion calculation. The confirmed server transaction releases that country's occupied regions, grants military access, and sets bilateral relations to 100. Foreign capital, override, and martial-law controls remain disabled, matching the source window's foreign-target restrictions. The numeric REFERENCE government-type catalog is not mapped one-to-one, the exact REFERENCE gained-proportion formula is unavailable, and broader source-specific martial-law effects remain unresolved.",
        "action_required": "Keep the domestic and qualified non-hostile foreign-form journeys passing, including the 75% boundary, confirmation, released regions, access treaty and relations. Define the remaining source government-type mapping and broader martial-law effects; retain the region-count formula as a documented OpenPower proxy, not an exact REFERENCE calculation.",
        "missing_action": "Source government-type mapping, broader martial-law effects, exact REFERENCE gained-proportion calculation, and unavailable city-level capital semantics",
        "current_implementation": "ConstitutionalFormPanel with GMLWidgets slots, inherited titlebar runtime positioning, domestic capital/martial-law/override controls, qualified confirmed foreign-form change with region release/access effects, DirtyCloseConfirmation, ActionSetGovernmentForm, and ActionSetCountryCapital",
    },
    "Country_Information_Window": {
        "reason": "The 519x431 Python panel uses source GML frames and slot coordinates, reads OpenPower country HDI/infrastructure/telecom and regional population/area, and marks missing land-cover, climate, water/total-area, birth/death-rate values unavailable. Source C++ confirms the world comparator is not an average of country HDI: GDataControlLayer::AverageHumanDevelopment aggregates life expectancy, mean/expected schooling and GDP per capita, then applies GCountryData::FindHumanDevelopment. OpenPower lacks the birth-rate and schooling inputs, so the prior unweighted mean was removed and the panel now shows World: — with an explanation; the adjacent source meter remains empty. The Country Information journey passes at 800x600, 1024x768, 1280x720 and 1920x1080, with 4 reviewed screenshots and 0 geometry errors. The country map journey separately confirms all 27 Ukraine regions across those viewports. Source code sets the selected country title and closes on btnExit; it hides btnApply and togLockWindow during creation, matching Python titlebar close behavior.",
        "action_required": "Keep world HDI unavailable until authoritative source inputs or a world aggregate are added; resolve the source localization token and keep source-only metrics unavailable until OpenPower equivalents exist.",
        "missing_action": "Authoritative world-HDI input data, localized caption parity, and OpenPower equivalents for source-only country metrics",
        "current_implementation": "CountryMoreInfoPanel with GMLWidgets slots, CountryMoreInfoPresenter and CountryRegionMapTextureCache",
    },
    "History_Window": {
        "reason": "The Python History panel uses the exact 530x311 GML frame, source-positioned indicator combo, and 405x166 graph with the six source time ticks and vertical min/max slots. The C++ source hides togLockWindow, btnApply, and the four range controls during initialization; Python hides the lock and omits the four hidden range controls from their GML slots. Their OpenPower-specific period filter remains available in the supplemental analytics popup, which still uses btnApply as its local entry point. All seventeen source metric slots have OpenPower-backed series in source enum order with source-style English labels. HistorySystem records gvt_corruption directly, derives budget balance from total_annual_revenue minus total_annual_expense, derives Overall Relations only when the directed country-relation matrix is complete, sums non-strategic unit strength for Conventional Forces, sums strategic weapon quantity for Strategic Forces, uses the annual expense_military_upkeep budget value for Upkeep, sums research track levels for Research, and sums complete valued resource_ledger balances for Resource Balance. These are OpenPower's native formulas and units, not claims of identical REFERENCE simulation outputs. Source fingerprints cause changed inputs to produce new samples. The source's initial Population selection maps to OpenPower's country.population series when present, with a deterministic first-enabled fallback otherwise. The 52-step fixture journey verifies all five previously unmapped measures, their values and screenshots, the Population default, GDP fallback/data gap, absence of source-hidden controls, the popup period selector, analytics, and panel geometry. Source localization strings remain unavailable.",
        "action_required": "Keep all seventeen source metric slots, OpenPower-native units/formulas, and source enum order covered. Keep the four source-hidden range slots absent and test the supplemental period filter only within analytics; retain the exact-source-localization limitation.",
        "missing_action": "Exact source localization bundle and numeric parity with REFERENCE's game-specific force, upkeep, research, and resource formulas",
        "current_implementation": "HistoryPanel with HistoryQueryService, GMLWidgets source slots, OpenPower history snapshots and a supplemental analytics popup",
    },
    "Trade_Detailed_Window": {
        "reason": "TradePanel now uses the exact 648x423 GML frame, centered in the available viewport, with source title controls, the inherited hidden-lock/Apply relocation behavior, bilateral country slots, vertical/horizontal dividers, source asset inputs, 289x147 draft lists, balance slots and footer actions. Numeric GML edits use their declared input kind, so cash fields stay in the source rectangles instead of falling back to ImGui flow. Cash, region and transferable research assets are added to a local draft and sent through guarded OpenPower trade actions; the offers/history view remains an OpenPower supplemental page. REFERENCE military-unit trade and its evaluation/price semantics do not have authoritative OpenPower equivalents.",
        "action_required": "Keep the source geometry and bilateral action journey passing; preserve explicit unavailable states for unit-transfer assets and source evaluation values until OpenPower publishes authoritative equivalents.",
        "missing_action": "Authoritative military-unit trade assets and source-equivalent trade valuation/evaluation",
        "current_implementation": "TradePanel with GMLWidgets source slots, bilateral cash/region/research drafts and BilateralTradeSystem actions",
    },
    "War_List_Window": {
        "reason": "WarListPanel uses the exact 543x296 GML frame and source slots for the active-war list, both participant lists, leader flags/statuses, and source join/peace/war buttons. The inherited base window hides togLockWindow and moves title Apply to that slot before the derived window hides it; OpenPower preserves this geometry for its supplemental peace-package page without showing a lock control. Its English column captions now follow the GML token roles: Country, Allies (from the txtNbAllies row fields), Status, and vs.; ally counts exclude the separately displayed coalition leader. The 18-step fixture journey checks source button rectangles, ActionJoinWar and ActionOfferPeace dispatch, the supplemental peace-package page, and close behavior at 1280x720 and 800x600. DiplomacySystem rechecks country authority, active war membership, target side, and duplicate membership before accepting a join. The reference status-icon artwork and source localization bundles are not present in this repository, so the panel retains semantic status markers and English captions.",
        "action_required": "Keep the source frame geometry, ally counts and authoritative war-list actions passing; map the reference status artwork and non-English text only when the corresponding source resources are available.",
        "missing_action": "reference war-status icon artwork and non-English localization resources",
        "current_implementation": "WarListPanel with GMLWidgets source slots, guarded war membership and intent actions, and a supplemental PeaceDealEditor",
    },
    "Unit_Design_New": {
        "reason": "The source 324x414 GDesignWindow is implemented with role/design selectors, description, cost, source-sized Unit View/Statistics tabs, read-only capability meters, source close, and the source New Design control. The Unit View and Statistics selectors use the 101x16 bottom GTabbed strip; the Statistics rows use the source frmList/scrList viewport and keep the OpenPower values clipped to that list. Its inherited base window hides togLockWindow and relocates btnApply into that slot before GDesignWindow hides Apply; Python omits both controls. It opens the separate 666x618 Unit_New_Design builder. The 16-step tab/scroll journey passes at 800x600, 1024x768, 1280x720, and 1920x1080 with zero geometry findings; detail-selection routes and the 12-step create plus 19-step rejected-create feedback journeys pass. The shared unit_type_options catalog preserves all 20 REFERENCE type IDs and their source order while mapping them to OpenPower roles; Missile Defense remains an explicitly labeled OpenPower extension. Source localization strings and matching 3D model assets are unavailable.",
        "action_required": "Keep the source type-ID/role mapping, tab strip, clipped statistics list, overview/detail routes, and hidden Apply state covered; retain explicit localization and model-asset limitations.",
        "missing_action": "Source unit-type localization strings and 3D model assets",
        "current_implementation": "UnitDesignPanel with the 324x414 GDesignWindow, source Unit View/Statistics tabs, clipped OpenPower statistics, design selection, and navigation to the builder",
    },
    "Unit_New_Design": {
        "reason": "The source 666x618 GCreateDesignWindow is implemented as the separate builder with the shared unit_type_options catalog in the source cboUnitType slot, a distinct disabled model-piece cboType slot, source name/cost slots, twelve adjustable OpenPower-bounded capability meters, and Confirm/Cancel actions. The catalog retains 20 REFERENCE IDs/order mapped to canonical OpenPower roles and appends Missile Defense as an explicitly labeled OpenPower extension. The source model/part/texture controls remain in their GML positions and disabled with unavailable explanations. Capability values use ActionCreateUnitDesign; an authoritative design row closes the builder, while rejected creation retains the draft and opens Generic_Message_Window. The create/acceptance and rejection journeys pass with zero geometry findings. Source localization strings, research-derived meter ceilings, cost calculation, and visual model/part/texture assets remain unavailable or non-equivalent.",
        "action_required": "Keep the bounded capability values and create action tied to OpenPower state; retain explicit unavailable states for source research limits and visual assets, and do not imply that manually entered cost uses the REFERENCE meter formula.",
        "missing_action": "Localized source type labels, research-based meter ceilings, cost formula, and visual model/part/texture assets",
        "current_implementation": "UnitDesignEditor with the 666x618 GCreateDesignWindow, source action slots, role profile, and ActionCreateUnitDesign",
    },
    "Unit_Research_Window": {
        "reason": "UnitResearchPanel uses the 607x455 GML frame, four source-positioned categories and funding meters, the right-side research summary, three 101x17 GTabbed selectors, and the 12-row detail layouts. The inherited base window hides togLockWindow and moves the visible title Apply button into that slot, which the Python GML session reproduces; it does not display a lock control. Funding edits stay in a local branch draft; the GML-sized Apply button commits only changed branches through ActionUpdateResearchFunding, and a dirty close opens the shared Apply/Discard dialog. The 24-step Apply journey and separate close-Apply/close-Discard journeys pass at 800x600, 1024x768, 1280x720 and 1920x1080 with zero layout findings. Strategic detail rows expose strategic_program, strategic_weapons and strategic_defense. Per-characteristic technology ceilings/progress/funding and 3D unit models are unavailable; OpenPower's independent branch ratios do not reproduce REFERENCE's linked-budget redistribution.",
        "action_required": "Keep the GML frame, draft staging, Apply/Discard close behavior, tab/category navigation and branch actions covered. Preserve N/A for absent per-characteristic data and explicit strategic branch mapping; only implement linked-budget redistribution when OpenPower has authoritative shared-budget rules.",
        "missing_action": "Per-characteristic research data, source linked-budget redistribution semantics, and 3D model assets",
        "current_implementation": "UnitResearchPanel with GMLWidgets source slots, branch funding drafts, dirty-close confirmation, strategic subtracks, and ActionUpdateResearchFunding",
    },
    "Unit_Buy_Used_Window": {
        "reason": "UnitMarketPanel reproduces the 712x472 GUsedUnitWindow with its source type selector, listing list, provider and price fields, quantity control, Buy action, design name and clipped capability view. The shared unit_type_options catalog retains the 20 REFERENCE type IDs and source order mapped to OpenPower roles, then preserves Missile Defense as an explicitly labeled OpenPower extension; the market only offers types present in the selected eligible-listing snapshot. Purchase and empty-market journeys pass with zero layout findings. OpenPower applies the same 0.75 used-unit factor when the seller creates a default listing; seller-provided prices remain authoritative under the OpenPower market model. Buy sends ActionBuyMarketUnit, whose server handler rechecks authority, listing status/quantity, demilitarization, trade permission, funds and transfer route. Remaining differences are source localization strings, cost basis (OpenPower's stored reference cost can differ from REFERENCE design cost), separate OpenPower speed/maneuverability versus the source combined meter, the source 0-10 meter scale, and unavailable 3D model assets. Python quantity stepping follows the source 1/10/100 hold thresholds and accelerated cadence, clamped to the OpenPower listing quantity.",
        "action_required": "Keep the source type-ID/role mapping, geometry, quantity hold behavior, 0.75 default resale factor, seller-set price display, and guarded purchase action covered; retain localization, 3D preview, and non-equivalent meter gaps.",
        "missing_action": "Source type localization, exact source cost basis, source meter scale/combined speed mapping, and 3D model assets",
        "current_implementation": "UnitMarketPanel with GMLWidgets source slots, OpenPower listings and capability values, and ActionBuyMarketUnit",
    },
    "Unit_Production_Window": {
        "reason": "UnitProductionPanel reproduces the source 842x462 window, category filters, builder selector, design tree and detail slots, quantity/priority controls, production queue row geometry, and foreign-order and deployment routes. Quantity arrows use the shared 1/10/100 source hold thresholds and accelerated cadence; the Python field retains its 0..1,000,000 bound because OpenPower does not publish the recruitable-manpower value used for REFERENCE's infantry-specific maximum. The domestic UI and authoritative action handler enforce REFERENCE's 50-row production queue limit, and the handler rejects quantities above the UI's 1,000,000 bound. Domestic orders, queue priority/pause/cancel, seller acceptance, foreign requests/contracts, and deployment dispatch/split are verified through fixture-backed journeys. Domestic new-order ETA now previews the exact provisional priority rule shared with ActionQueueUnitProduction; capacity allocation recalculates that value during simulation. The infantry slot displays OpenPower working-age population from regions.pop_15_64 or countries.total_core_manpower, labeled POP. 15-64; this is not recruitable manpower and does not cap orders. Foreign-order ETA stays N/A until the seller accepts. The source Fast option remains disabled because ActionQueueUnitProduction has no speed field and the supplied reference does not include the fast-production cost multiplier.",
        "action_required": "Keep ETA and queue submission on the shared production policy; preserve the explicitly labeled 15-64 population metric without treating it as an enlistment allowance; keep Fast disabled until OpenPower has authoritative speed and cost rules.",
        "missing_action": "REFERENCE Fast speed and cost semantics, recruitable infantry manpower and quantity cap, and exact localized unit-category labels",
        "current_implementation": "UnitProductionPanel with GMLWidgets slots, lstUnitProductionItem GML rows, MilitaryPresenter data projections, and guarded OpenPower production/foreign-order/deployment actions",
    },
    "Unit_Ground_Deployment_Window": {
        "reason": "UnitReservesPanel uses the source 507x390 frame, four category-specific GML list pages, the source lstUnitDeployItem row template, count slots, tab-button metrics and 17 px runtime page offset. Fixture journeys cover all four categories, Shift/Ctrl multi-selection, capital dispatch, and selected-group training confirmation with exact ActionTrainUnit and ActionDispatchUnitDeployment payloads. GameView also routes a selected reserve drag to a map-region deployment request. OpenPower uses its own unit taxonomy and status presentation; native REFERENCE tab/icon assets and localized captions are not verified, and OpenPower has no equivalent of the source NuclearAllowed option.",
        "action_required": "Keep source frame/list/tab geometry, count projections, categorized selection and guarded capital deployment/training workflows passing; preserve map-drop destination validation and the documented OpenPower taxonomy and option differences.",
        "missing_action": "reference REFERENCE tab/category caption localization and native unit-category icon assets; no equivalent of the source NuclearAllowed option",
        "current_implementation": "UnitReservesPanel with GMLWidgets, lstUnitDeployItem rows, MilitaryPresenter reserve projections, UnitTrainingConfirmation, and GameView drag/drop deployment routing",
    },
    "Unit_List_Window_New": {
        "reason": "UnitListPanel uses the exact 835x427 source window, its type filter and header slots, 20 fixed 753x16 row positions, source scrollbar and bottom action row. Its filter presents all 20 REFERENCE type IDs/order mapped to canonical OpenPower roles, even when a type has no current row; visible OpenPower-only and aggregate estimate/readiness types are appended. Recognized role names use source-style English labels in the row; all other row values and unknown type names stay bound to OpenPower data. Own units bind to design/type/count/location/status/training/market data; rows support source-style sorting, Ctrl multi-selection, design double-click, batch training confirmation, ActionListUsedUnit sale requests and ActionDisbandUnits. Disband checks issuer authority, unit availability and active orders, removes the selected units, releases their personnel from the country military total, and preserves completed deployment history. Own rows display and sort by an annual estimate allocated from OpenPower's existing country military-upkeep budget formula. Foreign views show aggregate OpenPower force and readiness estimates with explicit unknown/outdated states; individual units remain hidden. Source localization strings, per-unit upkeep modifiers, and exact training-level, sale-marker, and sort-header artwork are not available.",
        "action_required": "Keep the source-ID filter mapping, GML row geometry, filter/sort, scrollbar and guarded sale/training/disband journeys covered; preserve aggregate-only foreign unit information, identify own-unit upkeep as an OpenPower estimate, and retain localization/modifier/artwork gaps in the audit.",
        "missing_action": "Exact REFERENCE per-unit upkeep modifiers and training/sale/header icon assets",
        "current_implementation": "UnitListPanel with GMLWidgets source slots, UnitListRow view models, budget-derived upkeep, GML-slot training/sale markers, ActionDisbandUnits, guarded sale and batch training flows",
    },
    "Covert_Actions_Window": {
        "reason": "The source 746x344 frames and 681x16 cell rows bind the owned roster, selected mission, progress and configured upkeep. The PROGRESS heading is placed through its exported transparent-text meter slot, and its four-viewport journey asserts the GML-relative position and no overlap with the first row. Ready-mail callbacks select the exact cell; preparation, execution, cancellation and retirement have authoritative actions. Source row country/status combos dispatch guarded reassignment and Active/Dormant actions with server transit validation. Source cell-creation, training, and mission forms are registered modal windows; Python now uses source-sized modal popups with the GML title and close control. Framing country is saved on missions and changes discovered attribution, diplomacy effects, victim notifications and private result views. The mission form selects and validates source complexity and civilian resource or military unit targets, saves them on the mission, and displays them in the roster and outcome views. Mission resolution now applies the source low/medium/high success modifiers, the specific-target success penalty, and complexity-scaled effect strength. Civilian resource espionage/sabotage changes existing OpenPower production rows, distributed across controlled regions; military sabotage restricts its existing OpenPower unit-strength effect to the selected domain. Protection displays OpenPower domestic-security coverage using the same rule as covert mission detection; this is explicitly not the REFERENCE NationalSecurity formula. The base chance formula still uses OpenPower security/concealment inputs, and REFERENCE per-characteristic military espionage/sabotage research effects have no exact OpenPower counterpart.",
        "action_required": "Keep the OpenPower base chance inputs and protection estimate clearly identified. Trace whether OpenPower gains per-characteristic research data before attempting to represent REFERENCE military espionage/sabotage; retain the source modifier and civilian resource behavior tests.",
        "missing_action": "Exact REFERENCE base success probability and military research-characteristic espionage/sabotage effects",
        "current_implementation": "CovertOpsPanel composed with CovertSelection, CovertActionWindows and CovertIntelligenceWindow; CovertOperationsSystem owns mission readiness and command acceptance",
    },
    "Generic_Question_Window": {
        "reason": "The source-sized modal implements one-shot Yes/No observers, both Internal Laws party-count transitions, selected-group training, and confirmed constitutional edits to a non-hostile country with at least 75% regional control. The Unit List caller verifies both answers, preserves the selection on No, and sends quote-guarded per-unit actions on Yes while temporarily disabling TRAIN and SELL for that unchanged selection. The foreign constitutional caller preserves its draft on No and dispatches the qualified, server-validated form action on Yes; the server releases controlled regions, grants military access and sets bilateral relations to 100. The OpenPower threshold uses a region-count proxy because the REFERENCE proportion calculation is absent from the published source. OccupyTerritory uses OpenPower's separate Unit_Attack_Confirm_Window and server-validated ActionInvadeTerritory; the source route and its OpenPower equivalent are scenario-bound. The source's repeated-question branch is unreachable in the supplied active source because only one country is placed in the pending declaration set. RGAPI multiplayer join and advisor-event acceptance/rejection still lack supported OpenPower workflows.",
        "action_required": "Keep the source-sized question, Internal Laws, Unit List training, qualified foreign-form, and invasion confirmation journeys passing, including the post-Yes TRAIN/SELL lock until row selection recalculates eligibility; retain the remaining unsupported callers as explicit gaps until their authoritative OpenPower workflows exist.",
        "missing_action": "RGAPI multiplayer join and advisor-event acceptance/rejection workflows; exact REFERENCE gained-proportion calculation",
        "current_implementation": "InternalLawsPanel and UnitTrainingConfirmation/GenericQuestionDialog; Unit List quote/signature guards, selection retained on No, and post-Yes TRAIN/SELL lock; separate UnitAttackConfirmation for ActionInvadeTerritory",
    },
    "Small_Unit_Info_Window": {
        "reason": "The 86x51 source frame follows one selected visible group, shows own personnel/equipment quantities and category proportions, and hides for dragging, multiple selection or disappearance. Foreign and unknown-role quantities stay unknown because source noisy per-group intelligence has no equivalent OpenPower observation contract.",
        "action_required": "Bind foreign per-group composition only to a published authorized observation; preserve unknown values until that gameplay contract exists.",
        "missing_action": "Authorized per-group intelligence observation data",
        "current_implementation": "GameView/MapInformationWindows and selected_unit_composition",
    },
    "Battle_Window": {
        "reason": "The selected battle uses source GML frames, country selection, progress, per-force orders, global presets, retreat and observed coordinate mapping. OpenPower force cards expose current formations/personnel, recorded casualties by country/type, and the local player's aggregated current orders. The source 3D unit models, animation, and source-specific per-model hit counters are unavailable; foreign individual rosters and orders remain hidden.",
        "action_required": "Keep dynamic card rows tied to authorized battle groups, recorded personnel losses, and local-player postures. Preserve source interaction parity for per-force orders, global presets, retreat, side selection, and selection feedback; keep missing 3D assets and non-equivalent per-model hit state explicit.",
        "missing_action": "REFERENCE 3D models/animation assets and exact per-model combat hit state",
        "current_implementation": "GameLayout/BattleInspectionWindows composed with BattleInspection, force cards and BattlePositionMap",
    },
    "Advisor_Settings_Window": {
        "reason": "The GML-sized Python panel stages and applies the three authoritative per-country advisor modes. OpenPower's daily AISystem evaluates its bounded native policy registry: Automatic queues supported actions for execution, while Confirmations stores supported actions in advisor_recommendations. ObjectivesPanel presents those recommendations and GenericQuestionDialog accepts or dismisses them through ActionResolveAdvisorRecommendation. This covers the operational modes for OpenPower's supported policy subset, but does not reproduce REFERENCE's full advisor policy set or exact cadence.",
        "action_required": "Keep the authoritative mode update, automatic policy action, confirmation queue, accept/dismiss feedback, and Apply/Discard journeys passing. Preserve OpenPower's explicit supported-policy boundary; map further REFERENCE policies only when equivalent OpenPower data and actions exist.",
        "missing_action": "Exact REFERENCE advisor cadence and policy/action mappings outside the OpenPower native policy subset",
        "current_implementation": "AdvisorSettingsPanel/ActionUpdateAdvisorSettings, AISystem automatic and confirmation modes, AdvisorRecommendationSystem, ObjectivesPanel, and GenericQuestionDialog",
    },
    "Generic_Message_Window": {
        "reason": "The Python dialog is wired to simulation-error details, newly rejected local unit movement feedback with refused-unit counts, rejected unit-design results, and optional acknowledgement callbacks. All 28 active REFERENCE display sites and the OK callback receivers are crosswalked in generic_message_callback_map.csv; the map distinguishes verified results, equivalent validation/feed/loading routes, and REFERENCE-only workflows.",
        "action_required": "Use generic_message_callback_map.csv to retain verified OpenPower routes, wire supported result feedback where an authoritative result exists, and leave source-only workflows explicitly unsupported.",
        "missing_action": "Caller-specific feedback for REFERENCE workflows without an OpenPower equivalent",
        "current_implementation": "GameLayout/GenericMessageDialog with queued caller callbacks; CommandFeedback delivers local authoritative refusals/failures and final save outcomes without replaying loaded history",
    },
    "Increase_Production_Window": {
        "reason": "The GML-sized Python dialog reads OpenPower domestic_production and uses explicit regional_production rows only when the selected country controls those regions; it never invents a regional allocation. Apply selects the highest independently selected percentage, submits ActionIncreaseResourceProduction, debits the authoritative country treasury, updates production and the resource ledger, and emits EventResourceProductionIncreased for history. The OpenPower estimate is one year of added output value. The REFERENCE-HDM interface declares IncreaseProductionApproxCost, but its implementation is absent, so exact cost parity remains unverified.",
        "action_required": "Keep the OpenPower investment rule explicitly labeled and covered by UI/server evidence; reconcile its estimate only if the missing authoritative REFERENCE cost formula becomes available.",
        "missing_action": "Exact REFERENCE production-cost formula and localized cost presentation",
        "current_implementation": "ResourcesPanel/IncreaseProductionDialog plus authoritative ActionIncreaseResourceProduction, country-controlled regional/national production policy, treasury debit, ledger refresh, and history event",
    },
}
SEED_JOURNEY_MAP: dict[str, tuple[str, str, str]] = {
    "Main_Bar/btnPolitic": ("reference-politics-constitutional.json", "hud.panel.pol", "politics.panel"),
    "Main_Bar/btnEconomic": ("reference-economy-budget.json", "hud.panel.eco", "economy.panel"),
    "Main_Bar/btnMilitary": ("reference-military-unit-list.json", "hud.panel.mil", "military.panel"),
    "Main_Bar/btnMoreInfo": ("reference-country-info.json", "hud.more_info", "country_more_info.panel"),
    "Main_Bar/btnRelations": ("reference-relations.json", "hud.relations", "relations.panel"),
    "Main_Bar/togNews": ("reference-news.json", "hud.news", "news.panel"),
    "Main_Bar/togHistory": ("reference-main-bar-history.json", "hud.history", "history.panel"),
    "Main_Bar/togMail": ("reference-mail-context.json", "hud.mail", "mail.panel"),
    "Main_Bar/togAdvisor": ("reference-advisor-settings.json", "hud.advisor", "advisor.settings.panel"),
    "Politic_Window/frmInner/frmConstitutionalForm/btnMoreConstitutionalForm": (
        "reference-politics-constitutional.json", "politics.open_constitution", "constitutional_form.panel",
    ),
    "Politic_Window/frmInner/frmIdeology/btnInternalLaws": (
        "reference-politics-laws.json", "politics.open_laws", "laws.panel",
    ),
    "Politic_Window/frmInner/btnTreaties": (
        "reference-politics-treaties.json", "politics.open_treaties", "treaties.panel",
    ),
    "Economic_Window/frmInner/frmEconomicHealth/btnMoreEconomicHealth": (
        "reference-economy-health.json", "economy.health_btn", "economic_health.panel",
    ),
    "Economic_Window/frmInner/frmResources/btnMoreResources": (
        "reference-economy-resources.json", "economy.resources_btn", "resources.panel",
    ),
    "Economic_Window/frmInner/frmBudget/btnMoreBudget": (
        "reference-economy-budget.json", "economy.budget_btn", "budget.panel",
    ),
    "Economic_Window/frmInner/btnTrade": (
        "reference-economy-trade.json", "economy.trade_btn", "trade.panel",
    ),
    "Military_Window/frmInner/frmConventionalWarfare/btnConventionalForcesMore": (
        "reference-military-unit-list.json", "military.open_unit_list", "unit_list.panel",
    ),
    "Military_Window/frmInner/frmConventionalWarfare/btnDesign": (
        "reference-military-design.json", "military.open_design", "unit_design.panel",
    ),
    "Military_Window/frmInner/frmConventionalWarfare/btnBuild": (
        "reference-military-production.json", "military.open_production", "unit_production.panel",
    ),
    "Military_Window/frmInner/frmStrategicWeapons/btnBuild": (
        "reference-military-strategic-production.json", "military.open_strategic_build", "unit_production.panel",
    ),
    "Military_Window/frmInner/frmConventionalWarfare/btnBuy": (
        "reference-military-market.json", "military.open_market", "unit_market.panel",
    ),
    "Military_Window/frmInner/frmConventionalWarfare/btnResearch": (
        "reference-military-research.json", "military.open_research", "unit_research.panel",
    ),
    "Military_Window/frmInner/btnCovertActions": (
        "reference-military-covert.json", "military.open_covert", "covert_ops.panel",
    ),
    "Military_Window/frmInner/btnWarList": (
        "reference-war-list-gml.json", "military.open_war_list", "war_list.panel",
    ),
    "Military_Window/frmInner/frmConventionalWarfare/btnDeploy": (
        "reference-military-reserves.json", "military.open_reserves", "unit_reserves.panel",
    ),
    "Budget_Window/frmInner/frmIncome/btnPersonalIncomeTax": (
        "reference-budget-income-tax.json", "budget.navigate.income-tax", "economic_health.panel",
    ),
    "Budget_Window/frmInner/frmIncome/btnTrade": (
        "reference-budget-income-trade.json", "budget.navigate.income-trade", "resources.panel",
    ),
    "Budget_Window/frmInner/frmFixedExpenses/btnTrade": (
        "reference-budget-fixed-trade.json", "budget.navigate.fixed-trade", "resources.panel",
    ),
    "Budget_Window/frmInner/frmFixedExpenses/btnDiplomacy": (
        "reference-budget-fixed-diplomacy.json", "budget.navigate.fixed-diplomacy", "treaties.panel",
    ),
    "Budget_Window/frmInner/frmFixedExpenses/btnSecurity": (
        "reference-budget-fixed-security.json", "budget.navigate.fixed-security", "covert_ops.panel",
    ),
    "Budget_Window/frmInner/frmFixedExpenses/btnUnitUpkeep": (
        "reference-budget-fixed-military-upkeep.json", "budget.navigate.fixed-military-upkeep", "unit_list.panel",
    ),
}
@dataclass(frozen=True)
class NavigationJourneyBinding:
    journey_file: str
    operation: str
    control_id: str
    expected_region: str
    expected_visible: bool = True
    expected_present: bool | None = True


ADDITIONAL_NAVIGATION_JOURNEY_MAP: dict[
    tuple[str, str, str], NavigationJourneyBinding
] = {
    (
        "handler:GDataAccessLayerClient::AddTreatyRefusalMail", "Mail_Window", "show",
    ): NavigationJourneyBinding(
        "reference-mail-arrival.json", "server_event", "EventTreatyRefused", "mail.panel",
    ),
    (
        "handler:GDataAccessLayerClient::AddTradeMail", "Mail_Window", "show",
    ): NavigationJourneyBinding(
        "reference-live-combat-mail.json", "server_event", "EventDiplomaticTradeChanged", "mail.panel",
    ),
    (
        "handler:GDataAccessLayerClient::AddCombatOverMail", "Mail_Window", "show",
    ): NavigationJourneyBinding(
        "reference-live-combat-mail.json", "server_event", "EventBattleEnded", "mail.panel",
    ),
    (
        "Main_Bar/togHistory", "History_Window", "toggle",
    ): NavigationJourneyBinding(
        "reference-main-bar-history.json", "click", "hud.history", "history.panel",
    ),
    (
        "Resources_Window/frmInner/frmResources/btnIncreaseProduction",
        "Increase_Production_Window", "show",
    ): NavigationJourneyBinding(
        "reference-resource-production-dialog.json", "click", "resources.increase_production",
        "resources.increase_production.dialog",
    ),
    (
        "Treaty_Details_Window/frmInner/frmMain/frmModify/btnModify",
        "Add_Remove_Window", "show",
    ): NavigationJourneyBinding(
        "reference-politics-treaty-details.json", "click", "treaties.details.edit_participants",
        "treaty.participants.dialog",
    ),
    ("Main_Menu/frmInner/btnCredits", "Credits_Window", "show"): NavigationJourneyBinding(
        "reference-main-menu-credits.json", "click", "main_menu.credits", "main_menu.credits_screen",
    ),
    ("handler:GCreditsWindow::OnMouseClick", "Credits_Window", "close"): NavigationJourneyBinding(
        "reference-main-menu-credits-close.json", "click", "main_menu.credits_back", "main_menu.window",
    ),
    ("Main_Menu/frmInner/btnOptions", "Options_Window", "show"): NavigationJourneyBinding(
        "reference-main-menu-options.json", "click", "main_menu.options", "main_menu.options_screen",
    ),
    (
        "Join_Multiplayer_Game/frmInner/btnHostInJoinMenu",
        "Host_Multiplayer_Game",
        "show",
    ): NavigationJourneyBinding(
        "reference-host-window-navigation.json",
        "click",
        "multiplayer.join.host",
        "multiplayer.host.window",
    ),
    ("handler:GPoliticWindow::OnMouseClick", "Politic_Window", "close"): NavigationJourneyBinding(
        "reference-politics-close.json", "close_window", "politics.panel", "politics.panel", False, False,
    ),
    ("handler:GMilitaryWindow::OnMouseClick", "Military_Window", "close"): NavigationJourneyBinding(
        "reference-military-close.json", "close_window", "military.panel", "military.panel", False, False,
    ),
    ("handler:GUnitListWindowNew::OnMouseClick", "Unit_List_Window_New", "close"): NavigationJourneyBinding(
        "reference-unit-list-close.json", "close_window", "unit_list.panel", "unit_list.panel", False, False,
    ),
    ("handler:GUnitListWindowNew::OnMouseDown", "Unit_Design_New", "show"): NavigationJourneyBinding(
        "reference-unit-list-design-details.json", "click", "unit_list.view_design.unit-fighter-1", "unit_design.panel",
    ),
    ("handler:GUnitProductionWindow::OnCustomEvent", "Unit_Design_New", "show"): NavigationJourneyBinding(
        "reference-unit-production-design-details.json", "click", "unit_production.view_design.design-fighter-1", "unit_design.panel",
    ),
    ("handler:GWarListWindow::OnMouseClick", "War_List_Window", "close"): NavigationJourneyBinding(
        "reference-war-list-close.json", "close_window", "war_list.panel", "war_list.panel", False, False,
    ),
    (
        "Covert_Actions_Window/frmInner/frmCell/btnNewCell",
        "Covert_Actions_Cell_Creation", "show",
    ): NavigationJourneyBinding(
        "reference-military-covert-create.json", "click", "covert_ops.open_cell_creation",
        "covert.cell_creation.dialog",
    ),
    (
        "Covert_Actions_Window/frmInner/frmCell/btnNewMission",
        "Covert_Actions_New_Mission", "show",
    ): NavigationJourneyBinding(
        "reference-military-covert-mission.json", "click", "covert_ops.open_new_mission",
        "covert.new_mission.dialog",
    ),
    (
        "Covert_Actions_Window/frmInner/frmCell/btnTrainCell",
        "Covert_Actions_Cell_Training", "show",
    ): NavigationJourneyBinding(
        "reference-military-covert-train.json", "click", "covert_ops.open_cell_training",
        "covert.cell_training.dialog",
    ),
    (
        "Treaties_Window/frmInner/btnView", "Treaty_Details_Window", "show",
    ): NavigationJourneyBinding(
        "reference-politics-treaty-details.json", "click", "treaties.view_selected",
        "treaties.details.dialog",
    ),
    (
        "Treaty_Details_Window/frmInner/frmEligibleCountries/btnRemoveNotEligible",
        "Generic_Message_Window", "show",
    ): NavigationJourneyBinding(
        "reference-treaty-remove-ineligible.json", "click",
        "treaties.details.remove_ineligible", "generic_message.dialog",
    ),
    (
        "Treaties_Window/frmInner/btnNew", "Treaty_Details_Window", "show",
    ): NavigationJourneyBinding(
        "reference-politics-create-treaty.json", "click", "treaties.new_treaty",
        "treaty_proposal.panel",
    ),
    (
        "handler:GTreatiesWindow::OnCustomEvent", "Treaty_Details_Window", "show",
    ): NavigationJourneyBinding(
        "reference-politics-treaty-details.json", "click", "treaties.view_selected",
        "treaties.details.dialog",
    ),
    (
        "Unit_Design_New/frmInner/btnNewDesign", "Unit_New_Design", "show",
    ): NavigationJourneyBinding(
        "reference-military-create-design.json", "click", "unit_design.create.open",
        "unit_design.create.dialog",
    ),
}
@dataclass(frozen=True)
class DisplayBinding:
    state_binding: str
    units: str
    fallback: str
    update_rule: str
    openpower_source: str
    meaning: str = ""
    status: str = "verified_openpower"
    action_required: str = ""
    surface: str = ""


def _save_load_caption_binding(
    template: str,
    token: str,
    caption: str,
    meaning: str,
) -> DisplayBinding:
    return DisplayBinding(
        f"literal: English equivalent of GML text token {token}",
        "static English caption",
        f"{caption}; the supplied source mirror does not include the REFERENCE localization tables.",
        "Rendered in the matching SaveGameDialog mode while the window is open.",
        f"src/client/ui/components/shared/save_game_dialog.py; .codex/layout_catalog.gml#{template}",
        meaning,
        status="partial",
        action_required="Use the exact REFERENCE translation only if its reference localization bundle is recovered.",
    )


def _military_caption_binding(token: str, caption: str, meaning: str) -> DisplayBinding:
    return DisplayBinding(
        f"literal: English OpenPower caption corresponding to GML text token {token}",
        "static English caption",
        f"{caption}; the REFERENCE localization tables are not present in the supplied source mirror.",
        "Rendered from the current MilitaryPanel on each visible frame.",
        "src/client/ui/panels/military_panel.py; .codex/layout_catalog.gml",
        meaning,
        status="partial",
        action_required="Use exact REFERENCE localized copy only if the reference language tables are recovered; preserve the GML text slot.",
    )


def _explicit_gml_caption_binding(
    token: str,
    caption: str,
    surface: str,
    source_files: str,
    meaning: str,
    action_required: str,
) -> DisplayBinding:
    return DisplayBinding(
        f"literal: English OpenPower caption for GML text token {token}",
        "static English caption",
        f"{caption}; the supplied REFERENCE source mirror does not include localization tables.",
        f"Rendered in the matching GML slot while {surface.split('.', 1)[0]} is visible.",
        source_files,
        meaning,
        status="partial",
        action_required=action_required,
        surface=surface,
    )


def _host_multiplayer_option_binding(
    state_binding: str,
    units: str,
    meaning: str,
) -> DisplayBinding:
    return DisplayBinding(
        state_binding,
        units,
        "The choice is kept in the local host settings draft; no authoritative server consumes it.",
        "Updated when the matching combo changes; values remain local until host-session support exists.",
        "src/client/ui/components/shared/host_multiplayer_window.py; .codex/layout_catalog.gml#Host_Multiplayer_Game",
        meaning,
        status="partial",
        action_required="Keep Start disabled until an authoritative multiplayer session service can validate and use this draft.",
        surface="MainMenuContent/HostMultiplayerGameWindow",
    )


def _covert_outcome_value_binding(
    state_binding: str,
    units: str,
    fallback: str,
    update_rule: str,
    meaning: str,
    action_required: str,
) -> DisplayBinding:
    return DisplayBinding(
        state_binding,
        units,
        fallback,
        update_rule,
        "src/client/ui/components/shared/covert_outcome_dialog.py; src/client/ui/panels/military/presenter.py; .codex/layout_catalog.gml",
        meaning,
        status="partial",
        action_required=action_required,
        surface="GameLayout/CovertOutcomeDialog",
    )


def _campaign_setup_display_binding(
    state_binding: str,
    units: str,
    fallback: str,
    update_rule: str,
    meaning: str,
    action_required: str,
    surface: str,
) -> DisplayBinding:
    return DisplayBinding(
        state_binding,
        units,
        fallback,
        update_rule,
        (
            "src/client/views/new_game_view.py; "
            "src/client/ui/components/shared/campaign_scenario_selection_window.py; "
            "src/client/ui/components/shared/single_player_setup_window.py; "
            "src/client/services/campaign_selection.py; .codex/layout_catalog.gml"
        ),
        meaning,
        status="partial",
        action_required=action_required,
        surface=surface,
    )


def _covert_caption_binding(token: str, caption: str, surface: str) -> DisplayBinding:
    return _explicit_gml_caption_binding(
        token,
        caption,
        surface,
        "src/client/ui/panels/military/covert_ops_panel.py; .codex/layout_catalog.gml",
        f"OpenPower renders {caption!r} in this source caption slot; exact token translation remains unavailable.",
        "Keep the current English caption in its GML slot; use the exact source translation only if its language tables are recovered.",
    )


_COVERT_MISSION_FORM_SOURCE = (
    "src/client/ui/panels/military/covert_action_windows.py; "
    "src/shared/covert_mission_options.py; "
    "modules/base/systems/military/covert_policy.py; "
    ".codex/Client/Source/reference_covert_actions_new_mission.cpp; "
    ".codex/layout_catalog.gml#Covert_Actions_New_Mission"
)
_COVERT_MISSION_FORM_SURFACE = "PanelSpec/COVERT_OPS/CovertActionWindows mission dialog"


def _covert_mission_form_caption_binding(
    token: str,
    caption: str,
    meaning: str,
) -> DisplayBinding:
    return _explicit_gml_caption_binding(
        token,
        caption,
        _COVERT_MISSION_FORM_SURFACE,
        _COVERT_MISSION_FORM_SOURCE,
        meaning,
        "Keep the English caption in its GML slot; use exact source copy only if the reference localization tables are recovered.",
    )


def _covert_mission_form_value_binding(
    state_binding: str,
    units: str,
    fallback: str,
    update_rule: str,
    meaning: str,
    *,
    status: str = "verified_openpower",
    action_required: str = "",
) -> DisplayBinding:
    return DisplayBinding(
        state_binding,
        units,
        fallback,
        update_rule,
        _COVERT_MISSION_FORM_SOURCE,
        meaning,
        status=status,
        action_required=action_required,
        surface=_COVERT_MISSION_FORM_SURFACE,
    )


def _objectives_caption_binding(token: str, caption: str, surface: str) -> DisplayBinding:
    return _explicit_gml_caption_binding(
        token,
        caption,
        surface,
        "src/client/ui/panels/service/objectives_window_content.py; src/client/ui/panels/service/objectives_panel.py; .codex/layout_catalog.gml",
        f"ObjectivesPanel renders {caption!r} in the corresponding source caption slot; exact token translation remains unavailable.",
        "Keep the current English caption in its GML slot; use the exact source translation only if its language tables are recovered.",
    )


def _unit_production_caption_binding(token: str, caption: str, surface: str) -> DisplayBinding:
    return _explicit_gml_caption_binding(
        token,
        caption,
        surface,
        "src/client/ui/panels/military/unit_production_panel.py; .codex/layout_catalog.gml",
        f"UnitProductionPanel renders {caption!r} in the corresponding source slot; exact token translation remains unavailable.",
        "Keep the English caption in its GML slot and preserve any OpenPower-only value or action difference described by the adjacent contract.",
    )


def _economy_caption_binding(token: str, caption: str, meaning: str) -> DisplayBinding:
    return _explicit_gml_caption_binding(
        token,
        caption,
        "economy.panel",
        "src/client/ui/panels/economy_panel.py; .codex/layout_catalog.gml",
        f"EconomyPanel renders {caption!r} in the corresponding source caption slot; exact token translation remains unavailable.",
        "Keep the current English caption in its GML slot; use the exact source translation only if its language tables are recovered.",
    )


def _treaties_caption_binding(token: str, caption: str, meaning: str) -> DisplayBinding:
    return _explicit_gml_caption_binding(
        token,
        caption,
        "treaties.panel",
        "src/client/ui/panels/politics/treaties_live.py; src/client/ui/panels/politics/treaties_panel.py; .codex/layout_catalog.gml",
        f"LiveTreatiesPanel renders {caption!r} in the corresponding source caption slot; exact token translation remains unavailable.",
        "Keep the current English caption in its GML slot; preserve the documented OpenPower table layout and use exact source localization only if its language tables are recovered.",
    )


def _internal_laws_caption_binding(token: str, caption: str, meaning: str) -> DisplayBinding:
    return _explicit_gml_caption_binding(
        token,
        caption,
        "laws.panel",
        "src/client/ui/panels/politics/internal_laws_panel.py; .codex/layout_catalog.gml",
        f"InternalLawsPanel renders {caption!r} in the corresponding source caption slot; exact token translation remains unavailable.",
        "Keep the current English caption in its GML slot; use the exact source translation only if its language tables are recovered.",
    )


def _resources_caption_binding(token: str, caption: str, meaning: str) -> DisplayBinding:
    return _explicit_gml_caption_binding(
        token,
        caption,
        "resources.panel",
        "src/client/ui/panels/resources_panel.py; modules/base/schema.py; .codex/layout_catalog.gml",
        f"ResourcesPanel renders {caption!r} for {meaning.lower()} within the resource panel; exact source localization remains unavailable.",
        "Keep the English caption in its matching GML slot, document unavailable REFERENCE policy fields, and do not equate OpenPower's net balance with source stock availability.",
    )


def _system_bar_caption_binding(token: str, caption: str, meaning: str) -> DisplayBinding:
    return _explicit_gml_caption_binding(
        token,
        caption,
        "hud.system_bar",
        "src/client/ui/components/hud/system_bar.py; .codex/layout_catalog.gml",
        f"SystemBar._render_shortcuts renders {caption!r} beside its matching source shortcut; {meaning}",
        "Keep each caption in its source shortcut slot and preserve disabled state for multiplayer chat, which has no OpenPower route.",
    )


def _relations_caption_binding(token: str, caption: str, meaning: str) -> DisplayBinding:
    return _explicit_gml_caption_binding(
        token,
        caption,
        "relations.panel",
        "src/client/ui/panels/politics/relations_panel.py; .codex/layout_catalog.gml",
        f"RelationsPanel renders {caption!r} for {meaning.lower()}; exact source localization remains unavailable.",
        "Keep the country-pair controls and labels in their source slots; do not infer REFERENCE localization from OpenPower's English captions.",
    )


def _military_force_count_binding(source_category: str, openpower_bucket: str) -> DisplayBinding:
    return DisplayBinding(
        f"sum(units.strength for current-country rows in MilitaryPresenter {openpower_bucket} bucket)",
        "OpenPower unit strength (personnel)",
        "0 when the selected country's current snapshot has no matching unit rows.",
        "Recomputed from the selected country's current unit snapshot on each MilitaryPanel render.",
        "src/client/ui/panels/military/military_panel.py; src/client/ui/panels/military/presenter.py; modules/base/data/countries/MILITARY_DATA.md; .codex/Client/Source/reference_military_window.cpp",
        f"REFERENCE requests UnitQtyByCountryAndCategory({source_category}); OpenPower displays the summed strength of its {openpower_bucket} bucket. The source DAL implementation is absent, so the quantities are not asserted to be equivalent.",
        status="partial",
        action_required="Keep the displayed value identified as OpenPower personnel strength; do not claim exact REFERENCE quantity parity without the source DAL metric definition.",
    )


def _military_unit_group_count_binding(source_category: str, openpower_bucket: str) -> DisplayBinding:
    return DisplayBinding(
        f"MilitaryPresenter.build_summary().branches[{openpower_bucket}].unit_count",
        "OpenPower unit groups",
        "0 when the selected country's current snapshot has no matching unit rows.",
        "Recomputed from the selected country's current unit snapshot on each MilitaryPanel render.",
        "src/client/ui/panels/military/military_panel.py; src/client/ui/panels/military/presenter.py; .codex/Client/Source/reference_military_window.cpp",
        f"REFERENCE computes a cross-country TotalUnitsValue rank for {source_category}; OpenPower displays the number of local unit rows in its {openpower_bucket} bucket instead of a country rank.",
        status="partial",
        action_required="Keep the OpenPower column labeled UNITS; implement a rank only if an authorized comparable country-wide metric is defined.",
    )


_BUDGET_FIELD_FALLBACK = (
    "0.0 when the country field is absent; declared country fields use their ColumnSpec default where available."
)
_BUDGET_FIELD_UPDATE = (
    "BudgetPanel reads the current GameState row every render. BudgetSystem refreshes calculated budget fields "
    "on positive, unpaused EventRealSecond; trade income/expense also come from TradeSystem."
)
_BUDGET_PREVIEW_FALLBACK = (
    "0.0 when resource_ledger is absent or has no rows; the current panel treats these cases as zero demand."
)
_BUDGET_STATE_SOURCE = (
    "src/client/ui/panels/budget_panel.py; modules/base/schema.py; "
    "modules/base/systems/economy/budget_system.py; modules/base/systems/economy/trade_system.py"
)


def _source_credit_binding(
    group_id: str,
    entry_index: int | None,
    person_index: int | None,
    text: str,
) -> DisplayBinding:
    if entry_index is None:
        state_binding = f"REFERENCE_STEAM_CREDIT_GROUPS[{group_id!r}].name"
        meaning = f"Source-game credits group title {text!r}."
    elif person_index is None:
        state_binding = f"REFERENCE_STEAM_CREDIT_GROUPS[{group_id!r}].entries[{entry_index}].role"
        meaning = f"Source-game credits role {text!r}."
    else:
        state_binding = (
            f"REFERENCE_STEAM_CREDIT_GROUPS[{group_id!r}].entries[{entry_index}]"
            f".people[{person_index}]"
        )
        meaning = f"Source-game credits name {text!r}."
    return DisplayBinding(
        state_binding,
        "static English source-game credit text",
        "Rendered from the bundled English Steam credit roster; no GML token text is substituted if the roster entry is absent.",
        "Static content rendered when ProjectCreditsContent is visible.",
        "src/client/ui/components/project_credits_content.py; src/client/ui/components/reference_credit_roster.py; docs/ui/reference/source_links.md",
        f"{meaning} The exact reference REFERENCE localization bundle is absent, so exact token-to-string parity is not verified.",
        status="partial",
        action_required="Keep the English credit roster tied to its GML slots; recover the source language bundle before claiming exact localized text parity.",
    )


_CREDITS_SLOT_IDS = {
    "golemlabs": {
        "title": "lblTitle",
        "section": "lblTitle5",
        "roles": (
            "lblTitle1", "lblTitle2", "lblTitle3", "lblTitle4",
            "lblTitle21", "lblTitle22", "lblTitle23", "lblTitle25", "lblTitle6", "lblTitle7",
            "lblTitle8", "lblTitle87", "lblTitle89",
        ),
        "people": (
            "lblTitle10", "lblTitle11", "lblTitle12", "lblTitle13", "lblTitle14",
            "lblTitle15", "lblTitle16", "lblTitle17", "lblTitle18", "lblTitle19",
            "lblTitle20", "lblTitle24", "lblTitle26", "lblTitle27", "lblTitle28",
            "lblTitle29", "lblTitleMathieuLemay", "lblTitle30", "lblTitle32",
            "lblTitle31", "lblTitle33", "lblTitleWestDubois", "lblTitle86",
            "lblTitle34", "lblTitle88", "lblTitle90",
        ),
    },
    "nordic_games": {
        "title": "lblNordicGames",
        "roles": ("lblDevDirector", "lblNGManagement"),
        "people": ("lblReinhardPollice", "lblKlemensKreuzer", "lblLarsWingefors"),
    },
    "dreamcatcher": {
        "title": "lblTitle9",
        "roles": (
            "lblTitle41", "lblTitle40", "lblTitle39", "lblTitle42", "lblTitle43",
            "lblTitle44", "lblTitle49", "lblTitle57", "lblTitle56", "lblTitle55",
            "lblTitle50", "lblTitle58", "lblTitle59", "lblTitle65", "lblTitle60",
            "lblTitle71", "lblTitle68", "lblTitle73", "lblTitle81",
        ),
        "people": (
            "lblTitle38", "lblTitle37", "lblTitle36", "lblTitle45", "lblTitle46",
            "lblTitle47", "lblTitle48", "lblTitle54", "lblTitle53", "lblTitle52",
            "lblTitle51", "lblTitle61", "lblTitle62", "lblTitle63", "lblTitle64",
            "lblTitle67", "lblTitle66", "lblTitle70", "lblTitle69", "lblTitle72",
            "lblTitle74", "lblTitle75", "lblTitle76", "lblTitle77", "lblTitle80",
            "lblTitle79", "lblTitle78", "lblTitle82",
        ),
    },
}


def _build_credits_bindings() -> dict[str, DisplayBinding]:
    bindings = {
        "frmTitle/lblTitle": DisplayBinding(
            "literal: CREDITS screen title for GML text token 100011",
            "static English caption",
            "CREDITS; reference REFERENCE localization tables are not included.",
            "Rendered as the MainMenuContent credits page title.",
            "src/client/ui/components/main_menu_content.py; .codex/layout_catalog.gml",
            "OpenPower's CREDITS title in the source title slot.",
            status="partial",
            action_required="Resolve the source title string from the reference language table when available.",
        )
    }
    content_prefix = "frmInner/frmCredits/frmInner/"
    for group in REFERENCE_STEAM_CREDIT_GROUPS:
        slots = _CREDITS_SLOT_IDS[group.id]
        people_slots = iter(slots["people"])
        bindings[f"{content_prefix}{slots['title']}"] = _source_credit_binding(
            group.id, None, None, group.name
        )
        if section_id := slots.get("section"):
            bindings[f"{content_prefix}{section_id}"] = DisplayBinding(
                "literal: Art team section heading from the REFERENCE game manual; GML text token 101396",
                "static English section heading",
                "Art team; the reference localization bundle is not included.",
                "Rendered in the GML section slot before the individual art credits.",
                "src/client/ui/components/project_credits_content.py; .codex/layout_catalog.gml; docs/ui/reference/source_links.md",
                "Section heading that groups the individual art credits.",
                status="partial",
                action_required="Use the reference localization string when the source language bundle is available.",
            )
        if len(slots["roles"]) != len(group.entries):
            raise ValueError(f"Credits role slot count does not match roster group {group.id!r}.")
        for entry_index, entry in enumerate(group.entries):
            bindings[f"{content_prefix}{slots['roles'][entry_index]}"] = _source_credit_binding(
                group.id, entry_index, None, entry.role
            )
            for person_index, person in enumerate(entry.people):
                try:
                    person_slot = next(people_slots)
                except StopIteration as exc:
                    raise ValueError(f"Credits name slots are incomplete for {group.id!r}.") from exc
                bindings[f"{content_prefix}{person_slot}"] = _source_credit_binding(
                    group.id, entry_index, person_index, person
                )
        if next(people_slots, None) is not None:
            raise ValueError(f"Credits name slots exceed roster group {group.id!r}.")

    contact_url = REFERENCE_CREDIT_SUPPLEMENTAL_TEXT[("golemlabs", "Sound and Music")]
    bindings[f"{content_prefix}lblTitle35"] = DisplayBinding(
        f"literal: {contact_url}; inferred continuation of Eric Vigneault's Sound and Music credit for GML text token 101405",
        "static supplemental URL",
        "The published 2014 Steam Edition listing places this URL after Eric Vigneault, and GML exposes a separate adjacent row; mapping the URL to that row is an inference pending the reference localization bundle.",
        "Rendered in the lblTitle35 GML slot as a continuation of the Sound and Music credit.",
        "src/client/ui/components/project_credits_content.py; src/client/ui/components/reference_credit_roster.py; .codex/layout_catalog.gml; docs/ui/reference/source_links.md",
        "The contact URL published with Eric Vigneault is mapped to this dedicated source row by inference from the GML layout.",
        status="partial",
        action_required="Confirm this inferred row mapping against the reference REFERENCE localization text for token 101405 when available.",
    )

    copyright_text = REFERENCE_CREDIT_SUPPLEMENTAL_TEXT[("golemlabs", "Copyright")]
    bindings[f"{content_prefix}lblTitle91"] = DisplayBinding(
        f"literal: {copyright_text}; inferred credits footer for GML text token 102121",
        "static supplemental copyright footer",
        "The REFERENCE manual prints this footer immediately after the credits list, and GML provides a final full-width label; mapping it to token 102121 is an inference pending the reference localization bundle.",
        "Rendered in the final lblTitle91 GML slot after the credits roster.",
        "src/client/ui/components/project_credits_content.py; src/client/ui/components/reference_credit_roster.py; .codex/layout_catalog.gml; docs/ui/reference/source_links.md",
        "The copyright footer printed after the REFERENCE manual credits, mapped by inference to the final source row.",
        status="partial",
        action_required="Confirm this inferred row mapping against the reference REFERENCE localization text for token 102121 when available.",
    )
    return bindings


CREDITS_BINDINGS = _build_credits_bindings()


def _budget_field(state_binding: str, units: str) -> DisplayBinding:
    return DisplayBinding(
        state_binding, units, _BUDGET_FIELD_FALLBACK, _BUDGET_FIELD_UPDATE, _BUDGET_STATE_SOURCE,
    )


def _budget_caption_binding(token: str, caption: str) -> DisplayBinding:
    return DisplayBinding(
        f"literal: current English caption for GML text token {token}",
        "static English caption",
        f"{caption}; the supplied source mirror does not include the REFERENCE localization tables.",
        "Rendered by BudgetPanel while the panel is open.",
        "src/client/ui/panels/budget_panel.py; .codex/layout_catalog.gml",
        f"Current OpenPower caption for the {caption.lower()} slot; exact source localization is unavailable.",
        status="partial",
        action_required="Use the exact source caption only if the REFERENCE localization tables are recovered.",
    )


def _budget_preview_binding(
    column: str, label: str, weight: float, source_method: str
) -> DisplayBinding:
    return DisplayBinding(
        f"derived: resource_ledger.consumption_usd × 0.15 × {weight:g} × draft(countries.{column})",
        "USD per budget period (preview)",
        "0.0 when resource_ledger is absent or has no rows; the draft ratio defaults to 0.50 when the country value is unavailable.",
        "Recomputed from the selected country's resource-ledger demand and local draft allocation on each BudgetPanel render.",
        "src/client/ui/panels/budget_panel.py; modules/base/systems/economy/budget_system.py; .codex/Client/Source/reference_budget_window.cpp",
        f"OpenPower's {label} expense preview; REFERENCE delegates the amount to {source_method}(ratio), whose DAL formula is not included in the source mirror.",
        status="partial",
        action_required="Keep the value identified as an OpenPower preview until the source DAL return formula is available for comparison.",
    )


def _budget_meter_binding(column: str, label: str, source_method: str) -> DisplayBinding:
    return DisplayBinding(
        f"countries.{column} → BudgetPanel.draft_allocations[{column!r}]",
        "allocation ratio (0–1)",
        "0.50 panel default if the selected country row or field is absent.",
        "Loaded when the selected country changes; pointer input updates the local draft, and Apply sends ActionUpdateBudget.",
        "src/client/ui/panels/budget_panel.py; src/shared/actions.py; modules/base/systems/economy/budget_system.py; .codex/Client/Source/reference_budget_window.cpp",
        f"Draft allocation for {label}; REFERENCE reads the corresponding {source_method} value.",
        status="partial",
        action_required="Keep draft-versus-authoritative values explicit; source DAL ratio semantics are not included in the mirror.",
    )


def _budget_meter_decoration_binding(column: str, color: str) -> DisplayBinding:
    return DisplayBinding(
        f"visual: BudgetPanel._draw_gml_expense_slider({column!r}) {color} segment",
        "visual-only meter segment",
        "No independent value; omitted when the parent allocation meter is not rendered.",
        "Drawn each frame from the parent meter's draft ratio and the 0.50 requirement threshold.",
        "src/client/ui/panels/budget_panel.py; .codex/layout_catalog.gml",
        f"{color.capitalize()} fill segment inside the parent expense meter; this is presentation artwork, not a separate state field.",
        status="partial",
        action_required="Preserve the parent ratio and threshold behavior; exact source meter artwork is not represented by a state binding.",
    )


BUDGET_BINDINGS: dict[str, DisplayBinding] = {
    "frmInner/frmIncome/txtTotal": _budget_field("countries.total_annual_revenue", "USD/year"),
    "frmInner/frmIncome/txtPersonnalIncomeTax": _budget_field("countries.revenue_tax", "USD/year"),
    "frmInner/frmIncome/txtTrade": _budget_field("countries.trade_income", "USD/year"),
    "frmInner/frmIncome/txtTourism": _budget_field("countries.tourism_income", "USD/year"),
    "frmInner/frmExpenses/txtTotal": DisplayBinding(
        "derived:resource_ledger.consumption_usd × K_BUDGET × sector weights × draft allocations",
        "USD/year preview",
        _BUDGET_PREVIEW_FALLBACK,
        "Recomputed from the current resource ledger and draft allocations on every panel render.",
        "src/client/ui/panels/budget_panel.py; modules/base/systems/economy/internal_economy_system.py",
    ),
    "frmInner/frmFixedExpenses/txtSecurity": _budget_field("countries.security_upkeep", "USD/year"),
    "frmInner/frmFixedExpenses/txtDiplomacy": _budget_field("countries.diplomacy_upkeep", "USD/year"),
    "frmInner/frmFixedExpenses/txtTrade": _budget_field("countries.trade_expense", "USD/year"),
    "frmInner/frmFixedExpenses/txtUnitsUpkeep": _budget_field("countries.expense_military_upkeep", "USD/year"),
    "frmInner/frmFixedExpenses/txtDebt": _budget_field("countries.expense_debt_interest", "USD/year"),
    "frmInner/frmFixedExpenses/txtCorruption": _budget_field("countries.expense_corruption", "USD/year"),
    "frmInner/frmBalance/txtAmount": DisplayBinding(
        "derived:total income − dynamic expense preview − fixed expenses",
        "USD/year preview",
        "Uses the displayed zero defaults of its inputs; missing source fields can therefore appear as zero.",
        "Recomputed from the current state row, resource ledger, and draft allocations on every panel render.",
        "src/client/ui/panels/budget_panel.py; modules/base/systems/economy/budget_system.py",
    ),
    "frmInner/frmAvailable/txtAmount": _budget_field("countries.money_reserves", "USD"),
}
_BUDGET_CAPTIONS = {
    "frmTitle/lblTitle": ("100042", "BUDGET MENU"),
    "frmInner/frmFixedExpenses/lblTitle": ("100704", "FIXED EXPENSES"),
    "frmInner/frmFixedExpenses/txtLabel6": ("100022", "CORRUPTION"),
    "frmInner/frmFixedExpenses/txtLabel1": ("100709", "SECURITY"),
    "frmInner/frmFixedExpenses/txtLabel2": ("100710", "DIPLOMACY"),
    "frmInner/frmFixedExpenses/txtLabel3": ("100066", "TRADE"),
    "frmInner/frmFixedExpenses/txtLabel": ("100050", "TOTAL"),
    "frmInner/frmFixedExpenses/txtLabel4": ("100046", "DEBT INTEREST"),
    "frmInner/frmFixedExpenses/txtLabel5": ("100711", "MILITARY UPKEEP"),
    "frmInner/frmAvailable/lblTitle": ("100095", "AVAILABLE FUNDS"),
    "frmInner/frmExpenses/lblTitle": ("100044", "EXPENSES"),
    "frmInner/frmExpenses/lblEducation": ("100716", "EDUCATION"),
    "frmInner/frmExpenses/lblInfrastructure": ("100712", "INFRASTRUCTURE"),
    "frmInner/frmExpenses/lblPropaganda": ("100713", "PROPAGANDA"),
    "frmInner/frmExpenses/lblImf": ("101594", "FOREIGN AID (IMF)"),
    "frmInner/frmExpenses/lblGovernment": ("100718", "GOVERNMENT"),
    "frmInner/frmExpenses/lblTelecom": ("100717", "TELECOM"),
    "frmInner/frmExpenses/lblEnvironment": ("100714", "ENVIRONMENT"),
    "frmInner/frmExpenses/lblResearch": ("100030", "RESEARCH"),
    "frmInner/frmExpenses/lblTotal": ("100050", "TOTAL"),
    "frmInner/frmExpenses/lblTourism": ("100708", "TOURISM"),
    "frmInner/frmExpenses/lblHealthCare": ("100715", "HEALTH CARE"),
    "frmInner/frmBalance/lblTitle": ("100096", "SURPLUS / DEFICIT"),
    "frmInner/frmIncome/lblTitle": ("100043", "INCOME"),
    "frmInner/frmIncome/txtLabel4": ("100708", "TOURISM"),
    "frmInner/frmIncome/txtLabel": ("100050", "TOTAL"),
    "frmInner/frmIncome/txtLabel5": ("101594", "IMF AID"),
    "frmInner/frmIncome/txtLabel3": ("100066", "TRADE"),
    "frmInner/frmIncome/txtLabel2": ("100706", "PERSONAL INCOME TAX"),
}
BUDGET_BINDINGS.update({
    path: _budget_caption_binding(token, caption)
    for path, (token, caption) in _BUDGET_CAPTIONS.items()
})
BUDGET_BINDINGS.update({
    "frmInner/frmFixedExpenses/txtTotal": DisplayBinding(
        "derived: sum(countries.expense_debt_interest, diplomacy_upkeep, security_upkeep, trade_expense, expense_military_upkeep, expense_corruption)",
        "USD per budget period",
        "0.0 contribution for each missing country field; the value is shown only when a country row exists.",
        "Recomputed from the selected country's current country row on each BudgetPanel render.",
        "src/client/ui/panels/budget_panel.py; modules/base/systems/economy/budget_system.py; .codex/Client/Source/reference_budget_window.cpp",
        "Sum of six fixed expense values; REFERENCE obtains the same named categories through BudgetExpense* DAL methods.",
        status="partial",
        action_required="Keep each category and the six-term total explicit; exact DAL formulas are not available in the source mirror.",
    ),
    "frmInner/frmExpenses/txtHealthCare": _budget_preview_binding(
        "budget_health_ratio", "health-care", 0.25, "BudgetExpenseHealthcareReturn"
    ),
    "frmInner/frmExpenses/txtInfrastructure": _budget_preview_binding(
        "budget_infra_ratio", "infrastructure", 0.07, "BudgetExpenseInfrastructureReturn"
    ),
    "frmInner/frmExpenses/txtResearch": _budget_preview_binding(
        "budget_research_ratio", "research", 0.09, "BudgetExpenseResearchReturn"
    ),
    "frmInner/frmExpenses/txtTelecom": _budget_preview_binding(
        "budget_telecom_ratio", "telecom", 0.04, "BudgetExpenseTelecomReturn"
    ),
    "frmInner/frmExpenses/txtGovernment": _budget_preview_binding(
        "budget_gov_ratio", "government", 0.14, "BudgetExpenseGovernmentReturn"
    ),
    "frmInner/frmExpenses/txtEnvironment": _budget_preview_binding(
        "budget_env_ratio", "environment", 0.10, "BudgetExpenseEnvironmentReturn"
    ),
    "frmInner/frmExpenses/txtImf": _budget_preview_binding(
        "budget_imf_ratio", "IMF", 0.04, "BudgetExpenseIMFReturn"
    ),
    "frmInner/frmExpenses/txtEducation": _budget_preview_binding(
        "budget_edu_ratio", "education", 0.23, "BudgetExpenseEducationReturn"
    ),
    "frmInner/frmExpenses/txtTourism": _budget_preview_binding(
        "budget_tourism_promo_ratio", "tourism", 0.01, "BudgetExpenseTourismReturn"
    ),
    "frmInner/frmExpenses/txtPropaganda": _budget_preview_binding(
        "budget_propaganda_ratio", "propaganda", 0.03, "BudgetExpensePropagandaReturn"
    ),
    "frmInner/frmIncome/txtImf": DisplayBinding(
        "countries.budget_imf_ratio",
        "USD per budget period (current model interpretation)",
        "0.0 when the selected country row or field is absent.",
        "Read from the selected country row on each BudgetPanel render; BudgetSystem also uses this column as the IMF expense allocation ratio.",
        "src/client/ui/panels/budget_panel.py; modules/base/schema.py; modules/base/systems/economy/budget_system.py; .codex/Client/Source/reference_budget_window.cpp",
        "The source uses the distinct BudgetRevenueIMF() value. OpenPower currently reuses budget_imf_ratio for both the revenue contribution and the IMF sector ratio, so this is not a one-to-one source data contract.",
        status="partial",
        action_required="Preserve the source/OpenPower semantic difference; do not describe budget_imf_ratio as a distinct IMF revenue field.",
    ),
})
_BUDGET_METER_COLUMNS = {
    "Environment": ("budget_env_ratio", "environment", "BudgetExpenseEnvironmentRatio"),
    "Tourism": ("budget_tourism_promo_ratio", "tourism", "BudgetExpenseTourismRatio"),
    "Propaganda": ("budget_propaganda_ratio", "propaganda", "BudgetExpensePropagandaRatio"),
    "Infrastructure": ("budget_infra_ratio", "infrastructure", "BudgetExpenseInfrastructureRatio"),
    "Research": ("budget_research_ratio", "research", "BudgetExpenseResearchRatio"),
    "Imf": ("budget_imf_ratio", "IMF", "BudgetExpenseIMFRatio"),
    "Education": ("budget_edu_ratio", "education", "BudgetExpenseEducationRatio"),
    "Government": ("budget_gov_ratio", "government", "BudgetExpenseGovernmentRatio"),
    "HealthCare": ("budget_health_ratio", "health-care", "BudgetExpenseHealthcareRatio"),
    "Telecom": ("budget_telecom_ratio", "telecom", "BudgetExpenseTelecomRatio"),
}
for _budget_meter_name, (_budget_column, _budget_label, _budget_source_ratio) in _BUDGET_METER_COLUMNS.items():
    _budget_meter_path = f"frmInner/frmExpenses/frmMeter{_budget_meter_name}"
    BUDGET_BINDINGS[_budget_meter_path] = _budget_meter_binding(
        _budget_column, _budget_label, _budget_source_ratio
    )
    for _budget_color in ("Green", "Red"):
        BUDGET_BINDINGS[f"{_budget_meter_path}/pic{_budget_color}Meter"] = (
            _budget_meter_decoration_binding(_budget_column, _budget_color.lower())
        )
_RESOURCES_POLICY_UPDATE = (
    "ResourcesPanel reads the selected row from domestic_production. Combo edits update the local draft; Apply or close-confirmation Apply sends ActionUpdateResourcePolicy, handled by InternalEconomySystem."
)
_RESOURCES_POLICY_SOURCE = (
    "src/client/ui/panels/resources_panel.py; src/shared/actions.py; "
    "src/server/io/data_load_manager.py; modules/base/systems/economy/internal_economy_system.py"
)
RESOURCES_BINDINGS: dict[str, DisplayBinding] = {
    "frmInner/frmResources/cboManagement": DisplayBinding(
        "domestic_production.is_gov_controlled",
        "boolean: Private Market / State Monopoly",
        "False when the row or field is absent.",
        _RESOURCES_POLICY_UPDATE,
        _RESOURCES_POLICY_SOURCE,
        "Resource management policy: private market or state monopoly.",
    ),
    "frmInner/frmResources/cboStatus": DisplayBinding(
        "domestic_production.is_legal",
        "boolean: Legalized / Banned",
        "True when the row or field is absent.",
        _RESOURCES_POLICY_UPDATE,
        _RESOURCES_POLICY_SOURCE,
        "Resource legal status: legalized or banned.",
    ),
    "frmInner/frmResources/txtActual": DisplayBinding(
        "resource_ledger.trade_usd",
        "USD net recorded trade value (exports minus imports)",
        "Unavailable when the country/resource row is absent or the value is non-finite.",
        "Read from the selected country's current resource_ledger snapshot.",
        "src/client/ui/panels/resources_panel.py; modules/base/systems/economy/internal_economy_system.py",
        meaning="Actual net resource trade value; this is distinct from resource balance.",
        status="verified_openpower",
        action_required="Keep this field bound to trade_usd; never substitute balance_usd.",
    ),
}
_COUNTRY_INFO_SOURCE = (
    "src/client/ui/panels/country_more_info.py; modules/base/schema.py; "
    "modules/base/data/regions/regions.tsv; modules/base/data/regions/regions_pop.tsv; "
    "tests/test_country_more_info.py; tests/ui/journeys/reference-country-info.json"
)
_COUNTRY_INFO_UPDATE = (
    "CountryMoreInfoPresenter rebuilds values from current country and region tables on each panel render; "
    "source-only values remain unavailable when their inputs are absent."
)


def _country_info_binding(
    state_binding: str,
    units: str,
    fallback: str,
    meaning: str,
    *,
    status: str = "verified_openpower",
    action_required: str = "",
) -> DisplayBinding:
    return DisplayBinding(
        state_binding,
        units,
        fallback,
        _COUNTRY_INFO_UPDATE,
        _COUNTRY_INFO_SOURCE,
        meaning,
        status,
        action_required,
    )


_COUNTRY_INFO_SLOTS: dict[str, DisplayBinding] = {
    "frmLand/txtArableLand": _country_info_binding(
        "unavailable: no OpenPower arable-land share field",
        "percent of land area",
        "Em dash; the OpenPower region schema has no arable-land share field.",
        "REFERENCE displays m_fArableLand × 100; this source-only metric is not derived from unrelated OpenPower fields.",
        status="verified_unavailable",
    ),
    "frmLand/txtForests": _country_info_binding(
        "unavailable: no OpenPower forest-land share field",
        "percent of land area",
        "Em dash; the OpenPower region schema has no forest-land share field.",
        "REFERENCE displays m_fForestLand × 100; this source-only metric is not derived from unrelated OpenPower fields.",
        status="verified_unavailable",
    ),
    "frmLand/txtNationalParks": _country_info_binding(
        "unavailable: no OpenPower national-parks share field",
        "percent of land area",
        "Em dash; the OpenPower region schema has no national-parks share field.",
        "REFERENCE displays m_fParksLand × 100; this source-only metric is not derived from unrelated OpenPower fields.",
        status="verified_unavailable",
    ),
    "frmLand/txtUnusable": _country_info_binding(
        "unavailable: no OpenPower unusable-land share field",
        "percent of land area",
        "Em dash; the OpenPower region schema has no unusable-land share field.",
        "REFERENCE displays m_fUnusableLand × 100; this source-only metric is not derived from unrelated OpenPower fields.",
        status="verified_unavailable",
    ),
    "frmHumanDevelopment/frmInner/lblCountry": _country_info_binding(
        "countries.id/name and countries.human_dev",
        "localized country name and percent index",
        "Selected country tag/name; missing display values use an em dash.",
        "Selected country's OpenPower human-development index and country name.",
    ),
    "frmHumanDevelopment/frmInner/lblWorld": _country_info_binding(
        "literal: English 'World:' label followed by the source-index fallback",
        "caption and HDI availability marker",
        "World: — because the authoritative REFERENCE world-HDI inputs are unavailable in OpenPower.",
        "REFERENCE leaves this localized GML caption static; the adjacent picWorld bar carries HumanDevelopmentAvg. "
        "The exact localized caption is unavailable because the REFERENCE language tables are not in this repository.",
        status="partial",
        action_required="Add the verified localization for GML text token 101022 when the REFERENCE language tables are available.",
    ),
    "frmHumanDevelopment/frmInner/picWorld": _country_info_binding(
        "unavailable: REFERENCE world HDI requires world birth-rate, schooling, population, and GDP inputs not present in OpenPower",
        "HDI ratio [0, 1] represented by bar width",
        "Empty bar and 'World: —'; do not substitute an average of country.human_dev.",
        "REFERENCE sets bar width from m_fHumanDevAverage. GDataControlLayer::AverageHumanDevelopment aggregates "
        "world life expectancy, mean/expected schooling and GDP per capita, then applies GCountryData::FindHumanDevelopment. "
        "See docs/ui/reference/source_links.md "
        "and docs/ui/reference/source_links.md",
        status="verified_unavailable",
        action_required="Provide authoritative world-HDI inputs or a server aggregate; do not derive it from country.human_dev.",
    ),
    "frmHumanDevelopment/txtInfrastructure": _country_info_binding(
        "countries.infrastructure_index",
        "percent index",
        "Schema default is 0.0 when the country field is absent.",
        "National infrastructure index, distinct from the infrastructure budget share.",
    ),
    "frmHumanDevelopment/txtTelecom": _country_info_binding(
        "countries.telecom_index",
        "percent index",
        "Schema default is 0.0 when the country field is absent.",
        "National telecommunications index, distinct from the telecom budget share.",
    ),
    "frmPopulation/txt15": _country_info_binding(
        "sum(regions.pop_14) for the selected country's controlled regions",
        "people",
        "Em dash when regional rows or the population column are unavailable.",
        "OpenPower 0–14 age band.",
    ),
    "frmPopulation/txt1565": _country_info_binding(
        "sum(regions.pop_15_64) for the selected country's controlled regions",
        "people",
        "Em dash when regional rows or the population column are unavailable.",
        "OpenPower 15–64 age band.",
    ),
    "frmPopulation/txt65": _country_info_binding(
        "sum(regions.pop_65) for the selected country's controlled regions",
        "people",
        "Em dash when regional rows or the population column are unavailable.",
        "OpenPower 65+ age band.",
    ),
    "frmPopulation/txtTotal": _country_info_binding(
        "derived: sum of regions.pop_14 + pop_15_64 + pop_65",
        "people",
        "Em dash when regional rows or any age-band column are unavailable.",
        "Total population summed across the selected country's controlled regions.",
    ),
    "frmPopulation/txt15Ratio": _country_info_binding(
        "derived: regions.pop_14 / total population × 100",
        "percent of population",
        "Em dash when regional rows or population columns are unavailable.",
        "OpenPower 0–14 population share.",
    ),
    "frmPopulation/txt1565Ratio": _country_info_binding(
        "derived: regions.pop_15_64 / total population × 100",
        "percent of population",
        "Em dash when regional rows or population columns are unavailable.",
        "OpenPower 15–64 population share.",
    ),
    "frmPopulation/txt65Ratio": _country_info_binding(
        "derived: regions.pop_65 / total population × 100",
        "percent of population",
        "Em dash when regional rows or population columns are unavailable.",
        "OpenPower 65+ population share.",
    ),
    "frmPopulation/txtTotalRatio": _country_info_binding(
        "literal: 100.0% when regional population data is available",
        "percent of population",
        "Em dash when regional rows or population columns are unavailable.",
        "Total population share.",
    ),
    "frmPopulation/txtBirthRate": _country_info_binding(
        "unavailable: no OpenPower birth-rate field",
        "percent rate",
        "Em dash; the OpenPower country and region schemas have no birth-rate field.",
        "REFERENCE displays m_fBirthRate × 100; this rate is unavailable in OpenPower.",
        status="verified_unavailable",
    ),
    "frmPopulation/txtDeathRate": _country_info_binding(
        "unavailable: no OpenPower death-rate field",
        "percent rate",
        "Em dash; the OpenPower country and region schemas have no death-rate field.",
        "REFERENCE displays m_fDeathRate × 100; this rate is unavailable in OpenPower.",
        status="verified_unavailable",
    ),
    "frmTerrain/txtLandArea": _country_info_binding(
        "sum(regions.area_km2) for the selected country's controlled regions",
        "km²",
        "Em dash when regional rows or the area_km2 column are unavailable.",
        "Land area summed from OpenPower regions controlled by the selected country.",
    ),
    "frmTerrain/txtWaterArea": _country_info_binding(
        "unavailable: no OpenPower water-area field",
        "km²",
        "Em dash; the OpenPower region schema has no water-area field.",
        "REFERENCE displays m_fWaterArea; water area is unavailable in OpenPower.",
        status="verified_unavailable",
    ),
    "frmTerrain/txtTotalArea": _country_info_binding(
        "unavailable: no OpenPower total-area field",
        "km²",
        "Em dash; the OpenPower region schema has no total-area field.",
        "REFERENCE displays m_fTotalArea; total area is unavailable in OpenPower.",
        status="verified_unavailable",
    ),
    "frmClimate/frmInner/lblClimate": _country_info_binding(
        "unavailable: no OpenPower climate identifier field",
        "localized climate name",
        "Em dash; OpenPower region and country schemas have no climate identifier.",
        "REFERENCE resolves m_iClimateStid to a localized climate name; OpenPower has no climate identifier.",
        status="verified_unavailable",
    ),
}
COUNTRY_INFO_BINDINGS: dict[str, DisplayBinding] = {
    f"frmInner/{path}": binding for path, binding in _COUNTRY_INFO_SLOTS.items()
}


def _country_info_caption_binding(token: str, caption: str) -> DisplayBinding:
    return DisplayBinding(
        f"literal: current English CountryMoreInfoPanel caption for GML text token {token}",
        "static English caption",
        f"{caption}; the supplied source mirror does not include the REFERENCE localization tables.",
        "Rendered from CountryMoreInfoPanel while the country information window is open.",
        "src/client/ui/panels/country_more_info.py; .codex/layout_catalog.gml",
        f"Current OpenPower caption for the {caption.lower()} source slot; exact source localization is unavailable.",
        status="partial",
        action_required="Use the exact REFERENCE localized caption only if the reference language tables are recovered.",
    )


_COUNTRY_INFO_CAPTIONS = {
    "frmLand/lblArableLand": ("101005", "ARABLE LAND"),
    "frmLand/lblUnusable": ("101008", "UNUSABLE LAND"),
    "frmLand/lblNationalParks": ("101007", "NATIONAL PARKS"),
    "frmLand/lblForests": ("101006", "FORESTS"),
    "frmClimate/lblTitle": ("101016", "CLIMATE"),
    "frmHumanDevelopment/lblTitle": ("101021", "HUMAN DEVELOPMENT"),
    "frmHumanDevelopment/lblTelecommunication": ("101023", "TELECOMMUNICATION"),
    "frmHumanDevelopment/lblInfrastructure": ("100712", "INFRASTRUCTURE"),
    "frmTerrain/lblTitle": ("101009", "TERRAIN"),
    "frmTerrain/lblWaterArea": ("101011", "WATER AREA"),
    "frmTerrain/lblTotalArea": ("101012", "TOTAL AREA"),
    "frmTerrain/lblLandArea": ("101010", "LAND AREA"),
    "frmPopulation/lblTitle": ("100308", "POPULATION"),
    "frmPopulation/lblBirthRate": ("101577", "BIRTH RATE"),
    "frmPopulation/lbl65": ("101018", "65+"),
    "frmPopulation/lblDeathRate": ("101578", "DEATH RATE"),
    "frmPopulation/lblTotal": ("100050", "TOTAL"),
    "frmPopulation/lbl1565": ("101019", "15–64"),
    "frmPopulation/lbl15": ("101020", "0–14"),
}
COUNTRY_INFO_BINDINGS.update({
    f"frmInner/{path}": _country_info_caption_binding(token, caption)
    for path, (token, caption) in _COUNTRY_INFO_CAPTIONS.items()
})
COUNTRY_INFO_BINDINGS["frmTitle/lblTitle"] = DisplayBinding(
    "resolve_country_name(state, target_tag).upper()",
    "localized country name in uppercase",
    "Country tag or 'Unknown' when the country name cannot be resolved.",
    "Resolved from the current country tables on each CountryMoreInfoPanel render.",
    "src/client/ui/panels/country_more_info.py; src/client/ui/panels/shared/panel_data.py; .codex/layout_catalog.gml",
    "OpenPower uses the selected country name as the title. The source GML title token is localized separately, so exact title-string equivalence is not asserted.",
    status="partial",
    action_required="Keep the selected country identity visible and retain the source-title localization difference.",
)
_WAR_LIST_LABEL_BINDINGS = {
        "frmTitle/lblTitle": DisplayBinding(
            "literal: English title equivalent of GML text token 101608",
            "static English caption",
            "War List; the repository does not include the REFERENCE localization bundle.",
            "Static title rendered in the GML title slot on each visible frame.",
            "src/client/ui/panels/military/war_list_panel.py; .codex/layout_catalog.gml",
            "War-list window title.",
            status="partial",
            action_required="Add exact translations when the reference REFERENCE language tables are available.",
        ),
        "frmInner/frmWarList/txtTransparentLabel1": DisplayBinding(
            "literal: English equivalent of GML text token 100068",
            "static English caption",
            "Country; the repository does not include the REFERENCE localization bundle.",
            "Static column caption rendered in the source slot on each visible frame.",
            "src/client/ui/panels/military/war_list_panel.py; .codex/layout_catalog.gml",
            "Leader-country column header.",
            status="partial",
            action_required="Add exact translations when the reference REFERENCE language tables are available.",
        ),
        "frmInner/frmWarList/txtTransparentLabel2": DisplayBinding(
            "literal: English equivalent of GML text token 101522; the source row names the paired value txtNbAllies",
            "static English caption",
            "Allies; the repository does not include the REFERENCE localization bundle.",
            "Static column caption rendered above the attacking-side ally count.",
            "src/client/ui/panels/military/war_list_panel.py; .codex/layout_catalog.gml",
            "Attacking coalition ally-count column header.",
            status="partial",
            action_required="Add exact translations when the reference REFERENCE language tables are available.",
        ),
        "frmInner/frmWarList/txtTransparentLabel3": DisplayBinding(
            "literal: English equivalent of GML text token 101522; the source row names the paired value txtNbAllies1",
            "static English caption",
            "Allies; the repository does not include the REFERENCE localization bundle.",
            "Static column caption rendered above the defending-side ally count.",
            "src/client/ui/panels/military/war_list_panel.py; .codex/layout_catalog.gml",
            "Defending coalition ally-count column header.",
            status="partial",
            action_required="Add exact translations when the reference REFERENCE language tables are available.",
        ),
        "frmInner/frmWarList/txtTransparentLabel4": DisplayBinding(
            "literal: English equivalent of GML text token 100068",
            "static English caption",
            "Country; the repository does not include the REFERENCE localization bundle.",
            "Static column caption rendered in the source slot on each visible frame.",
            "src/client/ui/panels/military/war_list_panel.py; .codex/layout_catalog.gml",
            "Defending leader-country column header.",
            status="partial",
            action_required="Add exact translations when the reference REFERENCE language tables are available.",
        ),
        "frmInner/frmWarDetails/txtTransparentLabel1": DisplayBinding(
            "literal: English equivalent of GML text token 100068",
            "static English caption",
            "Country; the repository does not include the REFERENCE localization bundle.",
            "Static detail-column caption rendered on each visible frame.",
            "src/client/ui/panels/military/war_list_panel.py; .codex/layout_catalog.gml",
            "Attacking coalition leader column header.",
            status="partial",
            action_required="Add exact translations when the reference REFERENCE language tables are available.",
        ),
        "frmInner/frmWarDetails/txtTransparentLabel2": DisplayBinding(
            "literal: English equivalent of GML text token 100077",
            "static English caption",
            "Status; the repository does not include the REFERENCE localization bundle.",
            "Static detail-column caption rendered on each visible frame.",
            "src/client/ui/panels/military/war_list_panel.py; .codex/layout_catalog.gml",
            "Attacking coalition intent/status column header.",
            status="partial",
            action_required="Add exact translations when the reference REFERENCE language tables are available.",
        ),
        "frmInner/frmWarDetails/txtTransparentLabel3": DisplayBinding(
            "literal: English equivalent of GML text token 100077",
            "static English caption",
            "Status; the repository does not include the REFERENCE localization bundle.",
            "Static detail-column caption rendered on each visible frame.",
            "src/client/ui/panels/military/war_list_panel.py; .codex/layout_catalog.gml",
            "Defending coalition intent/status column header.",
            status="partial",
            action_required="Add exact translations when the reference REFERENCE language tables are available.",
        ),
        "frmInner/frmWarDetails/txtTransparentLabel4": DisplayBinding(
            "literal: English equivalent of GML text token 100068",
            "static English caption",
            "Country; the repository does not include the REFERENCE localization bundle.",
            "Static detail-column caption rendered on each visible frame.",
            "src/client/ui/panels/military/war_list_panel.py; .codex/layout_catalog.gml",
            "Defending coalition leader column header.",
            status="partial",
            action_required="Add exact translations when the reference REFERENCE language tables are available.",
        ),
        "frmInner/frmWarDetails/txtTransparentLabel5": DisplayBinding(
            "literal: English equivalent of GML text token 100115",
            "static English caption",
            "vs.; the repository does not include the REFERENCE localization bundle.",
            "Static center separator rendered in the source detail slot.",
            "src/client/ui/panels/military/war_list_panel.py; .codex/layout_catalog.gml",
            "Separator between the attacking and defending leader rows.",
            status="partial",
            action_required="Add exact translations when the reference REFERENCE language tables are available.",
        ),
}
DISPLAY_BINDINGS_BY_WINDOW = {
    "Load_Saved_Game": {
        "frmTitle/lblTitle": _save_load_caption_binding(
            "Load_Saved_Game", "100007", "LOAD GAME", "Load dialog title."
        ),
        "frmInner/frmList/lblSavegame": _save_load_caption_binding(
            "Load_Saved_Game", "101651", "SAVE GAME", "Save-slot name column header."
        ),
        "frmInner/frmList/lblScenarios": _save_load_caption_binding(
            "Load_Saved_Game", "100144", "SCENARIO", "Scenario-name column header."
        ),
        "frmInner/frmList/lblDate": _save_load_caption_binding(
            "Load_Saved_Game", "101652", "DATE", "Save timestamp column header."
        ),
        "frmInner/frmList/lblGametime": _save_load_caption_binding(
            "Load_Saved_Game", "102140", "GAME TIME", "Saved simulation time column header."
        ),
        "frmInner/frmList/lblCountry": _save_load_caption_binding(
            "Load_Saved_Game", "100068", "COUNTRY", "Saved country column header."
        ),
        "frmInner/frmList/lstGames": DisplayBinding(
            "SaveGameDialog._rows from list_available_saves(GameConfig)",
            "local save metadata rows",
            "No saved games.",
            "Reloaded when SaveGameDialog.toggle(\"load\") opens the load dialog.",
            "src/core/saves.py; src/client/ui/components/shared/save_game_dialog.py; .codex/Client/Source/reference_load_game_window.cpp",
            "Rows show save name, timestamp, scenario, country tag, and game time. REFERENCE filters by game type and uses a country flag; OpenPower lists available local saves and displays the country tag.",
            status="partial",
            action_required="Keep metadata tied to available local save files; reproduce REFERENCE game-type filtering only if OpenPower adds matching save-type metadata.",
        ),
    },
    "Save_Game_Window": {
        "frmTitle/lblTitle": _save_load_caption_binding(
            "Save_Game_Window", "101655", "SAVE GAME", "Save dialog title."
        ),
        "frmInner/frmSave/lblDate": _save_load_caption_binding(
            "Save_Game_Window", "101652", "DATE", "Existing save timestamp column header."
        ),
        "frmInner/frmSave/lblSaveName": _save_load_caption_binding(
            "Save_Game_Window", "101656", "SAVE NAME", "Save-name input label."
        ),
        "frmInner/frmSave/lblCountry": _save_load_caption_binding(
            "Save_Game_Window", "100068", "COUNTRY", "Existing save country column header."
        ),
        "frmInner/frmSave/lblGametime": _save_load_caption_binding(
            "Save_Game_Window", "102140", "GAME TIME", "Existing save simulation-time column header."
        ),
        "frmInner/frmSave/lblSavegame": _save_load_caption_binding(
            "Save_Game_Window", "101651", "SAVE GAME", "Existing save-slot name column header."
        ),
        "frmInner/frmSave/lblScenarios": _save_load_caption_binding(
            "Save_Game_Window", "100144", "SCENARIO", "Existing save scenario column header."
        ),
        "frmInner/frmSave/lstSaves": DisplayBinding(
            "SaveGameDialog._rows from list_available_saves(GameConfig)",
            "local save metadata rows",
            "No saved games.",
            "Reloaded when SaveGameDialog.toggle(\"save\") opens the save dialog.",
            "src/core/saves.py; src/client/ui/components/shared/save_game_dialog.py; .codex/Client/Source/reference_save_game_window.cpp",
            "Selecting an existing row fills the save-name input. Rows show save name, timestamp, scenario, country tag, and game time; OpenPower lists available local saves and displays country tags instead of source flags.",
            status="partial",
            action_required="Keep the save-name prefill and metadata columns; match REFERENCE mode filtering and flag assets only if OpenPower gains the same save metadata.",
        ),
    },
    "Strategic_Alert_Window": {
        "frmMessage/txtCountry": DisplayBinding(
            "none (inactive source template)",
            "unavailable source country label",
            "No alert country is available because the source class and runtime route are commented out.",
            "Not rendered in the supplied REFERENCE runtime mirror.",
            ".codex/Client/Source/reference_strategic_alert_window.cpp; .codex/layout_catalog.gml",
            "Country label in an inactive source alert card; it is not a live OpenPower field.",
            status="verified_unavailable",
            action_required="Keep the label unavailable unless an active source class and runtime route are recovered.",
        ),
        "frmMessage/txtMessage": DisplayBinding(
            "none (inactive source template)",
            "unavailable source alert text",
            "No alert message is available because the source class and runtime route are commented out.",
            "Not rendered in the supplied REFERENCE runtime mirror.",
            ".codex/Client/Source/reference_strategic_alert_window.cpp; .codex/layout_catalog.gml",
            "Message slot in an inactive source alert card; OpenPower strategic outcomes use their own authoritative feedback.",
            status="verified_unavailable",
            action_required="Keep the alert message unavailable unless an active source class and runtime route are recovered.",
        ),
        "frmFlag/frmTrim/picFlag": DisplayBinding(
            "none (inactive source template)",
            "unavailable source flag asset",
            "No alert flag is loaded because the source class and runtime route are commented out.",
            "Not rendered in the supplied REFERENCE runtime mirror.",
            ".codex/Client/Source/reference_strategic_alert_window.cpp; .codex/layout_catalog.gml",
            "Country-flag picture slot in an inactive source alert card.",
            status="verified_unavailable",
            action_required="Keep the flag asset unavailable unless an active source class and runtime route are recovered.",
        ),
    },
    "Strategic_News_Window": {
        "txtNews": DisplayBinding(
            "none (inactive source template)",
            "unavailable source text",
            "No ticker value is available because the source window class and runtime route are commented out.",
            "Not rendered in the supplied REFERENCE runtime mirror.",
            ".codex/Client/Source/reference_strategic_news_window.cpp; .codex/layout_catalog.gml",
            "Ticker slot in an inactive source template; it is separate from OpenPower's NEWS_LOG Event Feed.",
            status="verified_unavailable",
            action_required="Keep the ticker unavailable unless an active source class and runtime spawn/callback route are recovered.",
        ),
    },
    "Covert_Actions_Cell_Creation": {
        "frmInner/frmCell/lblCellName": DisplayBinding(
            "literal: English equivalent of GML text token 101036",
            "static English caption",
            "Cell name; the supplied source mirror has no REFERENCE localization tables.",
            "Static caption placed in the source label slot while the dialog is open.",
            "src/client/ui/panels/military/covert_action_windows.py; .codex/layout_catalog.gml",
            "Name of the new cell.",
            status="partial",
            action_required="Use the exact REFERENCE translation only if the reference language tables are recovered; preserve this GML slot.",
        ),
        "frmInner/frmCell/lblCountry": DisplayBinding(
            "literal: English equivalent of GML text token 101035",
            "static English caption",
            "Target country; OpenPower lists foreign target countries for this action.",
            "Static caption rendered beside the current local target-country selection.",
            "src/client/ui/panels/military/covert_action_windows.py; .codex/layout_catalog.gml",
            "The OpenPower field is target_country_tag; its available choices follow the OpenPower covert-cell contract.",
            status="partial",
            action_required="Use the exact REFERENCE translation only if the reference language tables are recovered; keep the OpenPower target-country meaning explicit.",
        ),
        "frmInner/frmCell/lblTraining": DisplayBinding(
            "literal: English equivalent of GML text token 101055",
            "static English caption",
            "Training level; the available values use OpenPower covert skill levels.",
            "Static caption rendered beside the selected Recruit, Regular, Veteran, or Elite value.",
            "src/client/ui/panels/military/covert_action_windows.py; modules/base/systems/military/covert_policy.py; .codex/layout_catalog.gml",
            "OpenPower skill level is passed on ActionCreateCovertCell and applied to the new cell.",
            status="partial",
            action_required="Use the exact REFERENCE translation only if the reference language tables are recovered.",
        ),
        "frmInner/frmCell/cboTraining": DisplayBinding(
            "local CovertActionWindows._create_training_level from SKILL_LEVELS",
            "OpenPower covert skill level",
            "Recruit when the creation dialog opens.",
            "Changing the selection updates the creation quote and the level sent with ActionCreateCovertCell; the authoritative system validates the level.",
            "src/client/ui/panels/military/covert_action_windows.py; modules/base/systems/military/covert_policy.py; modules/base/systems/military/covert_operations_system.py",
            "REFERENCE selects its cell training enum. OpenPower uses the same four visible names as skill levels, with OpenPower-specific skills, costs, upkeep, and route travel.",
            status="partial",
            action_required="Keep the selector and creation action on the same SKILL_LEVELS contract; do not copy REFERENCE pricing or calendar formulas.",
        ),
        "frmInner/frmCell/lblSetupCost": DisplayBinding(
            "literal: English equivalent of GML text token 101056",
            "static English caption",
            "Setup cost; the supplied source mirror has no REFERENCE localization tables.",
            "Static caption for the current OpenPower setup-cost quote.",
            "src/client/ui/panels/military/covert_action_windows.py; .codex/layout_catalog.gml",
            "The source setup-cost formula is unavailable; OpenPower shows its authoritative flat covert_cell_creation_cost.",
            status="partial",
            action_required="Use the exact REFERENCE translation only if the reference language tables are recovered.",
        ),
        "frmInner/frmCell/txtCost": DisplayBinding(
            "state.globals.covert_cell_creation_cost with OpenPower default 10.0",
            "whole USD setup cost",
            "Unavailable only when no quote can be constructed; otherwise the active scenario value or $10 default.",
            "Read by CovertOperationsSystem.quote_cell_creation for the current level/target selection; OpenPower charges this same flat amount on creation.",
            "src/client/ui/panels/military/covert_action_windows.py; modules/base/systems/military/covert_operations_system.py; modules/base/schema.py",
            "OpenPower's per-cell setup cost does not vary by selected skill level because no tier multiplier exists in its creation rules.",
            status="verified_openpower",
        ),
        "frmInner/frmCell/lblUpkeep": DisplayBinding(
            "literal: English equivalent of GML text token 101057",
            "static English caption",
            "Upkeep / day; the supplied source mirror has no REFERENCE localization tables.",
            "Static caption for the current OpenPower daily-upkeep quote.",
            "src/client/ui/panels/military/covert_action_windows.py; .codex/layout_catalog.gml",
            "OpenPower charges recurring covert-cell upkeep at the selected skill profile's upkeep multiplier.",
            status="partial",
            action_required="Use the exact REFERENCE translation only if the reference language tables are recovered.",
        ),
        "frmInner/frmCell/txtUpkeep": DisplayBinding(
            "state.globals.covert_cell_upkeep × skill_profile(training_level).upkeep_multiplier",
            "USD per simulation day",
            "The scenario base upkeep (0.25 by default) times the selected profile; unavailable if the quote cannot be constructed.",
            "Recomputed when the target or skill selection changes; the system stores the same base and selected-level upkeep when creating the cell.",
            "src/client/ui/panels/military/covert_action_windows.py; modules/base/systems/military/covert_policy.py; modules/base/systems/military/covert_operations_system.py",
            "REFERENCE's native upkeep modifiers are not copied; this value follows OpenPower's skill profile.",
            status="verified_openpower",
        ),
        "frmInner/frmCell/lblTime": DisplayBinding(
            "literal: English equivalent of GML text token 101058",
            "static English caption",
            "Deployment time; the supplied source mirror has no REFERENCE localization tables.",
            "Static caption for the route-based OpenPower arrival estimate.",
            "src/client/ui/panels/military/covert_action_windows.py; .codex/layout_catalog.gml",
            "OpenPower cells become available after their planned route rather than an REFERENCE training-month timer.",
            status="partial",
            action_required="Use the exact REFERENCE translation only if the reference language tables are recovered.",
        ),
        "frmInner/frmCell/txtTime": DisplayBinding(
            "CovertOperationsSystem.quote_cell_creation route plan and RegionTravelTime estimates",
            "route-based travel time in days/hours",
            "Immediate for an in-country cell; No legal route if no current deployment route is available.",
            "Recomputed when target or training selection changes; Confirm revalidates route and timing in the authoritative system.",
            "src/client/ui/panels/military/covert_action_windows.py; modules/base/systems/military/covert_operations_system.py; modules/base/systems/military/region_travel_time.py",
            "REFERENCE reports an initial training duration in months. OpenPower displays the authoritative geography-based deployment time instead.",
            status="verified_openpower",
        ),
    },
    "Country_Information_Window": COUNTRY_INFO_BINDINGS,
    "Constitutional_Form": {
        "frmInner/frmCapital/cboCapital": DisplayBinding(
            "country_governments.capital_region_id joined to regions.id/name; choices limited to current control",
            "capital region name",
            "Unknown when no valid capital region is stored; the current capital stays visible even if control changed.",
            "Read from the authoritative government row on each render; selection remains a local draft until Apply dispatches ActionSetCountryCapital.",
            "src/client/ui/panels/politics/constitutional_form_panel.py; src/shared/region_control.py; modules/base/schema.py",
            "OpenPower stores a region capital; the source can display a city when its city catalog is available.",
            status="partial",
            action_required="Keep selectable options restricted to current OpenPower control and do not replace the region-level field with an inferred city.",
        ),
        "frmInner/frmNextElection/lblElectionDate": DisplayBinding(
            "country_governments.next_election",
            "date text",
            "Unscheduled when the stored display value is empty.",
            "Read from the current government row on each render.",
            "src/client/ui/panels/politics/constitutional_form_panel.py; src/client/ui/panels/politics/presenter.py; modules/base/schema.py",
            "OpenPower displays its stored date text; REFERENCE formats its native GDateTime value.",
            status="partial",
            action_required="Preserve the stored OpenPower date and avoid converting election minutes to an inferred calendar date.",
        ),
        "frmInner/frmConstitutionalForm/cboConstitutionalForm": DisplayBinding(
            "country_governments.government_type with government_form_rules.display_name options",
            "current government-form label",
            "Current government type or Unavailable when no government row exists.",
            "Current value is read from the authoritative government row; compatible target forms are filtered by current eligible-party count and crisis status, staged locally, then submitted with the expected current form.",
            "src/client/ui/panels/politics/constitutional_form_panel.py; src/client/ui/panels/politics/presenter.py; modules/base/schema.py",
            "OpenPower form labels and transition rules are authoritative for this selector but are not mapped one-to-one to the REFERENCE numeric government-type catalog.",
            status="partial",
            action_required="Keep options constrained by OpenPower rules and define an explicit REFERENCE-to-OpenPower type map only if authoritative mappings become available.",
        ),
    },
    "Increase_Production_Window": {
        "frmTitle/lblTitle": DisplayBinding(
            "literal: English equivalent of GML text token 100079",
            "static English caption",
            "Increase production; the repository does not include the REFERENCE localization bundle.",
            "Static caption rendered in the source title slot while the dialog is open.",
            "src/client/ui/components/shared/increase_production_dialog.py; .codex/layout_catalog.gml",
            "English equivalent of the source title token; exact localized wording is unavailable.",
            status="partial",
            action_required="Use the reference REFERENCE translation only if its language tables are recovered; keep the English fallback explicit.",
            surface="ResourcesPanel/IncreaseProductionDialog GML title frame",
        ),
        **{
            f"frmInner/frmInner/txtIncrease{percent}": DisplayBinding(
                "derived: production_increase_basis(state, country, resource) × percentage × USD value scale",
                "USD investment estimate",
                "Unavailable without an unambiguous positive production basis; regional output requires at least one row in a region currently controlled by the selected country.",
                "Recomputed from the current GameState on each dialog render. OpenPower prices one year of added output value; labels show whole USD and tooltips retain cents.",
                "src/client/ui/components/shared/increase_production_dialog.py; src/shared/resource_production_policy.py; modules/base/schema.py",
                "The percentage and eligible production basis are authoritative OpenPower data, but the one-year valuation is OpenPower-specific because the REFERENCE IncreaseProductionApproxCost body is absent from the supplied source mirror.",
                status="partial",
                action_required="Keep the estimate labeled as OpenPower-specific and replace or reconcile it only if the reference REFERENCE formula is recovered.",
                surface="ResourcesPanel/IncreaseProductionDialog.render",
            )
            for percent in (1, 2, 5, 10, 25)
        },
    },
    "Unit_Production_Window": {
        "frmDesignList/frmEta/txtEta": DisplayBinding(
            "derived: initial_production_eta_days(selected domestic ActionQueueUnitProduction priority)",
            "days",
            "N/A without a selected domestic design; foreign orders remain N/A until the producer accepts the request.",
            "Recomputed from the selected build priority on each render; the shared production policy recalculates accepted-order ETA as capacity is allocated.",
            "src/client/ui/panels/military/unit_production_panel.py; modules/base/systems/military/production_policy.py; modules/base/systems/military/research_program_system.py",
            "Provisional domestic queue ETA from the same priority rule used by the authoritative production action; it does not model REFERENCE Fast speed.",
            status="verified_openpower",
        ),
    },
    "Unit_Buy_Used_Window": {
        "frmBorder/frmInner/frmDesignList/cboUnitType": DisplayBinding(
            "unit_market_listings joined to unit_designs; distinct canonical class_name roles (unit_type fallback)",
            "OpenPower unit-role labels",
            "Disabled selector with No eligible unit types when no eligible listing exists.",
            "Rebuilt from the selected-country market snapshot; changing type clears the local listing and quantity selection.",
            "src/client/ui/panels/military/unit_market_panel.py; src/client/ui/panels/military/presenter.py; modules/base/systems/military/capability_catalog.py",
            "All 20 REFERENCE EUnitType IDs and their order map to canonical OpenPower roles; labels use English enum names because source localization bundles are unavailable. An OpenPower-only role is appended explicitly.",
            status="partial",
            action_required="Keep the source-ID mapping and eligible-list filter covered; use source-localized labels only when the language bundle is available.",
        ),
        "frmBorder/frmInner/frmDesignList/lstUnits": DisplayBinding(
            "unit_market_listings rows joined to unit_designs by design_id; listing quantity, design display_name, seller and eligibility",
            "available listed unit count and design name",
            "Explicit no-eligible-listings state when the selected role has no visible listing.",
            "Filtered by the selected country, OpenPower weapons-trade permissions and selected canonical role on each render.",
            "src/client/ui/panels/military/unit_market_panel.py; src/client/ui/panels/military/presenter.py; modules/base/schema.py",
            "Selecting a row updates local design details and purchase quantity; it sends no action.",
            status="partial",
            action_required="Keep seller eligibility, listing selection and row content synchronized with the current OpenPower snapshot.",
        ),
        "frmBorder/frmInner/frmDesignList/edtUnitName": DisplayBinding(
            "unit_market_listings.seller_country_id -> countries.id/name",
            "localized seller country name",
            "Seller country tag when a localized country name is unavailable; em dash without a selected listing.",
            "Updated from the selected listing on each render.",
            "src/client/ui/panels/military/unit_market_panel.py; src/client/ui/panels/military/presenter.py; modules/base/schema.py",
            "Read-only seller value displayed in the source field slot.",
        ),
        "frmBorder/frmInner/frmDesignList/edtUnitName1": DisplayBinding(
            "unit_market_listings.price; default is 0.75 × the stored OpenPower unit cost at listing creation",
            "currency per listed unit",
            "Em dash without a selected listing; seller-set price is authoritative and is not discounted a second time.",
            "Set by ForeignOrderSystem when the listing is created, then read from the selected listing; displayed at whole-currency precision.",
            "Client/Source/reference_used_unit_window.cpp; includes/common_lib/reference_constants.h; modules/base/systems/military/foreign_order_system.py; src/client/ui/panels/military/unit_market_panel.py; tests/test_foreign_order_system.py",
            "OpenPower's default 0.75 factor matches the REFERENCE used-unit rebate; seller-set prices and stored reference-cost basis are OpenPower market semantics.",
            status="partial",
            action_required="Keep the default factor tested, preserve seller-provided listing prices, and do not apply the rebate again in the buyer UI.",
        ),
        "frmBorder/frmInner/frmDesignList/frmUpdatableValue1/edtText": DisplayBinding(
            "local UnitMarketPanel quantity selection bounded by the selected listing quantity",
            "units",
            "Disabled with zero when no listing is selected.",
            "Selection starts at the full available listing quantity; edits are clamped to 1..listing.quantity and total price is recomputed immediately.",
            "src/client/ui/panels/military/unit_market_panel.py; tests/ui/journeys/reference-military-market.json",
            "Python preserves the source 1/10/100 hold thresholds and accelerated repeat cadence; the live OpenPower listing supplies the current maximum.",
            status="verified_openpower",
            action_required="Keep the listing bound and source hold cadence covered by the quantity journeys.",
        ),
        "frmBorder/frmInner/frmDesignList/edtUnitName2": DisplayBinding(
            "selected unit_market_listings.price multiplied by the local selected quantity",
            "total currency price",
            "Em dash without a selected listing.",
            "Recomputed immediately whenever the selected listing or quantity changes.",
            "Client/Source/reference_used_unit_window.cpp; modules/base/systems/military/foreign_order_system.py; src/client/ui/panels/military/unit_market_panel.py; modules/base/schema.py",
            "Uses the listing's price, which includes the default 0.75 resale factor once when created; custom OpenPower listing prices are not rebated again.",
            status="verified_openpower",
            action_required="Keep the total synchronized with listing price and quantity; never apply a second rebate in the buyer panel.",
        ),
        "frmDesignView/frmUnitName/edtUnitName": DisplayBinding(
            "selected unit_market_listings.design_id -> unit_designs.display_name",
            "unit design name",
            "Em dash when the selected listing has no saved design row.",
            "Updated from the selected listing and its design row on each render.",
            "src/client/ui/panels/military/unit_market_panel.py; modules/base/schema.py",
            "The GML txtRectFrame node is used as a read-only design-name field, matching GUsedUnitWindow's GLabel binding.",
        ),
        "frmDesignView/frm3dModel/lblDescription": DisplayBinding(
            "unavailable: OpenPower has no unit-design 3D scene/model-variation assets",
            "visual model preview",
            "Explicit unavailable message in the source model preview frame.",
            "Static availability notice; does not imply that a model was loaded.",
            "src/client/ui/panels/military/unit_market_panel.py; .codex/Client/Source/reference_used_unit_window.cpp",
            "The source builds a GUnitViewScene; OpenPower has no corresponding visual assets or variation payload.",
            status="verified_unavailable",
            action_required="Retain the explicit unavailable preview until equivalent model assets and variations are available.",
        ),
        **{
            f"frmDesignView/frmUnitSpecs/frmList/frmInner/lbl{component}": DisplayBinding(
                f"literal capability label for unit_designs.capabilities_json.{key}",
                "label",
                "The source metric label remains visible even when its value is unavailable.",
                "Static source-positioned label.",
                "src/client/ui/panels/military/unit_market_panel.py; .codex/Client/Source/reference_used_unit_window.cpp",
                "Capability names follow the source metric rows; units/scales are documented in the corresponding meter binding.",
            )
            for component, key in (
                ("GunRange", "gun_range"), ("GunPrecision", "gun_precision"),
                ("GunDamage", "gun_damage"), ("MissileRange", "missile_range"),
                ("MissilePrecision", "missile_precision"), ("MissileDamage", "missile_damage"),
                ("MissilePayload", "missile_payload"), ("Speed", "speed"),
                ("Stealth", "stealth"), ("Countermeasures", "countermeasures"),
                ("Armor", "armor"), ("Sensors", "sensors"),
            )
        },
        **{
            f"frmDesignView/frmUnitSpecs/frmList/frmInner/frm{component}": DisplayBinding(
                f"unit_designs.capabilities_json.{key}",
                "OpenPower capability value and role-specific capability scale",
                "N/A when the selected design has no saved capability value; Speed is N/A because REFERENCE combines speed and maneuverability while OpenPower stores them separately.",
                "Read from the selected design; progress fraction uses that OpenPower capability's declared bounds.",
                "src/client/ui/panels/military/unit_market_panel.py; src/client/ui/panels/military/unit_design_widgets.py; modules/base/systems/military/capability_catalog.py",
                "The source meters use a 0-10 range; OpenPower values and bounds are not always scale-equivalent.",
                status="verified_unavailable" if key == "speed" else "partial",
                action_required="Do not derive unavailable source-equivalent values from unrelated OpenPower fields; retain N/A for combined speed and show stored values with their OpenPower scale.",
            )
            for component, key in (
                ("GunRange", "gun_range"), ("GunPrecision", "gun_precision"),
                ("GunDamage", "gun_damage"), ("MissileRange", "missile_range"),
                ("MissilePrecision", "missile_precision"), ("MissileDamage", "missile_damage"),
                ("MissilePayload", "missile_payload"), ("Speed", "speed"),
                ("Stealth", "stealth"), ("Countermeasures", "countermeasures"),
                ("Armor", "armor"), ("Sensors", "sensors"),
            )
        },
    },
    "Covert_Actions_Window": {
        **{
            path: DisplayBinding(binding, units, fallback,
                "Read from the current own-country snapshot every render. CovertOperationsSystem advances preparation/training on actions and game-time boundaries; selection remains local.",
                "src/client/ui/panels/military/covert_ops_panel.py; src/client/ui/panels/military/covert_selection.py; modules/base/systems/military/covert_operations_system.py; modules/base/schema.py; tests/test_covert_selection.py; tests/test_covert_operations_system.py",
                meaning)
            for path, binding, units, fallback, meaning in (
            ("frmInner/frmCell/lstCell", "covert_cells filtered by controlled country_id; id, cell_name, target_country_id, status, skill_level, upkeep; selected covert_missions.preparation_progress or cell training_progress/training_required/readiness",
             "owned cell records; progress as percent; configured currency per day",
             "Empty own roster has an explicit message; foreign private rosters are withheld; unavailable progress is zero, never a foreign intelligence estimate.",
             "Source cell-list frame uses the exported lstCovertActionsItem 681x16 row rectangles and text offsets."),
            ("frmInner/frmMission/txtMission", "selected covert_missions.mission_type by selected cell id, preferring an active mission",
             "mission type name", "Em dash when the selected cell has no recorded mission; full long names remain in the fit-text tooltip.",
             "Mission belonging to the selected cell, including an exact ready-mail request rather than the first roster entry."),
            ("frmInner/frmMission/txtSector", "selected covert_missions.target_sector; mission profile fallback for legacy records",
             "Civilian, Military or Political category", "Em dash without a selected mission.",
             "Saved covert_missions.target_sector, with the mission profile as a legacy fallback."),
            ("frmInner/frmMission/txtComplexity", "selected covert_missions.complexity",
             "mission complexity", "Em dash without a selected mission; Not recorded for a legacy mission without a saved complexity.",
             "Selected source complexity is persisted at preparation and applies the source success and effect multipliers; the base probability still uses OpenPower inputs."),
            ("frmInner/frmMission/txtResourceUnit", "selected covert_missions.target_resource_id or target_unit_category",
             "OpenPower resource name or source unit category", "Em dash without a selected mission; Not recorded for a legacy mission without a saved target.",
             "Civilian target resource is validated against the target country’s OpenPower rows and changes production across controlled regions; a specific target applies the source success penalty. Military sabotage filters OpenPower units by selected domain. REFERENCE's per-characteristic military espionage/sabotage research effects remain unavailable."),
            ("frmInner/frmMission/txtFramedCountry", "selected covert_missions.framed_country_id -> countries.id/name",
             "localized country name or None", "Em dash without a selected mission; None when no country was framed.",
             "Stored attribution choice is visible to the owning country; framed third-party outcome views remain redacted."),
            ("frmInner/frmUpkeep/txtUpkeep", "sum of own non-retired/non-captured/non-lost covert_cells.upkeep",
             "configured roster upkeep in currency per day (not actual charged expenditure)",
             "Zero for an empty owned roster; Unknown for a foreign country. Tooltip distinguishes configured upkeep from state-dependent charges.",
              "Configured roster upkeep quote; source protection uses the separate OpenPower coverage estimate below."),
            )
        },
        "frmTitle/lblTitle": _covert_caption_binding(
            "100024", "COVERT OPS", "CovertOpsPanel.render / WindowManager GML title"
        ),
        "frmInner/frmCell/lblTitle": _covert_caption_binding(
            "101033", "COVERT CELLS", "CovertOpsPanel._render_content"
        ),
        "frmInner/frmCell/lblName": _covert_caption_binding(
            "101036", "NAME", "CovertOpsPanel._render_content"
        ),
        "frmInner/frmCell/lblCountry": _covert_caption_binding(
            "101035", "ASSIGNED COUNTRY", "CovertOpsPanel._render_content"
        ),
        "frmInner/frmCell/lblStatus": _covert_caption_binding(
            "100077", "STATUS", "CovertOpsPanel._render_content"
        ),
        "frmInner/frmCell/lblUpkeep": _covert_caption_binding(
            "101034", "UPKEEP / DAY", "CovertOpsPanel._render_content"
        ),
        "frmInner/frmUpkeep/lblProtection": _covert_caption_binding(
            "101607", "PROTECTION", "CovertOpsPanel._render_content"
        ),
        "frmInner/frmUpkeep/lblUpkeep": _covert_caption_binding(
            "101048", "ROSTER / DAY", "CovertOpsPanel._render_content"
        ),
        "frmInner/frmMission/lblTitle": DisplayBinding(
            "CovertOpsPanel._render_mission: 'MISSION · ' plus selected cell name or fallback",
            "dynamic English caption",
            "MISSION · No selected cell",
            "Recomputed when the selected cell or mission panel selection changes.",
            "src/client/ui/panels/military/covert_ops_panel.py; .codex/layout_catalog.gml",
            "OpenPower uses the selected cell's stored name in its mission heading; exact source translation is unavailable.",
            status="partial",
            action_required="Keep the selected-cell heading current; use the exact source translation only if its language tables are recovered.",
            surface="CovertOpsPanel._render_mission",
        ),
        "frmInner/frmMission/lblType": _covert_caption_binding(
            "101043", "TYPE", "CovertOpsPanel._render_mission"
        ),
        "frmInner/frmMission/lblSector": _covert_caption_binding(
            "101044", "SECTOR", "CovertOpsPanel._render_mission"
        ),
        "frmInner/frmMission/lblComplexity": _covert_caption_binding(
            "101045", "COMPLEXITY", "CovertOpsPanel._render_mission"
        ),
        "frmInner/frmMission/lblResourceUnit": _covert_caption_binding(
            "101046", "RESOURCE / UNIT", "CovertOpsPanel._render_mission"
        ),
        "frmInner/frmMission/lblFramedCountry": _covert_caption_binding(
            "101047", "FRAMED COUNTRY", "CovertOpsPanel._render_mission"
        ),
        "frmInner/frmUpkeep/txtProtection": DisplayBinding(
            "domestic_security_coverage(active domestic-security covert_cells, country regional population, scenario globals)",
            "percent of OpenPower domestic-security coverage",
            "Unknown when owned-country regional population is unavailable; zero when population is available and no active domestic-security cells are present.",
            "Recomputed each render through the same domestic_security_coverage policy used by CovertOperationsSystem mission detection.",
            "src/client/ui/panels/military/covert_ops_panel.py; modules/base/systems/military/covert_policy.py; modules/base/systems/military/covert_operations_system.py",
            "OpenPower coverage estimate shown in the REFERENCE protection slot; it is not numerically equivalent to the source NationalSecurity formula.",
            status="partial",
            action_required="Keep the value labeled as OpenPower coverage and preserve the source formula difference in this contract.",
        ),
        "frmInner/frmCell/lblProgress": DisplayBinding(
            "Static source column heading: PROGRESS",
            "column caption",
            "English source-style caption; the reference localized source string is unavailable.",
            "Rendered each frame at the exported GML rectangle with GMLWidgets.text_at.",
            "src/client/ui/panels/military/covert_ops_panel.py; tests/ui/journeys/covert-ready-cancel.json",
            "Progress column heading; the journey asserts its source-relative position and separation from the first roster row.",
            status="partial",
            action_required="Keep the caption in its GML slot; use a localized token only when the verified source language bundle is available.",
        ),
    },
    "Budget_Window": BUDGET_BINDINGS,
    "Credits_Window": CREDITS_BINDINGS,
    "Resources_Window": RESOURCES_BINDINGS,
    "Treaty_Details_Window": {
        "frmInner/frmEligibleCountries/lstEligibleCountries": DisplayBinding(
            "countries.id/name filtered by DiplomacySystem.eligible_treaty_countries(state, current_treaty)",
            "country flag and tag; localized country name in the flag/code tooltip",
            "Empty list when no country satisfies the treaty conditions or when country data is absent; missing flags use FlagRenderer's fallback.",
            "Recomputed from current treaty conditions and diplomacy state on each visible detail render.",
            "src/client/ui/panels/politics/treaties_live.py; modules/base/systems/world/treaty_diplomacy.py; modules/base/systems/world/treaty_geography.py; src/shared/treaties.py",
            "Countries that satisfy the active treaty's current membership conditions.",
        ),
    },
    "Unit_Attack_Confirm_Window": {
        "txtCountry": DisplayBinding(
            "UnitMoveOrders.pending[expected_controller] -> countries.id/name",
            "localized country name",
            "Country tag if no localized name is available; long names are fitted with the full value in a tooltip.",
            "Captured controller identifies the queued country-specific dialog; Yes rechecks the latest units/controller/access before dispatch.",
            "src/client/controllers/unit_move_orders.py; src/client/ui/panels/military/unit_attack_confirmation.py; tests/test_unit_move_orders.py",
            "Country whose military-controlled destination prompted this confirmation.",
        ),
        **{path: DisplayBinding(
            f"UnitAttackConfirmation literal: {message}", "confirmation text",
            "English source-behavior description; no numeric placeholder.",
            "Constant while the country-specific confirmation is open.",
            "src/client/ui/panels/military/unit_attack_confirmation.py; tests/ui/journeys/reference-unit-invasion-confirm.json",
            "Explains that accepting the queued movement authorizes hostilities.",
        ) for path, message in (("txtTransparentLabel1", "Confirm military order"),
                                ("txtTransparentLabel2", "You are entering the territory of"),
                                ("txtTransparentLabel3", "This will declare war."))},
    },
    "Small_Unit_Info_Window": {
        "txt" + category: DisplayBinding(
            "selected own units.strength" if category == "I" else "selected own units.equipment_quantity",
            "personnel" if category == "I" else "equipment items",
            "Question mark for foreign groups, unknown roles or unavailable equipment counts; zero only for another known category in the same own group.",
            "Recomputed from the current selected visible group's snapshot every frame; hidden for multiple selection, dragging or a removed group.",
            "src/client/ui/panels/military/map_information.py; src/client/ui/panels/military/map_information_windows.py; src/client/views/game_view.py; tests/test_map_information.py",
            f"Selected group's category {category} quantity. OpenPower logical groups have one role; this does not claim the reference mixed equipment roster or noisy foreign intelligence model.",
        ) for category in "IGNA"
    },
    "Sphere_Control_Window": {
        path: DisplayBinding(
            binding, "localized place name",
            "Country tag when a localized name is unavailable; missing owner/region hides the frame. Missing controller uses the owner, matching OpenPower's political-map fallback.",
            "Reads the current map-hit region every frame while Tab is held outside UI/text input; follows cursor and hides on key release, UI coverage or ocean hit.",
            "src/client/ui/panels/military/map_information.py; src/client/ui/panels/military/map_information_windows.py; src/client/views/game_view.py; tests/test_map_information.py",
            meaning,
        ) for path, binding, meaning in (
            ("lblRegion", "regions.name resolved for current map-hit id", "Current map-hit region name."),
            ("frmPoliticCountry/lblCountry", "regions.owner -> countries.id/name", "Political owner, independent of occupation."),
            ("frmMilitaryCountry/lblCountry", "regions.controller -> countries.id/name", "Current military controller, including occupation."),
        )
    },
    "Battle_Info_Window": {
        f"frmInner/frmInner/frmBattleInfo/txt{category}Perc{slot}": DisplayBinding(
            f"battle_public_counts.unit_quantity where selected battle_id, side={side}, category={category}; sum of units.equipment_quantity",
            "unit quantities in the source-visible I/G/A/N categories",
            "Em dash when any side category is missing, duplicated, incomplete, null, negative, or sampled before the battle update.",
            "CombatSystem publishes post-casualty aggregates; the observer revalidates all four categories against battles.updated_at_minute each render.",
            "Client/Source/reference_battle_info_window.cpp; includes/common_lib/reference_arena_info.h; modules/base/systems/military/battle_public_counts.py; modules/base/systems/military/combat_system.py; src/client/ui/panels/military/battle_public_counts.py; src/client/ui/panels/military/battle_inspection_windows.py; tests/test_battle_public_counts.py",
            f"Published category {category} unit quantity for {'defenders' if slot == 'A' else 'attackers'}; source GActorInfo::CountUnitTypes sums m_iUnitQty, and source A/B visual order is reversed relative to authoritative attacker/defender side keys.",
            action_required="Keep published totals tied to equipment_quantity, hide stale/incomplete samples, and retain aggregate-only foreign visibility.",
        )
        for slot, side in (("A", "B"), ("B", "A")) for category in "IGAN"
    },
    "Battle_Summary_Window": {
        "frmTitle/lblTitle": DisplayBinding(
            "literal: Battle summary",
            "window title",
            "Fixed English title; exact REFERENCE localization is unavailable.",
            "Rendered by WindowManager while the result dialog is open.",
            "src/client/ui/components/shared/battle_summary_dialog.py; src/client/ui/core/containers.py; .codex/layout_catalog.gml",
            "English title for the source Battle_Summary_Window.",
            status="partial",
            action_required="Use source-localized title copy only if the REFERENCE language tables are recovered.",
        ),
        "frmInner/frmInner/frmBattleInfo/lblBattleName": DisplayBinding(
            "literal: BATTLE RESULT",
            "static caption",
            "Fixed English caption; exact REFERENCE localization is unavailable.",
            "Rendered in the battle-information frame while the result dialog is open.",
            "src/client/ui/components/shared/battle_summary_dialog.py; .codex/layout_catalog.gml",
            "Caption above the resolved battle region name.",
            status="partial",
            action_required="Use source-localized caption copy only if the REFERENCE language tables are recovered.",
        ),
        "frmInner/frmInner/frmBattleInfo/txtBattleName": DisplayBinding(
            "EventBattleEnded.region_id -> regions.id/name",
            "region name",
            "Unknown when region_id is absent or the region is not in the current snapshot.",
            "Resolved from the current region table when the result is rendered.",
            "src/client/ui/components/shared/battle_summary_dialog.py; src/client/ui/panels/shared/panel_data.py; modules/base/schema.py",
            "Region where the battle ended; OpenPower retains the region-level name rather than inferring a source city name.",
            status="partial",
            action_required="Keep region lookup tied to the result payload and preserve the explicit unknown-region fallback.",
        ),
        **{
            f"frmInner/frmInner/frmSide{pane}/lblSide": DisplayBinding(
                f"literal: {side_label}",
                "combat-side caption",
                "Fixed English caption; exact REFERENCE localization is unavailable.",
                "Pane A is the defender and pane B is the attacker, matching source combat-side order.",
                "src/client/ui/components/shared/battle_summary_dialog.py; .codex/reference-hdm-full-reference/Client/Source/reference_battle_summary_window.cpp",
                f"Source pane {pane}: {side_label.lower()}.",
                status="partial",
                action_required="Preserve defender-A/attacker-B ordering; use source-localized labels only if the language tables are recovered.",
            )
            for pane, side_label in (("A", "DEFENDERS"), ("B", "ATTACKERS"))
        },
        **{
            f"frmInner/frmInner/frmSide{pane}/lblLosses": DisplayBinding(
                f"literal: LOSSES; hover detail from EventBattleEnded.side_{event_side}_losses",
                "caption with total personnel-loss tooltip",
                "Caption remains visible when the total is unavailable; no category value is inferred from the total.",
                "The event-side total is exposed as a hover detail; source category slots remain independently bound.",
                "src/client/ui/components/shared/battle_summary_dialog.py; src/shared/events.py; .codex/reference-hdm-full-reference/Client/Source/reference_battle_summary_window.cpp",
                "Losses heading for the source pane; OpenPower's event total is personnel casualties, not an infantry count.",
                status="partial",
                action_required="Keep aggregate totals out of category slots and retain the explicit OpenPower personnel-loss unit.",
            )
            for pane, event_side in (("A", "b"), ("B", "a"))
        },
        **{
            f"frmInner/frmInner/frmSide{pane}/lbl{category}": DisplayBinding(
                f"literal category code {category}",
                "unit-category code",
                "The source code remains visible; exact localized category naming is unavailable.",
                "Rendered in the source category row on every visible result frame.",
                "src/client/ui/components/shared/battle_summary_dialog.py; .codex/layout_catalog.gml",
                f"Source casualty category abbreviation {category}.",
                status="partial",
                action_required="Keep the source category row order and use source-localized labels only if the language tables are recovered.",
            )
            for pane in ("A", "B") for category in "IGAN"
        },
        **{
            f"frmInner/frmInner/frmSide{pane}/txt{category}": DisplayBinding(
                f"battle_casualty_records for side={combat_side}, grouped by unit_type category {category}; validated against EventBattleEnded.side_{event_side}_losses",
                "OpenPower personnel casualties",
                "Em dash if casualty rows are missing, contain an unclassified unit role, or do not sum to the event-side total.",
                "Read through participant-authorized MilitaryPresenter.battle_loss_summary; category values are shown only when their total matches the result event.",
                "src/client/ui/components/shared/battle_summary_dialog.py; src/client/ui/panels/military/presenter.py; src/client/ui/panels/shared/unit_categories.py; src/shared/events.py; modules/base/schema.py",
                f"Category {category} personnel casualties for source pane {pane}. This does not claim equivalence to REFERENCE's abstract category-loss quantity.",
                status="partial",
                action_required="Never substitute a total for category data; retain the em-dash fallback when the OpenPower records do not validate.",
            )
            for pane, combat_side, event_side in (("A", "SIDE_B", "b"), ("B", "SIDE_A", "a"))
            for category in "IGAN"
        },
        **{
            f"frmInner/frmInner/frmSide{pane}/lblStatus": DisplayBinding(
                "EventBattleEnded.victor_side -> Victory/Defeat; victor_tag fallback when it matches a listed country",
                "battle outcome",
                "Unknown when the winner is absent or only a victor tag is available without a pane country mapping.",
                "Resolved from the immutable result payload when the summary is drawn.",
                "src/client/ui/components/shared/battle_summary_dialog.py; src/shared/events.py; .codex/reference-hdm-full-reference/Client/Source/reference_battle_summary_window.cpp",
                f"Winner status for source pane {pane}, using defender-A/attacker-B order.",
                status="verified_openpower",
            )
            for pane in ("A", "B")
        },
        **{
            f"frmInner/frmInner/frmSide{pane}/lstCountries": DisplayBinding(
                f"EventBattleEnded.side_{event_side}_country_ids -> battles.{battle_side}_side fallback",
                "country flag and three-letter code",
                "Not recorded when neither the result event nor battle snapshot has a country list.",
                "Rendered as clipped 16px GML rows with a country-name hover tooltip.",
                "src/client/ui/components/shared/battle_summary_dialog.py; src/client/renderers/flag_renderer.py; src/client/ui/panels/shared/panel_data.py; .codex/reference-hdm-full-reference/Client/Source/reference_battle_summary_window.cpp",
                f"Countries in source pane {pane}, preserving the source flag/code row and country-name tooltip behavior.",
                status="partial",
                action_required="Keep event-side country order authoritative and retain the explicit no-country fallback.",
            )
            for pane, event_side, battle_side in (("A", "b", "defender"), ("B", "a", "attacker"))
        },
    },
    "Event_Log": {
        "frmInner/lstEvents": DisplayBinding(
            "EventFeedPresenter.items(state): news_items + random_event_instances (+ active-event/journal fallbacks)",
            "event rows with category, country, headline, details, time, status and available response options",
            "Empty list shows an explicit no-events state; unavailable text uses presenter fallbacks and does not invent source-only event data.",
            "Rebuilt from the latest authoritative game-state snapshot on each visible render; response availability is limited to active instances and a connected client.",
            "src/client/ui/panels/service/news_panel.py; src/client/ui/panels/service/event_feed_presenter.py; src/shared/actions.py; tests/ui/journeys/reference-news.json",
            "Event_Log list rows and supported response controls.",
            action_required="Keep the journey asserting snapshot updates, row selection, category filters, region focus, response dispatch, and close.",
        ),
        "frmInner/togFilterDemographic": DisplayBinding(
            "EventFeedPresenter.counts(state)[DEMOGRAPHIC] and NewsPanel._enabled_filters[DEMOGRAPHIC]",
            "event count in tooltip; local visibility toggle",
            "Count is zero when no demographic events are present; the filter starts enabled and does not alter game state.",
            "Count is rebuilt from current feed items each render; filter state remains local to the open NewsPanel instance.",
            "src/client/ui/panels/service/news_panel.py; src/client/ui/panels/service/event_feed_presenter.py; tests/ui/journeys/reference-news.json",
            "Demographic category filter; GML numeric text token is not interpreted as user-facing copy.",
            action_required="Keep the demographic count tooltip and independent category filter journey checks passing.",
        ),
    },
    "Mail_Window": {
        "frmInner/lstMail": DisplayBinding(
            "LiveMailPanel._items_for_country: journal dispatches + messages + pending treaty proposals, filtered to the active country",
            "message subject rows; VIEW and DELETE actions follow each dynamic GML row template",
            "An explicit empty-inbox message is shown; unavailable subject text falls back to the dispatch title or Untitled dispatch.",
            "Rows are rebuilt from the current authoritative snapshot while the panel is visible. Client-session dismissals hide viewed/deleted items without mutating server state.",
            "src/client/ui/panels/service/mail_live.py; src/client/ui/panels/service/journal_dispatches.py; src/client/ui/panels/service/feed_presenter.py; src/client/ui/panels/service/mail_inbox_state.py; tests/ui/journeys/reference-mail-context.json; tests/ui/journeys/reference-mail-arrival.json",
            "OpenPower inbox combines current messages, contextual dispatches and response-required treaty proposals; the dynamic rows retain the 460×18 GML template.",
            action_required="Keep contextual VIEW routing, consume-on-view, per-row dismissal, Delete All, Escape close and incoming-event visibility journeys passing. OpenPower has no equivalent incoming-mail sound.",
        ),
    },
    "History_Window": {
        "frmInner/frmHistory/cboDisplay": DisplayBinding(
            "history_indicator_definitions.id/subject_type",
            "Source-style English labels for supported shared metrics; OpenPower names for additional measures",
            "Disabled 'No indicators available' entry when no enabled definitions exist.",
            "Definitions are read from the current snapshot; country.population is the initial country selection when available, otherwise the first enabled definition is used.",
            "src/client/ui/panels/service/history_panel.py; src/client/services/history_query_service.py; modules/base/schema.py",
            "Available OpenPower historical measure; all seventeen source metric slots use source-style labels and enum order with OpenPower-native formulas and units, while Population defaults to country.population when available.",
            action_required="Preserve all seventeen source labels and enum order. Conventional Forces sums non-strategic unit strength; Strategic Forces sums weapon quantity; Upkeep reads countries.expense_military_upkeep; Research sums track levels; Resource Balance sums complete resource_ledger.balance_usd rows by country. Keep OpenPower units explicit and retain the Population default. The source localization bundle remains unavailable.",
        ),
        "frmInner/frmHistory/frmGraph/Container": DisplayBinding(
            "history_snapshots filtered by subject_type, subject_id, indicator_id and selected minute range",
            "recorded values in the selected indicator's declared unit",
            "Explicit empty chart message when the selected range has no numeric samples; missing samples remain visible gaps.",
            "Queried from the latest GameState each visible render; the chart never interpolates missing samples.",
            "src/client/ui/panels/service/history_panel.py; src/client/services/history_query_service.py; modules/base/schema.py; tests/ui/journeys/reference-main-bar-history.json",
            "Selected OpenPower series, drawn in the GML 405x166 graph area.",
            action_required="Preserve OpenPower-native units and explicit data gaps; do not fill a missing historical sample with zero.",
        ),
        "frmInner/frmHistory/frmGraph/txtV0": DisplayBinding(
            "min(history_snapshots.value) for the selected series and range",
            "selected indicator unit; compact axis text",
            "Em dash when the selected range contains no numeric samples; full value and unit remain available by tooltip.",
            "Recomputed with the selected series on each visible render.",
            "src/client/ui/panels/service/history_panel.py; src/client/services/history_query_service.py",
            "Minimum recorded OpenPower sample in the selected range.",
        ),
        "frmInner/frmHistory/frmGraph/txtV1": DisplayBinding(
            "max(history_snapshots.value) for the selected series and range",
            "selected indicator unit; compact axis text",
            "Em dash when the selected range contains no numeric samples; full value and unit remain available by tooltip.",
            "Recomputed with the selected series on each visible render.",
            "src/client/ui/panels/service/history_panel.py; src/client/services/history_query_service.py",
            "Maximum recorded OpenPower sample in the selected range.",
        ),
        **{
            f"frmInner/frmHistory/frmGraph/txtH{index}": DisplayBinding(
                "selected range duration and current game minute",
                "relative days or months before current game time",
                "Tick labels are derived from the selected range, even when the series has no samples.",
                "Recomputed when the range or game time changes.",
                "src/client/ui/panels/service/history_panel.py",
                "Relative time tick for the selected OpenPower history range; exact source tick wording remains unresolved.",
            ) for index in range(6)
        },
    },
    "Trade_Detailed_Window": {
        "frmInner/frmSideA/txtCountry": DisplayBinding(
            "current target_tag -> countries.id/name",
            "country tag and concise trade direction",
            "Country tag when the localized name is unavailable; the GML label is fitted within its source slot.",
            "Recomputed from the active target country each visible frame.",
            "src/client/ui/panels/trade_panel.py; src/client/ui/core/panel_context.py",
            "Country giving the first side of the bilateral proposal.",
        ),
        "frmInner/frmSideB/cboCountry": DisplayBinding(
            "countries.id/name excluding the current target country",
            "localized country name and tag",
            "Disabled No trade partners option when the countries table has no counterpart.",
            "Selection remains local to the TradePanel draft and resets the package when changed.",
            "src/client/ui/panels/trade_panel.py; modules/base/schema.py",
            "Counterparty for the bilateral trade draft.",
        ),
        **{
            f"frmInner/{side}/frmItems/lstItems": DisplayBinding(
                f"TradePanel.{asset_list}: current local {direction} asset draft",
                "cash amount, territory name/tag or research branch and level",
                "An empty list remains visually empty; asset values are not inferred for territory or research.",
                "Rebuilt from the local draft on each visible render; accepted offers are owned by the server action result.",
                "src/client/ui/panels/trade_panel.py; tests/ui/journeys/bilateral-trade.json",
                f"Assets on the {direction} side of the bilateral proposal.",
            )
            for side, asset_list, direction in (
                ("frmSideA", "offered_assets", "offered"),
                ("frmSideB", "requested_assets", "requested"),
            )
        },
        "frmInner/frmBalance/lblBalance": DisplayBinding(
            "current trade action result or the cash-only balance notice",
            "status text",
            "Territory and research are explicitly unpriced; action rejection detail remains available by tooltip.",
            "Updated from the latest command result for the active player or the current proposal draft.",
            "src/client/ui/panels/trade_panel.py; modules/base/systems/world/bilateral_trade_system.py",
            "Clarifies that the visible meter only reflects cash and does not value non-cash assets.",
        ),
        "frmInner/frmBalance/txtPriceA": DisplayBinding(
            "sum(offered_assets.amount) for cash assets in the local draft",
            "currency units",
            "Zero when no cash is included on the giving side.",
            "Recomputed from the current proposal draft.",
            "src/client/ui/panels/trade_panel.py",
            "Cash included on the giving side; not an estimated value for other assets.",
        ),
        "frmInner/frmBalance/txtPriceB": DisplayBinding(
            "sum(requested_assets.amount) for cash assets in the local draft",
            "currency units",
            "Zero when no cash is included on the requested side.",
            "Recomputed from the current proposal draft.",
            "src/client/ui/panels/trade_panel.py",
            "Cash included on the requested side; not an estimated value for other assets.",
        ),
        "frmInner/frmBalance/frmOverviewMeter": DisplayBinding(
            "offered cash / (offered cash + requested cash)",
            "proportion of draft cash offered",
            "Empty when neither side contains cash; title states that this is a cash-only comparison.",
            "Recomputed from local draft amounts; no territory or research valuation is assumed.",
            "src/client/ui/panels/trade_panel.py",
            "Cash contribution ratio in the GML overview slot, not the REFERENCE trade-evaluation score.",
            action_required="Do not claim source trade fairness/evaluation parity until OpenPower has an authoritative valuation rule.",
        ),
    },
    "War_List_Window": {
        "frmInner/frmWarList/lstWar": DisplayBinding(
            "MilitaryPresenter.all_wars(countries_wars): war id, leader country ids, coalition side members and member counts",
            "active-war rows with localized leader names, flags, and coalition counts",
            "Explicit No active wars state when countries_wars is absent or empty; missing country names use country tags.",
            "Rebuilt from the current countries_wars and countries snapshot on every visible render; row selection is local to WarListPanel.",
            "src/client/ui/panels/military/war_list_panel.py; src/client/ui/panels/military/presenter.py; modules/base/schema.py; tests/ui/journeys/reference-war-list-gml.json",
            "Source lstWar uses the exported dynamic row fields for both war leaders and side-member counts.",
            action_required="Keep source row geometry, war selection and both join-side action checks passing.",
        ),
        "frmInner/frmWarDetails/frmMasterAttacker/txtName": DisplayBinding(
            "selected countries_wars.leader_a -> countries.id/name",
            "localized country name",
            "Country tag when no localized name is available; text is fitted to the source leader slot.",
            "Updated with the locally selected active war on each visible render.",
            "src/client/ui/panels/military/war_list_panel.py; src/client/ui/panels/military/presenter.py; modules/base/schema.py",
            "Attacking coalition leader name.",
        ),
        "frmInner/frmWarDetails/frmMasterDefender/txtName1": DisplayBinding(
            "selected countries_wars.leader_b -> countries.id/name",
            "localized country name",
            "Country tag when no localized name is available; text is fitted to the source leader slot.",
            "Updated with the locally selected active war on each visible render.",
            "src/client/ui/panels/military/war_list_panel.py; src/client/ui/panels/military/presenter.py; modules/base/schema.py",
            "Defending coalition leader name.",
        ),
        "frmInner/frmWarDetails/lstWar": DisplayBinding(
            "selected countries_wars.side_a excluding leader_a; war_exhaustion_states.exhaustion_index by war_id/country_id",
            "attacking coalition member names and war-exhaustion tooltip values",
            "Empty leader-only list; missing country names use country tags; missing exhaustion is shown as unknown in the hover tooltip.",
            "Rebuilt for the selected war each visible render; exhaustion reads the latest snapshot.",
            "src/client/ui/panels/military/war_list_panel.py; modules/base/schema.py; tests/ui/journeys/reference-war-list-gml.json",
            "Attacking coalition participants other than the leader.",
        ),
        "frmInner/frmWarDetails/lstWar1": DisplayBinding(
            "selected countries_wars.side_b excluding leader_b; war_exhaustion_states.exhaustion_index by war_id/country_id",
            "defending coalition member names and war-exhaustion tooltip values",
            "Empty leader-only list; missing country names use country tags; missing exhaustion is shown as unknown in the hover tooltip.",
            "Rebuilt for the selected war each visible render; exhaustion reads the latest snapshot.",
            "src/client/ui/panels/military/war_list_panel.py; modules/base/schema.py; tests/ui/journeys/reference-war-list-gml.json",
            "Defending coalition participants other than the leader.",
        ),
    },
}


def _trade_detail_binding(
    state_binding: str,
    units: str,
    fallback: str,
    update_rule: str,
    meaning: str,
    *,
    status: str,
    action_required: str,
) -> DisplayBinding:
    return DisplayBinding(
        state_binding,
        units,
        fallback,
        update_rule,
        "src/client/ui/panels/trade_panel.py; .codex/Client/Source/reference_trade_detailed_window.cpp; .codex/layout_catalog.gml",
        meaning,
        status=status,
        action_required=action_required,
    )


TRADE_DETAILED_BINDINGS = {
    "frmTitle/lblTitle": _trade_detail_binding(
        "WindowManager.window(title='BILATERAL TRADE')",
        "static window title",
        "BILATERAL TRADE; exact text for GML token 101487 is unavailable without the REFERENCE localization table.",
        "Rendered while TradePanel is open.",
        "OpenPower's bilateral proposal and offer-detail surface title.",
        status="partial",
        action_required="Keep the title in the GML title slot; use the exact REFERENCE translation only if its localization bundle is recovered.",
    ),
}

for _side_path, _side_name in (("frmSideA", "offered"), ("frmSideB", "requested")):
    _side_root = f"frmInner/{_side_path}"
    _trade_tabs = f"{_side_root}/tabGroups"

    # The source explicitly hides TAB_UNITS_IDX, so these retained GML slots are not rendered as trade choices.
    for _unit_slot in ("cboType", "cboModel", "cboUnit", "txtPrice"):
        TRADE_DETAILED_BINDINGS[f"{_trade_tabs}/Tab4/{_unit_slot}"] = _trade_detail_binding(
            "none (source hides TAB_UNITS_IDX; OpenPower omits unit-trade controls)",
            "unavailable military-unit trade selection/value",
            "Not rendered; the reference source hides the unit tab and OpenPower has no authoritative unit-trade action.",
            "Unavailable while the source unit tab remains hidden and OpenPower has no unit-trade action.",
            f"The { _side_name }-side GML unit slot has no active source workflow; OpenPower does not expose a corresponding selector or price.",
            status="verified_unavailable",
            action_required="Keep this source-hidden unit slot unrendered unless an authoritative unit-trade workflow is added.",
        )

    TRADE_DETAILED_BINDINGS[f"{_trade_tabs}/Tab1/cboRegion"] = _trade_detail_binding(
        f"TradePanel._regions_for_owner(state, { _side_name }_owner)",
        "eligible owned region names and IDs",
        "No eligible region when the owner has no transferable region rows.",
        "Recomputed from current regions and country_governments on each proposal render.",
        f"Candidate region for the { _side_name } side; source region eligibility and DAL identifiers are not proven equivalent to OpenPower's owned-region filter.",
        status="partial",
        action_required="Keep the selector limited to the current side's eligible owned regions; confirm source eligibility rules before claiming exact parity.",
    )
    TRADE_DETAILED_BINDINGS[f"{_trade_tabs}/Tab1/txtPrice"] = _trade_detail_binding(
        "none (authoritative source-equivalent region trade valuation is not available)",
        "source valuation currency units",
        "UNPRICED; OpenPower does not estimate territory value.",
        "Remains explicitly unpriced; no proxy metric is substituted.",
        f"The source displays a monetary value for the selected { _side_name }-side region; OpenPower has no authoritative equivalent valuation.",
        status="verified_unavailable",
        action_required="Keep the region value explicitly unpriced until an authoritative comparable trade valuation exists.",
    )
    TRADE_DETAILED_BINDINGS[f"{_trade_tabs}/Tab3/txtPrice"] = _trade_detail_binding(
        f"TradePanel.{_side_name}_cash: current local cash draft",
        "currency units",
        "Zero when no cash amount has been entered; the draft is shown without inventing non-cash values.",
        "Recomputed from the local side's cash input while editing the proposal.",
        f"Cash amount being added to the { _side_name } side; OpenPower's amount is directly bound to its local draft, though currency formatting differs from the source.",
        status="partial",
        action_required="Keep the cash amount tied to the selected side's local draft and preserve currency units; do not treat it as the total value of non-cash assets.",
    )
    TRADE_DETAILED_BINDINGS[f"{_trade_tabs}/Tab2/cboType"] = _trade_detail_binding(
        "fixed Research-only selector in TradePanel._render_asset_side",
        "research asset category",
        "Research is the only available category and the selector is disabled.",
        "Static while the technology category is selected.",
        f"Technology trade type for the { _side_name } side; OpenPower currently supports only research assets, while the source type selector has broader source-defined categories.",
        status="partial",
        action_required="Keep this selector restricted to supported research assets; add other categories only with authoritative trade actions and models.",
    )
    TRADE_DETAILED_BINDINGS[f"{_trade_tabs}/Tab2/cboTechnology"] = _trade_detail_binding(
        f"TradePanel._technology_options(state, giver, receiver): research_tracks.branch",
        "research branch names",
        "No transferable technology when the giver has no branch level above the receiver.",
        "Recomputed from both countries' research_tracks on each proposal render.",
        f"Technology branch available to transfer on the { _side_name } side; branch identity and eligibility are modeled by OpenPower research_tracks and are not asserted to match source unit-characteristic IDs exactly.",
        status="partial",
        action_required="Keep branches and transfer eligibility tied to both countries' authoritative research levels; confirm source category/name semantics before claiming exact parity.",
    )
    TRADE_DETAILED_BINDINGS[f"{_trade_tabs}/Tab2/cboLevel"] = _trade_detail_binding(
        f"TradePanel._technology_options(state, giver, receiver): levels receiver_level + 1 through giver_level",
        "research levels",
        "No selection when the giver has no higher transferable level.",
        "Recomputed when the country pair or selected research branch changes.",
        f"Selectable research level for the { _side_name } side; the OpenPower level interval is explicit, but exact source transfer eligibility is not verified.",
        status="partial",
        action_required="Keep offered/requested levels bounded by both countries' current research tracks and verify the source DAL rules before claiming exact equivalence.",
    )
    TRADE_DETAILED_BINDINGS[f"{_trade_tabs}/Tab2/txtPrice"] = _trade_detail_binding(
        f"TradePanel.{_side_name}_technology_level",
        "selected research level, not currency",
        "UNAVAILABLE when no transferable level exists; otherwise shows LEVEL N without a monetary estimate.",
        "Follows the selected research branch and transfer level.",
        f"The source slot displays a monetary technology value; OpenPower shows the selected { _side_name }-side technology level and deliberately does not claim it is a price.",
        status="partial",
        action_required="Keep the displayed level clearly distinguished from money; add a price only when an authoritative comparable valuation exists.",
    )

_HOST_MULTIPLAYER_SURFACE = "MainMenuContent/HostMultiplayerGameWindow"
_HOST_MULTIPLAYER_SOURCE = (
    "src/client/ui/components/shared/host_multiplayer_window.py; .codex/layout_catalog.gml"
)
_HOST_MULTIPLAYER_TRANSLATION_ACTION = (
    "Keep the caption in its GML slot; use exact REFERENCE copy only if the reference localization bundle is recovered."
)
_HOST_MULTIPLAYER_CAPTIONS = (
    ("frmTitle/lblTitle", "102178", "HOST MULTIPLAYER GAME", "Host form title."),
    ("frmInner/frmGameInfo/lblServerName", "100126", "SERVER NAME", "Server name field label."),
    ("frmInner/frmGameInfo/lblPassword", "100127", "PASSWORD", "Password field label."),
    ("frmInner/frmGameSettings/lblMaxPlayers", "100130", "MAX PLAYERS", "Maximum player count label."),
    ("frmInner/frmGameSettings/lblPort", "100128", "PORT", "Server port label."),
    ("frmInner/frmGameSettings/lblTimeLimit", "100131", "TIME LIMIT", "Server time-limit label."),
    ("frmInner/frmGameSettings/lblDedicatedServer", "100132", "DEDICATED SERVER", "Dedicated server setting label."),
    ("frmInner/frmGoals/lblGameSettings", "100784", "GAME SETTINGS", "Game settings section heading."),
    ("frmInner/frmGoals/txtGameSpeed", "100785", "GAME SPEED", "Game speed selector label."),
    ("frmInner/frmGoals/txtNukes", "102300", "NUCLEAR WARFARE", "Nuclear policy selector label."),
    ("frmInner/frmGoals/lblGoals", "100174", "OBJECTIVES", "Objective list heading."),
    ("frmInner/frmGoals/lblTimeLimit", "100173", "TIME LIMIT", "Objective time-limit column label."),
    ("frmInner/frmGoals/txtGoal1", "100560", "World peace", "First objective label."),
    ("frmInner/frmGoals/txtGoal2", "100561", "Balance resources", "Second objective label."),
    ("frmInner/frmGoals/txtGoal3", "100562", "Conquer the world", "Third objective label."),
    ("frmInner/frmGoals/txtGoal4", "100563", "Develop the nation", "Fourth objective label."),
    ("frmInner/frmGoals/txtGoal5", "100564", "Raise GDP per capita", "Fifth objective label."),
)
DISPLAY_BINDINGS_BY_WINDOW["Host_Multiplayer_Game"] = {
    path: _explicit_gml_caption_binding(
        token,
        caption,
        _HOST_MULTIPLAYER_SURFACE,
        _HOST_MULTIPLAYER_SOURCE,
        meaning,
        _HOST_MULTIPLAYER_TRANSLATION_ACTION,
    )
    for path, token, caption, meaning in _HOST_MULTIPLAYER_CAPTIONS
}
DISPLAY_BINDINGS_BY_WINDOW["Host_Multiplayer_Game"].update({
    "frmInner/frmGameSettings/lblPrivate": DisplayBinding(
        "source-hidden: GHostMultiplayerGameWindow::OnCreate.Hide(lblPrivate)",
        "hidden GML caption",
        "The source hides this label before showing the host form; OpenPower omits the hidden slot.",
        "Always hidden in the source host form.",
        "Client/Source/reference_host_multiplayer_game.cpp#L118; .codex/layout_catalog.gml#Host_Multiplayer_Game",
        "The private server label is hidden by source C++ and has no visible OpenPower counterpart.",
        status="verified_openpower",
        surface=_HOST_MULTIPLAYER_SURFACE,
    ),
    "frmInner/frmGoals/cboGameSpeed": _host_multiplayer_option_binding(
        "HostMultiplayerSettingsDraft.game_speed_index -> _GAME_SPEEDS",
        "ordered local server-speed choices",
        "Server speed draft from Slowest through Fastest; Start remains disabled without an authoritative host service.",
    ),
    "frmInner/frmGoals/cboGameSpeed1": _host_multiplayer_option_binding(
        "HostMultiplayerSettingsDraft.nuclear_option_index -> _NUCLEAR_OPTIONS",
        "local nuclear-policy choices",
        "Nuclear policy draft with Permitted and Not permitted choices.",
    ),
    **{
        f"frmInner/frmGoals/cboGoal{index}": _host_multiplayer_option_binding(
            f"HostMultiplayerSettingsDraft.objectives[{index - 1}].time_limit_index -> _GOAL_TIME_LIMITS",
            "ordered local objective time-limit choices",
            f"Objective {index} time-limit draft, enabled only while its objective checkbox is selected.",
        )
        for index in range(1, 6)
    },
})

DISPLAY_BINDINGS_BY_WINDOW["Covert_Actions_New_Mission"] = {
    "frmTitle/lblTitle": _covert_mission_form_caption_binding(
        "101040",
        "New Covert Mission",
        "Title of the mission preparation dialog.",
    ),
    "frmInner/frmMission/lblFramedCountry": _covert_mission_form_caption_binding(
        "101047",
        "Framed country",
        "Label for the optional country framed by the mission.",
    ),
    "frmInner/frmMission/cboResourceUnit": _covert_mission_form_value_binding(
        "CovertActionWindows._mission_target; civilian resources are the intersection of country_resource_ids(state, assigned_target_tags), military choices use UNIT_CATEGORY_OPTIONS",
        "OpenPower resource id or unit category key",
        "Unavailable when selected target countries share no listed resources; the shared resource helper falls back to RESOURCE_MAPPING only when no resource table exists.",
        "Recomputed when mission category, sector, or assigned target cells change; sent with ActionStartCovertMission on Prepare.",
        "Civilian missions list resources available to every assigned target country using OpenPower's resource tables. Military missions use Ground, Air, Naval, and Strategic categories. REFERENCE fills civilian choices from a fixed full catalog, so the country-scoped OpenPower list is intentional.",
        status="partial",
        action_required="Preserve the selected target countries' OpenPower resource list and do not replace it with REFERENCE's fixed full resource catalog.",
    ),
    "frmInner/frmMission/lblMissionType": _covert_mission_form_caption_binding(
        "101043",
        "Mission type",
        "Label for the selected espionage, sabotage, assassination, terrorism, or coup category.",
    ),
    "frmInner/frmMission/txtCountry": _covert_mission_form_value_binding(
        "Selected covert_cells.target_country_id resolved by resolve_country_name(state, target_tag)",
        "assigned country tag and country name",
        "Unavailable for a stale or missing selected cell; em dash when multiple cells have different assignments.",
        "Read from current selected covert_cells when the dialog renders.",
        "Shows the assigned target of the selected cell. OpenPower adds the country tag and supports multiple-cell selections; REFERENCE shows the country name or a dash for multiple cells.",
        status="partial",
        action_required="Keep the assigned target derived from authoritative cell state and preserve the multi-cell unavailable display.",
    ),
    "frmInner/frmMission/lblTargetSector": _covert_mission_form_caption_binding(
        "101053",
        "Target sector",
        "Label for the civilian or military target sector.",
    ),
    "frmInner/frmMission/cboCountry": _covert_mission_form_value_binding(
        "CovertActionWindows._mission_cover_country from _country_tags(state, own_country, include_own=True), excluding the assigned target",
        "country tag and resolved country name",
        "No cover when no country is selected; disabled when there is no single assigned target.",
        "Country choices follow current world state and selected assigned target; the selection is submitted as cover_country_tag on Prepare.",
        "Chooses a country to frame, excludes the assigned target, and includes the controlled country. OpenPower displays tags and names without the REFERENCE country flags.",
        status="partial",
        action_required="Keep the assigned target excluded and preserve the optional no-cover choice; exact source flag presentation requires the reference asset mapping.",
    ),
    "frmInner/frmMission/cboComplexity": _covert_mission_form_value_binding(
        "CovertActionWindows._mission_complexity from allowed_complexities(profile_type, target_sector)",
        "low, medium, or high complexity",
        "Medium by default, except coup attempts default to and allow only high.",
        "Options recalculate when mission category or sector changes; the selected value is sent on Prepare.",
        "Restricts military sabotage to medium/high, coup attempts to high, and permits low/medium/high for other profiles, matching the source form.",
    ),
    "frmInner/frmMission/lblResourceUnit": _covert_mission_form_caption_binding(
        "101046",
        "Resource / unit",
        "Label for a civilian resource or military unit category target.",
    ),
    "frmInner/frmMission/lblComplexity": _covert_mission_form_caption_binding(
        "101045",
        "Complexity",
        "Label for the mission complexity selection.",
    ),
    "frmInner/frmMission/lblTargetCountry": _covert_mission_form_caption_binding(
        "101052",
        "Target country",
        "Label for the selected cell's assigned target country.",
    ),
    "frmInner/frmMission/cboSector": _covert_mission_form_value_binding(
        "CovertActionWindows._mission_sector from TARGET_SECTOR_OPTIONS",
        "civilian or military target sector",
        "Military on form open; cleared for categories without a sector; civilian when returning to a sectored category after clearing.",
        "Recomputed when mission category changes; blank and disabled for assassination, terrorism, and coup attempts.",
        "Espionage and sabotage use the civilian/military choices. The Python form clears the disabled selection for non-sectored missions, matching REFERENCE's UpdateComboBox behavior.",
    ),
    "frmInner/frmMission/cboMissionType": _covert_mission_form_value_binding(
        "CovertActionWindows._mission_category from MISSION_CATEGORY_OPTIONS; coup_attempt omitted when the assigned target is the controlled country",
        "mission category",
        "Espionage on form open; coup attempt is omitted when the selected cell targets the controlled country.",
        "Local form choice maps to an OpenPower profile key when Prepare dispatches ActionStartCovertMission.",
        "Offers espionage, sabotage, assassination, terrorism, and coup attempt. The own-country coup restriction matches the source form.",
    ),
}


_COVERT_OUTCOME_SOURCE = (
    "src/client/ui/components/shared/covert_outcome_dialog.py; .codex/layout_catalog.gml"
)
_COVERT_OUTCOME_LABEL_ACTION = (
    "Keep the English caption in its GML slot; use exact REFERENCE copy only if the reference localization bundle is recovered."
)
_COVERT_OUTCOME_DATA_ACTION = (
    "Keep mission outcomes tied to authoritative covert state and preserve viewer-role and audience filtering; do not expose source-only identities."
)
_COVERT_OWN_CAPTIONS = (
    ("frmTitle/lblTitle", "101060", "Mission outcome", "Owner mission result title."),
    ("frmInner/frmMission/lblCellName", "101036", "CELL", "Cell name field label."),
    ("frmInner/frmMission/lblMissionType", "101043", "MISSION", "Mission type field label."),
    ("frmInner/frmMission/lblTargetSector", "101053", "SECTOR", "Target sector field label."),
    ("frmInner/frmMission/lblComplexity", "101045", "COMPLEXITY", "Mission complexity field label."),
    ("frmInner/frmMission/lblResourceUnit", "101046", "RESOURCE / UNIT", "Target resource or unit field label."),
    ("frmInner/frmMission/lblTargetCountry", "101052", "TARGET COUNTRY", "Target country field label."),
    ("frmInner/frmMission/lblFramedCountry", "101047", "FRAMED COUNTRY", "Framed country field label."),
)
DISPLAY_BINDINGS_BY_WINDOW["Covert_Actions_Mission_Outcome"] = {
    path: _explicit_gml_caption_binding(
        token,
        caption,
        "GameLayout/CovertOutcomeDialog",
        _COVERT_OUTCOME_SOURCE,
        meaning,
        _COVERT_OUTCOME_LABEL_ACTION,
    )
    for path, token, caption, meaning in _COVERT_OWN_CAPTIONS
}
DISPLAY_BINDINGS_BY_WINDOW["Covert_Actions_Mission_Outcome"].update({
    "frmInner/frmMission/lblResult": _covert_outcome_value_binding(
        "CovertOutcomeDialog own-result heading: literal RESULT",
        "static English caption",
        "The heading remains visible while the result body is shown.",
        "Rendered for each owned mission outcome.",
        "OpenPower renders RESULT above the audience-scoped outcome and effect summary.",
        _COVERT_OUTCOME_LABEL_ACTION,
    ),
    "frmInner/frmMission/txtCellName": _covert_outcome_value_binding(
        "covert_cells.cell_name for the owned mission cell; mission id fallback",
        "cell name or mission identifier",
        "Unavailable when the cell name and mission identifier are absent.",
        "Read from the current owned mission and matching covert_cells row when the dialog renders.",
        "Cell identity shown only to the mission owner.",
        _COVERT_OUTCOME_DATA_ACTION,
    ),
    "frmInner/frmMission/txtMissionType": _covert_outcome_value_binding(
        "covert_missions.mission_type normalized to a display label",
        "mission category label",
        "Unknown when no mission type was recorded.",
        "Read from the selected mission when the dialog renders.",
        "Mission type with civilian_ or military_ prefix removed for display.",
        _COVERT_OUTCOME_DATA_ACTION,
    ),
    "frmInner/frmMission/txtSector": _covert_outcome_value_binding(
        "covert_missions.target_sector or mission_sector(mission_type)",
        "target sector label",
        "Not recorded when neither the mission nor its type provides a sector.",
        "Resolved from the selected mission when the dialog renders.",
        "Target sector rendered in title case.",
        _COVERT_OUTCOME_DATA_ACTION,
    ),
    "frmInner/frmMission/txtComplexity": _covert_outcome_value_binding(
        "covert_missions.complexity",
        "mission complexity label",
        "Not recorded when mission complexity is absent.",
        "Read from the selected mission when the dialog renders.",
        "Recorded complexity rendered in title case.",
        _COVERT_OUTCOME_DATA_ACTION,
    ),
    "frmInner/frmMission/txtResourceUnit": _covert_outcome_value_binding(
        "resource_label(target_resource_id) for civilian missions; UNIT_CATEGORY_OPTIONS for military missions",
        "resource or unit category label",
        "Not recorded when the mission has no matching resource or unit category.",
        "Resolved from the selected mission's target sector and authoritative target fields.",
        "Civilian target resource or military target unit category.",
        _COVERT_OUTCOME_DATA_ACTION,
    ),
    "frmInner/frmMission/txtTargetCountry": _covert_outcome_value_binding(
        "covert_missions.target_country_id",
        "country tag",
        "Unknown when the target country is absent.",
        "Read from the selected owned mission when the dialog renders.",
        "Country targeted by the owned covert mission.",
        _COVERT_OUTCOME_DATA_ACTION,
    ),
    "frmInner/frmMission/txtFramedCountry": _covert_outcome_value_binding(
        "covert_missions.framed_country_id",
        "country tag",
        "None when no country was framed.",
        "Read from the selected owned mission when the dialog renders.",
        "Country framed by the owned covert mission, when present.",
        _COVERT_OUTCOME_DATA_ACTION,
    ),
    "frmInner/frmMission/txtResult": _covert_outcome_value_binding(
        "covert_missions.result plus covert_incidents.summary where mission_id matches and viewer is in audience_country_ids",
        "result and audience-scoped effect summary",
        "No public effect summary was recorded when no matching incident is visible to this viewer.",
        "Recomputed from the selected mission and only incident rows addressed to the current viewer.",
        "Owned mission result with effects restricted to the current viewer's incident audience.",
        _COVERT_OUTCOME_DATA_ACTION,
    ),
})
DISPLAY_BINDINGS_BY_WINDOW["Covert_Actions_Mission_Outcome_Attacked"] = {
    "lblTitle": _covert_outcome_value_binding(
        "CovertOutcomeDialog.lblTitle: DISCOVERED OPERATION or YOUR COUNTRY WAS FRAMED",
        "viewer-role-specific caption",
        "The title depends on whether the viewer is the discovered target or the framed country.",
        "Resolved from the selected mission's viewer role when the dialog renders.",
        "Attacked-view title states the viewer's public relation to the operation.",
        _COVERT_OUTCOME_DATA_ACTION,
    ),
    "lblOutcome": _covert_outcome_value_binding(
        "CovertOutcomeDialog.lblOutcome: OUTCOME when discovered target; hidden for framed viewer",
        "viewer-role-specific caption",
        "Hidden for a framed viewer; shown only in the discovered-target view.",
        "Visibility follows the selected mission's viewer role.",
        "The framed view deliberately omits the outcome heading.",
        _COVERT_OUTCOME_DATA_ACTION,
    ),
    "lblMission": _explicit_gml_caption_binding(
        "101043",
        "MISSION",
        "GameLayout/CovertOutcomeDialog",
        _COVERT_OUTCOME_SOURCE,
        "Mission type caption for the attacked-view dialog.",
        _COVERT_OUTCOME_LABEL_ACTION,
    ),
    "txtMission": _covert_outcome_value_binding(
        "covert_missions.mission_type normalized to a display label",
        "mission category label",
        "Unknown when no mission type was recorded.",
        "Read from the selected mission when the dialog renders.",
        "Mission type shown to discovered or framed viewers without exposing the source cell.",
        _COVERT_OUTCOME_DATA_ACTION,
    ),
    "lblCountry": _covert_outcome_value_binding(
        "CovertOutcomeDialog.lblCountry: TARGET COUNTRY when framed; ATTRIBUTION otherwise",
        "viewer-role-specific caption",
        "Uses TARGET COUNTRY for a framed viewer and ATTRIBUTION for the discovered target.",
        "Resolved from the selected mission's viewer role when the dialog renders.",
        "Country field label changes with the viewer role.",
        _COVERT_OUTCOME_DATA_ACTION,
    ),
    "txtCountry": _covert_outcome_value_binding(
        "target_country_id when framed; presenter-masked owner_country_id for discovered target",
        "country tag or Unknown",
        "Unknown when attribution is unavailable; framed viewers see the operation's target country.",
        "Read from the selected mission after covert_missions_for_country applies viewer-role masking.",
        "Never exposes owner or cell identity when the viewer is not entitled to it.",
        _COVERT_OUTCOME_DATA_ACTION,
    ),
    "lblEffect": _covert_outcome_value_binding(
        "CovertOutcomeDialog.lblEffect: EFFECT when discovered target; IMPLICATION when framed",
        "viewer-role-specific caption",
        "Uses IMPLICATION for a framed viewer and EFFECT for the discovered target.",
        "Resolved from the selected mission's viewer role when the dialog renders.",
        "Effect field label changes with the viewer role.",
        _COVERT_OUTCOME_DATA_ACTION,
    ),
    "txtEffect": _covert_outcome_value_binding(
        "covert_incidents.summary for the viewer audience; fixed redacted implication for framed viewer",
        "audience-scoped effect text",
        "No public effect summary was recorded; framed viewers receive a fixed implication message.",
        "Recomputed from only incident rows addressed to the current viewer.",
        "Effect text avoids private source identity and follows audience_country_ids.",
        _COVERT_OUTCOME_DATA_ACTION,
    ),
    "txtOutcome": _covert_outcome_value_binding(
        "covert_missions.result rendered only for discovered target",
        "mission result label",
        "Intentionally omitted from the framed-view dialog to avoid exposing mission outcome details.",
        "Rendered only when the selected mission is shown to its discovered target.",
        "Outcome is deliberately omitted for the framed-country viewer.",
        _COVERT_OUTCOME_DATA_ACTION,
    ),
}


_CAMPAIGN_SETUP_SOURCE_GAP = (
    "Keep the source GML slot and OpenPower scenario data binding; exact REFERENCE localization "
    "and the documented source-only difficulty or editable-goal semantics remain partial."
)
DISPLAY_BINDINGS_BY_WINDOW["Scenarios_Window"] = {
    "frmTitle/lblTitle": _campaign_setup_display_binding(
        "literal English title SELECT SCENARIO",
        "static English caption",
        "SELECT SCENARIO; supplied REFERENCE localization tables are unavailable.",
        "Rendered while CampaignScenarioSelectionWindow is open.",
        "Scenario-selection window title.",
        _CAMPAIGN_SETUP_SOURCE_GAP,
        "NewGameView/CampaignScenarioSelectionWindow",
    ),
    "frmInner/frmGolem/txtPolitics": _campaign_setup_display_binding(
        "literal OpenPower caption Politics; adjacent presets render N/A",
        "sphere label and unavailable preset labels",
        "Politics; N/A because OpenPower campaign scenarios have no REFERENCE sphere difficulty presets.",
        "Static while the scenario-selection window is open.",
        "Politics difficulty row label; preset choices are unavailable.",
        _CAMPAIGN_SETUP_SOURCE_GAP,
        "NewGameView/CampaignScenarioSelectionWindow",
    ),
    "frmInner/frmGolem/txtEconomy": _campaign_setup_display_binding(
        "literal OpenPower caption Economy; adjacent presets render N/A",
        "sphere label and unavailable preset labels",
        "Economy; N/A because OpenPower campaign scenarios have no REFERENCE sphere difficulty presets.",
        "Static while the scenario-selection window is open.",
        "Economy difficulty row label; preset choices are unavailable.",
        _CAMPAIGN_SETUP_SOURCE_GAP,
        "NewGameView/CampaignScenarioSelectionWindow",
    ),
    "frmInner/frmGolem/txtMilitary": _campaign_setup_display_binding(
        "literal OpenPower caption Military; adjacent presets render N/A",
        "sphere label and unavailable preset labels",
        "Military; N/A because OpenPower campaign scenarios have no REFERENCE sphere difficulty presets.",
        "Static while the scenario-selection window is open.",
        "Military difficulty row label; preset choices are unavailable.",
        _CAMPAIGN_SETUP_SOURCE_GAP,
        "NewGameView/CampaignScenarioSelectionWindow",
    ),
    "frmInner/frmScenario/frmInfo/lblTitle": _campaign_setup_display_binding(
        "literal English caption SCENARIO",
        "static English caption",
        "SCENARIO; supplied REFERENCE localization tables are unavailable.",
        "Rendered while scenario details are visible.",
        "Scenario-title field label.",
        _CAMPAIGN_SETUP_SOURCE_GAP,
        "NewGameView/CampaignScenarioSelectionWindow",
    ),
    "frmInner/frmScenario/frmInfo/txtTitle": _campaign_setup_display_binding(
        "campaign_scenarios.title for selected_scenario_id, falling back to id",
        "scenario title",
        "Select a scenario when no enabled scenario is selected.",
        "Updated when the scenario list selection changes.",
        "Title of the selected enabled OpenPower campaign scenario.",
        _CAMPAIGN_SETUP_SOURCE_GAP,
        "NewGameView/CampaignScenarioSelectionWindow",
    ),
    "frmInner/frmScenario/frmInfo/lblCountry": _campaign_setup_display_binding(
        "literal English caption COUNTRIES",
        "static English caption",
        "COUNTRIES; supplied REFERENCE localization tables are unavailable.",
        "Rendered while scenario details are visible.",
        "Eligible-country field label.",
        _CAMPAIGN_SETUP_SOURCE_GAP,
        "NewGameView/CampaignScenarioSelectionWindow",
    ),
    "frmInner/frmScenario/frmInfo/txtCountry": _campaign_setup_display_binding(
        "campaign_scenarios.selectable_country_ids_json for selected scenario",
        "country identifiers or All playable countries",
        "Shows All playable countries when the scenario does not restrict selectable countries.",
        "Updated when the selected scenario changes.",
        "Eligible country identifiers for the selected scenario.",
        _CAMPAIGN_SETUP_SOURCE_GAP,
        "NewGameView/CampaignScenarioSelectionWindow",
    ),
    "frmInner/frmScenario/tabInfo/Tab1/frmInner/txtDescription": _campaign_setup_display_binding(
        "campaign_scenarios.description for selected scenario",
        "scenario-authored description",
        "No scenario description is available when the selected row has no description.",
        "Updated when the selected scenario or description tab changes.",
        "Description of the selected OpenPower campaign scenario.",
        _CAMPAIGN_SETUP_SOURCE_GAP,
        "NewGameView/CampaignScenarioSelectionWindow",
    ),
    "frmInner/frmScenario/tabInfo/Tab2/frmObjectives/lblGoals": _campaign_setup_display_binding(
        "literal English caption OBJECTIVES",
        "static English caption",
        "OBJECTIVES; supplied REFERENCE localization tables are unavailable.",
        "Rendered while the objectives tab is visible.",
        "Scenario objective-list caption.",
        _CAMPAIGN_SETUP_SOURCE_GAP,
        "NewGameView/CampaignScenarioSelectionWindow",
    ),
    "frmInner/frmScenario/tabInfo/Tab2/frmObjectives/lblTimeLimit": _campaign_setup_display_binding(
        "campaign_scenarios.max_duration_minutes",
        "minutes or none",
        "Shows none when the selected scenario has no duration limit.",
        "Updated when the selected scenario changes.",
        "Maximum duration configured by the selected scenario.",
        _CAMPAIGN_SETUP_SOURCE_GAP,
        "NewGameView/CampaignScenarioSelectionWindow",
    ),
    "frmInner/frmScenario/tabInfo/Tab2/frmObjectives/lstGoals": _campaign_setup_display_binding(
        "campaign_scenarios.objectives_json via preview_campaign_scenario",
        "read-only objective titles and deadlines",
        "Shows that the selected scenario has no configured objectives when its objective list is empty.",
        "Updated when the selected scenario or objectives tab changes.",
        "Read-only preview; source completion toggles do not map to OpenPower setup.",
        _CAMPAIGN_SETUP_SOURCE_GAP,
        "NewGameView/CampaignScenarioSelectionWindow",
    ),
    "frmInner/frmScenario/tabInfo/Tab3/frmInner/txtTips": _campaign_setup_display_binding(
        "campaign_scenarios.enabled_rules rendered in the Rules tab",
        "scenario rule labels",
        "Shows that no optional rules are enabled when the selected scenario has no enabled rules.",
        "Updated when the selected scenario or Rules tab changes.",
        "OpenPower optional rules occupy the source Tips tab slot; REFERENCE tip copy is unavailable.",
        _CAMPAIGN_SETUP_SOURCE_GAP,
        "NewGameView/CampaignScenarioSelectionWindow",
    ),
    "frmInner/frmCustom/lblTitle": _campaign_setup_display_binding(
        "literal English caption CAMPAIGN SCENARIOS",
        "static English caption",
        "CAMPAIGN SCENARIOS; supplied REFERENCE localization tables are unavailable.",
        "Rendered while the scenario list is visible.",
        "Campaign scenario list title.",
        _CAMPAIGN_SETUP_SOURCE_GAP,
        "NewGameView/CampaignScenarioSelectionWindow",
    ),
    "frmInner/frmCustom/lstCustom": _campaign_setup_display_binding(
        "enabled rows from campaign_scenarios",
        "scenario title and id list",
        "Shows No enabled scenarios are available when no enabled scenario rows exist.",
        "Updated from the loaded scenario list; selection refreshes details and eligible countries.",
        "Selectable OpenPower campaign scenarios; REFERENCE's fixed custom-scenario row offset is not used.",
        _CAMPAIGN_SETUP_SOURCE_GAP,
        "NewGameView/CampaignScenarioSelectionWindow",
    ),
}

DISPLAY_BINDINGS_BY_WINDOW["Start_Single_Player"] = {
    "frmTitle/lblTitle": _campaign_setup_display_binding(
        "literal English title START SINGLE PLAYER",
        "static English caption",
        "START SINGLE PLAYER; supplied REFERENCE localization tables are unavailable.",
        "Rendered while SinglePlayerSetupWindow is open.",
        "Single-player setup window title.",
        _CAMPAIGN_SETUP_SOURCE_GAP,
        "NewGameView/SinglePlayerSetupWindow",
    ),
    "frmInner/frmSphereControl/lblTitle": _campaign_setup_display_binding(
        "literal English caption COUNTRY CONTROL",
        "static English caption",
        "COUNTRY CONTROL; OpenPower does not assign separate human and computer spheres.",
        "Rendered while country setup is visible.",
        "OpenPower summary for the selected country, not an editable sphere-assignment control.",
        _CAMPAIGN_SETUP_SOURCE_GAP,
        "NewGameView/SinglePlayerSetupWindow",
    ),
    "frmInner/frmSphereControl/lblParty": _campaign_setup_display_binding(
        "literal English caption PARTY",
        "static English caption",
        "PARTY; supplied REFERENCE localization tables are unavailable.",
        "Rendered while country setup is visible.",
        "Player-party selection field label.",
        _CAMPAIGN_SETUP_SOURCE_GAP,
        "NewGameView/SinglePlayerSetupWindow",
    ),
    "frmInner/frmSphereControl/txtParty": _campaign_setup_display_binding(
        "selected political_parties.display_name or Select a country first",
        "party display name",
        "Shows Select a country first until a country and eligible party are selected.",
        "Updated when country or party selection changes.",
        "Selected OpenPower party name; the party id is sent with ActionStartCampaign.",
        _CAMPAIGN_SETUP_SOURCE_GAP,
        "NewGameView/SinglePlayerSetupWindow",
    ),
    "frmInner/frmSphereControl/txtPolitics": _campaign_setup_display_binding(
        "literal OpenPower country-control status",
        "OpenPower or em dash",
        "Shows an em dash before country selection; OpenPower after selection because sphere assignments are unsupported.",
        "Updated when the selected country changes.",
        "OpenPower status in the source Politics sphere slot; not a separate sphere assignment.",
        _CAMPAIGN_SETUP_SOURCE_GAP,
        "NewGameView/SinglePlayerSetupWindow",
    ),
    "frmInner/frmSphereControl/txtEconomy": _campaign_setup_display_binding(
        "literal OpenPower country-control status",
        "OpenPower or em dash",
        "Shows an em dash before country selection; OpenPower after selection because sphere assignments are unsupported.",
        "Updated when the selected country changes.",
        "OpenPower status in the source Economy sphere slot; not a separate sphere assignment.",
        _CAMPAIGN_SETUP_SOURCE_GAP,
        "NewGameView/SinglePlayerSetupWindow",
    ),
    "frmInner/frmSphereControl/txtMilitary": _campaign_setup_display_binding(
        "literal OpenPower country-control status",
        "OpenPower or em dash",
        "Shows an em dash before country selection; OpenPower after selection because sphere assignments are unsupported.",
        "Updated when the selected country changes.",
        "OpenPower status in the source Military sphere slot; not a separate sphere assignment.",
        _CAMPAIGN_SETUP_SOURCE_GAP,
        "NewGameView/SinglePlayerSetupWindow",
    ),
    "frmInner/frmGoals/lblGoals": _campaign_setup_display_binding(
        "literal English caption OBJECTIVES",
        "static English caption",
        "OBJECTIVES; objective rows remain scenario-defined in OpenPower.",
        "Rendered while country setup is visible.",
        "Read-only objective-list caption.",
        _CAMPAIGN_SETUP_SOURCE_GAP,
        "NewGameView/SinglePlayerSetupWindow",
    ),
    "frmInner/frmGoals/lblTimeLimit": _campaign_setup_display_binding(
        "CampaignScenarioPreview.max_duration_minutes",
        "minutes or No limit",
        "Shows No limit when the selected scenario has no duration limit.",
        "Updated when the selected scenario changes.",
        "Maximum campaign duration configured by the selected scenario.",
        _CAMPAIGN_SETUP_SOURCE_GAP,
        "NewGameView/SinglePlayerSetupWindow",
    ),
    "frmInner/frmCountrySelection/lblTitle": _campaign_setup_display_binding(
        "selected country id or CHOOSE",
        "country identifier or prompt",
        "Shows CHOOSE until a country is selected.",
        "Updated when the country combo selection changes.",
        "Current country-selection summary.",
        _CAMPAIGN_SETUP_SOURCE_GAP,
        "NewGameView/SinglePlayerSetupWindow",
    ),
    "frmInner/frmCountrySelection/cboCountry": _campaign_setup_display_binding(
        "scenario-filtered playable countries from the initial OpenPower state",
        "country id and resolved country name",
        "Shows the Select country placeholder when no country has been selected.",
        "Country list changes with the selected scenario; selection defaults the ruling party.",
        "OpenPower country selection; campaign authority revalidates country eligibility on start.",
        _CAMPAIGN_SETUP_SOURCE_GAP,
        "NewGameView/SinglePlayerSetupWindow",
    ),
}
for _objective_index in range(1, 6):
    _objective_prefix = "frmInner/frmGoals"
    _objective_row = f"CampaignScenarioPreview.objectives[{_objective_index - 1}]"
    DISPLAY_BINDINGS_BY_WINDOW["Start_Single_Player"][
        f"{_objective_prefix}/txtGoal{_objective_index}"
    ] = _campaign_setup_display_binding(
        f"{_objective_row}.title when present",
        "read-only objective title",
        "Shows No configured objectives in row 1 or remains blank when that objective row is absent.",
        "Updated when the selected scenario changes.",
        "Scenario-defined objective title; player-editable REFERENCE goal choices are not supported.",
        _CAMPAIGN_SETUP_SOURCE_GAP,
        "NewGameView/SinglePlayerSetupWindow",
    )
    DISPLAY_BINDINGS_BY_WINDOW["Start_Single_Player"][
        f"{_objective_prefix}/cboGoal{_objective_index}"
    ] = _campaign_setup_display_binding(
        f"{_objective_row}.deadline when present",
        "read-only objective deadline",
        "Shows no deadline or remains blank when the scenario objective has no deadline; this is not an editable combo.",
        "Updated when the selected scenario changes.",
        "Read-only deadline rendered in the source goal-choice slot; editable REFERENCE objective semantics are unavailable.",
        _CAMPAIGN_SETUP_SOURCE_GAP,
        "NewGameView/SinglePlayerSetupWindow",
    )


DISPLAY_BINDINGS_BY_WINDOW["Trade_Detailed_Window"].update(TRADE_DETAILED_BINDINGS)


DISPLAY_BINDINGS_BY_WINDOW["Tutorial_Window"] = {
    "lblTooltip": DisplayBinding(
        "TutorialGuideContent._GUIDES[guide_id][1][step_index].body",
        "English OpenPower tutorial instruction text",
        "No guide text is shown while the tutorial is closed; an active guide shows its current step body.",
        "Changes on guide open/navigation and event-gated step advancement; the waiting status is rendered separately.",
        "src/client/ui/components/tutorial_guide_content.py::TutorialGuideContent.render",
        "OpenPower-authored instruction for the active interface or military guide step; source scripted lesson copy and localization are not reproduced.",
        status="partial",
        action_required="Keep instructions bound to the current OpenPower guide step and supported controls; claim source text parity only if the reference lesson and localization data are recovered.",
    ),
}


DISPLAY_BINDINGS_BY_WINDOW["Generic_Question_Window"] = {
    "lblMessage": DisplayBinding(
        "GenericQuestionDialog._question.message supplied to GenericQuestionDialog.show(message)",
        "caller-supplied confirmation question text",
        "No dialog is shown when the caller supplies an empty message.",
        "Set when the caller opens the one-shot question and cleared after Yes or No.",
        "src/client/ui/components/shared/generic_question_dialog.py; .codex/Client/Source/reference_generic_question_window.cpp",
        "Question wording and meaning belong to the caller; OpenPower keeps its native workflow text in the source GML slot.",
        status="partial",
        action_required="Keep the visible message bound to the active caller's question and verify each workflow's answer separately.",
    ),
}
DISPLAY_BINDINGS_BY_WINDOW["Military_Window"] = {
    "frmTitle/lblTitle": _military_caption_binding(
        "100001", "MILITARY", "Top-level Military window title."
    ),
    "frmInner/frmConventionalWarfare/lblTitle": _military_caption_binding(
        "100025", "CONVENTIONAL FORCES", "Conventional-force section heading."
    ),
    "frmInner/frmConventionalWarfare/lblLand": _military_caption_binding(
        "100035", "LAND", "Ground-force category caption."
    ),
    "frmInner/frmConventionalWarfare/lblAir": _military_caption_binding(
        "100036", "AIR", "Air-force category caption."
    ),
    "frmInner/frmConventionalWarfare/lblNaval": _military_caption_binding(
        "100037", "NAVAL", "Naval-force category caption."
    ),
    "frmInner/frmConventionalWarfare/lblSoldier": _military_caption_binding(
        "100187", "STRAT.", "OpenPower label for the strategic branch bucket; exact source wording is unresolved."
    ),
    "frmInner/frmConventionalWarfare/lblSoldiers": DisplayBinding(
        "literal OpenPower column caption UNITS",
        "static English caption",
        "UNITS; REFERENCE localization is unavailable and its source calculation is a country rank.",
        "Rendered from the current MilitaryPanel in the centered GML column-heading slot.",
        "src/client/ui/panels/military_panel.py; .codex/layout_catalog.gml; .codex/Client/Source/reference_military_window.cpp",
        "OpenPower displays local unit-group counts in this column, so it is labeled UNITS instead of implying REFERENCE's cross-country rank.",
        status="partial",
        action_required="Preserve the UNITS caption and centered GML alignment unless a comparable authoritative country-rank metric is added.",
    ),
    "frmInner/frmConventionalWarfare/lblSoldiersNb": _military_force_count_binding(
        "Infantry", "STRATEGIC"
    ),
    "frmInner/frmConventionalWarfare/lblLandNb": _military_force_count_binding(
        "Ground", "LAND"
    ),
    "frmInner/frmConventionalWarfare/lblAirNb": _military_force_count_binding(
        "Air", "AIR"
    ),
    "frmInner/frmConventionalWarfare/lblNavalNb": _military_force_count_binding(
        "Naval", "NAVAL"
    ),
    "frmInner/frmConventionalWarfare/lblSoldiersRank": _military_unit_group_count_binding(
        "Infantry", "STRATEGIC"
    ),
    "frmInner/frmConventionalWarfare/lblLandRank": _military_unit_group_count_binding(
        "Ground", "LAND"
    ),
    "frmInner/frmConventionalWarfare/lblAirRank": _military_unit_group_count_binding(
        "Air", "AIR"
    ),
    "frmInner/frmConventionalWarfare/lblNavalRank": _military_unit_group_count_binding(
        "Naval", "NAVAL"
    ),
    "frmInner/frmStrategicWeapons/lblTitle": _military_caption_binding(
        "100026", "STRATEGIC FORCES", "Strategic-force section heading."
    ),
    "frmInner/frmStrategicWeapons/frmNuclearProgress": DisplayBinding(
        "MilitaryPresenter.build_summary().strategic_ready and strategic_total",
        "ready and total OpenPower strategic units",
        "0 / 0 when the selected country's current strategic inventory is empty.",
        "Recomputed from the selected country's strategic-inventory snapshot on each MilitaryPanel render.",
        "src/client/ui/panels/military_panel.py; src/client/ui/panels/military/presenter.py; .codex/Client/Source/reference_military_window.cpp",
        "OpenPower shows ready/total inventory counts in the source nuclear-progress slot; these values are not the source NuclearReady research percentage.",
        status="partial",
        action_required="Keep ready/total units explicit and do not present them as nuclear-program progress.",
    ),
    "frmInner/frmStrategicWeapons/frmNuclearProgress/lblValue": DisplayBinding(
        "MilitaryPresenter.build_summary().strategic_ready and strategic_total rendered in the parent slot",
        "ready and total OpenPower strategic units",
        "0 / 0 when the selected country's current strategic inventory is empty.",
        "Rendered as the parent progress slot's value text from the current strategic-inventory snapshot.",
        "src/client/ui/panels/military_panel.py; src/client/ui/panels/military/presenter.py; .codex/Client/Source/reference_military_window.cpp",
        "The source child displays nuclear research progress or N/A; OpenPower's value is inventory readiness, not research progress.",
        status="partial",
        action_required="Keep the value associated with strategic inventory and avoid labeling it as a research percentage.",
    ),
    "frmInner/frmStrategicWeapons/lblMissileDefense": _military_caption_binding(
        "100028", "MISSILE DEFENSE", "Missile-defense section caption."
    ),
    "frmInner/frmStrategicWeapons/txtMissileDefenseStatus": DisplayBinding(
        "MilitaryPresenter.build_summary().missile_defense_pct",
        "OpenPower operational missile-defense coverage percent",
        "0% when no strategic defense rows are present in the current country snapshot.",
        "Recomputed from the selected country's current strategic-inventory snapshot on each MilitaryPanel render.",
        "src/client/ui/panels/military_panel.py; src/client/ui/panels/military/presenter.py; .codex/Client/Source/reference_military_window.cpp",
        "The source status reports AMDS research state/progress; OpenPower shows an operational coverage estimate from fielded defense layers.",
        status="partial",
        action_required="Keep the displayed percent identified as operational coverage and do not treat it as AMDS research completion.",
    ),
    "frmInner/frmStrategicWeapons/frmAmdsProgress": DisplayBinding(
        "MilitaryPresenter.build_summary().missile_defense_pct",
        "OpenPower operational missile-defense coverage percent",
        "0% when no strategic defense rows are present in the current country snapshot.",
        "Recomputed from the selected country's current strategic-inventory snapshot on each MilitaryPanel render.",
        "src/client/ui/panels/military_panel.py; src/client/ui/panels/military/presenter.py; .codex/Client/Source/reference_military_window.cpp",
        "The source meter is AMDS research progress; OpenPower fills this source-shaped slot with operational coverage instead.",
        status="partial",
        action_required="Keep the meter labeled as operational coverage and do not claim AMDS research-progress parity.",
    ),
    "frmInner/frmStrategicWeapons/frmAmdsProgress/lblValue": DisplayBinding(
        "MilitaryPresenter.build_summary().missile_defense_pct rendered in txtMissileDefenseStatus",
        "OpenPower operational missile-defense coverage percent",
        "0% when no strategic defense rows are present in the current country snapshot.",
        "The percentage is displayed beside the filled meter on each MilitaryPanel render.",
        "src/client/ui/panels/military_panel.py; src/client/ui/panels/military/presenter.py; .codex/Client/Source/reference_military_window.cpp",
        "The source child displays AMDS research progress or status text; OpenPower displays operational coverage in the adjacent status label.",
        status="partial",
        action_required="Keep the adjacent coverage value explicit and do not show an unlabeled research-progress value in the meter.",
    ),
}
DISPLAY_BINDINGS_BY_WINDOW["Unit_Production_Window"] = {
    "frmDesignList/frmCost/lblTotalUnits": DisplayBinding(
        "working-age population (15-64), not REFERENCE recruitable manpower",
        "people aged 15-64",
        "N/A when neither countries.total_core_manpower nor regions.owner/pop_15_64 exists in the snapshot.",
        "Read countries.total_core_manpower when present; otherwise sum pop_15_64 for regions owned by the selected country on each render.",
        "src/client/ui/panels/military/unit_production_panel.py::_working_age_population; modules/base/systems/military/military_system.py::_update_manpower",
        "REFERENCE displays MiliManpowerAvailable minus infantry already in production; OpenPower has no equivalent recruitable-manpower pool, so this slot is explicitly relabeled POP. 15-64.",
        status="partial",
        action_required="Keep the OpenPower population metric clearly labeled and never use it as an enlistment cap without an authoritative recruitment policy.",
    ),
    "frmDesignList/frmCost/txtUnitCost": DisplayBinding(
        "countries.total_core_manpower or sum(regions.pop_15_64 where regions.owner == country)",
        "people aged 15-64",
        "N/A when the current snapshot has no authoritative OpenPower working-age population fields.",
        "Read the current country aggregate or derive the same sum from the current owned-region population rows on each render.",
        "src/client/ui/panels/military/unit_production_panel.py::_working_age_population; modules/base/systems/military/military_system.py::_update_manpower",
        "This OpenPower demographic value is not REFERENCE's recruitable MiliManpowerAvailable and does not limit production orders.",
        status="partial",
        action_required="Preserve the demographic meaning in the UI label and tooltip; do not present this count as available recruits.",
    ),
}
DISPLAY_BINDINGS_BY_WINDOW["Unit_Production_Window"].update({
    "frmTitle/lblTitle": _unit_production_caption_binding(
        "100226", "UNIT PRODUCTION", "UnitProductionPanel.render / WindowManager title"
    ),
    "frmRight/frmProduction/lblTitle": DisplayBinding(
        "UnitProductionPanel._right_page plus queue, foreign-order, and deployment page controls",
        "right-pane page title and page navigation",
        "PRODUCTION QUEUE with QUEUE, FOREIGN, and DEPLOY page buttons.",
        "The page buttons update local right-pane state; the selected page content rerenders from the current snapshot.",
        "src/client/ui/panels/military/unit_production_panel.py; .codex/layout_catalog.gml",
        "OpenPower combines the source title slot with its three operational pages; source page naming and localization are not identical.",
        status="partial",
        action_required="Keep the three page destinations available in this title slot and preserve the current source geometry; exact source captions remain unavailable.",
        surface="UnitProductionPanel._render_right_page",
    ),
    "frmRight/frmProduction/lblNbType": _unit_production_caption_binding(
        "100235", "QTY", "UnitProductionPanel._render_right_page"
    ),
    "frmRight/frmProduction/lblNbType1": _unit_production_caption_binding(
        "102250", "FROM", "UnitProductionPanel._render_right_page"
    ),
    "frmRight/frmProduction/lblNbType2": _unit_production_caption_binding(
        "102251", "TO", "UnitProductionPanel._render_right_page"
    ),
    "frmRight/frmProduction/lblPriority": _unit_production_caption_binding(
        "100227", "PRIORITY", "UnitProductionPanel._render_right_page"
    ),
    "frmRight/frmProduction/lblProgress": _unit_production_caption_binding(
        "100027", "PROGRESS", "UnitProductionPanel._render_right_page"
    ),
    "frmRight/frmProduction/txtAcceptForeign": _unit_production_caption_binding(
        "100582", "ACCEPT FOREIGN", "UnitProductionPanel._render_accept_foreign_toggle"
    ),
    "frmRight/frmProduction/lblUnitName": _unit_production_caption_binding(
        "102345", "CAPACITY", "UnitProductionPanel._render_capacity"
    ),
    "frmDesignList/frmInfo/lblSpeed": _unit_production_caption_binding(
        "100202", "SPEED", "UnitProductionPanel._render_design_details"
    ),
    "frmDesignList/frmInfo/lblPriority": _unit_production_caption_binding(
        "100227", "PRIORITY", "UnitProductionPanel._render_design_details"
    ),
    "frmDesignList/frmUnitName/lblUnitName": _unit_production_caption_binding(
        "100193", "DESIGN", "UnitProductionPanel._render_design_details"
    ),
    "frmDesignList/frmCost/lblQty": _unit_production_caption_binding(
        "100229", "QUANTITY", "UnitProductionPanel._render_design_details"
    ),
    "frmDesignList/frmCost/lblTotalCost": _unit_production_caption_binding(
        "100230", "TOTAL COST", "UnitProductionPanel._render_design_details"
    ),
    "frmDesignList/frmEta/lblEta": _unit_production_caption_binding(
        "100810", "ETA", "UnitProductionPanel._render_design_details"
    ),
    "frmDesignList/frmDesignList/lblProducer": _unit_production_caption_binding(
        "100881", "BUILD IN", "UnitProductionPanel._render_builder_selector"
    ),
    "frmDesignList/frmEta/txtEta": DisplayBinding(
        "initial_production_eta_days(selected domestic design priority) or foreign order N/A",
        "initial production estimate in days",
        "Initial domestic ETA from the selected priority; N/A for foreign requests or no selected design.",
        "Recomputed when design, producer, or priority selection changes; production allocation can revise it during simulation.",
        "src/client/ui/panels/military/unit_production_panel.py; modules/base/systems/military/production_policy.py; .codex/layout_catalog.gml",
        "OpenPower presents an initial queue estimate and explicitly identifies foreign ETA as unavailable until seller acceptance.",
        status="partial",
        action_required="Keep this labeled as an initial estimate; do not present the foreign-request fallback as a confirmed delivery date.",
        surface="UnitProductionPanel._render_design_details",
    ),
})


DISPLAY_BINDINGS_BY_WINDOW["War_List_Window"].update(_WAR_LIST_LABEL_BINDINGS)


def _unit_reserve_category_display(category: str, tab_page: str) -> DisplayBinding:
    return DisplayBinding(
        "MilitaryPresenter.reserve_units_for_country(state, country_tag) filtered by "
        "UnitReservesPanel._categorize(unit_domain, unit_type)",
        "OpenPower reserve deployment-group rows",
        f"Empty {category.lower()} deployment list when no matching reserve deployment orders exist.",
        "Recomputed from the current country deployment orders, unit lifecycle/domain/type, design name, and training snapshot on each panel render.",
        "src/client/ui/panels/military/unit_reserves_panel.py; src/client/ui/panels/military/presenter.py; modules/base/schema.py; .codex/Client/Source/reference_unit_ground_deployment_window.cpp",
        f"The REFERENCE {category} list uses GTabbed page {tab_page}; OpenPower classifies its own deployment rows by domain/type keywords and displays native lifecycle/training status. The source and OpenPower taxonomies are not asserted to match one-to-one.",
        status="partial",
        action_required="Keep source page geometry and row controls, and preserve OpenPower-native rows and statuses; do not infer an REFERENCE type mapping from the display category.",
    )


DISPLAY_BINDINGS_BY_WINDOW["Unit_Ground_Deployment_Window"] = {
    "frmTitle/lblTitle": DisplayBinding(
        "literal: English caption in the source GML title slot",
        "static window caption",
        "UNDEPLOYED TROOPS; exact source localization is unavailable because the REFERENCE language tables are absent.",
        "Rendered in the source title slot while UnitReservesPanel is open.",
        "src/client/ui/panels/military/unit_reserves_panel.py; .codex/layout_catalog.gml",
        "OpenPower uses an English caption in the source title slot; exact localized source wording is not verified.",
        status="partial",
        action_required="Keep the caption in the GML title slot and use exact source text only if the localization tables are recovered.",
    ),
    "frmInner/lblHelp": DisplayBinding(
        "UnitReservesPanel selection count, country authority, and deployment/training guidance",
        "selection and eligibility guidance text",
        "Shows country-scope guidance when the viewer cannot control the selected country; otherwise shows the current selection prompt.",
        "Recomputed from the visible category's selected rows and current country authority on each panel render.",
        "src/client/ui/panels/military/unit_reserves_panel.py",
        "OpenPower uses English, action-oriented guidance rather than the source localized help copy.",
        status="partial",
        action_required="Keep help text tied to current selection and authority; exact source localization remains unavailable.",
    ),
    **{
        f"frmInner/{slot}": DisplayBinding(
            "count of rows in MilitaryPresenter.reserve_units_for_country(state, country_tag) "
            f"classified into the {category.lower()} bucket by UnitReservesPanel._categorize",
            "OpenPower reserve deployment-group rows",
            f"0 when the current country snapshot has no matching {category.lower()} deployment groups.",
            "Recomputed from the current eligible reserve rows on each panel render.",
            "src/client/ui/panels/military/unit_reserves_panel.py; src/client/ui/panels/military/presenter.py; modules/base/schema.py",
            f"The source {category.lower()} quantity counts rows in its REFERENCE category list. OpenPower counts rows in its native domain/type bucket; the type taxonomies are not asserted to be identical.",
            status="partial",
            action_required="Keep each count equal to the number of rows shown in its OpenPower category and do not claim source type-taxonomy parity.",
        )
        for slot, category in zip(
            ("txtQty", "txtQty1", "txtQty2", "txtQty3"),
            ("Ground", "Air", "Naval", "Strategic"),
        )
    },
    "frmInner/tabGroups/Tab4/lstDeploy": _unit_reserve_category_display("Ground", "Tab4"),
    "frmInner/tabGroups/Tab1/lstDeploy": _unit_reserve_category_display("Air", "Tab1"),
    "frmInner/tabGroups/Tab3/lstDeploy": _unit_reserve_category_display("Naval", "Tab3"),
    "frmInner/tabGroups/Tab2/lstDeploy": _unit_reserve_category_display("Strategic", "Tab2"),
}

DISPLAY_BINDINGS_BY_WINDOW["Main_Bar"] = {
    "cboCountry": DisplayBinding(
        "countries.id/name or display_name joined to the country flag assets",
        "country name, tag tooltip, and rendered flag",
        "The selected tag is used when no country name is available; an empty country table yields no options.",
        "Options are cached until the countries table identity or revision changes; the selected tag is read from GameLayout's active map context.",
        "src/client/ui/components/hud/country_selector.py; src/client/ui/components/hud/central_bar.py; src/client/ui/layouts/game_layout.py",
        "OpenPower sorts its native country rows by display name and focuses/highlights the chosen country's regions. The source list order, flag assets, zoom sound, and localization are not available for exact parity.",
        status="partial",
        action_required="Keep the flag-backed country popup and verified map-focus route; do not claim source ordering, sound, or localized-name parity without the REFERENCE data assets.",
    ),
    "btnStatus": DisplayBinding(
        "selected country relation classified against player, active countries_wars, active military alliance treaty, or active military_trespassing_right",
        "compact PLAYER, ALLIED, HOSTILE, ACCESS, or NEUTRAL label and semantic color; full relation in the hover tooltip",
        "NEUTRAL when the current snapshot has no matching active relation; PLAYER when the viewed tag is the controlled country.",
        "Resolved from the current game snapshot each GameLayout render.",
        "src/client/ui/components/hud/country_selector.py; src/client/ui/components/hud/central_bar.py; src/client/utils/diplomacy_utils.py; .codex/Client/Source/reference_main_bar.cpp",
        "The status slot and REFERENCE RGB values are preserved for OpenPower's available relations. ACCESS is used in the 65 px slot with Military Access in its tooltip; REFERENCE's localized PlayerName and relation labels are not present in the source mirror.",
        status="partial",
        action_required="Keep active war, alliance, transit-right, and player states distinct; use exact REFERENCE strings only if the localization tables are recovered.",
    ),
    "lblDate": DisplayBinding(
        "NetworkClient.get_display_date_text() or state.time.date_str date component",
        "YYYY-MM-DD date text",
        "Uses the authoritative TimeData.date_str when no interpolated display clock is available.",
        "Rendered from the current frame's interpolated date on each HUD render.",
        "src/client/ui/components/hud/central_bar.py; src/client/services/network_client_service.py; src/shared/state.py",
        "The source uses GMainBar::Update and ActualDate; OpenPower uses its presentation clock while preserving the GML date slot.",
        action_required="Keep the OpenPower date value in the source date-label slot and retain the authoritative-state fallback.",
    ),
    "lblTime": DisplayBinding(
        "NetworkClient.get_display_date_text() or state.time.date_str time component",
        "HH:MM time text",
        "Empty time component only when the source date text has no time separator.",
        "Rendered from the current frame's interpolated clock on each HUD render.",
        "src/client/ui/components/hud/central_bar.py; src/client/services/network_client_service.py; src/shared/state.py",
        "The source updates ActualDate and displays its first five time characters; OpenPower displays the interpolated time in the source label slot.",
        action_required="Keep the OpenPower time value in the source time-label slot and retain the authoritative-state fallback.",
    ),
    "frmMeterPolitic": DisplayBinding(
        "selected countries.gvt_approval in the OpenPower 0–100 percent contract",
        "government approval percentage",
        "Empty meter when the selected country or value is unavailable; otherwise clamp to 0–100.",
        "Read from the current selected-country row each Main Bar render.",
        "src/client/ui/components/hud/central_bar.py; src/client/ui/components/hud/sphere_metrics.py; modules/base/schema.py",
        "Uses OpenPower government approval in the source GML political-meter slot; the source sphere-meter formula is not available in the supplied C++ mirror.",
        status="partial",
        action_required="Keep the tooltip metric explicit and do not claim REFERENCE formula parity unless the custom source meter implementation is recovered.",
    ),
    "frmMeterMilitary": DisplayBinding(
        "selected-country units.owner readiness_status; percent at ready or fortified posture",
        "share of selected-country military units at ready or fortified posture",
        "0 when the country has no unit rows; empty meter when unit readiness data is unavailable.",
        "Aggregated from the current selected-country unit rows each Main Bar render using the shared ReadinessPolicy status rules.",
        "src/client/ui/components/hud/central_bar.py; src/client/ui/components/hud/sphere_metrics.py; modules/base/systems/military/readiness_policy.py",
        "Uses an explicit OpenPower readiness share in the source GML military-meter slot; the source sphere-meter formula is not available in the supplied C++ mirror.",
        status="partial",
        action_required="Keep the tooltip metric explicit and do not claim REFERENCE formula parity unless the custom source meter implementation is recovered.",
    ),
    "frmMeterEconomic": DisplayBinding(
        "selected countries.economic_health in the OpenPower 0–1 index contract, displayed as percent",
        "economic health percentage",
        "Empty meter when the selected country or value is unavailable; otherwise clamp the index to 0–1.",
        "Read from the current selected-country row each Main Bar render.",
        "src/client/ui/components/hud/central_bar.py; src/client/ui/components/hud/sphere_metrics.py; modules/base/schema.py",
        "Uses OpenPower economic health in the source GML economic-meter slot; the source sphere-meter formula is not available in the supplied C++ mirror.",
        status="partial",
        action_required="Keep the tooltip metric explicit and do not claim REFERENCE formula parity unless the custom source meter implementation is recovered.",
    ),
}

_UNIT_LIST_ROW_DISPLAY_BINDINGS = {
    "txtType": DisplayBinding(
        "units.unit_type mapped to a source English type label for recognized roles",
        "REFERENCE-style type name or preserved OpenPower unit-type label",
        "Unknown design when the type or design is unavailable.",
        "Read from the current own-country roster or aggregate foreign estimate; known roles use the shared REFERENCE-ID crosswalk, while unknown names remain unchanged.",
        "src/client/ui/panels/military/unit_list_panel.py; src/client/ui/panels/military/presenter.py; src/client/ui/panels/military/unit_type_options.py",
        "English enum labels align recognized roles with REFERENCE; localized strings are unavailable, and OpenPower-only/aggregate labels are preserved.",
        status="partial",
        action_required="Keep known-role labels tied to the source-ID map; preserve reference OpenPower names for unknown types.",
    ),
    "txtQty": DisplayBinding(
        "units.equipment_quantity with strength fallback",
        "equipment count",
        "0 when both row fields are absent.",
        "Read from the current unit row; foreign estimates use aggregate ranges instead of exact counts.",
        "src/client/ui/panels/military/unit_list_panel.py; src/client/ui/panels/military/presenter.py; modules/base/schema.py",
        "REFERENCE shows unit quantity; OpenPower currently binds equipment_quantity/strength.",
        status="partial",
        action_required="Keep exact values limited to own units and use aggregate ranges for foreign forces.",
    ),
    "txtName": DisplayBinding(
        "unit_designs.display_name joined by units.design_id",
        "unit design name",
        "Unknown design when no owned design record is available.",
        "Resolved from the current design table; row click selects and a double-click opens details only for supported designs.",
        "src/client/ui/panels/military/unit_list_panel.py; src/client/ui/panels/military/presenter.py",
        "OpenPower displays the design name in the source name column instead of a separate VIEW button.",
    ),
    "txtPosition": DisplayBinding(
        "units.current_region_id joined to regions.name and unit movement route summary",
        "region/location text",
        "Unknown location when the region is unavailable.",
        "Recomputed from the current unit and movement-route snapshot.",
        "src/client/ui/panels/military/unit_list_panel.py; src/client/ui/panels/military/presenter.py",
        "REFERENCE shows source map coordinates; OpenPower has region/location semantics but no equivalent per-unit coordinate contract.",
        status="partial",
        action_required="Keep region names explicit and do not derive source coordinates from region centroids.",
    ),
    "txtStatus": DisplayBinding(
        "units.readiness_status, unit_lifecycle and movement route state",
        "readiness/lifecycle status",
        "Ready when readiness_status is absent; explicit route states include blocked and in-transit.",
        "Recomputed from current lifecycle, readiness and route rows on every render.",
        "src/client/ui/panels/military/unit_list_panel.py; src/client/ui/panels/military/presenter.py; modules/base/schema.py",
        "The status vocabulary follows OpenPower readiness/lifecycle rather than every REFERENCE military-status enum.",
        status="partial",
        action_required="Keep movement, transit, training and blocked statuses tied to the current authoritative rows.",
    ),
    "txtUpkeep": DisplayBinding(
        "annual estimate allocated from countries.military_count × 500000 × human_dev × strength-weighted readiness factor, plus units.strength × unit_designs.maintenance_cost",
        "annual currency upkeep estimate per owned unit row",
        "Rounded OpenPower estimate for owned rows; em dash when required country/unit data is unavailable; foreign rows do not expose per-unit values.",
        "The allocated row estimates sum to the existing country military-upkeep formula for the same snapshot; the value is explicitly an OpenPower budget estimate, not an REFERENCE formula match.",
        "src/client/ui/panels/military/unit_list_panel.py; .codex/Client/Source/reference_unit_list_window_new.cpp",
        "The source CalculateUnitUpkeep applies government, development, readiness, training and sale modifiers; OpenPower's annual budget model does not apply every source modifier.",
        status="partial",
        action_required="Keep the estimate identified as OpenPower-derived; do not claim REFERENCE parity until the remaining source modifiers are authoritative.",
    ),
    "txtValue": DisplayBinding(
        "unit_designs.cost joined by units.design_id",
        "currency per unit design",
        "Em dash when no authoritative design cost is available.",
        "Read from the saved design snapshot; does not invent a cost for foreign estimates.",
        "src/client/ui/panels/military/unit_list_panel.py; modules/base/schema.py",
        "REFERENCE displays design cost; OpenPower uses the unit-design cost field.",
        status="partial",
        action_required="Keep the displayed value sourced from the selected design row and distinguish it from sale price or aggregate upkeep.",
    ),
    "picTraining": DisplayBinding(
        "units.training_level",
        "unit training-level marker",
        "Recruit has no colored marker; Regular, Veteran, and Elite use distinct OpenPower color markers; missing levels fall back to Recruit.",
        "Read from the current owned unit row; hovering the row shows the training level by name.",
        "src/client/ui/panels/military/unit_list_panel.py; src/client/ui/panels/military/presenter.py; .codex/Client/Source/reference_unit_list_window_new.cpp",
        "REFERENCE assigns image IDs 000159, 000825, 000826, and 000827; those raster assets are not present in the workspace, so Python uses color markers.",
        status="partial",
        action_required="Keep the marker bound to the live training level and the level name available in the row tooltip; use the source artwork only if its assets are available.",
    ),
    "picSell": DisplayBinding(
        "unit_market_listings.status=listed and quantity>0 joined by unit_id",
        "unit-for-sale marker",
        "Hidden when the owned unit has no active listing; shown for a current listing.",
        "Recomputed from the current unit-market snapshot; the row tooltip identifies a listed unit.",
        "src/client/ui/panels/military/unit_list_panel.py; src/client/ui/panels/military/presenter.py; .codex/Client/Source/reference_unit_list_window_new.cpp",
        "REFERENCE uses a dedicated picture asset; Python renders an OpenPower warning-color marker in the same GML slot.",
        status="partial",
        action_required="Keep visibility tied to active listing state and preserve the GML marker slot.",
    ),
}
DISPLAY_BINDINGS_BY_WINDOW["Unit_List_Window_New"] = {
    f"frmInner/frmList/frmList/frm{row_number}/{component_id}": binding
    for row_number in range(1, 21)
    for component_id, binding in _UNIT_LIST_ROW_DISPLAY_BINDINGS.items()
}
DISPLAY_BINDINGS_BY_WINDOW["Unit_List_Window_New"].update({
    "frmInner/frmList/lblUnitType": DisplayBinding(
        "source GML localized caption token 101480",
        "unit-type filter label",
        "Python currently shows UNIT TYPE.",
        "Static source-positioned filter caption.",
        "src/client/ui/panels/military/unit_list_panel.py; .codex/Client/Source/reference_unit_list_window_new.cpp",
        "Exact localized caption depends on the reference client string table.",
        status="partial",
        action_required="Keep the filter caption in its source slot and resolve the source localization token when string-table support is available.",
    ),
    "frmInner/frmList/cboUnitType": DisplayBinding(
            "REFERENCE unit-type catalog mapped to canonical roles for current unit/estimate rows",
            "source-ordered unit-type option",
        "All when no unit rows exist.",
            "Displays all source types in REFERENCE order, then visible OpenPower-only/aggregate row types; filtering matches canonical roles and resets selection/scroll.",
            "src/client/ui/panels/military/unit_list_panel.py; src/client/ui/panels/military/presenter.py; src/client/ui/panels/military/unit_type_options.py",
            "All 20 source IDs/order map to OpenPower roles; English enum labels substitute for the missing localized source bundle. Unit row captions remain OpenPower data.",
        status="partial",
            action_required="Keep source-ID ordering and role filtering covered; use exact localized labels only when source language resources are available.",
    ),
    "frmInner/frmList/lblAccuracy": DisplayBinding(
        "mean confidence of current foreign_force_estimates rows",
        "aggregate intelligence confidence",
        "Em dash with no published aggregate estimate.",
        "Foreign-only source slot; recomputed with the current estimate rows.",
        "src/client/ui/panels/military/unit_list_panel.py; src/client/ui/panels/military/presenter.py",
        "OpenPower aggregate-estimate confidence is not REFERENCE's AccuracyInformation value.",
        status="partial",
        action_required="Keep confidence labeled as OpenPower estimate confidence rather than source intelligence accuracy.",
    ),
    "frmInner/frmList/txtValue": DisplayBinding(
        "foreign_force_estimates.confidence mean formatted as a percentage",
        "aggregate estimate confidence percent",
        "Em dash when no authorized aggregate estimate exists.",
        "Recomputed from current foreign estimate rows and shown only for foreign-country views.",
        "src/client/ui/panels/military/unit_list_panel.py; src/client/ui/panels/military/presenter.py",
        "This field reports OpenPower estimate confidence, not exact REFERENCE sensor accuracy.",
        status="partial",
        action_required="Keep confidence provenance visible and do not use it to reveal raw foreign-unit quantities.",
    ),
})

def _hidden_base_window_lock_interaction(window_id: str) -> dict[str, str]:
    return {
        "reference_side_effect": (
            "GBaseWindow::OnCreate hides togLockWindow and moves btnApply into its title slot when present."
        ),
        "openpower_surface": "WindowManager.window / GMLLayoutSession.apply_base_window_titlebar_rules",
        "openpower_effect": (
            "The lock toggle is omitted; a title Apply control is moved to the hidden lock slot, matching source runtime geometry."
        ),
        "game_action": "none (hidden source lock control)",
        "read_only_or_state_changing": "non-interactive hidden control; title placement is local presentation behavior",
        "validation_condition": f"The source {window_id} uses inherited GBaseWindow::OnCreate behavior.",
        "country_scope_restriction": "None.",
        "confirmation_state": "None.",
        "error_state": "None.",
        "restrictions_confirmation_error": (
            "Do not expose a lock control hidden by source initialization; preserve the inherited title Apply relocation."
        ),
        "action_required": "Keep the source-hidden toggle omitted and the Apply slot relocation covered.",
        "status": "verified_openpower",
    }


def _hidden_title_apply_interaction(
    window_id: str,
    source_file: str,
    source_line: int,
    openpower_surface: str,
) -> dict[str, str]:
    return {
        "cpp_member_binding": "m_pObjApplyBtn",
        "reference_callback": "",
        "reference_game_event": "",
        "reference_side_effect": (
            f"{window_id}::OnCreate hides the inherited btnApply; no Apply callback is available."
        ),
        "verified_cpp_transition": (
            f"{window_id}::OnCreate calls m_pObjApplyBtn->Hide() at "
            f"{source_file}:{source_line}."
        ),
        "validation_condition": "The source window hides this title control during initialization.",
        "openpower_surface": openpower_surface,
        "openpower_effect": (
            "Unavailable: source OnCreate hides btnApply, and this OpenPower panel has no "
            "title Apply binding."
        ),
        "game_action": "none (source-hidden title control)",
        "read_only_or_state_changing": "non-interactive; source initialization hides the control",
        "country_scope_restriction": "None; the control is hidden before interaction.",
        "confirmation_state": "None; no Apply callback is exposed.",
        "error_state": "None; no Apply callback is exposed.",
        "restrictions_confirmation_error": "The source hides this control before interaction.",
        "action_required": "",
        "status": "verified_unavailable",
    }


def _hidden_apply_source_line(functions: list[dict[str, Any]]) -> int | None:
    """Find an active OnCreate hide call for the inherited title Apply control."""
    for function in functions:
        if function["method"] != "OnCreate":
            continue
        match = re.search(r"\bm_pObjApplyBtn\s*->\s*Hide\s*\(", function["body"])
        if match:
            return function["body_line"] + function["body"][:match.start()].count("\n")
    return None


BATTLE_SUMMARY_INTERACTION_BINDINGS = {
    "Battle_Summary_Window/frmTitle/btnExit": {
        "reference_side_effect": "GBaseWindow::ExitWindow hides/closes the summary after checking the base window's dirty state.",
        "openpower_surface": "BattleSummaryDialog / WindowManager native title-bar close",
        "openpower_effect": "Closes the read-only battle result dialog without changing game state.",
        "game_action": "none (local window close)",
        "read_only_or_state_changing": "local UI navigation",
        "validation_condition": "The result dialog is visible.",
        "country_scope_restriction": "None.",
        "confirmation_state": "No pending changes; closing requires no confirmation.",
        "error_state": "None.",
        "restrictions_confirmation_error": "The source GML exit slot exceeds the 283px root width, so OpenPower keeps the close action in ImGui's visible title bar.",
        "action_required": "Keep direct close behavior; restore the source icon/slot if its reference title-bar extent and assets become available.",
        "status": "partial",
    },
    "Battle_Summary_Window/frmTitle/btnApply": {
        "reference_side_effect": "GBaseWindow::Apply calls Save; GBattleSummaryWindow does not override Save, so Apply has no state effect.",
        "openpower_surface": "BattleSummaryDialog",
        "openpower_effect": "The source title Apply icon is omitted; the dialog is read-only and has nothing to commit.",
        "game_action": "none (source Save is a no-op)",
        "read_only_or_state_changing": "no-op title control",
        "validation_condition": "The result dialog is visible.",
        "country_scope_restriction": "None.",
        "confirmation_state": "None.",
        "error_state": "None.",
        "restrictions_confirmation_error": "GBaseWindow relocates Apply over its hidden lock toggle; the source asset is unavailable and the base Save implementation is empty.",
        "action_required": "Keep the no-op behavior explicit; add a source-style icon only with a verified asset and visible title-bar bounds.",
        "status": "partial",
    },
    "Battle_Summary_Window/frmTitle/togLockWindow": {
        "reference_side_effect": "GBaseWindow::OnCreate hides togLockWindow and moves btnApply into the lock control's former title slot.",
        "openpower_surface": "BattleSummaryDialog / GML title layout session",
        "openpower_effect": "The lock toggle is omitted; its source Apply slot is currently not drawn by this dialog's native title bar.",
        "game_action": "none (hidden source lock control)",
        "read_only_or_state_changing": "non-interactive hidden control",
        "validation_condition": "The summary uses inherited GBaseWindow title behavior.",
        "country_scope_restriction": "None.",
        "confirmation_state": "None.",
        "error_state": "None.",
        "restrictions_confirmation_error": "The GML btnExit lies beyond the 283px root width, so the current window falls back to ImGui's native title bar.",
        "action_required": "Keep the lock control hidden and account for the omitted no-op Apply icon and source title-bar overflow.",
        "status": "partial",
    },
    **{
        f"Battle_Summary_Window/frmInner/frmInner/frmSide{pane}/lstCountries": {
            "reference_side_effect": "SetArenaInformation replaces the defender/attacker rows; the source list has one-row selection but no callback or game action.",
            "openpower_surface": "BattleSummaryDialog._render_countries",
            "openpower_effect": "Renders each participant as a flag/code row with a country-name hover tooltip.",
            "game_action": "none (read-only participant list)",
            "read_only_or_state_changing": "read-only list; no battle state changes",
            "validation_condition": "Country tags come from the result event or the corresponding battle-side snapshot field.",
            "country_scope_restriction": "The summary is opened only for a result delivered to the local participant.",
            "confirmation_state": "None.",
            "error_state": "Shows Not recorded when no side country list is available.",
            "restrictions_confirmation_error": "OpenPower preserves the source's pane order and row dimensions but does not expose list selection because the source installs no selection callback.",
            "action_required": "Keep defender-A/attacker-B row order and the explicit missing-country fallback.",
            "status": "verified_openpower",
        }
        for pane in ("A", "B")
    },
}

BATTLE_INFO_INTERACTION_BINDINGS = {
    "Battle_Info_Window/frmTitle/btnApply": {
        "reference_side_effect": (
            "GBaseWindow::OnMouseClick routes btnApply to Apply(); GBattleInfoWindow has no Save override, "
            "so the inherited GBaseWindow::Save implementation is a no-op."
        ),
        "openpower_surface": "BattleInspectionWindows._render_small",
        "openpower_effect": (
            "Renders the relocated GML title Apply slot as a visible no-op control; this battle information "
            "window is read-only and has no pending changes."
        ),
        "game_action": "none (inherited Save is a no-op)",
        "read_only_or_state_changing": "read-only no-op title control",
        "validation_condition": (
            "GBaseWindow calls Save only when the controlled country matches the selected country or "
            "NeedCountryCheckToSave() is false; GBattleInfoWindow::Save remains a no-op either way."
        ),
        "country_scope_restriction": "No state change is possible; the inherited country gate cannot alter the no-op Save result.",
        "confirmation_state": "No confirmation; Apply calls the empty base Save implementation.",
        "error_state": "None; the inherited Save implementation has no operation or error result.",
        "restrictions_confirmation_error": (
            "The source Apply control is visible but has no GBattleInfoWindow Save implementation; keep its "
            "GML slot and no-op behavior rather than inventing a battle action."
        ),
        "action_required": "",
        "status": "verified_openpower",
    },
    **{
        f"Battle_Info_Window/frmInner/frmInner/frmBattleInfo/lstCountries{slot}": {
            "reference_side_effect": (
                f"UpdateContent fills country list {slot} with the {side_label} and installs no selection "
                "or click callback; the list is read-only."
            ),
            "openpower_surface": "BattleInspectionWindows._render_small",
            "openpower_effect": (
                f"Renders the {side_label} in the matching source list with country flags, tags, and name "
                "tooltips; clicking a row performs no action."
            ),
            "game_action": "none (read-only participant list)",
            "read_only_or_state_changing": "read-only country list; no battle state changes",
            "validation_condition": "The tags come from the selected battle's published defender_side or attacker_side field.",
            "country_scope_restriction": "Participant country tags are public; observers receive aggregate counts rather than foreign unit rosters.",
            "confirmation_state": "None; the list has no selection callback.",
            "error_state": "Shows Unknown when the selected battle has no recorded countries for this side.",
            "restrictions_confirmation_error": "Source slot A is defenders and slot B is attackers; preserve that order and keep the rows read-only.",
            "action_required": "",
            "status": "verified_openpower",
        }
        for slot, side_label in (("A", "defenders"), ("B", "attackers"))
    },
}


def _trade_interaction(
    effect: str,
    game_action: str = "none (local trade draft or view selection)",
    *,
    validation: str = "The client updates only the current draft; the authoritative trade system revalidates submitted terms.",
    restriction: str = "Trade drafts are scoped to the active own country and selected counterparty.",
    error: str = "Invalid or stale terms are rejected by BilateralTradeSystem and remain visible in the trade result feedback.",
    caveat: str = "",
    status: str = "verified_openpower",
) -> dict[str, str]:
    return {
        "openpower_effect": effect,
        "game_action": game_action,
        "read_only_or_state_changing": "local draft/view state; game state changes only after an accepted server action",
        "validation_condition": validation,
        "country_scope_restriction": restriction,
        "confirmation_state": "No extra confirmation; the source proposal/accept action is the user's confirmation.",
        "error_state": error,
        "restrictions_confirmation_error": caveat,
        "action_required": "Keep the GML slot and bilateral-trade journey checks passing; preserve server validation for state changes.",
        "status": status,
    }


_TRADE_WINDOW_CLICK_NOOP_SOURCE = {
    "reference_callback": "OnMouseClick@reference_trade_window.cpp:114",
    "reference_side_effect": (
        "GTradeWindow::OnMouseClick immediately returns Handled for every caller; "
        "it neither invokes GBaseWindow::OnMouseClick nor dispatches a trade action."
    ),
    "verified_cpp_transition": (
        "OnMouseClick@reference_trade_window.cpp:114 returns Handled without a caller branch or base-handler call."
    ),
    "validation_condition": "None; the source override exits before examining the clicked control.",
    "country_scope_restriction": "None in this callback; it does not inspect country authority or trade state.",
    "confirmation_state": "The source click does not submit, confirm, or save a trade action.",
    "error_state": "No callback-level trade result or rejection path exists.",
    "restrictions_confirmation_error": (
        "The source class consumes the click without running the inherited titlebar close/apply behavior."
    ),
}


TRADE_INTERACTION_BINDINGS = {
    **{
        "Trade_Window/frmTitle/btnExit": {
            **_trade_interaction(
                "Closes the GML-sized TradePanel using the titlebar close control.",
                "none (local trade view close)",
                caveat="The supplied GTradeWindow click override swallows titlebar clicks; OpenPower keeps the close affordance functional.",
                status="partial",
            ),
            **_TRADE_WINDOW_CLICK_NOOP_SOURCE,
            "action_required": "Keep the local close route working and identify that the source click override does not call the base close handler.",
        },
        "Trade_Window/frmTitle/btnApply": {
            **_trade_interaction(
                "Switches between the offers list and the proposal editor through the source titlebar slot.",
                "none (local trade view selection)",
                caveat="The supplied source click override swallows btnApply; OpenPower uses this slot for its offers/proposal page toggle.",
                status="partial",
            ),
            **_TRADE_WINDOW_CLICK_NOOP_SOURCE,
            "action_required": "Keep the offers/proposal toggle marked as an OpenPower extension because the source click override does not invoke Apply().",
        },
        "Trade_Window/frmInner/frmList/lstTrade": {
            **_trade_interaction(
                "Selects an OpenPower bilateral offer in the source GML list slot.",
                "none (local offer selection)",
                caveat="The source GTradeWindow callback has no list-selection branch; OpenPower supplies selectable offer rows.",
                status="partial",
            ),
            **_TRADE_WINDOW_CLICK_NOOP_SOURCE,
            "action_required": "Keep offer selection tied to the current country's bilateral-trade snapshot; do not claim a source callback exists.",
        },
        "Trade_Window/frmInner/frmList/btnViewTrade": {
            **_trade_interaction(
                "Opens the selected OpenPower offer in the source GML trade-detail layout.",
                "none (local trade detail navigation)",
                caveat="The source GTradeWindow callback has no ViewTrade branch; OpenPower provides the selected-offer detail route.",
                status="partial",
            ),
            **_TRADE_WINDOW_CLICK_NOOP_SOURCE,
            "action_required": "Keep the selected-offer detail route tested; it extends the source template, whose click callback is a no-op.",
        },
    },
    "Trade_Detailed_Window/frmTitle/btnExit": _trade_interaction(
        "Closes the TradePanel through its GML titlebar close control.",
        "none (close local trade view)",
    ),
    "Trade_Detailed_Window/frmTitle/togLockWindow": _hidden_base_window_lock_interaction("Trade_Detailed_Window"),
    "Trade_Detailed_Window/frmTitle/btnApply": _trade_interaction(
        "Switches between the source-sized proposal view and the supplemental OpenPower offers/history view.",
        "none (local trade view selection)",
        caveat="The source btnApply workflow is not present in the local C++ mirror; OpenPower uses this GML title slot for its offers page.",
    ),
    "Trade_Detailed_Window/frmInner/frmSideB/cboCountry": _trade_interaction(
        "Selects the recipient country for the current proposal draft.",
        validation="The counterparty must be present in countries and cannot be the current country.",
        error="Changing the counterparty clears the local package so assets cannot leak between countries.",
    ),
    "Trade_Detailed_Window/frmInner/frmSideA/frmItems/btnRemoveSelected": _trade_interaction(
        "Removes the selected asset from the local offered-asset draft.",
    ),
    "Trade_Detailed_Window/frmInner/frmSideA/frmItems/btnRemoveAll": _trade_interaction(
        "Clears all assets from the local offered-asset draft.",
    ),
    "Trade_Detailed_Window/frmInner/frmSideB/frmItems/btnRemoveSelected": _trade_interaction(
        "Removes the selected asset from the local requested-asset draft.",
    ),
    "Trade_Detailed_Window/frmInner/frmSideB/frmItems/btnRemoveAll": _trade_interaction(
        "Clears all assets from the local requested-asset draft.",
    ),
    "Trade_Detailed_Window/frmInner/btnPropose": _trade_interaction(
        "Submits the current proposal or counterproposal with the selected expiry.",
        "ActionCreateTradeDeal or ActionCounterTradeDeal",
        validation="Requires an authenticated own-country context, a non-empty asset package, an eligible counterparty, and a pending parent deal for counteroffers.",
        error="BilateralTradeSystem rechecks country scope, partner status, wars, expiry, cash, region ownership/capital restrictions, and research levels.",
        caveat="The Python client does not estimate source deal fairness; territory and research assets have no OpenPower price contract.",
    ),
    "Trade_Detailed_Window/frmInner/btnCancel": _trade_interaction(
        "Clears the editable local proposal draft.",
        "none (local draft discard)",
    ),
    "Trade_Detailed_Window/frmInner/btnAccept": _trade_interaction(
        "Accepts the selected incoming offer from the supplemental OpenPower offers list.",
        "ActionRespondTradeDeal(accept=True)",
        validation="The selected deal must still be pending, unexpired, and addressed to the current own country.",
        caveat="OpenPower renders actions per deal row because one panel can show several offers at once.",
    ),
    "Trade_Detailed_Window/frmInner/btnCounterOffer": _trade_interaction(
        "Starts a local counteroffer draft from the selected incoming offer.",
        "ActionCounterTradeDeal after user submits the draft",
        validation="The parent deal must still be pending and unexpired when the counteroffer is submitted.",
        caveat="OpenPower renders actions per deal row because one panel can show several offers at once.",
    ),
    "Trade_Detailed_Window/frmInner/btnCounterOffer1": _trade_interaction(
        "Rejects the selected incoming offer from the supplemental OpenPower offers list.",
        "ActionRespondTradeDeal(accept=False)",
        validation="The selected deal must still be pending, unexpired, and addressed to the current own country.",
        caveat="OpenPower renders actions per deal row because one panel can show several offers at once.",
    ),
}


def _war_list_interaction(
    effect: str,
    game_action: str = "none (local war-list behavior)",
    *,
    validation: str = "The current game snapshot determines available wars and actions.",
    error: str = "No game action is dispatched by this control.",
    caveat: str = "",
    status: str = "verified_openpower",
) -> dict[str, str]:
    return {
        "openpower_effect": effect,
        "game_action": game_action,
        "read_only_or_state_changing": "local selection/view behavior unless an accepted server action is dispatched",
        "validation_condition": validation,
        "country_scope_restriction": "State-changing actions require player control of the selected own country.",
        "confirmation_state": "No additional confirmation; clicking the source action slot is the user's intent.",
        "error_state": error,
        "restrictions_confirmation_error": caveat,
        "action_required": "Keep the source-sized war-list journey and server-side authority checks passing.",
        "status": status,
    }


WAR_LIST_INTERACTION_BINDINGS = {
    "War_List_Window/frmTitle/btnExit": _war_list_interaction(
        "Closes WarListPanel through its GML titlebar control.",
    ),
    "War_List_Window/frmTitle/togLockWindow": _hidden_base_window_lock_interaction("War_List_Window"),
    "War_List_Window/frmTitle/btnApply": _war_list_interaction(
        "Switches between the active-war overview and the supplemental OpenPower peace-package editor.",
        caveat="The supplied source C++ hides btnApply; OpenPower reuses its reserved GML title slot for a local page toggle.",
        status="partial",
    ),
    "War_List_Window/frmInner/frmWarList/lstWar": _war_list_interaction(
        "Selects the active war whose leaders, coalition members and actions appear below.",
        validation="Only wars present in the current countries_wars snapshot can be selected.",
    ),
    "War_List_Window/frmInner/frmWarDetails/lstWar": _war_list_interaction(
        "Displays attacking coalition members and exposes their war-exhaustion value in a hover tooltip.",
        validation="Read-only; member and exhaustion rows come from the selected war snapshot.",
    ),
    "War_List_Window/frmInner/frmWarDetails/lstWar1": _war_list_interaction(
        "Displays defending coalition members and exposes their war-exhaustion value in a hover tooltip.",
        validation="Read-only; member and exhaustion rows come from the selected war snapshot.",
    ),
    **{
        f"War_List_Window/frmInner/frmWarDetails/{slot}": _war_list_interaction(
            f"Sets the {terms} intent for the {side} coalition.",
            "ActionOfferPeace(terms='peace'|'war')",
            validation="The diplomacy system rechecks the active war, player country authority, and that the source country is the corresponding war leader.",
            error="Unauthorized or stale peace/war intent actions leave the war unchanged; both leaders must offer peace to close the war.",
        )
        for side, terms, slot in (
            ("attacking", "peace", "togPeace"),
            ("attacking", "war", "togWar"),
            ("defending", "peace", "togPeace1"),
            ("defending", "war", "togWar1"),
        )
    },
    **{
        f"War_List_Window/frmInner/frmWarDetails/{slot}": _war_list_interaction(
            f"Joins the {side} coalition in the selected active war.",
            "ActionJoinWar",
            validation="TreatyDiplomacySystem rechecks active status, player authority, valid side, no current membership, and a non-empty opposing side.",
            error="Unauthorized, duplicate, inactive-war, invalid-side or stale join actions leave wars, relations, messages and news unchanged.",
        )
        for side, slot in (("attacking", "btnJoin"), ("defending", "btnJoin1"))
    },
}

for _side, _prefix in (("frmSideA", "offer"), ("frmSideB", "request")):
    _trade_root = f"Trade_Detailed_Window/frmInner/{_side}"
    _TRADE_SIDE_BINDINGS = {
        f"{_trade_root}/tabGroups/Tab1/cboRegion": _trade_interaction(
            f"Selects a region owned by the {_prefix} country for the local trade draft.",
            validation="Only regions currently owned by the giving country are selectable; the sole capital region cannot be transferred.",
        ),
        f"{_trade_root}/tabGroups/Tab1/btnAdd": _trade_interaction(
            f"Adds the selected region to the local {_prefix} asset draft.",
            error="A region is added once per side; current eligibility is rechecked by the trade action.",
        ),
        f"{_trade_root}/tabGroups/Tab2/cboType": _trade_interaction(
            "Displays the only supported OpenPower trade technology type, Research.",
            "none (single supported research type)",
            validation="The single Research option is intentionally disabled until another authoritative technology trade type exists.",
            error="None.",
        ),
        f"{_trade_root}/tabGroups/Tab2/cboTechnology": _trade_interaction(
            f"Selects a research branch transferable from the {_prefix} country.",
            validation="Only research branches above the recipient's current level are selectable.",
        ),
        f"{_trade_root}/tabGroups/Tab2/cboLevel": _trade_interaction(
            f"Selects the {_prefix} research level to include in the local draft.",
            validation="The level must be greater than the recipient's current level and no greater than the giver's level.",
        ),
        f"{_trade_root}/tabGroups/Tab2/btnAdd": _trade_interaction(
            f"Adds the selected research branch and level to the local {_prefix} asset draft.",
            error="Duplicate research branches are not added twice on the same side.",
        ),
        f"{_trade_root}/tabGroups/Tab3/frmMoney/edtText": _trade_interaction(
            f"Edits the cash amount proposed on the {_prefix} side.",
            validation="Cash must be a finite non-negative value; final affordability is checked by BilateralTradeSystem.",
        ),
        f"{_trade_root}/tabGroups/Tab3/frmMoney/btnDown": _trade_interaction(
            f"Decreases the {_prefix} cash amount by one currency unit, clamped at zero.",
        ),
        f"{_trade_root}/tabGroups/Tab3/frmMoney/btnUp": _trade_interaction(
            f"Increases the {_prefix} cash amount by one currency unit.",
        ),
        f"{_trade_root}/tabGroups/Tab3/btnAdd": _trade_interaction(
            f"Adds the entered cash amount to the local {_prefix} asset draft.",
            validation="Only a positive cash amount can be added.",
        ),
        f"{_trade_root}/frmItems/lstItems": _trade_interaction(
            f"Selects an asset in the local {_prefix} draft for removal.",
        ),
    }
    TRADE_INTERACTION_BINDINGS.update(_TRADE_SIDE_BINDINGS)
    for _path, _effect in (
        ("Tab4/cboType", "Selects a military unit trade category."),
        ("Tab4/cboModel", "Selects a military unit model for trade."),
        ("Tab4/btnAdd", "Adds a military unit trade asset."),
        ("Tab4/frmQty/btnDown", "Decreases the military unit trade quantity."),
        ("Tab4/frmQty/edtText", "Edits the military unit trade quantity."),
        ("Tab4/frmQty/btnUp", "Increases the military unit trade quantity."),
        ("Tab4/cboUnit", "Selects a military unit for trade."),
    ):
        TRADE_INTERACTION_BINDINGS[f"{_trade_root}/tabGroups/{_path}"] = _trade_interaction(
            _effect,
            "none (unsupported OpenPower military-unit trade)",
            validation="This source control is displayed disabled because OpenPower has no authoritative military-unit trade asset/action.",
            error="None; no action is dispatched.",
            caveat="The unavailable source workflow stays explicit in the Units page.",
            status="verified_unavailable",
        )

for _path in (
    "Trade_Detailed_Window/frmInner/frmBalance/frmOverviewMeter/btnSeparator1",
    "Trade_Detailed_Window/frmInner/frmBalance/frmOverviewMeter/btnUnfilled",
    "Trade_Detailed_Window/frmInner/frmBalance/frmOverviewMeter/btnFill",
):
    TRADE_INTERACTION_BINDINGS[_path] = _trade_interaction(
        "Represents a visual segment of the source evaluation meter; OpenPower renders its cash-only ratio as a read-only indicator.",
        "none (read-only balance indicator)",
        validation="No action is dispatched by interacting with the balance meter.",
        error="None.",
        caveat="REFERENCE evaluation percentage and authoritative non-cash asset valuations are unavailable.",
        status="verified_unavailable",
    )


HISTORY_INTERACTION_BINDINGS = {
    "History_Window/frmTitle/togLockWindow": {
        "reference_side_effect": "GHistoryWindow::OnCreate hides togLockWindow during initialization.",
        "openpower_surface": "HistoryPanel",
        "openpower_effect": "Not rendered because the source hides this control during initialization.",
        "game_action": "none (source control hidden)",
        "read_only_or_state_changing": "not interactive; hidden by source initialization",
        "validation_condition": "None; the source control is hidden.",
        "country_scope_restriction": "None.",
        "confirmation_state": "None.",
        "error_state": "None.",
        "restrictions_confirmation_error": "Keep the Python titlebar draggable and do not expose a lock control absent from the source runtime.",
        "action_required": "Keep togLockWindow hidden.",
        "status": "verified_openpower",
    },
    "History_Window/frmTitle/btnApply": {
        "reference_side_effect": "GHistoryWindow::OnCreate hides btnApply; the source exposes no analytics popup through this slot.",
        "openpower_surface": "HistoryPanel._render_content",
        "openpower_effect": "Opens supplemental OpenPower history analytics from the source-sized title slot.",
        "game_action": "none (local analytics navigation)",
        "read_only_or_state_changing": "read-only local analysis",
        "validation_condition": "The History panel is visible.",
        "country_scope_restriction": "Analysis uses the selected OpenPower history subject and indicator.",
        "confirmation_state": "None; opening analysis does not change game state.",
        "error_state": "Unavailable data is reported without substituting values.",
        "restrictions_confirmation_error": "This title-slot behavior is an OpenPower addition because the source hides btnApply during initialization.",
        "action_required": "Keep supplemental analytics identified as OpenPower-specific.",
        "status": "partial",
    },
    "History_Window/frmTitle/btnExit": {
        "reference_side_effect": "The source exit button hides GHistoryWindow.",
        "openpower_surface": "WindowManager GML title close",
        "openpower_effect": "Closes the read-only History panel directly.",
        "game_action": "none (local window close)",
        "read_only_or_state_changing": "local UI navigation",
        "validation_condition": "The History panel is visible.",
        "country_scope_restriction": "None.",
        "confirmation_state": "None; History has no pending game-state draft.",
        "error_state": "None.",
        "restrictions_confirmation_error": "Closing does not alter saved history or current game state.",
        "action_required": "Keep direct close behavior for the read-only panel.",
        "status": "verified_openpower",
    },
    "History_Window/frmInner/frmHistory/cboDisplay": {
        "openpower_effect": "Changes the selected local history indicator and updates the current chart query; country.population is initially selected when available.",
        "game_action": "none (read-only history selection)",
        "read_only_or_state_changing": "local display selection; no game state is changed",
        "validation_condition": "Only enabled history_indicator_definitions entries are selectable.",
        "country_scope_restriction": "Subject lists are derived from OpenPower countries, regions, relationships and persisted history series.",
        "confirmation_state": "None.",
        "error_state": "A missing indicator definition shows a disabled empty state.",
        "restrictions_confirmation_error": "The source localization bundle is unavailable; all seventeen source metric slots use source-style English labels and OpenPower-native units, and Population maps to country.population when available.",
        "action_required": "Keep all seventeen source metrics in enum order, preserve OpenPower-native units/formulas, and cover the initial Population selection.",
        "status": "verified_openpower",
    },
    **{
        f"History_Window/frmInner/frmHistory/{slot}": {
            "openpower_effect": f"Not rendered in its source GML slot, matching C++ initialization; the analytics popup period selector can select the {label} OpenPower history window.",
            "game_action": "none (hidden source control; local analytics range)",
            "read_only_or_state_changing": "local display selection; no game state is changed",
            "validation_condition": "Exactly one of the four source time ranges is selected.",
            "country_scope_restriction": "The range only filters the selected subject's history query.",
            "confirmation_state": "None.",
            "error_state": "No samples in the selected range produce an explicit empty chart, not a zero line.",
            "restrictions_confirmation_error": "The source hides these controls and labels during initialization; Python omits the source slots and keeps its range filter in the supplemental analytics popup.",
            "action_required": "Keep these source-hidden controls absent and cover the popup period selector in the analytics journey.",
            "status": "verified_openpower",
        }
        for slot, label in (
            ("tog1Month", "one-month"), ("tog6Month", "six-month"),
            ("tog1Year", "one-year"), ("tog2Year", "two-year"),
        )
    },
}
EVENT_LOG_INTERACTION_BINDINGS = {
    **{
        f"Event_Log/frmInner/{control}": {
            "openpower_effect": f"Locally show or hide {category} EventFeedPresenter items; the category count is available in the tooltip.",
            "game_action": "none (local display filter)",
            "read_only_or_state_changing": "read-only local UI state",
            "validation_condition": "None; each category filter toggles independently.",
            "country_scope_restriction": "The feed uses the current session snapshot; the filter does not change country state.",
            "confirmation_state": "None.",
            "error_state": "None; filtering dispatches no GameAction.",
            "restrictions_confirmation_error": "General-category rows remain visible because the source exposes no General toggle.",
            "action_required": "Keep the source-sized filter slots and category visibility journey passing; retain General rows without assigning them to a different category.",
            "status": "verified_openpower",
        }
        for control, category in (
            ("togFilterPolitic", "political"),
            ("togFilterEconomic", "economic"),
            ("togFilterMilitary", "military"),
            ("togFilterDemographic", "demographic"),
        )
    },
    "Event_Log/frmInner/lstEvents": {
        "openpower_effect": "Selects a feed row locally; a supported response option separately dispatches ActionRespondToRandomEvent, and Goto can focus the selected row's region.",
        "game_action": "none on row selection; ActionRespondToRandomEvent(event_id, response_id, country_tag) on a response option",
        "read_only_or_state_changing": "local selection; authoritative state-changing intent only on a response option",
        "validation_condition": "Only active random-event instances with response options and a connected client expose response controls; Goto is enabled only when the selected item has a region_id.",
        "country_scope_restriction": "Response action is scoped to the event country; authorization and affordability are validated by the authoritative game system.",
        "confirmation_state": "Response click is the explicit player choice; no additional confirmation dialog is shown.",
        "error_state": "Server rejection feedback follows the shared command-feedback path; a row without a valid region cannot trigger Goto.",
        "restrictions_confirmation_error": "Ordinary news and source-only events remain informational; unsupported source response workflows are not fabricated.",
        "action_required": "Keep row selection, region focus, and the typed-event response journey asserting the exact ActionRespondToRandomEvent payload.",
        "status": "verified_openpower",
    },
    "Event_Log/frmInner/btnGoto": {
        "openpower_effect": "Focuses the selected feed item's region through PanelRenderContext.on_focus_request.",
        "game_action": "none (local viewport focus)",
        "read_only_or_state_changing": "read-only viewport navigation",
        "validation_condition": "Disabled unless a feed row is selected and its region_id is available.",
        "country_scope_restriction": "None; the action only requests local viewport focus.",
        "confirmation_state": "None.",
        "error_state": "Disabled when the selected item has no region_id.",
        "restrictions_confirmation_error": "The 27×21 GML slot is retained for Goto; OpenPower random-event controls are placed in a separate supplemental popup.",
        "action_required": "Keep the disabled-without-region and focus-request journey checks passing.",
        "status": "verified_openpower",
    },
}
MAIL_INTERACTION_BINDINGS = {
    "Mail_Window/frmInner/lstMail": {
        "openpower_effect": "Displays current-country contextual inbox rows. VIEW opens the associated dispatch, message or proposal details and consumes that row; DELETE dismisses only that row for the client session.",
        "game_action": "none for opening or dismissing a mail row; proposal ACCEPT/REJECT separately dispatches ActionRespondTreaty",
        "read_only_or_state_changing": "local inbox presentation and dismissal; explicit proposal response is authoritative state-changing intent",
        "validation_condition": "Rows are limited to the active country; treaty responses require the active player country, an outstanding required response and an unaccepted proposal.",
        "country_scope_restriction": "Private messages and pending treaty responses are filtered to the active country; public contextual dispatches retain their source country scope.",
        "confirmation_state": "VIEW is explicit; treaty acceptance or rejection is an explicit separate action in proposal details.",
        "error_state": "A dispatch without a current contextual destination remains informational; a stale or invalid treaty response is rejected through command feedback.",
        "restrictions_confirmation_error": "Dynamic lstMailItem retains the source 460×18 row geometry. Local dismissals do not remove authoritative proposals or messages.",
        "action_required": "Keep the mail-context route and exact row-consumption and proposal-response behavior passing.",
        "status": "verified_openpower",
    },
    "Mail_Window/frmInner/btnDeleteAll": {
        "openpower_effect": "Dismisses every row currently shown for the active country; the mail panel closes when the last row is consumed.",
        "game_action": "none (client-session inbox state only)",
        "read_only_or_state_changing": "local UI/session state; no server game state is changed",
        "validation_condition": "Uses only the rows visible to the active country at the time of the click.",
        "country_scope_restriction": "Dismissal keys include the row kind and id; other-country rows are not affected.",
        "confirmation_state": "No confirmation; this matches the source's immediate RemoveAllMails behavior.",
        "error_state": "No server action is sent; the panel closes after the final row is removed.",
        "restrictions_confirmation_error": "Dismissal lasts for the current game client session, matching the source's local mail list lifetime.",
        "action_required": "Keep Delete All dismissal and automatic close verified by the mail layout journey.",
        "status": "verified_openpower",
    },
}
VERIFIED_WINDOW_NOTES = {
    "Battle_Info_Window": {
        "current_implementation": "GameLayout/BattleInspectionWindows uses the source-sized observer frame, source row/flag geometry and country-name tooltips; published I/G/A/N totals sum authoritative OpenPower equipment quantities and withhold stale or incomplete foreign aggregates",
        "action_required": "Keep the many-country row and published-count journeys passing; source nuclear totals remain hidden because Battle_Info_Window binds only the I/G/A/N labels.",
    },
    "Event_Log": {
        "current_implementation": "PanelSpec/NEWS_LOG → NewsPanel/EventFeedPresenter; GML 488×199 frame, four category filters, region focus, typed-event response actions, and supplemental random-event controls",
        "action_required": "Known differences: General-category rows stay visible because the source has no General filter; OpenPower random-event policy controls use a supplemental popup; REFERENCE pending-news priority/advisor callbacks remain separate workflows.",
    },
    "Mail_Window": {
        "current_implementation": "PanelSpec/MAIL → LiveMailPanel; GML 489×219 window, 475×180 list, dynamic 460×18 rows, contextual VIEW/DELETE actions and country-scoped authoritative inbox data",
        "action_required": "Known difference: OpenPower does not play REFERENCE's first-mail incoming sound. Local row dismissal, consume-on-view, Delete All, Escape close and compact-viewport placement are verified by the mail journeys.",
    },
}
NAVIGATION_EDGE_BINDINGS = {
    "handler:GConstitutionalFormWindow::Save": {
        "openpower_current_implementation": "ConstitutionalFormPanel._request_apply opens GenericQuestionDialog for a qualified non-hostile foreign form change and dispatches the confirmed action after Yes; the authoritative transaction releases controlled regions, grants access, and updates bilateral relations.",
        "action_required": "Keep the qualified 75% foreign-form route and its authoritative release/access checks passing; document OpenPower's region-count proxy separately from the unavailable REFERENCE proportion formula.",
        "route_review": "The source Apply widget is Constitutional_Form/frmTitle/btnApply. GBaseWindow::OnMouseClick routes that slot through Apply() to GConstitutionalFormWindow::Save(); the qualified non-hostile journey verifies the confirmation and action.",
        "geometry_action_required": "Keep the GML btnApply slot and 267x130 Generic Question destination covered; the journey measures the source Apply control and modal destination at 1280x720.",
        "status": "partial",
    },
    "Main_Bar/togMail": {
        "openpower_current_implementation": "GameLayout/CentralBar hud.mail uses the Main_Bar/togMail 27×27 GML toggle and toggles PanelManager MAIL.",
        "action_required": "Keep the source-sized inbox route and dynamic row workflow passing.",
        "route_review": "reference-mail-context verifies opening the 489×219 inbox, contextual treaty/trade/battle routes, consume-on-view, and the matching destination panels.",
        "status": "verified_openpower",
    },
    "Main_Bar/togNews": {
        "openpower_current_implementation": "GameLayout/CentralBar hud.news uses the Main_Bar/togNews 25×19 GML slot and toggles PanelManager NEWS_LOG; the SystemBar has a separate OpenPower-only shortcut.",
        "action_required": "Keep the toggle route and source-sized destination geometry assertions passing.",
        "route_review": "The 28-step OpenPower journey opens from the GML Main_Bar toggle and verifies close, 488×199 destination geometry, list/filter slots, selection, region focus, and a typed-event response.",
        "status": "verified_openpower",
    },
    "handler:GDataAccessLayerClient::AddTreatyRefusalMail": {
        "openpower_current_implementation": "An authoritative EventTreatyRefused adds the scoped dispatch to an already-open inbox; the player opens Mail from the HUD. This source callback inserts a row but does not call Show on Mail_Window.",
        "action_required": "Keep the incoming dispatch scope/content and closed-inbox behavior covered by the mail-arrival journey.",
        "route_review": "The journey delivers a refusal while Mail is closed, verifies the row does not auto-open the window, then opens the inbox and reads the exact contextual report.",
        "geometry_action_required": "The callback adds a dynamic row to the existing Mail_Window; the source 489×219 window and 460×18 row geometry are verified by the mail layout/context journeys.",
        "status": "verified_openpower",
    },
    "handler:GDataAccessLayerClient::AddTradeMail": {
        "openpower_current_implementation": "An authoritative trade event adds a contextual dispatch to the current inbox snapshot; it does not auto-open the Mail window.",
        "action_required": "Keep the trade event payload and contextual route verified by the live-combat mail journey.",
        "route_review": "The mail-context journey reads a trade dispatch into the current Trade panel and verifies the selected deal.",
        "geometry_action_required": "The callback adds a dynamic row; the existing GML Mail_Window and row geometry are verified separately.",
        "status": "verified_openpower",
    },
    "handler:GDataAccessLayerClient::AddCombatOverMail": {
        "openpower_current_implementation": "A local battle result adds a contextual dispatch to the current inbox snapshot; it does not auto-open Mail or a battle summary.",
        "action_required": "Keep the local-country scope, battle result and explicit VIEW route verified by the live-combat mail journey.",
        "route_review": "The mail-context journey verifies the battle row opens its exact summary only after VIEW is clicked; foreign combat is excluded.",
        "geometry_action_required": "The callback adds a dynamic row; the existing GML Mail_Window and row geometry are verified separately.",
        "status": "verified_openpower",
    },
    "handler:GDataAccessLayerClient::InsertPendingNews": {
        "openpower_current_implementation": "Authoritative news_items arrive in the game-state snapshot and EventFeedPresenter adds the row to an already open NEWS_LOG; the snapshot path does not force-open the panel.",
        "action_required": "Preserve the equivalent snapshot journey and document REFERENCE-only pending-news priority/advisor workflows separately.",
        "geometry_action_required": "This is a data-update callback with no source UI widget coordinates; the equivalent journey verifies the existing Event_Log destination and incoming row.",
        "status": "verified_openpower",
    },
}
LATEST_JOURNEY_REPORTS = {
    "reference-foreign-constitutional-qualified-confirm.json": Path(
        "artifacts/ui/reference/foreign-constitutional-qualified-20261027/"
        "reference-foreign-constitutional-qualified-confirm/report.json"
    ),
    "reference-foreign-constitutional-unavailable.json": Path(
        "artifacts/ui/reference/foreign-constitutional-20261027/"
        "reference-foreign-constitutional-unavailable/report.json"
    ),
    "reference-main-bar-history.json": Path("artifacts/ui/reference/history-gml/1280x720/report.json"),
    "reference-news.json": Path("artifacts/ui/reference/news-gml/1280x720/report.json"),
    "reference-news-rolling-update.json": Path("artifacts/ui/reference/news-gml/rolling-update/1280x720/report.json"),
    "region-control-change.json": Path(
        "artifacts/ui/reference/navigation-gap-closure-20261022-continued/full/region-control-change/report.json"
    ),
    "reference-mail-context.json": Path("artifacts/ui/reference/mail-gml/1280x720/report.json"),
    "reference-mail-layout.json": Path("artifacts/ui/reference/mail-layout/1280x720/report.json"),
    "reference-mail-arrival.json": Path("artifacts/ui/reference/mail-arrival/1280x720/report.json"),
    "reference-treaty-refusal-mail.json": Path("artifacts/ui/reference/treaty-refusal-mail/1280x720/report.json"),
    "reference-live-combat-mail.json": Path("artifacts/ui/reference/live-combat-mail/1280x720/report.json"),
    "reference-war-list-gml.json": Path(
        "artifacts/ui/reference/war-list-gml-reconstruction/interactions-1280x720-final/report.json"
    ),
    "reference-military-create-design.json": Path(
        "artifacts/ui/reference/navigation-final/reference-military-create-design/report.json"
    ),
    "reference-design-create-failure-feedback.json": Path(
        "artifacts/ui/reference/navigation-final/reference-design-create-failure-feedback/report.json"
    ),
    "reference-unit-list-design-details.json": Path(
        "artifacts/ui/reference/navigation-final/reference-unit-list-design-details/report.json"
    ),
    "reference-unit-production-design-details.json": Path(
        "artifacts/ui/reference/military-gap-check-20261022/production-design/report.json"
    ),
    "reference-military-production.json": Path(
        "artifacts/ui/reference/military-gap-check-20261022/production-open/report.json"
    ),
    "reference-unit-production-actions.json": Path(
        "artifacts/ui/reference/military-gap-check-20261022/production-actions/report.json"
    ),
    "reference-unit-production-foreign.json": Path(
        "artifacts/ui/reference/military-gap-check-20261022/production-foreign/report.json"
    ),
    "reference-unit-production-deployments.json": Path(
        "artifacts/ui/reference/military-gap-check-20261022/production-deployments/report.json"
    ),
    "reference-unit-reserves-layout.json": Path(
        "artifacts/ui/reference/military-gap-check-20261022/reserves-layout/report.json"
    ),
    "reference-unit-reserves-actions.json": Path(
        "artifacts/ui/reference/military-gap-check-20261022/reserves-actions/report.json"
    ),
}
_RESOURCE_POLICY_INTERACTION = {
    "openpower_effect": _RESOURCES_POLICY_UPDATE,
    "game_action": "ActionUpdateResourcePolicy on Apply or close-confirmation Apply",
    "read_only_or_state_changing": "local draft until Apply; then authoritative state-changing action",
    "validation_condition": "Resource must be selected and the active country must be the player's own country.",
    "country_scope_restriction": "Controls and Apply are disabled for foreign countries or without a selected resource.",
    "confirmation_state": "DirtyCloseConfirmation offers Apply, Discard, and Remember when the policy draft is dirty.",
    "error_state": "Authoritative rejections are surfaced through CommandFeedback and GenericMessageDialog; the rejected resource draft remains available for correction and retry.",
    "restrictions_confirmation_error": "The panel gates edits by ownership and selected resource; InternalEconomySystem validates country authority, resource identity, policy values, and the domestic-production row.",
    "action_required": "Keep per-country, per-resource drafts until an authoritative acceptance or rejection resolves the pending update.",
    "status": "verified_openpower",
}
RESOURCE_POLICY_INTERACTION_BINDINGS = {
    _resource_policy_path: dict(_RESOURCE_POLICY_INTERACTION)
    for _resource_policy_path in (
    "Resources_Window/frmInner/frmResources/cboManagement",
    "Resources_Window/frmInner/frmResources/cboStatus",
    "Resources_Window/frmInner/frmResources/frmSectorTax/edtText",
    "Resources_Window/frmInner/frmResources/frmSectorTax/btnUp",
    "Resources_Window/frmInner/frmResources/frmSectorTax/btnDown",
    )
}
_RESOURCE_UNAVAILABLE_INTERACTION = {
    "openpower_effect": "Keep the source control visible in its GML slot and disabled with a reason because OpenPower has no matching authoritative field or action.",
    "game_action": "none (no matching OpenPower resource-policy action)",
    "read_only_or_state_changing": "disabled; no local state is changed",
    "validation_condition": "The control remains unavailable for every country until OpenPower exposes its domain contract.",
    "country_scope_restriction": "No country may submit this source-only policy.",
    "confirmation_state": "No confirmation or dirty state is created.",
    "error_state": "A tooltip explains the missing OpenPower field or action.",
    "restrictions_confirmation_error": "Do not substitute unrelated resource, budget, or trade values.",
    "action_required": "Enable only after an authoritative OpenPower model field or GameAction exists.",
    "status": "verified_unavailable",
}
RESOURCE_UNAVAILABLE_INTERACTION_BINDINGS = {
    path: dict(_RESOURCE_UNAVAILABLE_INTERACTION)
    for path in (
        "Resources_Window/frmInner/frmResources/cboTrade",
        "Resources_Window/frmInner/frmResources/togMeetConsumption",
        "Resources_Window/frmInner/frmResources/frmGlobalTaxMod/edtText",
        "Resources_Window/frmInner/frmResources/frmGlobalTaxMod/btnUp",
        "Resources_Window/frmInner/frmResources/frmGlobalTaxMod/btnDown",
        "Resources_Window/frmInner/frmResources/frmDesired/edtText",
        "Resources_Window/frmInner/frmResources/frmDesired/btnUp",
        "Resources_Window/frmInner/frmResources/frmDesired/btnDown",
    )
}


def _build_interaction_binding(
    *,
    reference: str,
    surface: str,
    effect: str,
    action: str = "none (local HUD display or navigation)",
    status: str = "verified_openpower",
    validation: str = "None.",
    constraints: str = "No persistent state changes unless explicitly described.",
    confirmation: str = "None.",
    error: str = "None.",
    mapping_notes: str = "No additional source-to-OpenPower behavior difference is known.",
    action_required: str,
    read_only_or_state_changing: str | None = None,
) -> dict[str, str]:
    return {
        "reference_side_effect": reference,
        "openpower_surface": surface,
        "openpower_effect": effect,
        "game_action": action,
        "read_only_or_state_changing": read_only_or_state_changing or (
            "authoritative time-control action" if action.startswith("Action")
            else "local HUD navigation, selection, or display state"
        ),
        "validation_condition": validation,
        "country_scope_restriction": constraints,
        "confirmation_state": confirmation,
        "error_state": error,
        "restrictions_confirmation_error": mapping_notes,
        "action_required": action_required,
        "status": status,
    }


BUDGET_RESOURCES_TITLE_INTERACTION_BINDINGS = {
    "Budget_Window/frmTitle/btnExit": _build_interaction_binding(
        reference=(
            "GBaseWindow::OnMouseClick routes btnExit through ExitWindow; a clean budget window hides, "
            "while dirty data follows the shared save-confirmation preferences."
        ),
        surface="BudgetPanel._close_intent / DirtyCloseConfirmation",
        effect=(
            "Closes a clean budget panel directly; dirty drafts require Apply or Discard, with Apply "
            "submitting ActionUpdateBudget before the panel closes."
        ),
        action="none on clean close or discard; ActionUpdateBudget only when Apply is chosen",
        status="verified_openpower",
        validation="A dirty draft opens the confirmation; Apply is enabled only for the controlled country with a client.",
        constraints="Budget changes are scoped to the controlled country and revalidated by the server.",
        confirmation="DirtyCloseConfirmation provides Apply, Discard, and Remember decisions for unsaved changes.",
        error="An authoritative Apply rejection preserves the budget draft for correction or retry.",
        mapping_notes=(
            "The Python panel uses the shared close-intent component instead of the source global window caller; "
            "clean close and dirty Apply/Discard outcomes are covered by journeys."
        ),
        action_required="Keep clean close, dirty confirmation, and the no-action Discard route covered.",
        read_only_or_state_changing="local close; state-changing only when the user selects Apply",
    ),
    "Budget_Window/frmTitle/btnApply": _build_interaction_binding(
        reference=(
            "GBaseWindow::OnMouseClick calls Apply, which reaches GBudgetWindow::Save and sends "
            "GBudgetUpdate for the controlled country when the budget is dirty."
        ),
        surface="BudgetPanel._dispatch_budget_update / budget.apply",
        effect="Submits the dirty budget allocation draft through ActionUpdateBudget and keeps it pending for authoritative reconciliation.",
        action="ActionUpdateBudget with the controlled country and changed budget allocation fields",
        status="verified_openpower",
        validation="Apply is enabled only for a dirty draft with a connected client and the player's country; the server rechecks authority and values.",
        constraints="Only the controlled country may submit a budget update.",
        confirmation="Title Apply commits directly; dirty close separately asks Apply or Discard.",
        error="A rejected action leaves the authoritative budget unchanged and the draft available for retry.",
        mapping_notes="The source sends GBudgetUpdate; OpenPower uses its equivalent authoritative ActionUpdateBudget contract.",
        action_required="Keep source title-slot geometry and the exact ActionUpdateBudget payload covered.",
        read_only_or_state_changing="authoritative state-changing country action",
    ),
    "Resources_Window/frmTitle/btnExit": _build_interaction_binding(
        reference=(
            "GBaseWindow::OnMouseClick routes btnExit through ExitWindow; a clean resources window hides, "
            "while dirty resource data follows the shared save-confirmation preferences."
        ),
        surface="ResourcesPanel._close_intent / DirtyCloseConfirmation",
        effect=(
            "Closes a clean resources panel directly; dirty per-resource drafts require Apply or Discard, "
            "with Apply submitting the supported policy updates before close."
        ),
        action="none on clean close or discard; ActionUpdateResourcePolicy only when Apply is chosen",
        status="verified_openpower",
        validation="A dirty policy draft opens the confirmation; Apply requires an owned country and a connected client.",
        constraints="Only policy drafts for the controlled country are submitted; the server rechecks country and resource authority.",
        confirmation="DirtyCloseConfirmation provides Apply, Discard, and Remember decisions for unsaved changes.",
        error="A rejected resource policy preserves the edited draft for correction or retry.",
        mapping_notes=(
            "The Python panel uses the shared close-intent component instead of the source global window caller; "
            "clean close and dirty Apply/Discard outcomes are covered by journeys."
        ),
        action_required="Keep clean close, dirty confirmation, and the no-action Discard route covered.",
        read_only_or_state_changing="local close; state-changing only when the user selects Apply",
    ),
    "Resources_Window/frmTitle/btnApply": _build_interaction_binding(
        reference=(
            "GBaseWindow::OnMouseClick calls Apply, which reaches GResourcesWindow::Save and sends "
            "GResourcesUpdate for dirty resource policies and the global tax modifier."
        ),
        surface="ResourcesPanel._dispatch_policy_updates / resources.apply",
        effect=(
            "Submits dirty supported resource-policy drafts through ActionUpdateResourcePolicy and "
            "waits for authoritative acceptance or rejection."
        ),
        action="ActionUpdateResourcePolicy per changed country/resource draft",
        status="partial",
        validation="Apply is enabled only with a connected client, controlled country, and unsubmitted dirty resource policies.",
        constraints="Only the controlled country's policy drafts may be submitted.",
        confirmation="Title Apply commits supported drafts directly; dirty close separately asks Apply or Discard.",
        error="A rejection preserves the affected resource draft for correction or retry.",
        mapping_notes=(
            "OpenPower has no authoritative equivalent for the source global tax modifier, which remains disabled; "
            "Apply therefore commits only supported per-resource fields."
        ),
        action_required="Keep supported resource payloads exact and retain the explicit unavailable boundary for global tax.",
        read_only_or_state_changing="authoritative state-changing country/resource action",
    ),
}
THEMATIC_MAP_LEGEND_INTERACTION_BINDINGS = {
    "Thematic_Map_Legend/lstCountries": _build_interaction_binding(
        reference=(
            "GThematicMapLegendWindow::OnCustomEvent handles OnListItemSelected, reads the selected row's "
            "country ID, and calls SelectedCountrySetLookAt; OnMouseClick itself has no separate action."
        ),
        surface="ThematicMapLegend._render_country_row / viewport country-selection request",
        effect="Selecting a visible country row sends a country-focus request for that row's country tag.",
        action="none (country selection and map focus only)",
        status="verified_openpower",
        validation="The selected row must be present in the current thematic ranking or empire-country list.",
        constraints="Only country rows produced from the current OpenPower snapshot are selectable.",
        confirmation="None; selection updates local country/map focus state.",
        error="No focus request is sent when there is no selectable country row.",
        mapping_notes=(
            "The source uses OnListItemSelected and AdditionalId; OpenPower row selection uses the same country identity "
            "to request viewport focus."
        ),
        action_required="Keep the selected country ID bound to the row and verify the resulting viewport request.",
        read_only_or_state_changing="local selection and viewport focus",
    ),
}
BATTLE_OVERVIEW_SMALL_UNIT_INFO_INTERACTION_BINDINGS = {
    "Battle_Overview_Small_Unit_Info/lstUnits": _build_interaction_binding(
        reference=(
            "GBattleOverviewSmallUnitInfoWindow::OnCustomEvent reads the selected row, but the only owner notification "
            "call is commented out; selecting a row emits no state-changing event."
        ),
        surface="BattleOverviewPanel / battle inspection route",
        effect=(
            "OpenPower does not expose this source country-unit list as a selectable battle-detail control; "
            "its battle overview selects a battle record and opens inspection separately."
        ),
        action="none (source row selection has no active game action)",
        status="partial",
        validation="Source selection is read-only; OpenPower inspection is scoped to a selected battle record.",
        constraints="Battle data is shown only for battles available in the current authorized snapshot.",
        confirmation="None; the source selection callback contains no active follow-up.",
        error="None; no action is emitted from selecting this source list row.",
        mapping_notes=(
            "The C++ owner-selection callback is commented out. OpenPower's battle-ID selection and per-country force "
            "summary are different workflows, so the source row selection is not inferred from INSPECT."
        ),
        action_required="Keep the no-action source behavior explicit and avoid mapping country rows to a battle command.",
        read_only_or_state_changing="read-only source selection with no active callback effect",
    ),
}
ECONOMIC_WINDOW_METER_INTERACTION_BINDINGS = {
    "Economic_Window/frmInner/frmEconomicModel/frmModelCursor/btnFill": _build_interaction_binding(
        reference=(
            "GIdeologyMeter::OnCreate configures btnFill as a non-draggable cursor; GEconomicWindow only assigns "
            "the selected country's economic-model value to the meter."
        ),
        surface="EconomyPanel.ui.meter / frmEconomicModel/frmModelCursor",
        effect="Displays the OpenPower free-market share as a fixed cursor meter with no independent button action.",
        action="none (read-only meter segment)",
        status="verified_openpower",
        validation="The value is derived from domestic production for the currently selected country.",
        constraints="The source cursor is also non-draggable; no policy action is sent from this meter.",
        mapping_notes=(
            "OpenPower derives a free-market production share rather than importing REFERENCE's CountryEconomicModel value; "
            "that data-semantic difference is tracked separately from this non-interactive control."
        ),
        action_required="Keep the source-sized meter read-only and preserve the explicit OpenPower value source.",
        read_only_or_state_changing="read-only display",
    ),
    "Economic_Window/frmInner/frmEconomicModel/frmModelCursor/btnUnfilled": _build_interaction_binding(
        reference=(
            "GIdeologyMeter::OnCreate configures btnUnfilled as a locked, non-draggable background segment; "
            "GEconomicWindow assigns its full-range value when initializing the meter."
        ),
        surface="EconomyPanel.ui.meter / frmEconomicModel/frmModelCursor",
        effect="Draws the static background of the economic-model meter; it has no independent button action.",
        action="none (read-only meter background)",
        status="verified_openpower",
        constraints="The source background segment is locked and is not an independent control.",
        action_required="Keep the background decorative and do not expose it as a separate hit target.",
        read_only_or_state_changing="read-only display",
    ),
    "Economic_Window/frmInner/frmEconomicHealth/frmGradient/btnFill": _build_interaction_binding(
        reference=(
            "GCursorMeter::OnCreate makes btnFill locally draggable and lockable; drag updates only the meter's "
            "transient cursor value and fires a custom notification. GEconomicWindow has no OnCustomEvent handler."
        ),
        surface="EconomyPanel.ui.meter / frmEconomicHealth/frmGradient",
        effect=(
            "Displays the selected country's health snapshot as a read-only meter; OpenPower does not expose a "
            "summary-meter drag target or authoritative health-edit action."
        ),
        action="none (summary health display)",
        status="partial",
        validation="The displayed health value comes from the selected country's current snapshot.",
        constraints="Do not turn a transient source cursor gesture into an unsupported authoritative health mutation.",
        confirmation="None; the source drag has no implemented owner callback or persistent update.",
        error="None; OpenPower's summary meter is not an editable control.",
        mapping_notes=(
            "The source generic meter accepts a local drag, but the economic window handles no meter-change event; "
            "the OpenPower summary deliberately remains a read-only snapshot."
        ),
        action_required="Keep the read-only boundary explicit unless an authoritative health-edit workflow is added.",
        read_only_or_state_changing="source-local transient cursor only; no game-state action",
    ),
    "Economic_Window/frmInner/frmEconomicHealth/frmGradient/btnUnfilled": _build_interaction_binding(
        reference=(
            "GCursorMeter::OnCreate configures btnUnfilled as a locked, non-draggable background segment; "
            "GEconomicWindow updates the meter value from the selected-country snapshot."
        ),
        surface="EconomyPanel.ui.meter / frmEconomicHealth/frmGradient",
        effect="Draws the non-interactive background of the economic-health summary meter.",
        action="none (read-only meter background)",
        status="verified_openpower",
        constraints="The source background segment is locked; it cannot change the displayed health value.",
        action_required="Keep the background decorative and do not expose it as a separate hit target.",
        read_only_or_state_changing="read-only display",
    ),
    "Economic_Window/frmInner/frmResources/frmGradient/btnFill": _build_interaction_binding(
        reference=(
            "GCursorMeter::OnCreate makes btnFill locally draggable and lockable; drag updates only the meter's "
            "transient cursor value and fires a custom notification. GEconomicWindow has no OnCustomEvent handler."
        ),
        surface="EconomyPanel.ui.meter / frmResources/frmGradient",
        effect=(
            "Displays OpenPower's resource-coverage estimate as a read-only meter; no summary-meter drag target or "
            "authoritative resource-coverage edit action is exposed."
        ),
        action="none (resource coverage summary display)",
        status="partial",
        validation="Resource coverage is derived from the selected country's current ledger snapshot.",
        constraints="Do not turn a transient source cursor gesture into an unsupported resource-policy mutation.",
        confirmation="None; the source drag has no implemented owner callback or persistent update.",
        error="None; OpenPower's summary meter is not an editable control.",
        mapping_notes=(
            "The source generic meter accepts a local drag, but the economic window handles no meter-change event; "
            "OpenPower resource policies are edited through the separate Resources panel."
        ),
        action_required="Keep resource policy edits in the Resources panel and retain the summary meter as read-only.",
        read_only_or_state_changing="source-local transient cursor only; no game-state action",
    ),
    "Economic_Window/frmInner/frmResources/frmGradient/btnUnfilled": _build_interaction_binding(
        reference=(
            "GCursorMeter::OnCreate configures btnUnfilled as a locked, non-draggable background segment; "
            "GEconomicWindow updates the meter value from the selected-country snapshot."
        ),
        surface="EconomyPanel.ui.meter / frmResources/frmGradient",
        effect="Draws the non-interactive background of the resource-coverage summary meter.",
        action="none (read-only meter background)",
        status="verified_openpower",
        constraints="The source background segment is locked; it cannot change the displayed resource value.",
        action_required="Keep the background decorative and do not expose it as a separate hit target.",
        read_only_or_state_changing="read-only display",
    ),
}
INTERNAL_LAWS_INTERACTION_BINDINGS = {
    "Internal_Laws/frmTitle/btnExit": _build_interaction_binding(
        reference=(
            "GBaseWindow::OnMouseClick routes btnExit through ExitWindow; a dirty Internal Laws window prompts "
            "for Save/Discard according to the shared source preference."
        ),
        surface="InternalLawsPanel._close_intent / DirtyCloseConfirmation",
        effect=(
            "Closes a clean panel directly; when policy drafts are dirty, asks Apply or Discard and keeps rejected "
            "drafts visible for correction."
        ),
        action="none until the user chooses Apply in the close confirmation",
        status="partial",
        validation="Only pending drafts for the currently selected country are included in the close decision.",
        constraints="Apply remains limited to the connected player's country and supported OpenPower law/identity/party policies.",
        confirmation="DirtyCloseConfirmation offers Apply or Discard; the source submits its bundled internal-laws update.",
        error="A rejected or stale OpenPower draft remains visible with a warning instead of being silently discarded.",
        mapping_notes=(
            "Both routes preserve an explicit dirty-close decision, but OpenPower stages several typed actions rather "
            "than one GInternalLawsUpdate event."
        ),
        action_required="Preserve Apply/Discard close behavior and do not merge unrelated policy actions into one payload.",
        read_only_or_state_changing="local close decision; authoritative actions only after Apply",
    ),
    "Internal_Laws/frmTitle/btnApply": _build_interaction_binding(
        reference=(
            "GBaseWindow::OnMouseClick routes btnApply through Apply() to GInternalLawsWindow::Save(), which sends "
            "one GInternalLawsUpdate containing changed laws, demographic statuses, and border policies."
        ),
        surface="InternalLawsPanel._apply_drafts / laws.apply",
        effect=(
            "Preflights and submits supported pending law, identity and party-policy actions for the selected country; "
            "migration opens its separate authoritative policy editor."
        ),
        action="ActionChangePoliticalLaw, ActionSetCountryIdentityPolicy, and ActionSetPartyEligibility as applicable",
        status="partial",
        validation="The selected country must be the player's own country and every staged policy must pass its model preflight.",
        constraints="Only supported OpenPower policy fields are submitted; migration and source-only status values are not fabricated.",
        confirmation="Drafts remain local until Apply; a transition to a new government form may require confirmation first.",
        error="A preflight rejection keeps the affected draft and reports the reason; server acceptance remains authoritative.",
        mapping_notes=(
            "OpenPower uses separate typed actions and does not combine source law, demographic, party, and migration "
            "values into the source GInternalLawsUpdate envelope."
        ),
        action_required="Keep all policy drafts preflighted and preserve typed action boundaries and confirmation routes.",
        read_only_or_state_changing="local drafts until Apply; then authoritative country policy updates",
    ),
    "Internal_Laws/frmInner/frmOrganizations/lstOrganization": _build_interaction_binding(
        reference=(
            "GInternalLawsWindow populates lstOrganization with party rows; each row's cboStatus reports the actual "
            "policy change through OnComboBoxSelectionEvent. The list itself has no separate selection action."
        ),
        surface="InternalLawsPanel._render_content / lstInternalLawsGroups party rows",
        effect=(
            "Renders current party records and their supported eligibility choices; a row choice stages a party-policy "
            "draft and Apply sends ActionSetPartyEligibility."
        ),
        action="none for selecting the list row; row status edits stage ActionSetPartyEligibility",
        status="partial",
        validation="Only eligible non-ruling parties with an authoritative editable party policy can be changed.",
        constraints="The ruling party cannot be prohibited; edits require the selected country to be player-controlled.",
        confirmation="Row edits remain drafts until Apply; government-form transitions may ask for confirmation.",
        error="Unavailable party rules leave the row disabled with an explanation.",
        mapping_notes=(
            "The list is a dynamic row host, not a click-to-select command. OpenPower preserves that role but applies "
            "its stricter eligibility model and typed action rather than the source combo's full status set."
        ),
        action_required="Keep the list as a row container and validate edits against authoritative party eligibility.",
        read_only_or_state_changing="read-only row host; child edits are local drafts until Apply",
    ),
    "Internal_Laws/frmInner/frmLaws/lstLaws": _build_interaction_binding(
        reference=(
            "GInternalLawsWindow populates lstLaws with law rows; each row's cboStatus is handled by "
            "OnComboBoxSelectionEvent. The list itself has no separate selection action."
        ),
        surface="InternalLawsPanel._render_laws / lstInternalLawsLawsItem rows",
        effect="Displays law rows with per-law choices that stage drafts for ActionChangePoliticalLaw on Apply.",
        action="none for selecting a list row; row status edits stage ActionChangePoliticalLaw",
        status="partial",
        validation="Choices are derived from the law's current authoritative row and the player-country scope.",
        constraints="Only law values represented by the OpenPower country-law model can be submitted.",
        confirmation="Law changes remain local until Apply or the user's Apply choice in dirty-close confirmation.",
        error="Stale or invalid values remain staged with a notice rather than silently applying.",
        mapping_notes=(
            "OpenPower uses typed per-law actions and its own supported choices; it does not reproduce the bundled "
            "source event's complete internal-law vector."
        ),
        action_required="Keep source list geometry for the row host and preserve per-law typed validation and draft state.",
        read_only_or_state_changing="read-only row host; child edits are local drafts until Apply",
    ),
    "Internal_Laws/frmInner/frmDemographicGroups/tabGroups/Tab1/lstGroups": _build_interaction_binding(
        reference=(
            "GInternalLawsWindow hosts religion rows in Tab1/lstGroups; the row cboStatus controls, not list selection, "
            "are handled as internal-law status changes."
        ),
        surface="InternalLawsPanel._identity / IdentityPolicyView religion rows",
        effect="Displays religion records and stages supported per-country identity-status edits from their row controls.",
        action="none for selecting a list row; child status edits stage ActionSetCountryIdentityPolicy",
        status="partial",
        validation="The identity record must be present and editable for the selected player country.",
        constraints="Only identity statuses represented by the OpenPower policy model are available.",
        confirmation="Identity edits remain local until Apply.",
        error="Missing identity records are omitted or disabled rather than mapped to another demographic group.",
        mapping_notes=(
            "The source list is a dynamic religion-row host with a broader source status set; OpenPower uses typed "
            "identity policies and its supported status subset."
        ),
        action_required="Keep religion rows bound by identity ID and retain player-country validation and draft semantics.",
        read_only_or_state_changing="read-only row host; child edits are local drafts until Apply",
    ),
    "Internal_Laws/frmInner/frmDemographicGroups/tabGroups/Tab2/lstGroups": _build_interaction_binding(
        reference=(
            "GInternalLawsWindow hosts language rows in Tab2/lstGroups; the row cboStatus controls, not list selection, "
            "are handled as internal-law status changes."
        ),
        surface="InternalLawsPanel._identity / IdentityPolicyView language rows",
        effect="Displays language records and stages supported per-country identity-status edits from their row controls.",
        action="none for selecting a list row; child status edits stage ActionSetCountryIdentityPolicy",
        status="partial",
        validation="The identity record must be present and editable for the selected player country.",
        constraints="Only identity statuses represented by the OpenPower policy model are available.",
        confirmation="Identity edits remain local until Apply.",
        error="Missing identity records are omitted or disabled rather than mapped to another demographic group.",
        mapping_notes=(
            "The source list is a dynamic language-row host with a broader source status set; OpenPower uses typed "
            "identity policies and its supported status subset."
        ),
        action_required="Keep language rows bound by identity ID and retain player-country validation and draft semantics.",
        read_only_or_state_changing="read-only row host; child edits are local drafts until Apply",
    ),
    "Internal_Laws/frmInner/frmHumanMigration/cboImmigrationStatus": _build_interaction_binding(
        reference=(
            "GInternalLawsWindow::OnCustomEvent maps cboImmigrationStatus to the source closed/open border flag; "
            "the changed value is saved in GInternalLawsUpdate."
        ),
        surface="InternalLawsPanel._render_migration / MigrationPanel",
        effect="Opens the OpenPower migration-policy editor for the selected country instead of toggling a source-only binary border flag.",
        action="none in Internal Laws; MigrationPanel submits supported ActionUpdateMigrationPolicy fields",
        status="partial",
        validation="The migration editor requires a current migration profile and player-country authority to apply changes.",
        constraints="Do not infer a binary border-closure state from OpenPower migration-posture or region-movement data.",
        confirmation="Migration policy edits are staged in their own editor until Apply.",
        error="Countries without a migration profile show an unavailable state and cannot submit a policy update.",
        mapping_notes=(
            "REFERENCE exposes a binary immigration-border flag; OpenPower offers a richer migration policy and has no "
            "equivalent border-closure action."
        ),
        action_required="Keep the navigation route distinct from changing immigration access and expose only supported migration policy.",
        read_only_or_state_changing="navigation to a separate local policy editor",
    ),
    "Internal_Laws/frmInner/frmHumanMigration/cboEmigrationStatus": _build_interaction_binding(
        reference=(
            "GInternalLawsWindow::OnCustomEvent maps cboEmigrationStatus to the source closed/open border flag; "
            "the changed value is saved in GInternalLawsUpdate."
        ),
        surface="InternalLawsPanel._render_migration / MigrationPanel",
        effect="Opens the OpenPower migration-policy editor for the selected country instead of toggling a source-only binary border flag.",
        action="none in Internal Laws; MigrationPanel submits supported ActionUpdateMigrationPolicy fields",
        status="partial",
        validation="The migration editor requires a current migration profile and player-country authority to apply changes.",
        constraints="Do not infer a binary border-closure state from OpenPower migration-posture or region-movement data.",
        confirmation="Migration policy edits are staged in their own editor until Apply.",
        error="Countries without a migration profile show an unavailable state and cannot submit a policy update.",
        mapping_notes=(
            "REFERENCE exposes a binary emigration-border flag; OpenPower offers a richer migration policy and has no "
            "equivalent border-closure action."
        ),
        action_required="Keep the navigation route distinct from changing emigration access and expose only supported migration policy.",
        read_only_or_state_changing="navigation to a separate local policy editor",
    ),
}
TREATIES_WINDOW_INTERACTION_BINDINGS = {
    "Treaties_Window/frmTitle/btnExit": _build_interaction_binding(
        reference=(
            "GTreatiesWindow::OnMouseClick delegates the title exit to GBaseWindow::ExitWindow; treaty browsing "
            "does not create a dirty draft in the source window."
        ),
        surface="LiveTreatiesPanel WindowManager window close / PanelManager visibility",
        effect="Closes the treaty browser; selected record and filter state stay local to the panel instance.",
        action="none (local treaty-browser close)",
        status="verified_openpower",
        constraints="Closing the browser does not accept, reject, create or modify a treaty.",
        action_required="Keep title close as local navigation and leave treaty actions to their explicit detail controls.",
        read_only_or_state_changing="local window visibility and selection state",
    ),
    "Treaties_Window/frmTitle/btnApply": _build_interaction_binding(
        reference=(
            "GTreatiesWindow::OnCreate explicitly hides the inherited GBaseWindow Apply button; treaty changes are "
            "handled by detail and proposal actions instead."
        ),
        surface="GMLLayoutSession.apply_base_window_titlebar_rules / LiveTreatiesPanel",
        effect="No title Apply control is drawn; treaty changes are submitted from explicit proposal/detail actions.",
        action="none (source title Apply is hidden)",
        status="verified_unavailable",
        constraints="Do not expose a generic title Apply action for read-only treaty browsing.",
        mapping_notes="The source explicitly hides this inherited control in GTreatiesWindow::OnCreate.",
        action_required="Keep the source-hidden Apply button absent and route mutations through treaty-specific controls.",
        read_only_or_state_changing="unavailable hidden control",
    ),
    "Treaties_Window/frmInner/frmFilters/cboType": _build_interaction_binding(
        reference=(
            "GTreatiesWindow::OnCustomEvent maps cboType to an ETreatyType filter and refreshes active and pending "
            "treaty rows; the source dropdown contains its full static treaty enumeration."
        ),
        surface="LiveTreatiesPanel._render_content / treaties.filter_type",
        effect="Filters active agreements and pending proposals by canonical treaty type without sending a game action.",
        action="none (local list filter)",
        status="partial",
        validation="The selected canonical type must be in the OpenPower treaty catalog or occur in the current mod data.",
        constraints="Only rows involving the selected country are displayed before the type filter is applied.",
        mapping_notes=(
            "OpenPower offers its full treaty-definition catalog plus observed mod types; the category vocabulary is "
            "not identical to REFERENCE's ETreatyType enumeration."
        ),
        action_required="Keep the filter read-only, stable by canonical type key, and independent of proposal actions.",
        read_only_or_state_changing="local filtered view",
    ),
    "Treaties_Window/frmInner/frmFilters/cboCountry": _build_interaction_binding(
        reference=(
            "GTreatiesWindow::OnCustomEvent stores the selected member and refreshes both treaty lists; FillCountries "
            "populates the control from the source country catalog."
        ),
        surface="LiveTreatiesPanel._render_content / treaties.filter_member",
        effect="Filters active agreements and pending proposals by a country tag from the country catalog.",
        action="none (local list filter)",
        status="verified_openpower",
        validation="The selected member tag must be a current country or a country referenced by the displayed treaty rows.",
        constraints="Filtering never changes the treaty participant set or sends an action.",
        mapping_notes="OpenPower labels country tags with their country name and tag; the source uses localized names and flags.",
        action_required="Keep country identity bound to the tag and apply the filter to both active and pending rows.",
        read_only_or_state_changing="local filtered view",
    ),
    "Treaties_Window/frmInner/frmActiveTreaties/lstTreaties": _build_interaction_binding(
        reference=(
            "OnListItemSelected stores the active treaty ID and enables View Selected; OnListItemDoubleClicked opens "
            "the selected treaty details directly."
        ),
        surface="LiveTreatiesPanel._render_active_table / treaties.active.<id> and treaties.view_selected",
        effect="Selects an active treaty by ID; the explicit View Details control opens the supported OpenPower details route.",
        action="none for selection; View Details opens read-only treaty inspection",
        status="partial",
        validation="Only active treaties involving the selected country and passing current filters are selectable.",
        constraints="Selection cannot change treaty membership; participant edits are gated by the separate detail workflow.",
        confirmation="None for selection or inspection; participant changes use their own Apply action.",
        mapping_notes=(
            "OpenPower preserves select-then-view but does not map REFERENCE's list double-click gesture; the active treaty "
            "identity and separate inspection route remain explicit."
        ),
        action_required="Keep row selection bound to treaty ID and preserve the distinct read-only inspection action.",
        read_only_or_state_changing="local selection and read-only inspection",
    ),
    "Treaties_Window/frmInner/frmPendingTreaties/lstTreaties": _build_interaction_binding(
        reference=(
            "OnListItemSelected stores the pending proposal ID and enables View Selected; OnListItemDoubleClicked "
            "opens that proposal's treaty details directly."
        ),
        surface="LiveTreatiesPanel._render_pending_table / treaties.pending.<id> and treaties.view_selected",
        effect="Selects a pending proposal by ID; the explicit View Details control opens its response/details route.",
        action="none for selection; a later response is a separate ActionRespondTreaty",
        status="partial",
        validation="Only pending proposals addressed to or involving the selected country and passing current filters are selectable.",
        constraints="Selection does not accept, reject, or modify a proposal.",
        confirmation="None for selection or inspection; Accept and Reject are separate explicit proposal actions.",
        mapping_notes=(
            "OpenPower preserves pending proposal identity and the separate view action but does not map REFERENCE's list "
            "double-click gesture."
        ),
        action_required="Keep proposal selection separate from acceptance/rejection and retain the pending proposal ID.",
        read_only_or_state_changing="local selection and read-only inspection",
    ),
}
_ADVISOR_SETTINGS_DRAFT_INTERACTION = {
    "reference_side_effect": (
        "GAdvisorSettingsWindow::OnMouseClick marks the window dirty when a selected mode differs "
        "from the authoritative player-country status; Save later sends all three modes."
    ),
    "openpower_surface": "AdvisorSettingsPanel._render_content / ActionUpdateAdvisorSettings",
    "openpower_effect": (
        "Edits the selected per-country mode in the panel draft; Apply submits all three modes "
        "through ActionUpdateAdvisorSettings. On daily policy evaluation, Automatic queues supported "
        "OpenPower actions and Confirmations stores them for ObjectivesPanel review; accepted and "
        "dismissed recommendations resolve through ActionResolveAdvisorRecommendation."
    ),
    "game_action": "none while editing; ActionUpdateAdvisorSettings(player_id, country_tag, economy_status, politics_status, military_status) on Apply",
    "read_only_or_state_changing": "local draft until Apply; then authoritative country-state update",
    "validation_condition": "Requires the active player country and one valid mode per advisor domain.",
    "country_scope_restriction": "Only the connected player's country can update its advisor statuses; the server rechecks authority.",
    "confirmation_state": "DirtyCloseConfirmation offers Apply or Discard when a mode draft is pending.",
    "error_state": "Rejected actions do not update the country snapshot; the panel keeps the draft available for retry.",
    "restrictions_confirmation_error": "Automatic and Confirmations operate on the bounded OpenPower policy subset; they do not claim the full REFERENCE advisor policy set or exact source cadence.",
    "action_required": "Keep the mode update and Apply/Discard draft paths covered; preserve verified execution/review for supported policies and explicit boundaries for source-only policies.",
    "status": "partial",
}
_ADVISOR_SETTINGS_WINDOW_ACTIONS = {
    "Advisor_Settings_Window/frmTitle/btnExit": {
        "reference_side_effect": "GAdvisorSettingsWindow::OnMouseClick hides a clean window; a dirty window opens Save_Confirmation_Window, or applies/discards according to the remembered preference.",
        "openpower_surface": "AdvisorSettingsPanel._request_close / DirtyCloseConfirmation",
        "openpower_effect": "Closes directly when clean; a dirty draft goes through the shared Apply/Discard close confirmation.",
        "game_action": "none (local window close; Apply is delegated to the caller)",
        "read_only_or_state_changing": "local UI close with explicit draft disposition",
        "validation_condition": "The Advisor Settings panel is visible.",
        "country_scope_restriction": "None for closing; applying the draft is restricted to the connected player's country.",
        "confirmation_state": "DirtyCloseConfirmation offers Apply or Discard while the draft is dirty.",
        "error_state": "A rejected Apply retains the draft and leaves the panel available for correction or retry.",
        "restrictions_confirmation_error": "Closing does not silently save or discard a pending draft.",
        "action_required": "Keep direct clean close and explicit dirty-draft disposition covered.",
        "status": "verified_openpower",
    },
    "Advisor_Settings_Window/frmTitle/btnApply": {
        "reference_side_effect": "GAdvisorSettingsWindow::Save sends GUpdateAdvisorSettings with the economy, politics, and military modes.",
        "openpower_surface": "AdvisorSettingsPanel._apply_changes",
        "openpower_effect": "Apply submits the three per-country advisor statuses in ActionUpdateAdvisorSettings and reconciles the draft against the authoritative country snapshot.",
        "game_action": "ActionUpdateAdvisorSettings(player_id, country_tag, economy_status, politics_status, military_status)",
        "read_only_or_state_changing": "authoritative state-changing country action",
        "validation_condition": "Requires a dirty supported draft, an active network client, and valid economy/politics/military modes; the server rechecks ownership and authority.",
        "country_scope_restriction": "Only the connected player's country may be updated.",
        "confirmation_state": "The title Apply commits directly; dirty close offers Apply or Discard.",
        "error_state": "A rejected action leaves authoritative statuses unchanged and preserves the draft for retry.",
        "restrictions_confirmation_error": "The action persists per-country modes; automatic execution and confirmation review apply to the supported OpenPower policy subset, not the complete REFERENCE advisor catalog.",
        "action_required": "Keep the authoritative status update and reconciliation covered; retain explicit source-policy boundaries until OpenPower has matching data and actions.",
        "status": "partial",
    },
}

ADVISOR_PLAN_INTERACTION_BINDINGS = {
    "Advisor_Window/frmInner/btnExecute": {
        "reference_side_effect": (
            "GAdvisorWindow::OnMouseClick sends GSendPlan with m_bAccept=true for the current plan, "
            "removes that plan from the local queue, then displays the next plan or hides the window."
        ),
        "openpower_surface": "ObjectivesPanel._open_recommendation_question / ActionResolveAdvisorRecommendation",
        "openpower_effect": (
            "OpenPower accepts an active recommendation by its string recommendation_id and executes its "
            "stored optional_action_json after authority and country checks. The REFERENCE numeric objective ID, "
            "plan type, and action-ID bundle have no direct field-level translation to that row."
        ),
        "game_action": (
            "ActionResolveAdvisorRecommendation(recommendation_id, accept=True) is the OpenPower accept analogue; "
            "no direct GSendPlan ID/action mapping exists."
        ),
        "read_only_or_state_changing": "source server event; OpenPower acceptance executes a stored action",
        "validation_condition": (
            "The source requires the current objective ID to remain in m_Plans. The server handles EHE plans "
            "and the Specific/TooManyMilitaryUnits case; that specific case only acts on an accepted ParkUnits action."
        ),
        "country_scope_restriction": (
            "REFERENCE resolves the event source to the active player's country. OpenPower checks that the player "
            "controls the recommendation country and that the stored action targets that country."
        ),
        "confirmation_state": (
            "Execute submits accept=true; the source removes the plan locally before displaying the next plan "
            "or hiding the window. OpenPower asks for explicit Review confirmation and resolves the recommendation asynchronously."
        ),
        "error_state": (
            "OpenPower rejects missing or inactive recommendation IDs, unsupported stored actions, and country mismatches. "
            "REFERENCE plan IDs and bundled action IDs are not directly accepted by this resolver."
        ),
        "restrictions_confirmation_error": (
            "The OpenPower recommendation resolver is a semantic analogue, not a wire-compatible mapping for "
            "REFERENCE's numeric objective/action ID payload."
        ),
        "action_required": (
            "Keep this path partial until a field-level adapter maps supported REFERENCE objectives and actions to "
            "OpenPower recommendation rows without inventing unsupported policies."
        ),
        "status": "partial",
    },
    "Advisor_Window/frmTitle/btnExit": {
        "reference_side_effect": (
            "GAdvisorWindow::OnMouseClick sends GSendPlan with m_bAccept=false for the current plan, "
            "removes that plan from the local queue, then displays the next plan or hides the window."
        ),
        "openpower_surface": "ObjectivesPanel._resolve_recommendation / ActionResolveAdvisorRecommendation",
        "openpower_effect": (
            "OpenPower dismisses an active recommendation by its string recommendation_id. The REFERENCE numeric "
            "objective ID and plan type have no direct field-level translation to an OpenPower recommendation row."
        ),
        "game_action": (
            "ActionResolveAdvisorRecommendation(recommendation_id, accept=False) is the OpenPower dismiss analogue; "
            "no direct GSendPlan ID mapping exists."
        ),
        "read_only_or_state_changing": "source server event; OpenPower dismissal changes recommendation status",
        "validation_condition": (
            "The source requires the current objective ID to remain in m_Plans. The REFERENCE EHE server path removes "
            "the pending plan; the Specific/TooManyMilitaryUnits handler ignores a rejection after the client removes it."
        ),
        "country_scope_restriction": (
            "REFERENCE resolves the event source to the active player's country for EHE plans. OpenPower checks that "
            "the player controls the recommendation country."
        ),
        "confirmation_state": (
            "Exit submits accept=false; the source removes the plan locally and displays the next plan or hides "
            "the window. OpenPower dismissal is an explicit negative answer in GenericQuestionDialog."
        ),
        "error_state": (
            "OpenPower rejects missing or inactive recommendation IDs. The source plan's numeric objective ID "
            "is not an OpenPower recommendation ID."
        ),
        "restrictions_confirmation_error": (
            "The OpenPower recommendation resolver is a semantic analogue, not a wire-compatible mapping for "
            "REFERENCE's numeric objective/action ID payload."
        ),
        "action_required": (
            "Keep this path partial until a field-level adapter maps supported REFERENCE plans to OpenPower "
            "recommendation rows without conflating dismissal with a generic window close."
        ),
        "status": "partial",
    },
}
for _advisor_toggle in (
    "togEconManual", "togEconAutomatic", "togEconConfirmations",
    "togPoliManual", "togPoliAutomatic", "togPoliConfirmations",
    "togMiliManual", "togMiliAutomatic", "togMiliConfirmations",
):
    _ADVISOR_SETTINGS_WINDOW_ACTIONS[
        f"Advisor_Settings_Window/frmInner/frmSettings/{_advisor_toggle}"
    ] = dict(_ADVISOR_SETTINGS_DRAFT_INTERACTION)
INCREASE_PRODUCTION_INTERACTION_BINDINGS = {
    "Increase_Production_Window/frmTitle/btnExit": {
        "openpower_effect": "Close the local dialog and discard its temporary percentage selection, matching GIncreaseProductionWindow::OnMouseClick.",
        "game_action": "none (local dialog dismissal)",
        "read_only_or_state_changing": "local UI state only",
        "validation_condition": "The dialog is opened only for a selected resource in ResourcesPanel.",
        "country_scope_restriction": "The parent ResourcesPanel disables the entry point for foreign countries.",
        "confirmation_state": "The source override calls Hide() directly; Python closes directly and resets all choices on the next open.",
        "error_state": "No close error state.",
        "restrictions_confirmation_error": "No production action is sent by closing the dialog.",
        "action_required": "Keep direct close and clear-on-open behavior aligned with the source override.",
        "status": "verified_openpower",
    },
    "Increase_Production_Window/frmTitle/togLockWindow": {
        "openpower_effect": "Hidden by GBaseWindow::OnCreate and absent from the Python dialog.",
        "game_action": "none (inactive source control)",
        "read_only_or_state_changing": "inactive",
        "validation_condition": "The source base window hides the lock toggle during creation.",
        "country_scope_restriction": "Not applicable while hidden.",
        "confirmation_state": "Not applicable while hidden.",
        "error_state": "Not applicable while hidden.",
        "restrictions_confirmation_error": "The control is hidden by source initialization.",
        "action_required": "Keep the lock toggle hidden to match the source initialization.",
        "status": "verified_unavailable",
    },
    "Increase_Production_Window/frmTitle/btnApply": {
        "openpower_panel_spec": "RESOURCES",
        "openpower_surface": "ResourcesPanel/IncreaseProductionDialog",
        "openpower_effect": "Chooses the highest independently selected percentage, closes the dialog, and returns that value for one ResourcesPanel ActionIncreaseResourceProduction dispatch; Apply stays disabled without an eligible estimate or while a matching action is pending.",
        "game_action": "ActionIncreaseResourceProduction(country_tag, resource_id, increase_percent)",
        "read_only_or_state_changing": "authoritative state-changing action",
        "validation_condition": "The server validates country authority, supported resource/percentage, finite treasury data, one national production row, and positive national or currently controlled regional output.",
        "country_scope_restriction": "Only the connected player's country may fund the increase; explicit regional rows outside its control are not increased.",
        "confirmation_state": "Independent percentage toggles remain selected until Apply or close. Apply submits once and remains unavailable while the authoritative result is pending.",
        "error_state": "Rejected commands flow through CommandFeedback/GenericMessageDialog; the pending entry point is restored after its result arrives.",
        "restrictions_confirmation_error": "The exact REFERENCE IncreaseProductionApproxCost implementation is missing. OpenPower uses one year of added output value and does not claim source cost parity.",
        "action_required": "Keep the OpenPower-specific estimate explicit; the live production journey verifies selection, dispatch, and close behavior. Exact source cost parity remains open in the value rows.",
        "status": "verified_openpower",
    },
    **{
        f"Increase_Production_Window/frmInner/frmInner/togIncrease{percent}": {
            "openpower_effect": "Toggle this percentage independently; multiple percentages may remain selected, and opening the dialog clears every choice.",
            "game_action": "local selection until Apply; Apply submits the highest selected percentage",
            "read_only_or_state_changing": "local UI selection",
            "validation_condition": f"Percentage choice is limited to {percent}%.",
            "country_scope_restriction": "The parent ResourcesPanel disables the entry point for foreign countries.",
            "confirmation_state": "Close hides the dialog directly; the next opening clears all choices.",
            "error_state": "Apply is enabled only for a supported OpenPower production basis and connected own-country session.",
            "restrictions_confirmation_error": "GML sets ToggleGroup=0 for each choice; the C++ Apply handler uses the last selected value in ascending control order, which is the highest selected percentage.",
            "action_required": "Preserve independent selection and the highest-selected-value Apply behavior.",
            "status": "verified_openpower",
        }
        for percent in (1, 2, 5, 10, 25)
    },
}
COVERT_CONTROL_INTERACTION_BINDINGS = {
    "Covert_Actions_Window/frmInner/frmCell/" + button: {
        "openpower_effect": effect,
        "game_action": action,
        "read_only_or_state_changing": "authoritative state-changing intent; new mission initially opens a local preparation form",
        "validation_condition": "Selected cell and mission ids must still exist, belong to the issuer and have the required stage. Execute additionally validates communications, assignment location and target availability.",
        "country_scope_restriction": "Own country with a connected session only; foreign private roster and forms are withheld.",
        "confirmation_state": "Preparing a UI mission explicitly opts into the ready stage. Execute starts the selected ready mission; cancellation does not refund preparation or charge again.",
        "error_state": "Server command rejection appears through GameLayout/CommandFeedback in GenericMessageDialog. A stale ready-mail request reports unavailable context and never selects another cell.",
        "restrictions_confirmation_error": "Server validates both authority and stage; duplicate execution is rejected and retirement cancels unresolved missions.",
        "action_required": "Keep native ready-mail/execute/cancel/retire/rejection journeys and authoritative lifecycle tests passing. Other source row controls remain separate gaps.",
        "status": "verified_openpower",
    } for button, effect, action in (
        ("btnNewMission", "Open preparation for the selected active cell, or execute its exact ready mission.", "ActionStartCovertMission(requires_execution_confirmation=True); ActionExecuteCovertMission"),
        ("btnCancelMission", "Cancel the selected preparing or ready mission and restore its cell to active.", "ActionCancelCovertMission"),
        ("btnDisbandCell", "Retire the selected owned cell and cancel its unresolved mission.", "ActionRetireCovertCell"),
    )
}
COVERT_CONTROL_INTERACTION_BINDINGS["Covert_Actions_Window/frmTitle/btnExit"] = {
    "reference_side_effect": "Inherited GBaseWindow::OnMouseClick calls ExitWindow; this panel has no unsaved local draft, so closing hides it without a Save confirmation.",
    "verified_cpp_transition": "GBaseWindow::OnMouseClick -> ExitWindow -> Hide (Client/Source/reference_base_window.cpp)",
    "openpower_effect": "Close CovertOpsPanel through the GML titlebar close control; cell and mission state changes are already submitted as authoritative actions.",
    "game_action": "none (local window close)",
    "read_only_or_state_changing": "local UI-only close",
    "validation_condition": "The Covert Actions panel is visible.",
    "country_scope_restriction": "None; closing the panel does not change country or mission state.",
    "confirmation_state": "No confirmation; this panel has no unsaved local draft.",
    "error_state": "None; closing sends no GameAction.",
    "restrictions_confirmation_error": "The inherited ExitWindow path hides this clean panel; Python uses the mapped GML titlebar close control.",
    "action_required": "Keep the titlebar close and no-GameAction behavior covered by the Covert Actions journey.",
    "status": "verified_openpower",
}
COVERT_MISSION_FORM_INTERACTION_BINDINGS = {
    "Covert_Actions_New_Mission/frmInner/frmMission/" + control: {
        "openpower_effect": "Local mission form selection; Prepare sends the selected mission category/profile, sector, complexity, target resource or unit category, assigned target country, and optional framed country.",
        "game_action": "ActionStartCovertMission(target_sector, complexity, target_resource_id, target_unit_category, target_country_tag, cover_country_tag)",
        "read_only_or_state_changing": "local selection until Prepare; authoritative state-changing intent on Prepare",
        "validation_condition": "Server validates issuer/cell ownership and stage, assigned target country, profile/sector compatibility, allowed complexity, target resource availability or military category, and framing country before charging preparation.",
        "country_scope_restriction": "Own country with an active assigned cell; the target country is inherited from that cell. Framed country cannot be the target, and foreign cell rosters remain private.",
        "confirmation_state": "Prepare opts into the ready stage; Execute remains a separate explicit action. Cancel closes the local form without dispatching a mission.",
        "error_state": "Invalid or stale terms are rejected by the authoritative command and surfaced through CommandFeedback/GenericMessageDialog.",
        "restrictions_confirmation_error": "Source complexity and specific-target modifiers now affect success; complexity scales effects. Civilian resource missions modify existing production, while military sabotage filters OpenPower units by domain. Base chance inputs remain OpenPower-specific; per-characteristic military research effects and the REFERENCE NationalSecurity protection formula are unavailable.",
        "action_required": "Preserve source modifiers and controlled-region resource effects. Trace an OpenPower per-characteristic research model before representing the REFERENCE military espionage/sabotage effect.",
        "status": "verified_openpower",
    } for control in ("cboMissionType", "cboSector", "cboComplexity", "cboResourceUnit", "cboCountry")
}
COVERT_FORM_ACTION_INTERACTION_BINDINGS = {
    "Covert_Actions_Cell_Creation/frmTitle/btnExit": _build_interaction_binding(
        reference="Close the cell-creation window.",
        surface="PanelSpec/COVERT_OPS/CovertActionWindows creation dialog",
        effect="Closes the local creation dialog without dispatching an action.",
        action="none (local window close)",
        action_required="",
    ),
    "Covert_Actions_Cell_Creation/frmTitle/btnApply": _build_interaction_binding(
        reference="Apply the window's changes.",
        surface="PanelSpec/COVERT_OPS/CovertActionWindows creation dialog",
        effect="Unavailable: the source creation window hides btnApply and this form submits through its Confirm button.",
        action="none (hidden source control)",
        status="verified_unavailable",
        action_required="",
    ),
    "Covert_Actions_Cell_Creation/frmInner/btnCancel": _build_interaction_binding(
        reference="Cancel cell creation and close the dialog.",
        surface="PanelSpec/COVERT_OPS/CovertActionWindows creation dialog",
        effect="Closes the local creation dialog without dispatching an action.",
        action="none (local window close)",
        action_required="",
    ),
    "Covert_Actions_Cell_Creation/frmInner/frmCell/edtName": _build_interaction_binding(
        reference="Edit the covert-cell name.",
        surface="PanelSpec/COVERT_OPS/CovertActionWindows creation dialog",
        effect="Keeps the cell name as local form state; Confirm trims and submits it with ActionCreateCovertCell.",
        action="ActionCreateCovertCell(cell_name)",
        validation="Confirm is disabled until the trimmed name is nonempty.",
        confirmation="No action is sent until Confirm is pressed.",
        error="The authoritative action handler records later capacity, funding, authority, or route failures.",
        action_required="",
    ),
    "Covert_Actions_Cell_Creation/frmInner/frmCell/cboCountry": _build_interaction_binding(
        reference="Choose the country assigned to the new cell.",
        surface="PanelSpec/COVERT_OPS/CovertActionWindows creation dialog",
        effect="Selects an OpenPower target country; the controlled country is excluded, and Confirm submits the selection as target_country_tag.",
        action="ActionCreateCovertCell(target_country_tag)",
        validation="The selected country must exist and the authoritative system must find a legal deployment route.",
        confirmation="Local selection until Confirm; route and country checks run authoritatively after dispatch.",
        error="Invalid countries and unavailable deployment routes are surfaced through CommandFeedback.",
        mapping_notes="OpenPower's target-country semantics determine the choices; the source combo also exposes its controlled-country default.",
        action_required="",
    ),
    "Covert_Actions_Cell_Creation/frmInner/frmCell/cboTraining": _build_interaction_binding(
        reference="Choose Recruit, Regular, Veteran, or Elite training for the new cell.",
        surface="PanelSpec/COVERT_OPS/CovertActionWindows creation dialog",
        effect="Selects one of OpenPower's covert skill levels; the quote recalculates upkeep and deployment time, and Confirm sends the level in ActionCreateCovertCell.",
        action="ActionCreateCovertCell(training_level)",
        validation="The authoritative system accepts only Recruit, Regular, Veteran, or Elite.",
        confirmation="Local selection until Confirm; the selected level is then applied to the created cell.",
        error="Invalid levels are rejected before funds or cell state change.",
        mapping_notes="REFERENCE prices each level and shows creation months. OpenPower keeps its flat setup-cost rule and previews the selected skill's upkeep plus route-based travel time.",
        action_required="",
    ),
    "Covert_Actions_Cell_Creation/frmInner/btnConfirm": {
        "openpower_surface": "PanelSpec/COVERT_OPS/CovertActionWindows creation dialog",
        "openpower_effect": "The dialog dispatches ActionCreateCovertCell with the controlled country, selected target, trimmed name, and selected skill level. CovertOperationsSystem checks issuer authority, country availability, skill level, capacity, funds, and foreign deployment routing before creating the cell.",
        "game_action": "ActionCreateCovertCell",
        "read_only_or_state_changing": "state-changing OpenPower GameAction",
        "country_scope_restriction": "The UI enables creation only for the player-controlled country; the system checks that authority and that both owner and target countries exist. Foreign deployment requires a valid route.",
        "confirmation_state": "No separate confirmation; dispatch closes the form. A later authoritative rejection is shown through GenericMessageDialog.",
        "error_state": "Blank names are prevented by the UI. Authority, capacity, funding, and route failures are recorded by the system and surfaced through CommandFeedback.",
        "restrictions_confirmation_error": "System-side checks are authoritative; the form cannot create cells for a country the issuer does not control.",
        "action_required": "",
        "status": "verified_openpower",
    },
    "Covert_Actions_Cell_Training/frmInner/btnConfirm": {
        "openpower_surface": "PanelSpec/COVERT_OPS/CovertActionWindows training dialog",
        "openpower_effect": "The dialog dispatches ActionTrainCovertCell with the selected cell and training allocation. CovertOperationsSystem checks cell availability, issuer authority, skill cap, positive allocation, and owner funds before starting timed training.",
        "game_action": "ActionTrainCovertCell",
        "read_only_or_state_changing": "state-changing OpenPower GameAction",
        "country_scope_restriction": "The UI lists cells for the current country; the system verifies the issuer controls the cell owner.",
        "confirmation_state": "No separate confirmation; training begins after the action is accepted. The form closes on dispatch.",
        "error_state": "Cell, authority, skill, allocation, or funding failures are recorded by the system and surfaced through CommandFeedback.",
        "restrictions_confirmation_error": "The system authoritatively rejects unavailable or foreign cells, maxed-out skill, nonpositive training, and unaffordable allocations.",
        "action_required": "",
        "status": "verified_openpower",
    },
    "Covert_Actions_New_Mission/frmInner/btnConfirm": {
        "openpower_surface": "PanelSpec/COVERT_OPS/CovertActionWindows mission preparation dialog",
        "openpower_effect": "The dialog dispatches ActionStartCovertMission with the selected cell, mission, target sector, complexity, optional cover country, and target resource or unit category. CovertOperationsSystem checks cell authority, readiness/location, assignment, mission/target compatibility, and funds before creating a preparation record.",
        "game_action": "ActionStartCovertMission",
        "read_only_or_state_changing": "state-changing OpenPower GameAction",
        "country_scope_restriction": "The UI starts missions only for the player-controlled country; the system verifies control of the selected cell and its assigned target.",
        "confirmation_state": "Preparation is a separate stage and sets requires_execution_confirmation=True; the later Execute action is explicit.",
        "error_state": "Invalid cell state, target, sector, complexity, cover, assignment, or funding is recorded by the system and surfaced through CommandFeedback.",
        "restrictions_confirmation_error": "Server-side validation is authoritative; preparation does not immediately execute the mission, and explicit execution remains required.",
        "action_required": "",
        "status": "verified_openpower",
    },
}
UNIT_ATTACK_INTERACTION_BINDINGS = {
    "Unit_Attack_Confirm_Window/" + button: {
        "openpower_effect": effect,
        "game_action": action,
        "read_only_or_state_changing": "local queue cancellation" if button == "btnNo" else "authoritative state-changing intent after explicit confirmation",
        "validation_condition": "Latest selected groups must remain alive/owned and the destination controller must match. Server validates actor, all groups, coordinates, domains and route before war creation.",
        "country_scope_restriction": "Own groups only; queues and actions are scoped to the captured target controller. Other countries' pending dialogs remain independent.",
        "confirmation_state": "One source-sized dialog per country; pending movement requests are accumulated until Yes or No.",
        "error_state": "Stale local selection shows GenericMessageDialog; authoritative rejections are delivered by CommandFeedback. A changed stationing permission uses ordinary movement without declaring war.",
        "restrictions_confirmation_error": "Yes consumes the queue before dispatch; No sends no action. Diplomacy preflight cannot authorize a foreign group or a blocked route.",
        "action_required": "Keep native confirm/cancel/stale/concurrent-country scenarios and real-engine authority tests passing.",
        "status": "verified_openpower",
    } for button, effect, action in (
        ("btnYes", "Consume this country's captured movement queue and submit each revalidated intent.", "ActionInvadeTerritory; ActionMoveUnit only if current access already permits entry"),
        ("btnNo", "Discard only this country's pending movement queue and hide its confirmation.", "none"),
    )
}
_UNIT_DESIGN_METERS = (
    ("GunRange", "gun_range"),
    ("GunPrecision", "gun_precision"),
    ("GunDamage", "gun_damage"),
    ("MissileRange", "missile_range"),
    ("MissilePrecision", "missile_precision"),
    ("MissileDamage", "missile_damage"),
    ("MissilePayload", "missile_payload"),
    ("Speed", "speed"),
    ("Stealth", "stealth"),
    ("Countermeasures", "countermeasures"),
    ("Armor", "armor"),
    ("Sensors", "sensors"),
)
_UNIT_DESIGN_OVERVIEW_METER_ROOT = (
    "Unit_Design_New/frmInner/tabGroups/Tab2/frmList/frmSpecs"
)
_UNIT_DESIGN_BUILDER_METER_ROOT = (
    "Unit_New_Design/frmDesignSpecs/frm1stLvlInner1/frmInner"
)


def _unit_design_caption_binding(token: str, caption: str, surface: str) -> DisplayBinding:
    return DisplayBinding(
        f"literal: current English {surface} caption for GML text token {token}",
        "static English caption",
        f"{caption}; the supplied source mirror does not include the REFERENCE localization tables.",
        "Rendered while the unit-design surface is visible.",
        "src/client/ui/panels/military/unit_design_panel.py; src/client/ui/panels/military/unit_design_editor.py; .codex/layout_catalog.gml",
        f"Current OpenPower caption for the {caption.lower()} source slot; exact source localization is unavailable.",
        status="partial",
        action_required="Use the exact REFERENCE localized caption only if the reference language tables are recovered.",
    )


def _unit_design_capability_binding(
    key: str, label: str, *, editable: bool
) -> DisplayBinding:
    if editable:
        state_binding = f"UnitDesignEditor._capabilities_by_role[selected_role][{key!r}]"
        update_rule = (
            "Initialized from DEFAULT_ROLE_PROFILES when a role is opened; slider edits stay in the role-local draft until CREATE sends ActionCreateUnitDesign."
        )
        fallback = (
            "The selected role's DEFAULT_ROLE_PROFILES capability value; slider bounds come from CAPABILITY_BOUNDS."
        )
        meaning = (
            f"Editable OpenPower {label.lower()} draft. REFERENCE uses the corresponding source characteristic meter with its own numeric scale and design validation."
        )
    else:
        state_binding = f"capabilities_for_design(selected_design or role_default)[{key!r}]"
        update_rule = (
            "Recomputed when the selected design or role changes; a missing saved value falls back to the role catalog."
        )
        fallback = (
            "DEFAULT_ROLE_PROFILES for the selected design role when the saved capability field is absent or invalid."
        )
        meaning = (
            f"OpenPower {label.lower()} value from the selected design or role profile. The progress-bar fill is normalized to CAPABILITY_BOUNDS and the displayed number remains in OpenPower units; REFERENCE uses a distinct source characteristic-meter scale."
        )
    return DisplayBinding(
        state_binding,
        "OpenPower role-bounded capability value",
        fallback,
        update_rule,
        f"src/client/ui/panels/military/{'unit_design_editor.py' if editable else 'unit_design_panel.py'}; src/client/ui/panels/military/unit_design_widgets.py; modules/base/systems/military/capability_catalog.py; .codex/Client/Source/reference_{'create_design_window.cpp' if editable else 'design_window.cpp'}",
        meaning,
        status="partial",
        action_required=(
            "Keep role bounds and the pending create action authoritative; do not label OpenPower values as REFERENCE's 0–10 meter readings."
            if editable else
            "Keep the selected design/profile source and OpenPower units explicit; do not imply the source meter scale is equivalent."
        ),
    )


_UNIT_DESIGN_CAPTION_TOKENS = {
    "GunRange": ("100195", "Gun range"),
    "GunPrecision": ("100196", "Gun precision"),
    "GunDamage": ("100197", "Gun damage"),
    "MissileRange": ("100198", "Missile range"),
    "MissilePrecision": ("100199", "Missile precision"),
    "MissileDamage": ("100200", "Missile damage"),
    "MissilePayload": ("100201", "Missile payload"),
    "Speed": ("100202", "Speed"),
    "Stealth": ("100203", "Stealth"),
    "Countermeasures": ("100204", "Countermeasures"),
    "Armor": ("100205", "Armor"),
    "Sensors": ("100206", "Sensors"),
}


def _build_unit_design_display_bindings() -> tuple[dict[str, DisplayBinding], dict[str, DisplayBinding]]:
    overview_root = _UNIT_DESIGN_OVERVIEW_METER_ROOT.removeprefix("Unit_Design_New/")
    builder_root = _UNIT_DESIGN_BUILDER_METER_ROOT.removeprefix("Unit_New_Design/")
    overview = {
        "frmTitle/lblTitle": _unit_design_caption_binding(
            "100188", "UNIT DESIGN", "design browser"
        ),
        "frmInner/frmUnitInfo/lblUnitName": _unit_design_caption_binding(
            "100193", "DESIGN", "design browser"
        ),
        "frmInner/frmUnitInfo/lblUnitType": _unit_design_caption_binding(
            "101480", "UNIT TYPE", "design browser"
        ),
        "frmInner/frmUnitInfo1/lblUnitCost": _unit_design_caption_binding(
            "100194", "UNIT COST", "design browser"
        ),
    }
    builder = {
        "frmTitle/lblTitle": _unit_design_caption_binding(
            "100188", "UNIT DESIGN", "design builder"
        ),
        "frmDesignSpecs/frm1stLvlInner1/lblTitle": _unit_design_caption_binding(
            "101482", "ADJUSTABLE CAPABILITIES", "design builder"
        ),
        "frmDesignSpecs/frmUnitInfo/lblUnitName": _unit_design_caption_binding(
            "100193", "DESIGN NAME", "design builder"
        ),
        "frmDesignSpecs/frmUnitInfo/lblUnitType": _unit_design_caption_binding(
            "101480", "UNIT TYPE", "design builder"
        ),
        "frmDesignSpecs/frm1stLvlInner1/frmUnitInfo1/lblUnitCost": _unit_design_caption_binding(
            "100194", "UNIT COST", "design builder"
        ),
    }
    for metric, key in _UNIT_DESIGN_METERS:
        token, label = _UNIT_DESIGN_CAPTION_TOKENS[metric]
        overview[f"{overview_root}/lbl{metric}"] = (
            _unit_design_caption_binding(token, label, "design statistics")
        )
        overview[f"{overview_root}/frm{metric}"] = (
            _unit_design_capability_binding(key, label, editable=False)
        )
        builder[f"{builder_root}/lbl{metric}"] = (
            _unit_design_caption_binding(token, label, "design builder")
        )
        builder[f"{builder_root}/frm{metric}"] = (
            _unit_design_capability_binding(key, label, editable=True)
        )

    overview.update({
        "frmInner/frmUnitInfo/cboUnitType": DisplayBinding(
            "UnitDesignPanel._role from unit_type_options_for_roles(DEFAULT_ROLE_PROFILES)",
            "OpenPower canonical unit role",
            "First available source-ordered role when the saved design's role is missing or unsupported.",
            "Updated by the local role combo; it filters compatible designs and selects the role profile when none is saved.",
            "src/client/ui/panels/military/unit_design_panel.py; src/client/ui/panels/military/unit_type_options.py; modules/base/systems/military/capability_catalog.py",
            "OpenPower role labels follow the 20 REFERENCE type IDs/order mapped to canonical roles; exact localized source type names remain unavailable.",
            status="partial",
            action_required="Keep the source type-ID/order mapping and expose OpenPower role names as mapped labels, not source-localized strings.",
        ),
        "frmInner/frmUnitInfo/cboUnitName": DisplayBinding(
            "UnitDesignPanel compatible designs_for_country(target_tag) filtered by canonical_role(class_name)",
            "saved design display name",
            "Disabled with 'No saved designs' when the selected role has no compatible rows.",
            "Reloaded from the current country design snapshot; selection updates UnitDesignSelection.design_id.",
            "src/client/ui/panels/military/unit_design_panel.py; src/client/ui/panels/military/design_selection.py; src/client/ui/panels/military/presenter.py",
            "OpenPower lists country-owned designs compatible with the selected role; it does not reproduce the source's full design-type taxonomy or localization.",
            status="partial",
            action_required="Keep selection country-scoped and role-filtered; preserve the explicit empty-design state.",
        ),
        "frmInner/frmUnitInfo/frmDescription/txtText": DisplayBinding(
            "UnitDesignPanel._design_description(selected_design)",
            "design name, domain, and canonical role text",
            "Explains that no saved design exists for the selected role when selection is empty.",
            "Rebuilt when the selected design or role changes.",
            "src/client/ui/panels/military/unit_design_panel.py; src/client/ui/panels/military/design_selection.py",
            "OpenPower gives a compact design/domain/role description; source description formatting and localization differ.",
            status="partial",
            action_required="Keep the description derived from the current design or role and retain the no-design explanation.",
        ),
        "frmInner/frmUnitInfo1/txtCost": DisplayBinding(
            "unit_designs.cost for the selected design",
            "OpenPower currency units",
            "Em dash when no design is selected; zero-valued or missing cost displays as zero for an existing row.",
            "Read from the selected design row whenever the design selection changes.",
            "src/client/ui/panels/military/unit_design_panel.py; src/client/ui/panels/military/presenter.py; modules/base/schema.py",
            "Selected design cost formatted as currency; cost basis can differ from REFERENCE's source-calculated design cost.",
            status="partial",
            action_required="Keep cost bound to the selected design record and preserve the documented source/OpenPower cost-basis difference.",
        ),
    })
    builder.update({
        "frmDesignSpecs/frmUnitInfo/cboUnitType": DisplayBinding(
            "UnitDesignEditor._role from unit_type_options_for_roles(DEFAULT_ROLE_PROFILES)",
            "OpenPower canonical unit role",
            "Defaults to infantry when no role is passed; unsupported values fall back to the first available role.",
            "Role changes select that profile's local capability draft; Create submits the selected role.",
            "src/client/ui/panels/military/unit_design_editor.py; src/client/ui/panels/military/unit_type_options.py; modules/base/systems/military/capability_catalog.py",
            "OpenPower roles map REFERENCE type IDs/order into its canonical role catalog; values/ranges remain OpenPower-specific.",
            status="partial",
            action_required="Keep type-ID translation/order explicit and keep role-specific capability drafts isolated by role.",
        ),
        "frmDesignSpecs/frmUnitInfo/frmDescription/txtText": DisplayBinding(
            "DEFAULT_ROLE_PROFILES[UnitDesignEditor._role].domain and role description",
            "domain and capability guidance text",
            "Uses the selected role profile; the selected role is normalized to a supported catalog entry.",
            "Rebuilt from the selected role profile during each editor render.",
            "src/client/ui/panels/military/unit_design_editor.py; modules/base/systems/military/capability_catalog.py",
            "OpenPower states the role/domain and clarifies that target rules stay fixed while capability values use OpenPower ranges.",
            status="partial",
            action_required="Keep the fixed-target and OpenPower-range explanation visible for every role.",
        ),
        "frmDesignSpecs/frm1stLvlInner1/frmUnitInfo1/txtCost": DisplayBinding(
            "UnitDesignEditor._cost draft",
            "OpenPower currency units",
            "0.0 until the user enters a cost; submission requires a positive value.",
            "Updated by the local numeric input; ActionCreateUnitDesign sends the entered cost with the capability draft.",
            "src/client/ui/panels/military/unit_design_editor.py; src/shared/actions.py; modules/base/systems/military/capability_catalog.py; .codex/Client/Source/reference_create_design_window.cpp",
            "OpenPower accepts a user-entered cost; REFERENCE computes cost from the source design formula, so numeric parity is not asserted.",
            status="partial",
            action_required="Keep the positive-cost validation and identify the value as user-entered; do not claim it matches REFERENCE's cost calculation.",
        ),
        "frmBuild/frmPage/cboType": DisplayBinding(
            "unavailable: no OpenPower model-part selector or unit model asset workflow",
            "disabled model-part selector",
            "Disabled and labeled as unavailable in the design builder.",
            "No update; OpenPower has no equivalent model-piece selection action.",
            "src/client/ui/panels/military/unit_design_editor.py; .codex/Client/Source/reference_create_design_window.cpp; .codex/layout_catalog.gml",
            "Source model-part selector is not connected to a supported OpenPower model asset workflow.",
            status="verified_unavailable",
            action_required="Keep the source slot visibly disabled and explain that model-part assets are unavailable.",
        ),
    })
    return overview, builder


UNIT_DESIGN_DISPLAY_BINDINGS, UNIT_DESIGN_BUILDER_DISPLAY_BINDINGS = (
    _build_unit_design_display_bindings()
)
DISPLAY_BINDINGS_BY_WINDOW["Unit_Design_New"] = UNIT_DESIGN_DISPLAY_BINDINGS
DISPLAY_BINDINGS_BY_WINDOW["Unit_New_Design"] = UNIT_DESIGN_BUILDER_DISPLAY_BINDINGS


def _unit_research_interaction(
    *,
    reference: str,
    surface: str,
    effect: str,
    action: str,
    status: str,
    validation: str,
    action_required: str,
    constraints: str = "OpenPower's selected country must be the player's own country for funding changes.",
    confirmation: str = "No confirmation is required for this interaction.",
    error: str = "None.",
    mapping_notes: str = "No additional source-to-OpenPower behavior difference is known.",
) -> dict[str, str]:
    return {
        "reference_side_effect": reference,
        "openpower_surface": surface,
        "openpower_effect": effect,
        "game_action": action,
        "read_only_or_state_changing": (
            "local navigation or window behavior" if action.startswith("none")
            else "authoritative research funding update"
        ),
        "validation_condition": validation,
        "country_scope_restriction": constraints,
        "confirmation_state": confirmation,
        "error_state": error,
        "restrictions_confirmation_error": mapping_notes,
        "action_required": action_required,
        "status": status,
    }


def _unit_production_interaction(
    *,
    reference: str,
    surface: str,
    effect: str,
    action: str = "none (local selection or display)",
    status: str = "verified_openpower",
    validation: str = "None.",
    constraints: str = "None; this interaction does not change persistent game state.",
    confirmation: str = "None.",
    error: str = "None.",
    mapping_notes: str = "No additional source-to-OpenPower behavior difference is known.",
    action_required: str,
) -> dict[str, str]:
    return {
        "reference_side_effect": reference,
        "openpower_surface": surface,
        "openpower_effect": effect,
        "game_action": action,
        "read_only_or_state_changing": (
            "read-only display" if action.startswith("none") and "display" in action
            else "local window behavior" if action.startswith("none") and "window" in action
            else "local selection or quantity draft" if action.startswith("none")
            else "authoritative production or deployment action"
        ),
        "validation_condition": validation,
        "country_scope_restriction": constraints,
        "confirmation_state": confirmation,
        "error_state": error,
        "restrictions_confirmation_error": mapping_notes,
        "action_required": action_required,
        "status": status,
    }


UNIT_PRODUCTION_INTERACTION_BINDINGS = {
    "Unit_Production_Window/frmRight/frmProduction/lstProduction": _unit_production_interaction(
        reference="GUnitProductionWindow::UpdateProductionStatus populates live production rows; each dynamic row contains a priority combo for order controls.",
        surface="UnitProductionPanel._render_production_queue / _render_production_row",
        effect="Renders current OpenPower production orders and their GML-positioned row controls; priority, hold, and cancel choices dispatch the corresponding verified actions.",
        action="ActionSetProductionPriority, ActionSetProductionPaused, ActionCancelProductionOrder from a row priority combo",
        constraints="Only queued or paused orders in the player's own country can be changed.",
        error="Stale or terminal order changes are rejected by the authoritative research program system.",
        action_required="Keep the GML row geometry and authoritative row actions covered by the production action journey.",
    ),
    "Unit_Production_Window/frmRight/frmProduction/frmCapacity/btnUnfilled": _unit_production_interaction(
        reference="A child of the source capacity meter; it is a visual segment and has no callback in GUnitProductionWindow.",
        surface="UnitProductionPanel._render_capacity / GMLWidgets.meter",
        effect="Draws the unfilled portion of the capacity meter; it does not accept input.",
        action_required="Keep the capacity meter in its source GML slot and do not expose a state-changing click action.",
    ),
    "Unit_Production_Window/frmRight/frmProduction/frmCapacity/btnFill": _unit_production_interaction(
        reference="A child of the source capacity meter; production-row fill buttons are explicitly disabled when rows are created.",
        surface="UnitProductionPanel._render_capacity / GMLWidgets.meter",
        effect="Draws the filled portion of the capacity meter; it does not accept input.",
        action_required="Keep the capacity meter as a read-only projection of allocated production capacity.",
    ),
    "Unit_Production_Window/frmRight/frmProduction/togAcceptForeign": _unit_production_interaction(
        reference="GUnitProductionWindow::OnMouseClick calls AcceptForeignOrder with the changed toggle state.",
        surface="UnitProductionPanel._render_accept_foreign_toggle",
        effect="Sends ActionSetForeignOrderAcceptance and reflects seller_acceptance_profiles on the next snapshot.",
        action="ActionSetForeignOrderAcceptance(player_id, country_tag, is_accepting)",
        constraints="Enabled only while the player controls the displayed country and has a network client.",
        error="The diplomacy and production systems recheck authority and seller eligibility.",
        action_required="Keep the toggle tied to the authoritative seller acceptance profile and the foreign-order journey.",
    ),
    "Unit_Production_Window/frmDesignList/frmInfo/cboPriority": _unit_production_interaction(
        reference="The selected build priority updates the displayed ETA and is passed to RequestBuildOrder when the player clicks Build.",
        surface="UnitProductionPanel._render_design_details",
        effect="Keeps a local priority draft, previews the shared production-policy ETA, and sends the selected priority with the domestic queue action.",
        action="ActionQueueUnitProduction.priority on submit",
        constraints="Enabled for a selected domestic design in the player's own country.",
        error="The authoritative handler validates country authority, design eligibility, funds, research, and demilitarization limits.",
        action_required="Keep the selected priority reflected in the preview and submitted queue action.",
    ),
    "Unit_Production_Window/frmDesignList/frmInfo/cboSpeed": _unit_production_interaction(
        reference="The NORMAL/FAST selection updates displayed price and ETA and is passed as m_iProductionSpeed with the build request.",
        surface="UnitProductionPanel._render_design_details",
        effect="The source-shaped combo is disabled because OpenPower's production action and order schema do not yet represent speed; the source cost modifier is also unavailable in the supplied reference files.",
        action="No action; ActionQueueUnitProduction has no production_speed field.",
        status="partial",
        validation="The control remains disabled for both domestic and foreign builders.",
        constraints="Do not enable FAST until an authoritative speed and cost policy is available.",
        confirmation="No order can be submitted with a speed selection.",
        error="None; unsupported speed cannot be selected.",
        mapping_notes="The source ETA formula shows a speed level of 0 or 1 and applies (speed + 1) to unit throughput, but the source production cost multiplier value is absent from the supplied C++ mirror and OpenPower has no matching authoritative policy.",
        action_required="Add a server-validated speed field, source-compatible cost policy, and queue ETA/throughput behavior before enabling the source combo.",
    ),
    "Unit_Production_Window/frmDesignList/btnBuild": _unit_production_interaction(
        reference="GUnitProductionWindow::OnMouseClick calls RequestBuildOrder for a domestic build or foreign request.",
        surface="UnitProductionPanel._render_design_details",
        effect="Disables domestic queue submission at 50 production rows, queues a valid order below that limit, or requests a foreign seller order; completed orders flow into deployment orders.",
        action="ActionQueueUnitProduction or ActionRequestForeignUnitOrder",
        status="partial",
        validation="Requires a selected design and quantity from 1 to 1,000,000; a domestic order also requires fewer than 50 production rows, while a foreign request requires an eligible seller.",
        constraints="The server revalidates authority, the 50-order queue limit, the 1,000,000 quantity bound, research, available funds, demilitarization limits, and foreign-order eligibility.",
        error="Rejected actions leave the production state unchanged; available rejection feedback is surfaced by the authoritative action path.",
        mapping_notes="OpenPower uses its native queued-production and foreign-contract models and now enforces the source row and quantity bounds. It does not reproduce REFERENCE's client advisor confirmation or available-manpower cap.",
        action_required="Preserve the tested queue bounds and foreign-request path; keep the remaining advisor-confirmation and recruitable-manpower differences explicit.",
    ),
    "Unit_Production_Window/frmDesignList/frmCost/frmQty/btnDown": _unit_production_interaction(
        reference="GUpdatableValue decreases quantity by one on press and selects 1/10/100 decrements by hold count after a 0.5-second delay.",
        surface="UnitProductionPanel._render_design_details",
        effect="Decreases the local requested quantity by one on press and applies the source 1/10/100 hold cadence.",
        action_required="Keep the zero bound, source hold cadence and submitted quantity covered by production journeys.",
    ),
    "Unit_Production_Window/frmDesignList/frmCost/frmQty/edtText": _unit_production_interaction(
        reference="The source quantity edit control changes the selected unit count and triggers a design-detail refresh.",
        surface="UnitProductionPanel._render_design_details",
        effect="Accepts a nonnegative integer quantity capped at 1,000,000 and refreshes cost and ETA previews; the authoritative handler rejects larger action payloads.",
        validation="Nondigit input is discarded; an empty digit sequence retains the prior quantity.",
        action_required="Keep quantity parsing and server-side validation bounded and verify the submitted quantity in the production journeys.",
    ),
    "Unit_Production_Window/frmDesignList/frmCost/frmQty/btnUp": _unit_production_interaction(
        reference="GUpdatableValue increases quantity by one on press and selects 1/10/100 increments by hold count after a 0.5-second delay.",
        surface="UnitProductionPanel._render_design_details",
        effect="Increases the local requested quantity by one on press and applies the source 1/10/100 hold cadence, within the existing OpenPower UI bound.",
        action_required="Keep the 1,000,000 UI bound, source hold cadence and submitted quantity covered by production journeys.",
    ),
    "Unit_Production_Window/frmDesignList/frmDesignList/cboCountry": _unit_production_interaction(
        reference="GUnitProductionWindow rebuilds the design list when the selected building country changes.",
        surface="UnitProductionPanel._render_builder_selector / _visible_designs",
        effect="Switches between own designs and eligible foreign designs and clears the previous design selection.",
        status="partial",
        constraints="Foreign designs are selectable only for the player's own country and eligible sellers; the selector is disabled when no alternate builder exists.",
        error="A foreign request remains disabled when the seller has not accepted requests.",
        mapping_notes="OpenPower derives builders from current eligible foreign designs and acceptance profiles instead of the source server's building-country list event.",
        action_required="Keep the builder list derived from current eligible seller data and verify both local and foreign order routes.",
    ),
    **{
        f"Unit_Production_Window/frmDesignList/frmFilter/{control}": _unit_production_interaction(
            reference=f"GUnitProductionWindow::OnMouseClick selects the {label.lower()} source unit category.",
            surface="UnitProductionPanel._render_category_filters / _visible_designs",
            effect=f"Filters the design tree to OpenPower designs mapped to the {category} category.",
            status="partial" if category == "strategic" else "verified_openpower",
            mapping_notes=(
                "OpenPower classifies design rows from domain, branch, class_name, and unit_type; exact localized REFERENCE type taxonomy is unavailable."
                if category == "strategic" else "Category filtering uses OpenPower design domain and role fields."
            ),
            action_required="Keep each source category filter interactive and preserve the known OpenPower-to-REFERENCE category mapping.",
        )
        for control, label, category in (
            ("togGround", "Ground", "ground"),
            ("togAir", "Air", "air"),
            ("togNaval", "Naval", "naval"),
            ("togStrategic", "Strategic", "strategic"),
        )
    },
    "Unit_Production_Window/frmTitle/btnExit": _unit_production_interaction(
        reference="The source titlebar exit hides GUnitProductionWindow.",
        surface="WindowManager.window('unit_production.panel')",
        effect="Closes the clean production panel without changing game state.",
        action="none (local window close)",
        action_required="Keep the GML titlebar close route reachable without dispatching a production action.",
    ),
}


UNIT_RESEARCH_INTERACTION_BINDINGS = {
    "Unit_Research_Window/frmTitle/btnExit": _unit_research_interaction(
        reference="The base window prompts to apply or discard dirty research changes before closing.",
        surface="WindowManager.window('unit_research.panel')",
        effect="Closes a clean research panel directly; dirty funding drafts use the shared Apply/Discard confirmation.",
        action="none (local window close)",
        status="verified_openpower",
        validation="A dirty draft stays open until Apply or Discard is selected.",
        confirmation="Uses the shared source-sized Save_Confirmation_Window when funding values are dirty.",
        action_required="Keep the titlebar close route available in the military research journey.",
        constraints="None; the panel is available while inspecting any country.",
    ),
    "Unit_Research_Window/frmTitle/togLockWindow": _unit_research_interaction(
        reference="GBaseWindow::OnCreate hides togLockWindow during initialization and relocates the title Apply button into its slot.",
        surface="GMLLayoutSession.apply_base_window_titlebar_rules",
        effect="The lock control is omitted; the visible Apply action uses the source-relocated title slot.",
        action="none (hidden source lock control)",
        status="verified_openpower",
        validation="The source Unit_Research_Window uses inherited GBaseWindow::OnCreate behavior.",
        action_required="Keep togLockWindow hidden and preserve the Apply slot relocation.",
        constraints="None.",
        mapping_notes="Do not expose lock behavior absent from the source runtime.",
    ),
    "Unit_Research_Window/frmTitle/btnApply": _unit_research_interaction(
        reference="Applies the modified research financing draft through GUnitResearchWindow::Save().",
        surface="UnitResearchPanel._render_title_controls",
        effect="Enables when funding differs from its baseline; Apply sends one ActionUpdateResearchFunding for each changed branch and keeps the panel open.",
        action="ActionUpdateResearchFunding for changed research branches",
        status="verified_openpower",
        validation="Enabled only for the player's own selected country and an active network client; unchanged branches are omitted.",
        confirmation="The title Apply commits directly; closing a dirty panel opens the shared Apply/Discard confirmation.",
        action_required="Keep the source-sized Apply control disabled for a clean draft and dispatch only the changed branch ratios when applied.",
        mapping_notes="OpenPower stores independent branch ratios; the source redistributes a linked budget across categories and characteristics.",
    ),
}

def _save_load_interaction(
    *,
    reference: str,
    callback: str,
    transition: str,
    effect: str,
    action: str,
    behavior: str,
    validation: str,
    error: str,
    action_required: str,
    status: str = "partial",
) -> dict[str, str]:
    return {
        "reference_callback": callback,
        "reference_side_effect": reference,
        "verified_cpp_transition": transition,
        "validation_condition": validation,
        "openpower_surface": "GameLayout/SaveGameDialog",
        "openpower_effect": effect,
        "game_action": action,
        "read_only_or_state_changing": behavior,
        "country_scope_restriction": "Save slots are local to the configured game project; REFERENCE further filters by active game type.",
        "confirmation_state": "No extra confirmation; the selected save name or slot is the user's intent.",
        "error_state": error,
        "restrictions_confirmation_error": "REFERENCE's save/load callbacks operate on local save slots; OpenPower validates names and reports loader/action failures through its existing feedback route.",
        "action_required": action_required,
        "status": status,
    }


SAVE_LOAD_INTERACTION_BINDINGS = {
    "Save_Game_Window/frmInner/frmSave/edtSaveName": _save_load_interaction(
        reference="On edit-end, the source enables Save only for a non-empty name; the value is saved only after btnSaveGame is clicked.",
        callback="OnCustomEvent@reference_save_game_window.cpp:95",
        transition="The c_iOnEditBoxEditEnd branch checks m_pObjNameEdt->Text().size() and enables or disables m_pObjSaveGameBtn at line 117.",
        effect="Edits the local save-name draft bound to save_game.name; submit validates it before sending ActionSaveGame.",
        action="none (local save-name draft)",
        behavior="local input draft; no save occurs until submit",
        validation="OpenPower rejects empty or non-canonical save names; REFERENCE enables the Save button when the text is non-empty.",
        error="Invalid names show a warning and do not dispatch ActionSaveGame.",
        action_required="Keep name validation before save dispatch and preserve the source name-input slot.",
    ),
    "Save_Game_Window/frmInner/frmSave/lstSaves": _save_load_interaction(
        reference="OnListItemSelected copies the selected row name into edtSaveName and enables the Save button.",
        callback="OnCustomEvent@reference_save_game_window.cpp:95",
        transition="The OnListItemSelected branch reads the selected save row, copies txtName to m_pObjNameEdt, and enables m_pObjSaveGameBtn at lines 97-114.",
        effect="Selecting an existing local save row prefills the save name; submit can replace that slot through the save action.",
        action="none (local save-slot selection)",
        behavior="local save selection and name prefill",
        validation="Only rows returned by the current local save listing can be selected.",
        error="An empty save list leaves no slot row to select.",
        action_required="Keep selection-to-name prefill; retain the documented source game-type filter and flag-column difference.",
    ),
    "Save_Game_Window/frmInner/btnSaveGame": _save_load_interaction(
        reference="The source save button passes edtSaveName text to GClientDCL::SaveGame and hides the window.",
        callback="OnMouseClick@reference_save_game_window.cpp:80",
        transition="The m_pObjSaveGameBtn branch calls SaveGame(m_pObjNameEdt->Text()) and hides the dialog at lines 87-89.",
        effect="Submits ActionSaveGame(player_id, save_name); command feedback reports success or rejection and closes the dialog.",
        action="ActionSaveGame(player_id, save_name)",
        behavior="state-changing save request",
        validation="The name must pass validate_save_name; the server validates the save request before persistence.",
        error="CommandFeedback shows rejected or failed save results; invalid names are blocked before dispatch.",
        action_required="Keep the save journey asserting the exact ActionSaveGame name and result feedback.",
        status="verified_openpower",
    ),
    "Load_Saved_Game/frmInner/frmList/lstGames": _save_load_interaction(
        reference="OnListItemSelected enables the Load button and marks the chosen save row selected.",
        callback="OnCustomEvent@reference_load_game_window.cpp:110",
        transition="The OnListItemSelected branch selects the row and enables m_pObjLoadGameBtn at lines 112-122.",
        effect="Selecting a local save row sets SaveGameDialog._selected and enables load_game.submit.",
        action="none (local save-slot selection)",
        behavior="local save selection",
        validation="Only rows returned by list_available_saves are selectable; submit validates the selected slot name.",
        error="An empty save list leaves Load disabled; an unreadable or stale slot reports through the existing load error path.",
        action_required="Keep the fixture-backed journey asserting the selected local slot and the enabled Load control.",
        status="verified_openpower",
    ),
    "Load_Saved_Game/frmInner/btnLoadGame": _save_load_interaction(
        reference="The source load button reads the selected row name, calls GClientDCL::LoadGame for a non-empty name, and hides the window.",
        callback="OnMouseClick@reference_load_game_window.cpp:80",
        transition="The m_pObjLoadGameBtn branch reads the selected row name, calls LoadGame(l_sGame) when non-empty, and hides the dialog at lines 87-100.",
        effect="Calls the configured local navigation loader with the selected save name and closes after dispatch.",
        action="none (local saved-game navigation)",
        behavior="local load request and view navigation",
        validation="A selected slot name must pass validate_save_name before navigation loads it.",
        error="A missing game configuration reports an error; load failures are shown by the loading view.",
        action_required="Keep the fixture-backed journey asserting the exact local load request and selected save name.",
        status="verified_openpower",
    ),
}


SAVE_CONFIRMATION_INTERACTION_BINDINGS = {
    "Save_Confirmation_Window/togRemember": {
        "reference_side_effect": "Sets the shared do-not-show preference; when selected, the next Apply or Discard choice is remembered.",
        "openpower_surface": "DirtyCloseConfirmation.render",
        "openpower_effect": "Stores the remember checkbox and selected decision in the GameLayout-scoped SaveConfirmationPreferences shared by dirty panels.",
        "game_action": "none (local UI preference)",
        "read_only_or_state_changing": "local preference update",
        "validation_condition": "The preference is updated only when Apply or Discard closes the confirmation.",
        "country_scope_restriction": "None.",
        "confirmation_state": "The checkbox changes whether later dirty-close prompts use the saved choice.",
        "error_state": "None; no game action is sent by the checkbox.",
        "restrictions_confirmation_error": "The preference is shared by the seven dirty-capable panels for the active GameLayout session.",
        "action_required": "Keep the remembered choice shared across dirty-close callers and scoped to the active game layout.",
        "status": "verified_openpower",
    },
    "Save_Confirmation_Window/btnApply": {
        "reference_side_effect": "Calls Save() on the dirty caller, hides the caller and closes the confirmation.",
        "openpower_surface": "DirtyCloseConfirmation.render followed by the caller panel's _finish_close handler",
        "openpower_effect": "Returns Apply to the caller, which commits through its existing supported action or local settings path and closes only after that handler accepts the draft.",
        "game_action": "caller-specific; the shared confirmation itself dispatches no GameAction",
        "read_only_or_state_changing": "delegated to caller commit behavior",
        "validation_condition": "Disabled when the caller cannot apply; the caller validates authority, draft state and current snapshot before committing.",
        "country_scope_restriction": "Caller-specific; own-country-only callers enforce player-country authority.",
        "confirmation_state": "This button is the explicit Apply choice for the pending dirty-close confirmation.",
        "error_state": "The caller retains a rejected draft and reports its existing validation or action error where supported.",
        "restrictions_confirmation_error": "The caller owns the authoritative commit; choosing Apply is not itself evidence that a GameAction succeeded.",
        "action_required": "Keep Apply connected to each caller's supported commit handler and retain its rejection behavior.",
        "status": "verified_openpower",
    },
    "Save_Confirmation_Window/btnDont": {
        "reference_side_effect": "Hides the dirty caller without calling Save(), then closes the confirmation.",
        "openpower_surface": "DirtyCloseConfirmation.render followed by the caller panel's discard handler",
        "openpower_effect": "Returns Discard to the caller, which clears its pending draft and closes without dispatching a GameAction.",
        "game_action": "none (local draft discard)",
        "read_only_or_state_changing": "local draft discard and window close",
        "validation_condition": "Available while the dirty-close confirmation is open.",
        "country_scope_restriction": "None.",
        "confirmation_state": "This button is the explicit Discard choice for the pending dirty-close confirmation.",
        "error_state": "None; discard sends no state-changing action.",
        "restrictions_confirmation_error": "Caller-side discard clears staged edits; committed game state remains unchanged.",
        "action_required": "Keep discard free of state-changing actions and clear the caller's staged edits.",
        "status": "verified_openpower",
    },
}

for _branch, _toggle, _frame in (
    ("ground", "togGround", "frmGroundFinancing"),
    ("air", "togAir", "frmAirFinancing"),
    ("naval", "togNaval", "frmNavalFinancing"),
    ("strategic", "togStrategic", "frmStrategicFinancing"),
):
    UNIT_RESEARCH_INTERACTION_BINDINGS[f"Unit_Research_Window/frmMain/{_toggle}"] = _unit_research_interaction(
        reference=f"Selects the {_branch} category, refreshes its research details and changes the model preview.",
        surface="UnitResearchPanel._render_categories",
        effect=f"Selects the {_branch} OpenPower research branch and updates the summary and selected detail page.",
        action="none (local research category selection)",
        status="verified_openpower",
        validation="None; each category selector remains available.",
        action_required="Keep category selection reflected in the right-side program summary and active detail tab.",
        constraints="None; category selection does not expose a state-changing action.",
    )

for _branch, _frame in (
    ("ground", "frmGroundFinancing"),
    ("air", "frmAirFinancing"),
    ("naval", "frmNavalFinancing"),
    ("strategic", "frmStrategicFinancing"),
):
    for _part in ("btnFill", "btnUnfilled"):
        UNIT_RESEARCH_INTERACTION_BINDINGS[
            f"Unit_Research_Window/frmMain/{_frame}/frmFinancing/{_part}"
        ] = _unit_research_interaction(
            reference="A linked GFinancingMeter changes the category share of the modified research-budget draft.",
            surface="UnitResearchPanel._render_funding_controls",
        effect=f"Stages the {_branch} branch's funding_ratio; title Apply sends ActionUpdateResearchFunding for changed branches.",
            action=f"ActionUpdateResearchFunding(branch='{_branch}', funding_ratio)",
            status="partial",
            validation="Enabled only for the player's country and an active network client; the authoritative handler checks country ownership.",
            action_required="Keep the source meter slot and OpenPower action connected; preserve the documented difference between linked source allocations and independent OpenPower branch ratios.",
            confirmation="Editing stages a draft; title Apply commits it, while closing a dirty panel asks Apply or Discard.",
            error="The server records a rejection when the issuer does not control the selected country.",
            mapping_notes="REFERENCE redistributes a linked category budget draft; OpenPower changes this branch ratio independently.",
        )

_UNIT_RESEARCH_METRICS = (
    "GunRange", "GunPrecision", "GunDamage", "MissileRange", "MissilePrecision",
    "MissileDamage", "MissilePayload", "Speed", "Sensors", "Armor", "Stealth",
    "Countermeasures",
)
_UNIT_RESEARCH_METRIC_LABELS = (
    "Gun Range", "Gun Precision", "Gun Damage", "Missile Range", "Missile Precision",
    "Missile Damage", "Missile Payload", "Speed", "Sensors", "Armor", "Stealth",
    "Countermeasures",
)
_UNIT_RESEARCH_STRATEGIC_BRANCHES = (
    "strategic_program", "strategic_weapons", "strategic_defense",
)


def _unit_research_caption_binding(token: str, caption: str) -> DisplayBinding:
    return DisplayBinding(
        f"literal: current English UnitResearchPanel caption for GML token {token}",
        "static English caption",
        f"{caption}; the supplied source mirror does not include the REFERENCE localization tables.",
        "Rendered from the selected research detail page.",
        "src/client/ui/panels/military/unit_research_panel.py; .codex/layout_catalog.gml",
        f"English caption for the {caption.lower()} source slot; exact source localization is unavailable.",
        status="partial",
        action_required="Use the exact REFERENCE localized caption only if the reference language tables are recovered.",
    )


def _unit_research_characteristic_binding(
    page: str, metric_index: int, metric: str, label: str, *, value_label: bool = False
) -> DisplayBinding:
    strategic_branch = (
        _UNIT_RESEARCH_STRATEGIC_BRANCHES[metric_index]
        if metric_index < len(_UNIT_RESEARCH_STRATEGIC_BRANCHES)
        else None
    )
    if page == "Tab1":
        display_kind = "technology ceiling"
        if strategic_branch:
            state_binding = f"research_tracks[{strategic_branch}].research_level"
            units = "OpenPower research level (displayed for Strategic only)"
            status = "partial"
            meaning = (
                f"The source slot is a per-characteristic {display_kind}; OpenPower overlays the {strategic_branch} branch level in this slot only when Strategic is selected."
            )
        else:
            state_binding = f"unavailable: no per-characteristic {display_kind} field in OpenPower research_tracks"
            units = "source technology ceiling"
            status = "verified_unavailable"
            meaning = f"REFERENCE displays a {label} {display_kind}; OpenPower has no per-characteristic ceiling field."
    elif page == "Tab2":
        display_kind = "per-characteristic progress and remaining days"
        if strategic_branch:
            state_binding = f"research_tracks[{strategic_branch}].progress"
            units = "OpenPower branch progress ratio (0–1), displayed as percent"
            status = "partial"
            meaning = (
                f"The source slot reports {label} completion days; OpenPower displays {strategic_branch} branch progress here instead of characteristic-specific remaining days."
            )
        else:
            state_binding = f"unavailable: no per-characteristic progress or completion-time field for {metric}"
            units = "source remaining days"
            status = "verified_unavailable"
            meaning = f"REFERENCE computes {label} completion days; OpenPower stores no per-characteristic progress or time-to-completion value."
    else:
        display_kind = "per-characteristic funding ratio"
        if strategic_branch:
            state_binding = f"research_tracks[{strategic_branch}].funding_ratio → local funding draft"
            units = "OpenPower branch funding ratio (0–1)"
            status = "partial"
            meaning = (
                f"The source slot allocates part of the selected category budget to {label}; OpenPower maps this slot to {strategic_branch} only when Strategic is selected."
            )
        else:
            state_binding = f"unavailable: no per-characteristic funding ratio for {metric}"
            units = "source budget share (%)"
            status = "verified_unavailable"
            meaning = "REFERENCE allocates linked budget by characteristic; OpenPower exposes only independent branch funding ratios."

    if value_label:
        meaning += " The Python progress value is a percent for the first three Strategic tracks and N/A otherwise."
    return DisplayBinding(
        state_binding,
        units,
        "N/A for source-only per-characteristic values; strategic branch overlays are empty when the relevant track is absent.",
        "Recomputed from the selected branch's research snapshot and current funding draft when UnitResearchPanel renders.",
        "src/client/ui/panels/military/unit_research_panel.py; src/client/ui/panels/military/presenter.py; .codex/Client/Source/reference_unit_research_window.cpp",
        meaning,
        status=status,
        action_required=(
            "Keep strategic branch values labeled as OpenPower branch data; do not present them as REFERENCE characteristic-level values."
            if status == "partial" else
            "Keep the source-specific per-characteristic value explicitly unavailable; do not derive it from branch totals."
        ),
    )


def _build_unit_research_display_bindings() -> dict[str, DisplayBinding]:
    bindings: dict[str, DisplayBinding] = {
        "frmTitle/lblTitle": _unit_research_caption_binding("100207", "UNIT RESEARCH"),
    }
    source = (
        "src/client/ui/panels/military/unit_research_panel.py; "
        "src/client/ui/panels/military/presenter.py; "
        ".codex/Client/Source/reference_unit_research_window.cpp"
    )
    for branch, frame in (
        ("ground", "frmGroundFinancing"),
        ("air", "frmAirFinancing"),
        ("naval", "frmNavalFinancing"),
        ("strategic", "frmStrategicFinancing"),
    ):
        bindings[f"frmMain/{frame}/frmFinancing"] = DisplayBinding(
            f"research_tracks[{branch}].funding_ratio → UnitResearchPanel local draft",
            "OpenPower branch funding ratio (0–1)",
            "0.0 and NEW when no matching branch track or pending funding request exists.",
            "Loaded from the selected country's research snapshot; edits remain local until Apply sends ActionUpdateResearchFunding.",
            source,
            f"{branch.capitalize()} research funding. REFERENCE displays a share of one linked budget and redistributes category funding; OpenPower stores this branch ratio independently.",
            status="partial",
            action_required="Keep branch funding identified as an OpenPower ratio; do not imply REFERENCE's linked-budget redistribution.",
        )
        bindings[f"frmMain/{frame}/lblNextAdvancement"] = DisplayBinding(
            f"research_tracks[{branch}].funding_ratio or pending_funding_by_country[{branch}]",
            "OpenPower funding percent or NEW marker",
            "NEW when no branch track or pending value exists.",
            "Rendered from the current local funding draft and pending action state.",
            source,
            "Python displays the funding ratio in this source label slot. The source GML contains localized token 100209 and the C++ mirror does not assign a data member to it; exact source wording and intended display semantics remain unresolved.",
            status="partial",
            action_required="Verify token 100209 from the reference localization bundle and keep the funding value in its confirmed source slot.",
        )

    # The specialized source frame is a visual wrapper, not an independent metric.
    bindings["frmDetails/tabResearch/Tab2/frmInner"] = DisplayBinding(
        "visual: per-characteristic progress detail page container",
        "visual-only detail page",
        "No independent value; child rows carry the data contract.",
        "Rendered as the selected progress tab page.",
        source,
        "REFERENCE's frmUnitResearchProgress visual container; OpenPower draws its GML-positioned child slots directly.",
        status="partial",
        action_required="Keep this row classified as a visual container and bind values only to its children.",
    )

    text_tokens = (
        "100195", "100196", "100197", "100198", "100199", "100200",
        "100201", "100202", "100206", "100205", "100203", "100204",
    )
    for page in ("Tab1", "Tab2", "Tab3"):
        for metric_index, (metric, label, token) in enumerate(
            zip(_UNIT_RESEARCH_METRICS, _UNIT_RESEARCH_METRIC_LABELS, text_tokens, strict=True)
        ):
            page_root = f"frmDetails/tabResearch/{page}/frmInner"
            bindings[f"{page_root}/lbl{metric}"] = _unit_research_caption_binding(token, label)
            bindings[f"{page_root}/frm{metric}"] = _unit_research_characteristic_binding(
                page, metric_index, metric, label
            )
            if page == "Tab2":
                bindings[f"{page_root}/frm{metric}/lblValue"] = _unit_research_characteristic_binding(
                    page, metric_index, metric, label, value_label=True
                )

    return bindings


UNIT_RESEARCH_DISPLAY_BINDINGS = _build_unit_research_display_bindings()
DISPLAY_BINDINGS_BY_WINDOW["Unit_Research_Window"] = UNIT_RESEARCH_DISPLAY_BINDINGS


for _page, _page_label in (("Tab1", "technology ceiling"), ("Tab2", "per-characteristic progress")):
    for _metric in _UNIT_RESEARCH_METRICS:
        for _part in ("btnFill", "btnUnfilled"):
            UNIT_RESEARCH_INTERACTION_BINDINGS[
                f"Unit_Research_Window/frmDetails/tabResearch/{_page}/frmInner/frm{_metric}/{_part}"
            ] = _unit_research_interaction(
                reference=f"The {_page_label} meter child is read-only in the source research window.",
                surface="UnitResearchPanel._render_detail_page",
                effect=(
                    "Shows N/A for per-characteristic values; OpenPower exposes only branch research levels and progress."
                ),
                action="none (read-only source meter component)",
                status="verified_unavailable",
                validation="The source meter has no edit callback; corresponding per-characteristic values are absent from OpenPower research_tracks.",
                action_required="Keep these per-characteristic meter parts read-only and label them unavailable rather than deriving values from branch aggregates.",
                constraints="None; the values are informational and cannot be edited.",
            )

for _index, _metric in enumerate(_UNIT_RESEARCH_METRICS):
    _strategic_branch = ("strategic_program", "strategic_weapons", "strategic_defense")[_index] if _index < 3 else ""
    for _part in ("btnFill", "btnUnfilled"):
        UNIT_RESEARCH_INTERACTION_BINDINGS[
            f"Unit_Research_Window/frmDetails/tabResearch/Tab3/frmInner/frm{_metric}/{_part}"
        ] = _unit_research_interaction(
            reference="The owned GFinancingMeter edits one characteristic share in the research draft; the source sliders are cursor-linked.",
            surface="UnitResearchPanel._render_detail_page",
            effect=(
                f"When Strategic is selected, this first-three meter slot controls {_strategic_branch} branch funding."
                if _strategic_branch else
                "Shows N/A because OpenPower does not store per-characteristic funding."
            ),
            action=(
                f"ActionUpdateResearchFunding(branch='{_strategic_branch}', funding_ratio)"
                if _strategic_branch else
                "none (unavailable per-characteristic funding action)"
            ),
            status="partial" if _strategic_branch else "verified_unavailable",
            validation=(
                "The Strategic category must be selected; editing is enabled only for the player's country and an active client."
                if _strategic_branch else
                "No per-characteristic funding field or action exists in OpenPower."
            ),
            action_required=(
                "Keep the conditional strategic-branch mapping visible and stage the value until Apply."
                if _strategic_branch else
                "Keep this source meter disabled and explicitly unavailable in OpenPower."
            ),
            confirmation=(
                "The selected strategic sub-branch ratio is staged; title Apply commits it and close prompts Apply or Discard."
                if _strategic_branch else
                "No edit is possible because this source-specific funding field is unavailable."
            ),
            error=(
                "The server records a rejection when the issuer does not control the selected country."
                if _strategic_branch else
                "None; the control is read-only and unavailable."
            ),
            mapping_notes=(
                "OpenPower maps these first three Strategic slots to strategic_program, strategic_weapons, and strategic_defense branch ratios; non-strategic per-stat ratios are not modeled."
                if _strategic_branch else
                "REFERENCE applies cursor-linked per-characteristic allocations; OpenPower has no per-characteristic funding fields."
            ),
        )

def _unit_market_interaction(
    *,
    reference: str,
    surface: str,
    effect: str,
    action: str = "none (local selection or display)",
    status: str = "verified_openpower",
    validation: str = "None.",
    constraints: str = "None; this control does not change persistent game state.",
    confirmation: str = "None.",
    error: str = "None.",
    mapping_notes: str = "No additional source-to-OpenPower behavior difference is known.",
    action_required: str,
) -> dict[str, str]:
    return {
        "reference_side_effect": reference,
        "openpower_surface": surface,
        "openpower_effect": effect,
        "game_action": action,
        "read_only_or_state_changing": (
            "read-only display" if action.startswith("none") and "display" in action
            else "local UI window behavior" if action.startswith("none") and "window" in action
            else "local selection or quantity draft" if action.startswith("none")
            else "authoritative state-changing purchase request"
        ),
        "validation_condition": validation,
        "country_scope_restriction": constraints,
        "confirmation_state": confirmation,
        "error_state": error,
        "restrictions_confirmation_error": mapping_notes,
        "action_required": action_required,
        "status": status,
    }


def _unit_list_interaction(
    *,
    reference: str,
    surface: str,
    effect: str,
    action: str = "none (local display or selection)",
    status: str = "verified_openpower",
    validation: str = "None.",
    constraints: str = "None; this interaction does not change persistent game state.",
    confirmation: str = "None.",
    error: str = "None.",
    mapping_notes: str = "No additional source-to-OpenPower behavior difference is known.",
    read_only_or_state_changing: str | None = None,
    action_required: str,
) -> dict[str, str]:
    return {
        "reference_side_effect": reference,
        "openpower_surface": surface,
        "openpower_effect": effect,
        "game_action": action,
        "read_only_or_state_changing": read_only_or_state_changing or (
            "authoritative state-changing action" if not action.startswith("none")
            else "local window, sort, filter, or selection state"
        ),
        "validation_condition": validation,
        "country_scope_restriction": constraints,
        "confirmation_state": confirmation,
        "error_state": error,
        "restrictions_confirmation_error": mapping_notes,
        "action_required": action_required,
        "status": status,
    }


def _unit_reserves_interaction(
    *,
    reference: str,
    surface: str,
    effect: str,
    callback: str = "",
    action: str = "none (local selection or window behavior)",
    status: str = "verified_openpower",
    validation: str = "None.",
    constraints: str = "None; this interaction does not change persistent game state.",
    confirmation: str = "None.",
    error: str = "None.",
    mapping_notes: str = "No additional source-to-OpenPower behavior difference is known.",
    action_required: str,
) -> dict[str, str]:
    return {
        "reference_side_effect": reference,
        "reference_callback": callback,
        "openpower_surface": surface,
        "openpower_effect": effect,
        "game_action": action,
        "read_only_or_state_changing": (
            "authoritative deployment or training action" if not action.startswith("none")
            else "local panel, category, or selection state"
        ),
        "validation_condition": validation,
        "country_scope_restriction": constraints,
        "confirmation_state": confirmation,
        "error_state": error,
        "restrictions_confirmation_error": mapping_notes,
        "action_required": action_required,
        "status": status,
    }


UNIT_RESERVES_INTERACTION_BINDINGS = {
    "Unit_Ground_Deployment_Window/frmTitle/btnExit": _unit_reserves_interaction(
        reference="GBaseWindow::ExitWindow closes Unit_Ground_Deployment_Window without changing deployment state.",
        callback="GBaseWindow::OnMouseClick@reference_base_window.cpp:94",
        surface="UnitReservesPanel / WindowManager GML title close",
        effect="Closes the reserves panel and preserves all current game state.",
        action="none (local panel close)",
        action_required="Keep title close as a local dismissal path; do not dispatch a unit action when the panel closes.",
    ),
    "Unit_Ground_Deployment_Window/frmTitle/btnApply": _unit_reserves_interaction(
        reference="GUnitGroundDeploymentWindow::OnCreate hides m_pObjApplyBtn after base-window initialization.",
        surface="UnitReservesPanel GML title slots",
        effect="The source-hidden Apply button is omitted; the panel has no Apply operation.",
        action="none (source-hidden control)",
        validation="GUnitGroundDeploymentWindow::OnCreate explicitly hides the inherited Apply button.",
        constraints="The hidden control cannot change game state.",
        error="None; no Apply request can be made from this panel.",
        action_required="Keep Apply hidden for this source window; do not apply the generic base-window title relocation after the derived OnCreate hides it.",
    ),
    "Unit_Ground_Deployment_Window/frmInner/btnDeploy": _unit_reserves_interaction(
        reference="OnMouseClick deploys the non-training selected groups to the controlled country's capital, except while the strategic tab is active.",
        callback="OnMouseClick@reference_unit_ground_deployment_window.cpp:337",
        surface="UnitReservesPanel._render_actions",
        effect="Sends one ActionDispatchUnitDeployment per selected dispatchable group to the current country's capital region.",
        action="ActionDispatchUnitDeployment(player_id, unit_id, destination_region_id=capital_region_id, quantity=0)",
        status="partial",
        validation="Enabled only for current-country reserve groups outside training, with a valid current capital region and a network client; disabled on the strategic tab.",
        constraints="The player must control the displayed country; the authoritative handler revalidates ownership, deployment eligibility, and destination access.",
        confirmation="No confirmation dialog; an enabled click sends each selected deployment action immediately.",
        error="Missing capital or ineligible selection leaves the control disabled; stale or unauthorized deployment is rejected by the authoritative military system.",
        mapping_notes="The capital dispatch route and source strategic-tab disable are preserved. OpenPower revalidates current country and unit state on the server.",
        action_required="Keep the source capital route and strategic-tab guard covered by the reserves action journey and server-side deployment validation.",
    ),
    "Unit_Ground_Deployment_Window/frmInner/btnTrain": _unit_reserves_interaction(
        reference="OnMouseClick gathers selected units not already in training and calls TrainUnits with the selected list.",
        callback="OnMouseClick@reference_unit_ground_deployment_window.cpp:337",
        surface="UnitReservesPanel._render_actions / UnitTrainingConfirmation",
        effect="Opens one quote-backed confirmation for selected eligible groups; Yes dispatches one ActionTrainUnit per group.",
        action="ActionTrainUnit(player_id, country_tag, unit_id, target_level, expected_cost, expected_required_days, expected_from_level)",
        status="partial",
        validation="Requires an own-country selection with current training offers and a network client; current quotes and unit state are rechecked before dispatch and by the server.",
        constraints="Training is limited to units owned by the issuing country and currently eligible under OpenPower training, facility, movement, and funds rules.",
        confirmation="One selected-group confirmation precedes all per-unit actions; No sends none and Yes submits only still-valid quotes.",
        error="Unavailable or stale quotes prevent submission; authoritative rejection does not begin training.",
        mapping_notes="OpenPower preserves the selected-group confirmation workflow but uses per-unit quote-guarded actions instead of REFERENCE's TrainUnits batch call.",
        action_required="Keep the quote-backed confirmation, No/Yes behavior, and exact per-unit action payloads covered by the reserves action journey.",
    ),
    **{
        f"Unit_Ground_Deployment_Window/frmInner/tabGroups/{tab}/lstDeploy": _unit_reserves_interaction(
            reference="OnListItemSelected replaces the active selected-list rows, rebuilds the selected unit set, and enables capital deployment only for a non-empty non-strategic selection; GTabbed pages use MultiExtended selection.",
            callback="OnCustomEvent@reference_unit_ground_deployment_window.cpp:296",
            surface="UnitReservesPanel._render_group_list / _render_group_row",
            effect="Renders OpenPower reserve groups in the corresponding GML page; click selects a row, Shift selects a range, Ctrl toggles membership, and dragging a selection can request map deployment.",
            action="none for selection; ActionDispatchUnitDeployment(player_id, unit_id, destination_region_id) on a valid map drop",
            status="partial",
            validation="Selection is limited to the visible category. A map drop requires a selected non-training group and a valid map region; the server rechecks ownership and destination eligibility.",
            constraints="Only the current player's reserve groups are shown as actionable rows; foreign-country views are restricted to guidance and unavailable counts.",
            confirmation="Row selection is local. A valid map drop dispatches immediately without a confirmation dialog.",
            error="A drop over UI or outside a valid region sends no action; stale or unauthorized deployment is rejected by the authoritative military system.",
            mapping_notes="OpenPower implements source-style extended selection and map deployment, but category assignment follows native OpenPower unit domain/type values rather than a one-to-one REFERENCE catalog map.",
            action_required="Keep source row geometry and extended selection covered; preserve GameView valid-map drops and server-side destination validation in tests/test_unit_interaction_controller.py.",
        )
        for tab in ("Tab4", "Tab1", "Tab3", "Tab2")
    },
    "Unit_Ground_Deployment_Window/frmInner/tabGroups/@tabButtons": _unit_reserves_interaction(
        reference="GUnitGroundDeploymentWindow::OnMouseClick recognizes the four runtime GTabbed buttons and clears the previous row selection; CleanSelection disables capital deployment and applies the source NuclearAllowed gate to the strategic button.",
        callback="OnMouseClick@reference_unit_ground_deployment_window.cpp:337",
        surface="UnitReservesPanel._render_category_tabs",
        effect="Changes the visible category and clears selection using GML-derived button geometry. OpenPower has no equivalent NuclearAllowed setting, so the strategic category remains available.",
        status="partial",
        validation="A click changes the active category; the source category name tokens are supplied by GTabbed TabNames.",
        constraints="Category navigation is local. Strategic deployment to the capital stays disabled.",
        confirmation="No confirmation is required for category navigation.",
        error="None; the selected category is a local panel state.",
        mapping_notes="Button size, spacing, and page offset come from source GML. English category labels substitute for missing localization, and the source NuclearAllowed option has no OpenPower equivalent.",
        action_required="Keep all four source-positioned category buttons and selection clearing covered; preserve the NuclearAllowed difference as a partial mapping.",
    ),
}


GENERIC_QUESTION_INTERACTION_BINDINGS = {
    "Generic_Question_Window/btnOk": _build_interaction_binding(
        reference="The source notifies the question's OK observer, plays ConfirmOrder, and dismisses the one-shot modal.",
        surface="GenericQuestionDialog.answer(True) / Question.accept caller callback",
        effect=(
            "Yes clears pending dialog state before invoking the caller-supplied accept callback; "
            "the shared dialog does not dispatch a game action itself."
        ),
        action="caller-supplied callback; no direct GameAction in the shared dialog",
        status="partial",
        validation="The shared dialog requires nonempty caller text; each caller validates its own action.",
        constraints="Caller-defined; the shared dialog does not apply country-authority rules.",
        confirmation="Yes is delivered as the caller's affirmative answer, then the dialog closes.",
        error="Caller-specific action errors are handled by the active workflow.",
        mapping_notes="The REFERENCE ConfirmOrder sound is not available in the shared Python dialog; caller actions remain independently guarded.",
        action_required="Keep Yes bound to the active workflow's accept callback and preserve caller-side validation; add the source confirmation sound only if an equivalent asset/event is available.",
        read_only_or_state_changing="caller-defined; the shared dialog only returns Yes to its workflow",
    ),
    "Generic_Question_Window/btnCancel": _build_interaction_binding(
        reference="The source notifies the question's Cancel observer and dismisses the one-shot modal without the OK sound.",
        surface="GenericQuestionDialog.answer(False) / Question.cancel caller callback",
        effect=(
            "No clears pending dialog state before invoking the caller-supplied cancel callback; "
            "the shared dialog does not dispatch a game action itself."
        ),
        action="caller-supplied callback; no direct GameAction in the shared dialog",
        status="verified_openpower",
        validation="The shared dialog requires nonempty caller text; each caller defines its cancel behavior.",
        constraints="Caller-defined; the shared dialog does not apply country-authority rules.",
        confirmation="No is delivered as the caller's negative answer, then the dialog closes.",
        error="Caller-specific action errors are handled by the active workflow.",
        mapping_notes="The caller retains or discards its draft according to its own workflow contract.",
        action_required="Keep No bound to the active workflow's cancel callback and verify its state-retention behavior at the caller route.",
        read_only_or_state_changing="caller-defined; the shared dialog only returns No to its workflow",
    ),
}


MAIN_BAR_INTERACTION_BINDINGS = {
    "Main_Bar/cboCountry": _build_interaction_binding(
        reference="Before opening, the source fills the combo with country names and flags. On selection, it plays ZoomToCountry when the selection changes, focuses the camera on the country, and highlights all its regions.",
        surface="CentralBar._render_country_section / CountrySelector / GameLayout country-selection route",
        effect="Opens a flag-backed country popup; selecting a row updates the active country, focuses the map on it, and highlights its controlled regions.",
        action="none (local country focus and highlight)",
        status="partial",
        validation="The selected country must exist in the current countries table; focus uses the current region snapshot and may return no region for a country without mapped regions.",
        mapping_notes="The focus/highlight route is verified. OpenPower does not have the source ZoomToCountry sound event or the REFERENCE localized country-name ordering assets.",
        action_required="Keep the popup-to-map focus route covered by the main-bar journey and preserve the missing source sound/localization as an explicit difference.",
    ),
    "Main_Bar/btnStatus": _build_interaction_binding(
        reference="GMainBar::Status updates this read-only button's text and RGB color for player, allied, neutral, hostile, and military-access diplomatic statuses.",
        surface="GameLayout.resolve_country_status / CentralBar._render_country_section",
        effect="Displays PLAYER, ALLIED, HOSTILE, ACCESS, or NEUTRAL using the REFERENCE color values; ACCESS fits the source-width button and exposes its full Military Access label in the tooltip. The button sends no action.",
        status="partial",
        validation="Status is recalculated from the current country, active war, alliance, and military-trespassing treaty snapshot.",
        mapping_notes="The source labels are localized, including the current PlayerName; OpenPower currently uses English semantic labels and the supplied state has no player display-name contract.",
        action_required="Keep the status slot read-only, preserve source semantic colors and relation precedence, and use source-localized labels only if the language tables are recovered.",
    ),
    "Main_Bar/btnLocate": _build_interaction_binding(
        reference="When the latest source news item has a country capital position, the transient ticker enables btnLocate; clicking plays a camera animation to that position.",
        surface="CentralBar._render_ticker / FeedPresenter._ticker_region_id / GameLayout._on_focus_region",
        effect="The source-sized ticker hitbox focuses the mapped region for the latest country-linked OpenPower bulletin; it is disabled when the bulletin has no mapped location.",
        action="none (local viewport focus)",
        status="partial",
        validation="Enabled only when the current ticker item resolves to a region or to its related country's capital region in the current snapshot.",
        constraints="Viewport navigation only; no simulation state changes.",
        mapping_notes="The source animates to an exact CapitalPosition while a transient news animation is active. OpenPower news rows may omit coordinates and persist in the feed, so Python resolves the related country's authoritative capital region and focuses it directly.",
        action_required="Keep the source 461×19 hitbox, latest-bulletin location guard, and region-focus request covered; retain the exact-coordinate and transient-news behavior difference.",
    ),
    "Main_Bar/btnFlag": _build_interaction_binding(
        reference="Clicking m_pObjFlag calls SelectedCountrySetLookAt for the currently selected country.",
        surface="CentralBar._render_country_section / GameLayout._on_focus_country / ViewportController.focus_on_country",
        effect="Clicking the rendered flag focuses and selects the active country's representative region, highlighting its controlled regions.",
        status="partial",
        validation="No-op when the active country has no controlled mapped regions in the current snapshot.",
        constraints="Local viewport selection only; no simulation state changes.",
        mapping_notes="OpenPower focuses the country's representative region directly and highlights all controlled regions; exact source camera-animation timing is not reproduced.",
        action_required="Keep the flag click bound to the active country and verify the focus/highlight route; retain the camera-animation difference as partial.",
    ),
    "Main_Bar/btnTime": _build_interaction_binding(
        reference="GMainBar::SwapTimeDisplay alternates between bringing the date/time labels and frmTimeSelection to the front.",
        surface="CentralBar._render_time_section",
        effect="Toggles the source-positioned time-speed controls against the date/time labels without dispatching an action.",
        action_required="Keep the date/time versus speed-control toggle local and preserve the source frame anchor.",
    ),
    "Main_Bar/frmTimeSelection/togTime1": _build_interaction_binding(
        reference="The source pause toggle raises GChangeGameSpeed with c_fREFERENCEGamePausedSpeed.",
        surface="CentralBar._draw_speed_controls / NetworkClient.send_action",
        effect="Toggles ActionSetPaused while preserving the currently selected OpenPower speed level.",
        action="ActionSetPaused(player_id, is_paused)",
        status="partial",
        validation="The local single-player client sends the toggle from the authoritative TimeData.is_paused value.",
        mapping_notes="OpenPower models pause separately from speed; the supplied single-player NetworkClient is always local_admin, while the source disables all speed toggles for a non-admin player.",
        action_required="Keep pause changes action-backed; preserve source admin gating if a non-admin multiplayer client is added.",
    ),
    **{
        f"Main_Bar/frmTimeSelection/togTime{source_index}": _build_interaction_binding(
            reference=f"The source speed toggle raises GChangeGameSpeed with the {source_speed} REFERENCE time rate.",
            surface="CentralBar._draw_speed_controls / NetworkClient.send_action",
            effect=f"Clears pause and selects OpenPower speed level {openpower_speed}.",
            action=f"ActionSetPaused(player_id, false) and ActionSetGameSpeed(player_id, speed_level={openpower_speed})",
            status="partial",
            validation="The local single-player client sends the selected speed; the authoritative clock clamps speed levels to its supported range.",
            mapping_notes="REFERENCE has four non-paused rates, while OpenPower has five speed levels. Source togTime2..togTime5 map in order to OpenPower levels 1..4; OpenPower level 5 is an extra control and exact simulation rates differ.",
            action_required="Keep source speed toggles bound to the four verified OpenPower counterparts and describe the fifth OpenPower level as an extension rather than a source control.",
        )
        for source_index, source_speed, openpower_speed in (
            (2, "slowest", 1),
            (3, "normal", 2),
            (4, "high", 3),
            (5, "highest", 4),
        )
    },
}


UNIT_LIST_INTERACTION_BINDINGS = {
    "Unit_List_Window/frmInner/frmActions/btnSell": _unit_list_interaction(
        reference="GUnitListWindow::OnMouseClick raises GTransfertUnit with for-sale semantics for the selected unit.",
        surface="UnitReorganizationWindows._legacy_list / NetworkClient.send_action",
        effect="The selected-unit group window uses this GML control to list an eligible own unit with ActionListUsedUnit or withdraw its existing listing.",
        action="ActionListUsedUnit(player_id, country_tag, unit_id) or ActionWithdrawUsedUnitListing(player_id, country_tag, listing_id)",
        status="partial",
        validation="Enabled by the selected own unit; the authoritative used-unit market rechecks ownership, availability, marketability, and stale listings.",
        constraints="Only units owned by the issuing country can be listed or withdrawn.",
        confirmation="The source and OpenPower both dispatch immediately without a separate confirmation dialog.",
        error="Rejected or stale market actions do not create or withdraw a listing and return command feedback.",
        mapping_notes="OpenPower reaches the same GML template through unit.group.list. Listing price follows the OpenPower default-price rule, and the button also supports withdrawal; the source window still has no registered C++ spawn call site.",
        action_required="Keep the GML group-list route and its explicit sell/withdraw behavior tested; retain the source spawn-call gap and the price-policy difference.",
    ),
    "Unit_List_Window/frmTitle/btnExit": _unit_list_interaction(
        reference="GUnitListWindow::OnMouseDown hides the selected-unit group window when its title exit is clicked.",
        surface="UnitReorganizationWindows._legacy_list / WindowManager GML title close",
        effect="Closes the selected-unit group window and clears its current unit selection without changing simulation state.",
        action="none (local window close)",
        status="verified_openpower",
        action_required="Keep the source title close local and preserve the source GML window frame.",
    ),
    "Unit_List_Window/frmTitle/btnApply": _unit_list_interaction(
        reference="GUnitListWindow::OnCreate explicitly hides the inherited Apply control; GBaseWindow::Save is an empty default.",
        surface="UnitReorganizationWindows._legacy_list",
        effect="The OpenPower group window does not expose an Apply control; each supported action has its own guarded route.",
        action="none (hidden inherited Apply control)",
        status="verified_unavailable",
        read_only_or_state_changing="hidden inherited control",
        action_required="Keep Apply hidden; do not add a save action to the read-only unit-group window.",
    ),
    "Unit_List_Window/frmInner/frmInformationAccuracy/frmAccuracy/btnUnfilled": _unit_list_interaction(
        reference="GUnitListWindow::Update shows the source accuracy meter for a selected-unit view and sets it from AccuracyInformation; the meter is a read-only display.",
        surface="UnitReorganizationWindows._legacy_list / foreign group detail",
        effect="The OpenPower group window currently shows Unknown and does not draw this meter for foreign groups, while keeping individual foreign-unit details hidden.",
        action="none (read-only intelligence-confidence display)",
        status="partial",
        validation="No interaction or GameAction is bound to either meter fragment; an authorized OpenPower confidence value is required before rendering a numeric meter.",
        constraints="Foreign unit rows remain aggregate or hidden unless the current intelligence observation permits detail.",
        error="Without a current authorized confidence value, the group window displays Unknown rather than a fabricated percentage.",
        mapping_notes="This is a visual fill segment, not a user control. OpenPower does not yet reproduce the source percentage in this selected-unit group view.",
        read_only_or_state_changing="read-only intelligence-confidence presentation",
        action_required="Keep the meter read-only and render a percentage only when it is backed by an authorized current intelligence value.",
    ),
    "Unit_List_Window/frmInner/frmInformationAccuracy/frmAccuracy/btnFill": _unit_list_interaction(
        reference="GUnitListWindow::Update shows the source accuracy meter for a selected-unit view and sets it from AccuracyInformation; the meter is a read-only display.",
        surface="UnitReorganizationWindows._legacy_list / foreign group detail",
        effect="The OpenPower group window currently shows Unknown and does not draw this meter for foreign groups, while keeping individual foreign-unit details hidden.",
        action="none (read-only intelligence-confidence display)",
        status="partial",
        validation="No interaction or GameAction is bound to either meter fragment; an authorized OpenPower confidence value is required before rendering a numeric meter.",
        constraints="Foreign unit rows remain aggregate or hidden unless the current intelligence observation permits detail.",
        error="Without a current authorized confidence value, the group window displays Unknown rather than a fabricated percentage.",
        mapping_notes="This is a visual fill segment, not a user control. OpenPower does not yet reproduce the source percentage in this selected-unit group view.",
        read_only_or_state_changing="read-only intelligence-confidence presentation",
        action_required="Keep the meter read-only and render a percentage only when it is backed by an authorized current intelligence value.",
    ),
    "Unit_List_Window/frmInner/frmActions/btnMerge": _unit_list_interaction(
        reference="The source initializes a Merge button member but the supplied GUnitListWindow::OnMouseClick handler has no branch for it.",
        surface="UnitReorganizationWindows._legacy_list / UnitReorganizationWindows._merge",
        effect="Opens a compatible-unit selector and dispatches a merge only after the player chooses source units and confirms.",
        action="ActionMergeUnits(player_id, target_unit_id, source_unit_ids)",
        status="partial",
        validation="The server checks ownership, current availability, matching design/domain/status/location, and non-empty distinct source IDs.",
        constraints="All units in the merge must be controlled by the issuing country and remain compatible and co-located.",
        confirmation="The source mirror has no merge click branch; OpenPower requires an explicit selection and Merge confirmation before dispatch.",
        error="If no compatible source units remain, Merge is disabled; stale or invalid selections are rejected without merging.",
        mapping_notes="Python implements the GML btnMerge route through the selected-unit group window even though the supplied C++ callback does not handle the initialized button member.",
        action_required="Keep the compatible-unit validation and explicit confirmation; do not claim the source mirror has an active merge callback.",
    ),
    "Unit_List_Window_New/frmTitle/btnExit": _unit_list_interaction(
        reference="The source titlebar exit hides GUnitListWindowNew.",
        surface="UnitListPanel / WindowManager GML title close",
        effect="Closes the unit list window.",
        action="none (local window close)",
        action_required="Keep the GML title close control reachable and do not send a unit action when closing.",
    ),
    "Unit_List_Window_New/frmInner/frmList/cboUnitType": _unit_list_interaction(
        reference="GUnitListWindowNew::OnCustomEvent rebuilds the unit list for the selected EUnitType.",
        surface="UnitListPanel._render_type_filter",
        effect="Filters the current own roster or aggregate foreign estimate rows by canonical role using the source type order.",
        action="none (local roster filter)",
        status="partial",
        validation="All 20 source types are selectable even when no matching OpenPower row exists; visible OpenPower-only and aggregate rows are appended. Selecting a type resets scroll and selection.",
        constraints="Own rosters show per-unit rows; foreign countries show only published aggregate estimates.",
        mapping_notes="The source type IDs map to canonical OpenPower roles; row captions stay bound to OpenPower unit/estimate data and use no invented source coordinates or units.",
        action_required="Keep the source-ID order and current-row filter synchronized; do not expose unauthorized foreign units.",
    ),
    "Unit_List_Window_New/frmInner/frmList/btnTrain": _unit_list_interaction(
        reference="GUnitListWindowNew::OnMouseClick sends the selected unit group to TrainUnits after the source confirmation flow.",
        surface="UnitListPanel._render_actions / UnitTrainingConfirmation.request_many",
        effect="Shows one guarded aggregate confirmation; No preserves the selection, while Yes sends one ActionTrainUnit per selected unit using its current published quote and temporarily disables TRAIN/SELL for that unchanged selection.",
        action="ActionTrainUnit(player_id, country_tag, unit_id, target_level, expected_cost, expected_required_days, expected_from_level)",
        status="partial",
        validation="Enabled only for selected own units with current available unit_training_quotes; all quotes and unit signatures are rechecked before dispatch, and the server validates the order again.",
        constraints="Every selected unit must be owned by the issuing country and eligible under its current movement, battle, training facility, and funds rules.",
        confirmation="One source-sized Yes/No question confirms all selected units and their combined quoted cost before any action is sent; No closes the question and preserves the selection, while Yes keeps TRAIN/SELL disabled until a row-selection callback recalculates eligibility.",
        error="Unavailable or stale quotes keep the action disabled or produce a warning; rejected server actions do not begin training.",
        mapping_notes="OpenPower uses per-unit authoritative quotes and dispatches independent actions; it does not reuse REFERENCE's client-side TrainUnits batch event.",
        action_required="Keep quote/signature checks ahead of every action, preserve one explicit batch confirmation, retain selection on No, and block duplicate TRAIN/SELL submissions after Yes until row selection recalculates current eligibility.",
    ),
    "Unit_List_Window_New/frmInner/frmList/btnSell": _unit_list_interaction(
        reference="GUnitListWindowNew::SellUnit raises GTransfertUnit with m_bForSale=true for each selected unit.",
        surface="UnitListPanel._render_actions",
        effect="Sends ActionListUsedUnit once per selected eligible own unit; the OpenPower handler uses 75% of reference/design cost when no price is supplied.",
        action="ActionListUsedUnit(player_id, country_tag, unit_id, price=0)",
        status="partial",
        validation="Enabled only when every selected row is an available marketable design and no selected unit is moving, training, engaged, or already listed; the server rechecks ownership and availability.",
        constraints="The player may list only units owned by the issuing country; unsupported infantry/design rows are excluded from this source action.",
        confirmation="The source sends the listing request immediately without a confirmation dialog.",
        error="The OpenPower market system ignores stale, already listed, ineligible, or unauthorized unit requests.",
        mapping_notes="OpenPower derives a 75% design-cost listing price by default; the Python panel does not guess or send a client-side price.",
        action_required="Keep listing eligibility server-validated and document the default-price mapping.",
    ),
    "Unit_List_Window_New/frmInner/frmList/btnDisband": _unit_list_interaction(
        reference="GUnitListWindowNew::OnMouseClick sends the selected units to DisbandUnits.",
        surface="UnitListPanel._render_actions",
        effect="Sends one ActionDisbandUnits for the selected owned units; the military system removes them and decreases their owners' serving personnel totals.",
        action="ActionDisbandUnits(player_id, unit_ids)",
        status="verified_openpower",
        validation="The system rechecks distinct existing IDs, authority over every owner, positive strength, availability, and absence of active battle, movement, readiness, training, deployment, pending-order, or market references.",
        constraints="Each selected unit must belong to a country controlled by the issuer; a mixed-owner batch is accepted only if the issuer controls every owner.",
        confirmation="REFERENCE dispatches immediately; OpenPower does the same and clears the local selection after dispatch.",
        error="Rejected commands leave units and military totals unchanged and report the rejection through the command-result journal.",
        mapping_notes="The OpenPower disband effect releases the unit personnel count and retains completed deployment records; exact REFERENCE server-side accounting is not present in the supplied source mirror.",
        action_required="Keep batch authority and availability validation on the server; preserve active-order rejection and completed deployment history.",
    ),
    "Unit_List_Window_New/frmInner/frmList/scrList": _unit_list_interaction(
        reference="GUnitListWindowNew::OnMouseWheel and OnCustomEvent route vertical input to the 14x300 source scrollbar.",
        surface="UnitListPanel._apply_wheel_scroll / _render_scrollbar",
        effect="Scrolls the fixed twenty-row source window through the filtered and sorted roster.",
        action="none (local list scroll)",
        validation="The thumb is bounded to the number of rows beyond the visible 20-row page.",
        mapping_notes="OpenPower implements the source custom scrollbar track with a draggable Python hitbox and mouse-wheel page offset.",
        action_required="Keep vertical drag, wheel scrolling and the 14x300 source hitbox geometry verified.",
    ),
}

for _sort_component, _sort_label, _sort_field in (
    ("btnTrainingIcon", "training icon", "training level"),
    ("btnType", "type", "unit type"),
    ("btnTypeIcon", "type arrow", "unit type"),
    ("btnQty", "quantity", "unit quantity"),
    ("btnQtyIcon", "quantity arrow", "unit quantity"),
    ("btnName", "name", "design name"),
    ("btnNameIcon", "name arrow", "design name"),
    ("btnStatus", "status", "readiness/lifecycle status"),
    ("btnStatusIcon", "status arrow", "readiness/lifecycle status"),
    ("btnValue", "value", "unit design cost"),
    ("btnValueIcon", "value arrow", "unit design cost"),
    ("btnForSaleIcon", "for-sale icon", "listing state"),
):
    UNIT_LIST_INTERACTION_BINDINGS[
        f"Unit_List_Window_New/frmInner/frmList/{_sort_component}"
    ] = _unit_list_interaction(
        reference=f"The source header { _sort_label } toggles the corresponding GUnitListWindowNew sort order.",
        surface="UnitListPanel._render_headers / _select_sort",
        effect=f"Sorts the visible OpenPower roster by {_sort_field}; activating the same header reverses order.",
        action="none (local list sort)",
        validation="The selected sort key reads the current displayed row fields and resets the first visible row.",
        action_required="Keep every supported sort hitbox on its GML header and preserve the source default type-ascending order.",
    )

for _component_id, _glyph, _asset_note in (
    ("btnTrainingIcon", "T", "source picture ID 000159"),
    ("btnForSaleIcon", "$", "source for-sale header picture"),
):
    _binding = UNIT_LIST_INTERACTION_BINDINGS[
        f"Unit_List_Window_New/frmInner/frmList/{_component_id}"
    ]
    _binding["status"] = "partial"
    _binding["restrictions_confirmation_error"] = (
        f"Python uses the {_glyph!r} text glyph in the source GML slot; the {_asset_note} asset is not present in the workspace. "
        "Sorting behavior is bound to current OpenPower row data."
    )
    _binding["action_required"] = (
        "Keep the local sort operation bound to the live row value and restore the source picture asset if it becomes available."
    )

UNIT_LIST_INTERACTION_BINDINGS["Unit_List_Window_New/frmInner/frmList/btnUpkeep"] = _unit_list_interaction(
    reference="The source header sorts by CalculateUnitUpkeep.",
    surface="UnitListPanel._render_headers",
    effect="Sorts own unit rows by the displayed annual OpenPower budget estimate; remains disabled for foreign aggregate rows where per-unit values are hidden.",
    action="none (local roster sort)",
    status="partial",
    validation="Own-row sorting uses the same displayed OpenPower estimate; foreign roster keeps the header disabled. The exact REFERENCE modifier formula remains unrepresented.",
    action_required="Keep own-row sorting aligned with displayed estimates and retain the explicit source-formula parity gap.",
)
UNIT_LIST_INTERACTION_BINDINGS["Unit_List_Window_New/frmInner/frmList/btnUpkeepIcon"] = dict(
    UNIT_LIST_INTERACTION_BINDINGS["Unit_List_Window_New/frmInner/frmList/btnUpkeep"],
    reference_side_effect="The source upkeep sort arrow changes direction for CalculateUnitUpkeep.",
)
UNIT_LIST_INTERACTION_BINDINGS["Unit_List_Window_New/frmInner/frmList/btnPosition"] = _unit_list_interaction(
    reference="The source position header is a visible control but GUnitListWindowNew binds no position sort handler.",
    surface="UnitListPanel._render_headers",
    effect="Displays the source Position heading; no sort action is assigned.",
    action="none (source header has no bound sort behavior)",
    status="verified_unavailable",
    validation="Static source-position label; it has no click target.",
    action_required="Keep Position as a label unless the source handler is found to bind a sort operation.",
)

for _row_number in range(1, 21):
    UNIT_LIST_INTERACTION_BINDINGS[
        f"Unit_List_Window_New/frmInner/frmList/frmList/frm{_row_number}"
    ] = _unit_list_interaction(
        reference="GUnitListWindowNew selects a unit row and opens its supported design details on double-click.",
        surface="UnitListPanel._render_rows",
        effect="Own-unit rows support Ctrl multi-selection and a design double-click when the saved design supports detail view; foreign rows stay aggregate-only.",
        action="none (local selection) or UnitDesignPanel selection on supported design double-click",
        status="partial",
        validation="Selection is restricted to rows in the current filtered roster; design navigation requires a supported saved design ID.",
        constraints="Foreign row contents are aggregate estimates and do not expose individual unit identities or details.",
        action_required="Keep row hitboxes on the exact source frame and maintain the infantry/design detail exclusion.",
    )


UNIT_SPLIT_INTERACTION_BINDINGS = {
    "Unit_Split_Window/frmSplit/frmDown/btnDown": _build_interaction_binding(
        reference="GUnitSplitWindow::OnMouseClick decreases the detached group quantity by one and updates the split meter.",
        surface="UnitReorganizationWindows._quantity_window / unit.split.quantity.down",
        effect="Decreases the pending detached quantity by one without submitting an action.",
        status="verified_openpower",
        validation="Enabled only while the pending detached quantity is greater than zero.",
        confirmation="The change stays in the local split draft until the parent split is applied.",
        mapping_notes="The source popup notifies its parent when closed; the Python popup updates the same local draft directly.",
        action_required="Keep the decrement bound to the source btnDown slot and prevent the quantity from becoming negative.",
    ),
    "Unit_Split_Window/frmSplit/frmDown1/btnUp": _build_interaction_binding(
        reference="GUnitSplitWindow::OnMouseClick increases the detached group quantity by one and updates the split meter.",
        surface="UnitReorganizationWindows._quantity_window / unit.split.quantity.up",
        effect="Increases the pending detached quantity by one without submitting an action.",
        status="verified_openpower",
        validation="Enabled only while the pending detached quantity is below the remaining transferable capacity.",
        confirmation="The change stays in the local split draft until the parent split is applied.",
        mapping_notes="The source popup notifies its parent when closed; the Python popup updates the same local draft directly.",
        action_required="Keep the increment bound to the source btnUp slot and clamp it to the remaining transferable quantity.",
    ),
    "Unit_Split_Window/frmSplit/edtGroupA": _build_interaction_binding(
        reference="GUnitSplitWindow::UpdateQuantityFromRatio writes the remaining group A quantity into this edit-box slot.",
        surface="UnitReorganizationWindows._quantity_window / unit.split.quantity.remaining",
        effect="Displays the remaining quantity and accepts direct numeric edits that keep the transfer amount in range.",
        status="partial",
        validation="The entered remaining quantity is clamped to the transferable capacity and converted to the detached quantity.",
        mapping_notes="The source writes this field from meter changes; Python also supports direct numeric editing as an OpenPower convenience.",
        action_required="Keep this field synchronized with the ratio and transfer field; retain the explicit direct-edit behavior difference.",
    ),
    "Unit_Split_Window/frmSplit/edtGroupB": _build_interaction_binding(
        reference="GUnitSplitWindow::UpdateQuantityFromRatio writes the detached group B quantity into this edit-box slot.",
        surface="UnitReorganizationWindows._quantity_window / unit.split.quantity.transfer",
        effect="Displays the detached quantity and accepts direct numeric edits that keep the transfer amount in range.",
        status="partial",
        validation="The entered transfer quantity is clamped to the remaining transferable capacity.",
        mapping_notes="The source writes this field from meter changes; Python also supports direct numeric editing as an OpenPower convenience.",
        action_required="Keep this field synchronized with the ratio and remaining field; retain the explicit direct-edit behavior difference.",
    ),
    "Unit_Split_Window/frmSplit/frmSplit/btnFill": _build_interaction_binding(
        reference="GSplitMeter configures btnFill as the draggable cursor; GUnitSplitWindow consumes meter-change events and converts the ratio into integer group quantities.",
        surface="UnitReorganizationWindows._quantity_window / unit.split.quantity.ratio",
        effect="Dragging the transfer slider updates the pending detached quantity and its complementary remaining quantity.",
        status="partial",
        validation="The slider is bounded by the remaining transferable capacity; integer quantities are derived from its value.",
        confirmation="The change remains a local draft until the split is applied.",
        mapping_notes="Python binds the full meter slot to one integer slider instead of reproducing the source fill/unfilled child-button composition.",
        action_required="Keep the slider mapped to the source meter slot, test its bounds and quantity conversion, and preserve this renderer-level difference.",
    ),
    "Unit_Split_Window/frmSplit/frmSplit/btnUnfilled": _build_interaction_binding(
        reference="GSplitMeter configures btnUnfilled as a locked remainder segment; it is not the draggable cursor.",
        surface="UnitReorganizationWindows._quantity_window / unit.split.quantity.ratio",
        effect="Renders as part of the combined transfer slider track; input updates the same bounded local quantity draft.",
        status="partial",
        validation="The transfer amount cannot exceed the remaining transferable capacity.",
        mapping_notes="The Python slider does not expose a separate hit target for the source locked remainder segment.",
        action_required="Do not make the unfilled segment independently adjustable; keep the combined meter input bounded and documented.",
    ),
    "Unit_Split_Window/frmTitle/btnClose": _build_interaction_binding(
        reference="GUnitSplitWindow::OnMouseClick notifies the parent through c_iOnSplitWindowClose, then hides the quantity popup.",
        surface="UnitReorganizationWindows._quantity_window / unit.split.quantity.close",
        effect="Commits the chosen transfer quantity into the local split draft and closes the popup; the direct unit-list route applies its split immediately after this step.",
        action="none for the parent split draft; ActionSplitUnit is used by the direct unit-list route",
        status="partial",
        confirmation="Closing the quantity popup does not apply a normal parent split; its Apply control remains the confirmation point.",
        mapping_notes="Python updates the parent draft directly rather than sending the source custom close event; the standalone unit-list route has no source parent split window.",
        action_required="Keep close scoped to quantity-draft commit; preserve parent Apply as the normal action boundary and test the direct-route exception.",
    ),
}


START_SINGLE_PLAYER_INTERACTION_BINDINGS = {
    "Start_Single_Player/frmTitle/btnExit": {
        "reference_side_effect": "GStartSinglePlayerWindow handles title exit by calling g_ClientDCL.CancelConnect().",
        "openpower_surface": "SinglePlayerSetupWindow native title close -> NewGameView._return_to_scenario_selection",
        "openpower_effect": "Closes the setup step and returns to scenario selection without dispatching campaign setup.",
        "game_action": "none (local setup navigation)",
        "read_only_or_state_changing": "local UI navigation",
        "validation_condition": "The country setup step is open.",
        "country_scope_restriction": "None; no campaign action is sent by closing the step.",
        "confirmation_state": "No extra confirmation; Start Campaign is the only setup commit.",
        "error_state": "None.",
        "restrictions_confirmation_error": (
            "OpenPower returns to scenario selection; the source CancelConnect callback exits the current connection/setup flow."
        ),
        "action_required": "Keep close separate from campaign start and preserve the OpenPower back-to-scenario route.",
        "status": "partial",
    },
    "Start_Single_Player/frmTitle/btnApply": {
        "reference_side_effect": "GStartSinglePlayerWindow::OnCreate hides m_pObjApplyBtn; it is not a visible setup commit control.",
        "openpower_surface": "SinglePlayerSetupWindow / GML title-bar rules",
        "openpower_effect": "The hidden title Apply control is omitted; Start Campaign remains the explicit setup commit.",
        "game_action": "none (hidden source title control)",
        "read_only_or_state_changing": "hidden local title control",
        "validation_condition": "The source hides the control during window initialization.",
        "country_scope_restriction": "None.",
        "confirmation_state": "None.",
        "error_state": "None.",
        "restrictions_confirmation_error": "Do not expose a second commit action for scenario setup.",
        "action_required": "Keep the source-hidden Apply control absent and the Start action explicit.",
        "status": "verified_openpower",
    },
    "Start_Single_Player/frmInner/frmSphereControl/btnParty": {
        "reference_side_effect": "The source opens Party_Selection_Window when party choices are available for the selected country.",
        "openpower_surface": "NewGameView._open_party_selection / PartySelectionWindow",
        "openpower_effect": "Opens the country-specific OpenPower party list; selection is carried by ActionStartCampaign without changing the ruling party.",
        "game_action": "none on open; ActionStartCampaign includes the selected player_party_id",
        "read_only_or_state_changing": "local party selection followed by authoritative campaign setup",
        "validation_condition": "Enabled only after a country with selectable political parties is selected.",
        "country_scope_restriction": "The chosen party must belong to the selected country; CampaignSystem validates membership.",
        "confirmation_state": "Selecting a party updates the local draft; Start Campaign submits it.",
        "error_state": "The server rejects a party that is unavailable for the selected country.",
        "restrictions_confirmation_error": "OpenPower party rows come from current political_parties state rather than the source party-ID list.",
        "action_required": "Keep country filtering, Cancel retention, and selected party ID forwarding covered.",
        "status": "verified_openpower",
    },
    "Start_Single_Player/frmInner/frmCountrySelection/btnProfile": {
        "reference_side_effect": "The source opens Country_Profile_Window for the currently selectable country list.",
        "openpower_surface": "NewGameView._open_country_profile / CountryProfileWindow",
        "openpower_effect": "Opens the GML-sized country profile for the selected scenario's eligible countries; Select updates the parent country and Cancel preserves it.",
        "game_action": "none (local profile navigation and country draft selection)",
        "read_only_or_state_changing": "local UI navigation and selection",
        "validation_condition": "Enabled while the current scenario has selectable countries.",
        "country_scope_restriction": "The profile selector receives only countries allowed by the selected scenario.",
        "confirmation_state": "Select confirms the local country choice; Cancel leaves the current selection unchanged.",
        "error_state": "The button is disabled if there are no eligible countries.",
        "restrictions_confirmation_error": "OpenPower profile metrics use current country state; the route does not start a campaign.",
        "action_required": "Keep the profile route limited to scenario-eligible countries and preserve Select/Cancel behavior.",
        "status": "verified_openpower",
    },
    "Start_Single_Player/frmInner/frmCountrySelection/cboCountry": {
        "reference_side_effect": (
            "The source country selector loads country choices before opening and requests GGetCountryParties after selection."
        ),
        "openpower_surface": "NewGameView._select_country / SinglePlayerSetupWindow country combo",
        "openpower_effect": (
            "Selects a country allowed by the current scenario, defaults to its ruling party, and reads party choices from the initial OpenPower state."
        ),
        "game_action": "none on selection; ActionStartCampaign submits the selected country and party",
        "read_only_or_state_changing": "local country selection followed by authoritative campaign setup",
        "validation_condition": "The combo contains countries allowed by the selected scenario; Start stays disabled until a country is selected.",
        "country_scope_restriction": "CampaignSystem rechecks the scenario's country allowlist and player-country assignment.",
        "confirmation_state": "No confirmation on selection; Start Campaign submits the current draft.",
        "error_state": "A stale or ineligible country is rejected during ActionStartCampaign and shown in LoadingView.",
        "restrictions_confirmation_error": (
            "REFERENCE requests country-party rows after each selection; OpenPower preloads current political_parties and filters them locally. "
            "OpenPower also applies the selected scenario's country allowlist."
        ),
        "action_required": "Keep the scenario allowlist, default-party behavior, profile/party navigation, and campaign-start validation synchronized.",
        "status": "partial",
    },
    "Start_Single_Player/frmInner/btnStart": {
        "reference_side_effect": (
            "After a country is selected, GStartSinglePlayerWindow sends player information, raises GSetGameObjectives "
            "with g_ClientDCL.m_vGameObjectives, applies the three advisor CPU-toggle modes, and disables setup controls. "
            "Without a country it shows MustChooseCountryBeforeStartGame."
        ),
        "openpower_surface": (
            "NewGameView._start_game -> NewGameTask -> ActionStartCampaign; "
            "CampaignSystem._start_campaign"
        ),
        "openpower_effect": (
            "Starts the selected enabled scenario for the selected country and party; CampaignSystem validates the request, "
            "applies its fixed setup, and creates its scenario-defined objective records."
        ),
        "game_action": "ActionStartCampaign(player_id, scenario_id, country_tag, player_party_id)",
        "read_only_or_state_changing": "authoritative scenario and campaign initialization",
        "validation_condition": (
            "NewGameView requires a selected country and scenario. CampaignSystem validates the player-country assignment, "
            "scenario availability and country allowlist, party membership, setup data, and outcome configuration."
        ),
        "country_scope_restriction": (
            "The actor country must be assigned to the player and selectable in the scenario; a supplied party must belong to that country."
        ),
        "confirmation_state": "No extra confirmation; selecting Start launches the asynchronous campaign setup task.",
        "error_state": (
            "Rejected setup is returned through the action result; NewGameTask preserves the reason in the recoverable LoadingView error panel. "
            "The source no-country modal is represented by disabling Start until a country is selected."
        ),
        "restrictions_confirmation_error": (
            "ActionStartCampaign is the authoritative OpenPower counterpart for campaign setup, but it reads fixed objectives from the selected "
            "scenario rather than accepting the source's editable m_vGameObjectives list. The action also does not accept the source's three "
            "advisor CPU-toggle values; those remain separate OpenPower advisor settings."
        ),
        "action_required": (
            "Keep scenario objective initialization, country/party validation, the start guard, and recoverable failure feedback covered. "
            "Keep source objective editing and advisor CPU assignments partial until matching scenario fields and authoritative actions exist."
        ),
        "status": "partial",
    },
}


def _single_player_unavailable_setting(
    *, reference: str, effect: str, action_required: str,
) -> dict[str, str]:
    return {
        "reference_side_effect": reference,
        "openpower_surface": "NewGameView/SinglePlayerSetupWindow scenario preview",
        "openpower_effect": effect,
        "game_action": "none (source-only setup input is not editable in OpenPower)",
        "read_only_or_state_changing": "unavailable source setup input",
        "validation_condition": "OpenPower renders selected-scenario data instead of an editable input for this source control.",
        "country_scope_restriction": "Scenario and player-country restrictions are checked by ActionStartCampaign.",
        "confirmation_state": "No input is submitted from this source-only control.",
        "error_state": "No action is dispatched.",
        "restrictions_confirmation_error": (
            "The source value is an editable objective or country-control setting; OpenPower has no matching setup field in ActionStartCampaign."
        ),
        "action_required": action_required,
        "status": "verified_unavailable",
    }


for _domain in ("Economy", "Politics", "Military"):
    for _control, _label in (("togHuman", "Human"), ("togComputer", "Computer")):
        _path = f"Start_Single_Player/frmInner/frmSphereControl/frmControl{_domain}/{_control}"
        START_SINGLE_PLAYER_INTERACTION_BINDINGS[_path] = _single_player_unavailable_setting(
            reference=(
                f"The source {_domain.lower()} {_label.lower()} toggle stores the startup control choice; "
                "Start maps each Computer toggle to its advisor status."
            ),
            effect=(
                f"Displays OpenPower as the {_domain.lower()} controller. The setup page has no Human/Computer selector; "
                "advisor execution modes are configured separately after campaign start."
            ),
            action_required=(
                "Keep the source choice unavailable until campaign setup accepts and authoritatively applies a per-domain control mode; "
                "do not equate the static OpenPower label with a selectable toggle."
            ),
        )


for _index, _objective, _description in (
    (1, "AchieveWorldPeace", "world peace"),
    (2, "MeetResourcesNeeds", "resource needs"),
    (3, "ConquerTheWorld", "world conquest"),
    (4, "DevelopNation", "nation development"),
    (5, "RaiseGDPPerCapita", "GDP per capita growth"),
):
    _toggle_path = f"Start_Single_Player/frmInner/frmGoals/frmTog{_index}/togGoal"
    START_SINGLE_PLAYER_INTERACTION_BINDINGS[_toggle_path] = _single_player_unavailable_setting(
        reference=(
            f"The source toggle adds or removes the {_objective} goal from m_vGameObjectives "
            "and enables or disables its deadline combo."
        ),
        effect=f"Shows the selected scenario's {_description} objective marker as a static preview.",
        action_required=(
            "Keep objective rows tied to selected-scenario definitions; add interactive goal selection only with an authoritative campaign objective contract."
        ),
    )
    _combo_path = f"Start_Single_Player/frmInner/frmGoals/cboGoal{_index}"
    START_SINGLE_PLAYER_INTERACTION_BINDINGS[_combo_path] = _single_player_unavailable_setting(
        reference=(
            f"The source combo sets the {_objective} deadline to no limit, 1, 5, or 10 years and updates m_vGameObjectives."
        ),
        effect=f"Displays the selected scenario's {_description} deadline; it is not editable in the setup preview.",
        action_required=(
            "Keep scenario deadlines visible and non-interactive until OpenPower supports authoritative objective-deadline editing."
        ),
    )


def _multiplayer_lobby_unavailable_interaction(reference: str) -> dict[str, str]:
    return {
        "reference_side_effect": reference,
        "openpower_surface": "MultiplayerLobbyWorkflowUnavailable",
        "openpower_effect": "The multiplayer lobby is unavailable in OpenPower; no player, chat, kick, ban, or start request is sent.",
        "game_action": "none (unavailable multiplayer lobby workflow)",
        "read_only_or_state_changing": "unavailable multiplayer workflow",
        "validation_condition": "OpenPower has no multiplayer lobby session or server-side player-management workflow.",
        "country_scope_restriction": "None; no multiplayer request is available.",
        "confirmation_state": "No request is sent.",
        "error_state": "The unsupported lobby action is unavailable rather than dispatched.",
        "restrictions_confirmation_error": (
            "The source event requires an active REFERENCE multiplayer lobby. OpenPower's current network session and action registry do not provide that workflow."
        ),
        "action_required": "Keep this source action explicitly unavailable until OpenPower has an authoritative multiplayer lobby and matching server actions.",
        "status": "verified_unavailable",
    }


def _unused_source_template_interaction() -> dict[str, str]:
    return {
        "reference_side_effect": (
            "The supplied source mirror has no active C++ window class, spawn call, or callback route for this GML template."
        ),
        "openpower_surface": "Unavailable: unused source template with no runtime route",
        "openpower_effect": "The control is not exposed because the source template is never instantiated in the supplied runtime mirror.",
        "game_action": "none (unused source template; no runtime callback)",
        "read_only_or_state_changing": "unavailable source workflow",
        "validation_condition": "The source window registry marks the template unused and no C++ class or spawn route resolves.",
        "country_scope_restriction": "None; the source template has no active runtime path.",
        "confirmation_state": "No control is exposed and no action is dispatched.",
        "error_state": "No source runtime behavior is available to reproduce.",
        "restrictions_confirmation_error": "Do not infer behavior from the GML control name or widget type without an active C++ callback path.",
        "action_required": "Keep this template unavailable unless a source C++ class and runtime spawn/callback path are recovered.",
        "status": "verified_unavailable",
    }


_UNUSED_SOURCE_TEMPLATE_CONTROLS = {
    "Strategic_Alert_Window": (
        "frmMessage/btnOk",
        "frmMessage/btnRetaliate",
    ),
    "Strategic_News_Window": (
        "btnAlert",
        "btnGoto",
    ),
    "Player_Options_Window": (
        "frmTitle/btnExit",
        "frmTitle/togLockWindow",
        "frmTitle/btnApply",
        "frmInner/frmPlayerName/edtPlayerName",
        "frmInner/frmSphereControl/btnCancel",
        *(f"frmInner/frmSphereControl/frmControl{sphere}/tog{control}"
          for sphere in ("Military", "Economy", "Politics")
          for control in ("Human", "Computer")),
        *(f"frmInner/frmGoals/frmTog{index}/togGoal" for index in range(1, 6)),
        *(f"frmInner/frmGoals/cboGoal{index}" for index in range(1, 6)),
        "frmInner/btnStart",
        "frmInner/btnCancel",
    ),
    "Political_Parties_Window": (
        "frmTitle/btnExit",
        "frmTitle/togLockWindow",
        "frmTitle/btnApply",
        "frmInner/btnCancel",
        "frmInner/frmParties/lstParties",
        "frmInner/btnConfirm",
    ),
}
UNUSED_SOURCE_TEMPLATE_INTERACTION_BINDINGS = {
    f"{window}/{suffix}": _unused_source_template_interaction()
    for window, controls in _UNUSED_SOURCE_TEMPLATE_CONTROLS.items()
    for suffix in controls
}


def _scenario_selection_interaction(
    *,
    reference: str,
    surface: str,
    effect: str,
    game_action: str,
    behavior: str,
    status: str,
    action_required: str = "",
) -> dict[str, str]:
    return {
        "reference_side_effect": reference,
        "openpower_surface": surface,
        "openpower_effect": effect,
        "game_action": game_action,
        "read_only_or_state_changing": behavior,
        "validation_condition": "Scenario setup uses enabled campaign scenario data and filters eligible playable countries.",
        "country_scope_restriction": "Scenario eligibility limits the countries available for the subsequent country-selection stage.",
        "confirmation_state": "Scenario selection is a local setup draft; the campaign action is sent only after country and party setup.",
        "error_state": "Unavailable source presets stay visibly disabled; invalid or stale campaign setup is rejected by the authoritative start action.",
        "restrictions_confirmation_error": "Do not claim REFERENCE sphere difficulty, custom-scenario indexing, or immediate scenario startup where OpenPower uses a different setup model.",
        "action_required": action_required,
        "status": status,
    }


SCENARIO_SELECTION_INTERACTION_BINDINGS = {
    "Scenarios_Window/frmTitle/btnExit": _scenario_selection_interaction(
        reference="GGameScenarioWindow::OnMouseClick hides the window and calls CancelConnect.",
        surface="CampaignScenarioSelectionWindow close -> NewGameView._return_to_main_menu",
        effect="Closes scenario setup and returns to the main menu; this local setup has no pending multiplayer connection to cancel.",
        game_action="none (local setup navigation)",
        behavior="local navigation",
        status="partial",
        action_required="Keep the close route local and do not claim it cancels a network connection that OpenPower did not start.",
    ),
    "Scenarios_Window/frmTitle/btnApply": _scenario_selection_interaction(
        reference="GGameScenarioWindow::OnCreate hides the inherited title Apply control.",
        surface="CampaignScenarioSelectionWindow / GML base-window title rules",
        effect="The title Apply control is not exposed and dispatches no action, matching the source initialization.",
        game_action="none (hidden source control)",
        behavior="hidden presentation control",
        status="verified_openpower",
    ),
    "Scenarios_Window/frmInner/frmScenario/tabInfo/Tab2/frmObjectives/lstGoals": _scenario_selection_interaction(
        reference="GFrameScenario::UpdateSelectedScenario fills a read-only objective list with titles, deadlines, and disabled completion toggles.",
        surface="CampaignScenarioSelectionWindow OBJECTIVES tab",
        effect="Shows configured scenario objective titles and deadlines as read-only preview items; REFERENCE's initial completion-state toggles are not represented.",
        game_action="none (read-only scenario preview)",
        behavior="read-only preview",
        status="partial",
        action_required="Keep scenario objectives read-only and document that OpenPower does not reproduce the source's initial objective completion-state indicators.",
    ),
    "Scenarios_Window/frmInner/frmCustom/lstCustom": _scenario_selection_interaction(
        reference="OnListItemSelected resolves the selected custom-list row after the first nine regular scenarios, sets that scenario, and refreshes its detail frame.",
        surface="CampaignScenarioSelectionWindow campaign scenario list",
        effect="Selecting an enabled OpenPower campaign scenario updates the local scenario draft, its preview, and eligible-country options; the list is not restricted to REFERENCE's custom-scenario rows.",
        game_action="none (local scenario selection)",
        behavior="local setup selection",
        status="partial",
        action_required="Preserve selection from OpenPower's enabled campaign_scenarios data and do not apply REFERENCE's fixed nine-row custom-scenario offset.",
    ),
    "Scenarios_Window/frmInner/btnStart": _scenario_selection_interaction(
        reference="When a scenario is selected, the source reads its selected country, calls SelectScenario, disables Start, and hides the window.",
        surface="CampaignScenarioSelectionWindow CONTINUE -> NewGameView country setup -> ActionStartCampaign",
        effect="CONTINUE advances to country and party setup. ActionStartCampaign is sent only after those selections are complete.",
        game_action="none on click (local setup navigation); ActionStartCampaign after country and party selection",
        behavior="local setup navigation followed by authoritative campaign start",
        status="partial",
        action_required="Keep the scenario-to-country setup stage explicit; do not dispatch ActionStartCampaign before country and party validation.",
    ),
    "Scenarios_Window/frmInner/btnCancel": _scenario_selection_interaction(
        reference="GGameScenarioWindow::OnMouseClick hides the window and calls CancelConnect.",
        surface="CampaignScenarioSelectionWindow CANCEL -> NewGameView._return_to_main_menu",
        effect="Closes scenario setup and returns to the main menu; no multiplayer connection is pending in this OpenPower flow.",
        game_action="none (local setup navigation)",
        behavior="local navigation",
        status="partial",
        action_required="Keep the cancel route local and do not claim it cancels a network connection that OpenPower did not start.",
    ),
}


OBJECTIVES_INTERACTION_BINDINGS = {
    "Objectives_Window/frmInner/frmInner/tabInfo/Tab2/frmObjectives/lstGoals": {
        "reference_side_effect": (
            "GFrameScenario::UpdateSelectedScenario populates the list with objective titles, timeout labels, "
            "and disabled completion toggles. GObjectivesWindow::OnMouseClick handles only the exit button; "
            "selecting an objective has no source action."
        ),
        "openpower_surface": "ObjectivesPanel / ObjectivesWindowContent GML tabs",
        "openpower_effect": (
            "Renders current-country campaign objectives as read-only rows with a disabled completion-status "
            "indicator, status, description, progress, deadline, and available evidence. Objective rows dispatch no action."
        ),
        "game_action": "none (read-only objective display)",
        "read_only_or_state_changing": "read-only display",
        "validation_condition": "CampaignPresenter scopes objective rows to the active campaign or target country.",
        "country_scope_restriction": "The displayed campaign objective collection follows PanelRenderContext.target_tag.",
        "confirmation_state": "none (objective rows are read-only)",
        "error_state": "No row-level action or validation error is produced.",
        "restrictions_confirmation_error": (
            "Keep objective presentation read-only and the completion-status indicator disabled; do not treat a row click as a campaign command."
        ),
        "action_required": (
            "Keep read-only row selection and the disabled completion-status indicator covered; track remaining source-field and localization differences in data contracts."
        ),
        "status": "verified_openpower",
    },
}

for _sphere, _difficulty_rows in {
    "Politics": (
        ("Beginner", "togPoliticBeginner", 0, False),
        ("Intermediate", "togPoliticIntermediate", 1, False),
        ("Expert", "togPoliticExpert", 2, True),
    ),
    "Economy": (
        ("Beginner", "togEconomicBeginner", 3, False),
        ("Intermediate", "togEconomicIntermediate", 4, False),
        ("Expert", "togEconomicExpert", 5, True),
    ),
    "Military": (
        ("Beginner", "togMilitaryBeginner", 6, False),
        ("Intermediate", "togMilitaryIntermediate", 7, False),
        ("Expert", "togMilitaryExpert", 8, True),
    ),
}.items():
    for _difficulty, _control, _scenario_index, _hard in _difficulty_rows:
        SCENARIO_SELECTION_INTERACTION_BINDINGS[
            f"Scenarios_Window/frmInner/frmGolem/{_control}"
        ] = _scenario_selection_interaction(
            reference=(
                f"The source toggle selects regular scenario index {_scenario_index} "
                f"for {_sphere} {_difficulty} and sets that sphere's ScenarioSphere hard flag to {_hard}."
            ),
            surface="CampaignScenarioSelectionWindow disabled sphere-difficulty placeholders",
            effect=f"Renders N/A for {_sphere} {_difficulty}; OpenPower scenarios do not expose independent REFERENCE sphere-difficulty presets.",
            game_action="none (unavailable REFERENCE sphere-difficulty preset)",
            behavior="unavailable source-specific setup option",
            status="verified_unavailable",
            action_required="Keep the source-specific difficulty preset disabled until OpenPower has an equivalent scenario difficulty model.",
        )


def _battle_inspection_interaction(
    *, reference: str, effect: str, game_action: str, behavior: str,
    validation: str, action_required: str,
) -> dict[str, str]:
    return {
        "reference_side_effect": reference,
        "openpower_surface": "BattleInspectionWindows / BattleInspection",
        "openpower_effect": effect,
        "game_action": game_action,
        "read_only_or_state_changing": behavior,
        "validation_condition": validation,
        "country_scope_restriction": "Battle commands are limited to the controlled country; inspection-only country selection is local to the dialog.",
        "confirmation_state": "Local inspection selections apply immediately; battle commands dispatch through the authoritative action handler without a separate confirmation dialog.",
        "error_state": "Stale, inactive, unauthorized, or unsupported battle commands are rejected by BattleStrategySystem and reported through command feedback.",
        "restrictions_confirmation_error": "OpenPower's battle records, strategy actions, and public force observations differ from REFERENCE's tactical scene, actor-value progress, and combat-event protocol.",
        "action_required": action_required,
        "status": "partial",
    }


BATTLE_INSPECTION_INTERACTION_BINDINGS = {
    "Battle_Window/lstFlagsYou": _battle_inspection_interaction(
        reference="Dynamic ally-side flag buttons select an allied country; changing it resets accumulated hit visualization for allied units.",
        effect="Selects the ally country shown in the force cards and updates the selected-country border; OpenPower has no accumulated-hit animation to reset.",
        game_action="none (local battle inspection selection)",
        behavior="local inspection selection",
        validation="The selected tag must belong to the battle's ally-side participant list.",
        action_required="Keep ally selection local and preserve the source side grouping; do not imply that it changes command authority or resets combat state.",
    ),
    "Battle_Window/lstFlagsEnemy": _battle_inspection_interaction(
        reference="Dynamic enemy-side flag buttons select an enemy country; changing it resets accumulated hit visualization for allied units.",
        effect="Selects the enemy country shown in the force cards and updates the selected-country border; OpenPower has no accumulated-hit animation to reset.",
        game_action="none (local battle inspection selection)",
        behavior="local inspection selection",
        validation="The selected tag must belong to the battle's enemy-side participant list.",
        action_required="Keep enemy selection local and preserve the source side grouping; do not imply that it changes command authority or resets combat state.",
    ),
    "Battle_Window/frmTrimYou/frmFlagYou/btnHighlight": _battle_inspection_interaction(
        reference="The source GML flag shell supplies a highlighted button skin; the battle click handler only changes country when a button belongs to one of the dynamic flag lists.",
        effect="The selected country in the ally flag list receives an outline; the source shell's separate button skin is not a separate OpenPower action.",
        game_action="none (flag selection presentation)",
        behavior="local selection presentation",
        validation="The outline follows the selected ally country in the current battle.",
        action_required="Keep selection indication attached to the selected participant flag and do not turn the decorative shell into a separate command.",
    ),
    "Battle_Window/frmTrimEnemy/frmFlagEnemy/btnHighlight": _battle_inspection_interaction(
        reference="The source GML flag shell supplies a highlighted button skin; the battle click handler only changes country when a button belongs to one of the dynamic flag lists.",
        effect="The selected country in the enemy flag list receives an outline; the source shell's separate button skin is not a separate OpenPower action.",
        game_action="none (flag selection presentation)",
        behavior="local selection presentation",
        validation="The outline follows the selected enemy country in the current battle.",
        action_required="Keep selection indication attached to the selected participant flag and do not turn the decorative shell into a separate command.",
    ),
    "Battle_Window/frmBattle/cboStrategies": _battle_inspection_interaction(
        reference="Strategy selection applies a theme-specific XML preset to allied tactical units and sends GBattleOverviewUnitActionUpdate with per-unit attack flags and a retreat flag.",
        effect="Selecting a strategy sends ActionSetBattleStrategy for all eligible forces of the controlled country; OpenPower uses its own generic posture model rather than the source's theme-specific tactical presets.",
        game_action="ActionSetBattleStrategy(battle_id, strategy, country_tag, unit_type='all')",
        behavior="authoritative battle strategy change",
        validation="BattleInspection requires an active participant battle, controlled-country authority, and at least one eligible force of the requested scope.",
        action_required="Keep server-side battle validation and the OpenPower posture vocabulary explicit; do not claim source XML presets or per-unit attack flags are identical.",
    ),
    "Battle_Window/frmBattle/btnRetreat": _battle_inspection_interaction(
        reference="The source selects its final theme strategy as Retreat and sends GBattleOverviewUnitActionUpdate with m_bRetreat set.",
        effect="Dispatches ActionSetBattleStrategy with strategy='retreat' for all eligible forces of the controlled country; OpenPower's battle system begins retreat movement using its route rules.",
        game_action="ActionSetBattleStrategy(battle_id, strategy='retreat', country_tag, unit_type='all')",
        behavior="authoritative battle retreat order",
        validation="The battle must be active, the player must control a participant country, eligible own forces must be present, and retreat needs a valid safe-capital route.",
        action_required="Preserve the route-validity rejection and do not claim REFERENCE's retreat event or tactical animation is reproduced.",
    ),
    "Battle_Window/frmOverviewMeter/btnSeparator1": _battle_inspection_interaction(
        reference="The source moves the separator to the end of the filled battle-progress segment after each arena update and final result.",
        effect="GMLWidgets.meter draws a marker in the btnSeparator1 slot at the edge of OpenPower's current battle-balance fill.",
        game_action="none (battle progress presentation)",
        behavior="read-only battle progress display",
        validation="The displayed fraction comes from the current battle row and is clamped to the meter range.",
        action_required="Keep the GML marker positioned at the OpenPower balance edge while preserving the distinct source actor-value progress formula.",
    ),
    "Battle_Window/frmOverviewMeter/btnUnfilled": _battle_inspection_interaction(
        reference="The source uses btnUnfilled as the red remainder segment of the locked two-part battle progress meter.",
        effect="GMLWidgets.meter draws the red remainder in the btnUnfilled slot; the displayed balance semantics differ from the source progress formula.",
        game_action="none (battle progress presentation)",
        behavior="read-only battle progress display",
        validation="The displayed fraction comes from the current battle row and is clamped to the meter range.",
        action_required="Keep progress tied to OpenPower's battle balance and preserve the source red remainder slot and color.",
    ),
    "Battle_Window/frmOverviewMeter/btnFill": _battle_inspection_interaction(
        reference="The source uses btnFill as the green filled segment of the locked two-part battle progress meter.",
        effect="GMLWidgets.meter draws the green fill in the btnFill geometry and aligns the source separator slot; OpenPower still uses its own battle-balance value rather than the source actor-value formula.",
        game_action="none (battle progress presentation)",
        behavior="read-only battle progress display",
        validation="The displayed fraction comes from the current battle row and is clamped to the meter range.",
        action_required="Keep the green fill and separator aligned to the source slots while preserving the distinct OpenPower balance semantics.",
    ),
}


def _strategic_target_interaction(
    *, reference: str, effect: str, game_action: str, behavior: str,
    validation: str, status: str, action_required: str = "",
) -> dict[str, str]:
    return {
        "reference_side_effect": reference,
        "openpower_surface": "StrategicWarfarePanel / StrategicPlanner",
        "openpower_effect": effect,
        "game_action": game_action,
        "read_only_or_state_changing": behavior,
        "validation_condition": validation,
        "country_scope_restriction": "Launch drafts are limited to the controlled country and a currently foreign-owned target region.",
        "confirmation_state": "Target and weapon selections remain local until the user prepares and confirms a launch.",
        "error_state": "Stale inventory, ownership, research, authorization, or funding is revalidated by StrategicWarfareSystem and returned as command feedback.",
        "restrictions_confirmation_error": "REFERENCE selects missile categories and counts for a country-wide target; OpenPower launches selected strategic weapon records at a specific region through ActionLaunchStrategicStrike.",
        "action_required": action_required,
        "status": status,
    }


STRATEGIC_TARGET_SELECTION_INTERACTION_BINDINGS = {
    "Strategic_Target_Country_Window/btnReturn": _strategic_target_interaction(
        reference="The source Return button calls SwapToMilitary and leaves the strategic target window.",
        effect="Closes the local target-planning phase and returns to the still-open Strategic Warfare panel.",
        game_action="none (local planner navigation)",
        behavior="local navigation",
        validation="The target planner phase is open.",
        status="partial",
        action_required="Keep Return as a local planner dismissal and do not claim it changes the campaign's military state.",
    ),
    "Strategic_Target_Country_Window/frmAttackType/cboAttackType": _strategic_target_interaction(
        reference="The source selection sets the nuclear target type to country-wide Military or Civilian and refreshes missile assignment when a missile type is selected.",
        effect="Stores military or civilian target mode in the local plan; the eventual OpenPower action still targets one selected region rather than auto-assigning country-wide targets.",
        game_action="ActionLaunchStrategicStrike(target_mode='military'|'civilian') after launch confirmation",
        behavior="local plan selection; authoritative action on confirmed launch",
        validation="The selected target region must remain foreign-owned and the launch preview must pass authorization, weapon, research, and funding checks.",
        status="partial",
        action_required="Keep the target mode explicit while preserving OpenPower's region-specific target and server validation.",
    ),
    "Strategic_Target_Country_Window/frmAttackStrength/btnSuggested": _strategic_target_interaction(
        reference="The source Suggest button changes Specific or Undefined targeting to Military and computes available missile assignment, selected strength, and projected casualties.",
        effect="Selects a default eligible region for the chosen country; it does not estimate or assign a missile count or projected casualties.",
        game_action="none (local region suggestion)",
        behavior="local plan suggestion",
        validation="At least one eligible foreign region must belong to the selected target country.",
        status="partial",
        action_required="Keep the suggested region behavior distinct from the source's missile-assignment and casualty estimate.",
    ),
    "Strategic_Target_Country_Window/frmAttackStrength/btnArrowDecrease1": _strategic_target_interaction(
        reference="The source button decreases the selected missile count by one while missiles are available.",
        effect="There is no single-target missile-count decrement: the OpenPower planner selects discrete weapon records and ActionLaunchStrategicStrike has no quantity field.",
        game_action="none (unavailable REFERENCE missile-count control)",
        behavior="unavailable source-specific quantity control",
        validation="OpenPower launch actions identify a weapon record rather than a count of category missiles.",
        status="verified_unavailable",
        action_required="Do not synthesize missile quantities from a strategic weapon record; keep count editing unavailable until the action model supports it.",
    ),
    "Strategic_Target_Country_Window/frmAttackStrength/cboMissileType": _strategic_target_interaction(
        reference="The selector filters the source inventory to ground-based missiles, submarine-based missiles, or both.",
        effect="Selects an individual OpenPower strategic weapon record; its weapon type and origin are carried into the launch action, but source category filtering is not reproduced.",
        game_action="ActionLaunchStrategicStrike(weapon_id, weapon_type, origin_region_id) after launch confirmation",
        behavior="local weapon selection; authoritative action on confirmed launch",
        validation="The weapon must belong to the controlled country, be ready, and satisfy research, authorization, range, and funding constraints.",
        status="partial",
        action_required="Keep selection tied to OpenPower weapon records and do not label an individual record as the source's ground/submarine/all category filter.",
    ),
    "Strategic_Target_Country_Window/frmAttackStrength/frmAttackStrengthValue/btnUnfilled": _strategic_target_interaction(
        reference="The source unfilled meter segment accepts dragging to set the percentage of available missiles selected for the launch.",
        effect="The source quantity slider is not exposed; OpenPower uses this GML slot for launch-authorization context selection.",
        game_action="none (unavailable REFERENCE missile-count slider)",
        behavior="unavailable source-specific quantity control",
        validation="Launch authorization is selected from configured contexts; weapon readiness and launch validity are checked by the server.",
        status="verified_unavailable",
        action_required="Keep authorization selection distinct from the source missile-count slider and do not present it as a quantity control.",
    ),
    "Strategic_Target_Country_Window/frmAttackStrength/frmAttackStrengthValue/btnFill": _strategic_target_interaction(
        reference="The source filled meter segment accepts dragging to set the percentage of available missiles selected for the launch.",
        effect="The source quantity slider is not exposed; OpenPower uses this GML slot for launch-authorization context selection.",
        game_action="none (unavailable REFERENCE missile-count slider)",
        behavior="unavailable source-specific quantity control",
        validation="Launch authorization is selected from configured contexts; weapon readiness and launch validity are checked by the server.",
        status="verified_unavailable",
        action_required="Keep authorization selection distinct from the source missile-count slider and do not present it as a quantity control.",
    ),
    "Strategic_Target_Country_Window/frmAttackStrength/btnArrowIncrease1": _strategic_target_interaction(
        reference="The source button increases the selected missile count by one up to the number of available missiles.",
        effect="There is no single-target missile-count increment: the OpenPower planner selects discrete weapon records and ActionLaunchStrategicStrike has no quantity field.",
        game_action="none (unavailable REFERENCE missile-count control)",
        behavior="unavailable source-specific quantity control",
        validation="OpenPower launch actions identify a weapon record rather than a count of category missiles.",
        status="verified_unavailable",
        action_required="Do not synthesize missile quantities from a strategic weapon record; keep count editing unavailable until the action model supports it.",
    ),
    "Strategic_Target_Country_Window/frmCountry/cboCountry": _strategic_target_interaction(
        reference="The source country selector chooses a country-wide target or starts map picking for a specific target location.",
        effect="Selects a foreign target country, a specific region on the map, or the OpenPower multi-target workflow; a country selection resolves to a concrete region before launch.",
        game_action="ActionLaunchStrategicStrike(target_region_id, target_country_tag) after launch confirmation",
        behavior="local target selection; authoritative action on confirmed launch",
        validation="The target must be a currently foreign-owned region; specific-location selection only accepts eligible foreign regions.",
        status="partial",
        action_required="Preserve explicit country, region, and multi-target choices; do not imply a country-wide source target is represented by one OpenPower region.",
    ),
}


def _strategic_warfare_interaction(
    *, reference: str, effect: str, game_action: str, behavior: str,
    validation: str, status: str, action_required: str,
) -> dict[str, str]:
    return {
        "reference_side_effect": reference,
        "openpower_surface": "StrategicWarfarePanel / StrategicPlanner",
        "openpower_effect": effect,
        "game_action": game_action,
        "read_only_or_state_changing": behavior,
        "validation_condition": validation,
        "country_scope_restriction": "No country restriction applies to local window controls; planner launches are limited to the controlled country and foreign-owned regions.",
        "confirmation_state": "Local controls do not change campaign state; planner launch choices require explicit confirmation.",
        "error_state": "No game command is sent by local controls; confirmed launch requests return authoritative validation feedback when rejected.",
        "restrictions_confirmation_error": "The source form is country-wide; OpenPower's campaign-changing route targets a specific region and weapon record.",
        "action_required": action_required,
        "status": status,
    }


STRATEGIC_WARFARE_INTERACTION_BINDINGS = {
    "Strategic_Warfare/frmTitle/btnExit": _strategic_warfare_interaction(
        reference="GStrategicWarfareWindow::OnMouseClick hides the strategic-warfare window.",
        effect="The window close control dismisses StrategicWarfarePanel and its visible planner phase without changing campaign state.",
        game_action="none (local window dismissal)",
        behavior="local navigation",
        validation="The strategic-warfare window is open.",
        status="verified_openpower",
        action_required="Keep close routed through the window manager and preserve the GML-sized panel frame.",
    ),
    "Strategic_Warfare/frmTitle/btnApply": _strategic_warfare_interaction(
        reference="The inherited Apply handler calls Save only when the window is dirty; this source initializes clean and never marks the strategic window dirty or implements a Save override.",
        effect="OpenPower exposes no generic Apply action for this panel; strategic choices remain a draft and commit only through the planner's confirmed launch route.",
        game_action="none (no source save operation or OpenPower Apply action)",
        behavior="unavailable inert source action",
        validation="The source Apply control remains disabled while the inherited dirty flag is false.",
        status="verified_unavailable",
        action_required="Do not add an Apply button unless the panel gains persistent edits that need a separate save operation.",
    ),
    "Strategic_Warfare/frmInner/frmButton/btnLaunch": _strategic_warfare_interaction(
        reference="The source callback reads the selected attack type, but the launch request construction and event dispatch are inside a block comment.",
        effect="The OpenPower Target planner collects a validated region and weapon draft, then dispatches ActionLaunchStrategicStrike only after explicit confirmation.",
        game_action="ActionLaunchStrategicStrike after planner confirmation",
        behavior="local planning followed by an authoritative confirmed action",
        validation="The controlled country, target ownership, selected weapon readiness, research, authorization, range, and funding are checked before dispatch.",
        status="partial",
        action_required="Keep the implemented planner route guarded by confirmation and revalidation; do not restore the source's country-wide request shape.",
    ),
    "Strategic_Warfare/frmInner/frmAttackType/cboAttackType": _strategic_warfare_interaction(
        reference="The source intends three attack-type labels; its population loop is commented out, while the launch callback only computes a selected index before the event block.",
        effect="The target planner stores Military or Civilian mode in the draft and carries it into the confirmed strike action.",
        game_action="ActionLaunchStrategicStrike(target_mode='military'|'civilian') after planner confirmation",
        behavior="local plan selection followed by a confirmed action",
        validation="The target region and launch preview must remain valid for the chosen mode.",
        status="partial",
        action_required="Keep the two supported OpenPower target modes explicit; do not claim the commented source initialization supplies a third mode.",
    ),
    "Strategic_Warfare/frmInner/frmAttackStrength/frmAttackStrengthValue/btnUnfilled": _strategic_warfare_interaction(
        reference="The source meter represents a draggable percentage of available missiles; OnMouseMove copies its current value to the percentage label.",
        effect="OpenPower has no missile-count percentage control or quantity field; payload profiles select a discrete yield level and do not represent this slider.",
        game_action="none (source-local meter value; no matching OpenPower quantity action)",
        behavior="unavailable source-specific quantity control",
        validation="OpenPower launch actions identify a weapon record and validate its availability; they do not accept a missile-count percentage.",
        status="verified_unavailable",
        action_required="Keep the source quantity slider unavailable and do not conflate it with the separate discrete payload-profile selector.",
    ),
    "Strategic_Warfare/frmInner/frmAttackStrength/frmAttackStrengthValue/btnFill": _strategic_warfare_interaction(
        reference="The source meter represents a draggable percentage of available missiles; OnMouseMove copies its current value to the percentage label.",
        effect="OpenPower has no missile-count percentage control or quantity field; payload profiles select a discrete yield level and do not represent this slider.",
        game_action="none (source-local meter value; no matching OpenPower quantity action)",
        behavior="unavailable source-specific quantity control",
        validation="OpenPower launch actions identify a weapon record and validate its availability; they do not accept a missile-count percentage.",
        status="verified_unavailable",
        action_required="Keep the source quantity slider unavailable and do not conflate it with the separate discrete payload-profile selector.",
    ),
    "Strategic_Warfare/frmInner/frmCountry/cboCountry": _strategic_warfare_interaction(
        reference="The source intends to populate a country selector and use the selected country as a country-wide target; its country-population loop is commented out.",
        effect="The OpenPower planner selects a foreign target country, a specific foreign region, or its multi-target workflow; the final strike remains region-specific.",
        game_action="ActionLaunchStrategicStrike(target_region_id, target_country_tag) after planner confirmation",
        behavior="local target selection followed by a confirmed action",
        validation="Selected targets must be foreign-owned and remain eligible at launch time.",
        status="partial",
        action_required="Preserve explicit country, map-region, and multi-target choices without presenting a single regional strike as a country-wide attack.",
    ),
}


def _multiplayer_workflow_interaction(
    *, reference: str, surface: str, action_required: str,
) -> dict[str, str]:
    return {
        "reference_side_effect": reference,
        "openpower_surface": surface,
        "openpower_effect": "OpenPower has no multiplayer server/session workflow, so this source-only control is not exposed.",
        "game_action": "none (unavailable multiplayer workflow)",
        "read_only_or_state_changing": "unavailable multiplayer workflow",
        "validation_condition": "No authoritative multiplayer server or lobby session exists in OpenPower.",
        "country_scope_restriction": "No active multiplayer session or server authority is available.",
        "confirmation_state": "No control is exposed and no multiplayer request is dispatched.",
        "error_state": "No request is sent because the multiplayer workflow is unavailable.",
        "restrictions_confirmation_error": "Do not redirect network setup, lobby, chat, or objective controls to unrelated single-player actions.",
        "action_required": action_required,
        "status": "verified_unavailable",
    }


MULTIPLAYER_WORKFLOW_UNAVAILABLE_INTERACTION_BINDINGS: dict[str, dict[str, str]] = {}

_HOST_MULTIPLAYER_HIDDEN_CONTROLS = {
    "frmTitle/btnExit": "GHostMPGameWindow::OnCreate hides the title Exit control.",
    "frmTitle/btnApply": "GHostMPGameWindow::OnCreate hides the title Apply control.",
    "frmInner/frmGameSettings/togPrivate": "GHostMPGameWindow::OnCreate hides the private-server toggle; LAN mode determines the private flag.",
}

for _suffix, _reference in _HOST_MULTIPLAYER_HIDDEN_CONTROLS.items():
    MULTIPLAYER_WORKFLOW_UNAVAILABLE_INTERACTION_BINDINGS[
        f"Host_Multiplayer_Game/{_suffix}"
    ] = _multiplayer_workflow_interaction(
        reference=_reference,
        surface="MultiplayerHostWorkflowUnavailable",
        action_required="Keep the multiplayer host control unavailable until OpenPower has an authoritative host-server configuration and startup workflow.",
    )

_HOST_MULTIPLAYER_DRAFT_CONTROLS = {
    "frmInner/frmGameSettings/edtPort": "The value is copied to the multiplayer server port when Start is pressed.",
    "frmInner/frmGameSettings/edtMaxPlayers": "The value is copied to the multiplayer server player limit when Start is pressed.",
    "frmInner/frmGameSettings/edtTimeLimit": "The value is copied to the multiplayer server time limit when Start is pressed.",
    "frmInner/frmGameSettings/togDedicatedServer": "The toggle supplies the dedicated-server flag to multiplayer server startup.",
    "frmInner/frmGoals/cboGameSpeed1": "The selector configures whether nuclear warfare is permitted in the hosted multiplayer game.",
    "frmInner/frmGoals/cboGameSpeed": "The selector configures hosted multiplayer simulation speed.",
    "frmInner/frmGameInfo/edtServerName": "The value is copied to the multiplayer server name when Start is pressed.",
    "frmInner/frmGameInfo/edtPassword": "The value is copied to the multiplayer server password when Start is pressed.",
}
for _suffix, _reference in _HOST_MULTIPLAYER_DRAFT_CONTROLS.items():
    MULTIPLAYER_WORKFLOW_UNAVAILABLE_INTERACTION_BINDINGS[
        f"Host_Multiplayer_Game/{_suffix}"
    ] = _build_interaction_binding(
        reference=_reference,
        surface="HostMultiplayerGameWindow local settings draft",
        effect="Edits a local draft value without sending an action to OpenPower's simulation.",
        action="none (local multiplayer setup draft only)",
        status="partial",
        validation="Values remain in the host-window draft; no host service validates or consumes them.",
        constraints="No multiplayer server authority or player assignment exists in OpenPower.",
        confirmation="The Start Game control remains disabled, so the draft is never submitted.",
        error="No server action is issued while the multiplayer host service is unavailable.",
        mapping_notes="GML slots and local editing are implemented; authoritative host startup is not.",
        action_required="Keep edits confined to the local draft and preserve the disabled Start state until a server-backed host workflow exists.",
        read_only_or_state_changing="local in-memory host setup draft",
    )

_HOST_MULTIPLAYER_START = _build_interaction_binding(
    reference="The source gathers host settings and starts the multiplayer server through StartHostServerGame.",
    surface="HostMultiplayerGameWindow / multiplayer.host.start",
    effect="Displays the source Start Game control in its GML slot but keeps it disabled because OpenPower has no host service.",
    action="none (unavailable multiplayer host workflow)",
    status="verified_unavailable",
    read_only_or_state_changing="unavailable multiplayer workflow",
    validation="No authoritative multiplayer server or lobby session exists in OpenPower.",
    constraints="No host server can be started or assigned players.",
    confirmation="The Start Game button is visible but disabled; no host request is sent.",
    error="The multiplayer host workflow is unavailable.",
    mapping_notes="The screen is implemented as a local settings draft; no single-player action is substituted for host startup.",
    action_required="Keep Start disabled until OpenPower has an authoritative host-server configuration and startup workflow.",
)
MULTIPLAYER_WORKFLOW_UNAVAILABLE_INTERACTION_BINDINGS[
    "Host_Multiplayer_Game/frmInner/btnStart"
] = _HOST_MULTIPLAYER_START

MULTIPLAYER_WORKFLOW_UNAVAILABLE_INTERACTION_BINDINGS[
    "Host_Multiplayer_Game/frmInner/btnCancel"
] = _build_interaction_binding(
    reference="The source cancels multiplayer host setup through CancelHostMPGame.",
    surface="HostMultiplayerGameWindow.close / JoinMultiplayerWindow",
    effect="Closes the host settings draft and reveals the still-open server browser.",
    action="none (local window navigation)",
    status="verified_openpower",
    read_only_or_state_changing="local UI navigation",
    validation="The host settings window is open.",
    constraints="No gameplay or server state is changed.",
    confirmation="Cancel returns to the server browser; no host request is sent.",
    error="None.",
    mapping_notes="The Python route follows the source host-setup cancellation path back to the server browser.",
    action_required="Keep Cancel connected to the browser return path without dispatching a server action.",
)

for _index, _objective in enumerate(
    ("world peace", "resource needs", "conquer the world", "develop the nation", "raise GDP per capita"),
    start=1,
):
    MULTIPLAYER_WORKFLOW_UNAVAILABLE_INTERACTION_BINDINGS[
        f"Host_Multiplayer_Game/frmInner/frmGoals/frmTog{_index}/togGoal"
    ] = _build_interaction_binding(
        reference=f"The toggle adds or removes the local hosted-game {_objective} objective from m_vGameObjectives.",
        surface="MultiplayerHostWorkflowUnavailable",
        effect="Toggles the corresponding local objective draft; no game action is sent.",
        action="none (local multiplayer setup draft only)",
        status="partial",
        validation="The value remains in HostMultiplayerGameWindow and is not evaluated by the simulation.",
        constraints="No multiplayer session or objective model exists in OpenPower.",
        confirmation="Start remains disabled, so the draft objective is never submitted.",
        error="No server action is issued while the multiplayer host service is unavailable.",
        mapping_notes="The source control, label, and local toggle state are rendered in their GML slots; server objective behavior is not implemented.",
        action_required="Keep objective selection local and do not claim game behavior until a host session can consume it.",
        read_only_or_state_changing="local in-memory host setup draft",
    )
    MULTIPLAYER_WORKFLOW_UNAVAILABLE_INTERACTION_BINDINGS[
        f"Host_Multiplayer_Game/frmInner/frmGoals/cboGoal{_index}"
    ] = _build_interaction_binding(
        reference=f"The selector updates the hosted-game {_objective} deadline in m_vGameObjectives when that objective is enabled.",
        surface="MultiplayerHostWorkflowUnavailable",
        effect="Stages the deadline locally while the corresponding objective is enabled; no game action is sent.",
        action="none (local multiplayer setup draft only)",
        status="partial",
        validation="The value remains in HostMultiplayerGameWindow and is not evaluated by the simulation.",
        constraints="No multiplayer session or objective model exists in OpenPower.",
        confirmation="Start remains disabled, so the draft deadline is never submitted.",
        error="No server action is issued while the multiplayer host service is unavailable.",
        mapping_notes="The source control is bound to its GML slot and disabled unless its objective is selected; server objective behavior is not implemented.",
        action_required="Keep deadlines as local draft state and do not claim game behavior until a host session can consume them.",
        read_only_or_state_changing="local in-memory host setup draft",
    )

_GAME_LOBBY_UNAVAILABLE_CONTROLS = {
    "frmTitle/btnExit": "The source closes the lobby while Playing and cancels the connection before play.",
    "frmTitle/btnApply": "GGameLobbyWindow::OnCreate hides the title Apply control.",
    "frmInner/frmAdministrator/cboCountry": "Country selection sends GSetPlayerInfo and requests the country's party list from the multiplayer server.",
    "frmInner/frmPlayers/lstPlayers": "The list presents lobby players and supplies selected-player identities to private chat, kick, and ban actions.",
    "frmInner/frmChat/lstChat": "The list displays multiplayer lobby chat messages.",
    "frmInner/btnSendPrivate": "The button sends the current chat text to selected lobby players.",
    "frmInner/frmAdministrator/btnParty": "The button opens the source party selector for the chosen lobby country.",
    "frmInner/frmAdministrator/btnProfile": "The button opens the source country profile selector for lobby country selection.",
    "frmInner/btnSend": "The button sends the current chat text to the lobby.",
    "frmInner/frmChat/edtMsg": "Enter or Send submits the draft to lobby chat; Shift+Enter targets selected players.",
}
for _suffix, _reference in _GAME_LOBBY_UNAVAILABLE_CONTROLS.items():
    MULTIPLAYER_WORKFLOW_UNAVAILABLE_INTERACTION_BINDINGS[
        f"Game_Lobby/{_suffix}"
    ] = _multiplayer_workflow_interaction(
        reference=_reference,
        surface="MultiplayerLobbyWorkflowUnavailable",
        action_required="Keep the lobby control unavailable until OpenPower has an authoritative multiplayer session and server-backed player/chat workflow.",
    )


MULTIPLAYER_LOBBY_UNAVAILABLE_INTERACTION_BINDINGS = {
    "Game_Lobby/frmInner/frmAdministrator/togReady": _multiplayer_lobby_unavailable_interaction(
        "The source ready toggle calls SendPlayerInfo and raises GSetPlayerInfo with the player's ready/country state."
    ),
    "Game_Lobby/frmInner/frmAdministrator/edtPlayerName": _multiplayer_lobby_unavailable_interaction(
        "The source player-name input calls SendPlayerInfo and raises GSetPlayerInfo while editing the lobby profile."
    ),
    "Game_Lobby/frmInner/btnKickPlayer": _multiplayer_lobby_unavailable_interaction(
        "The source sends a server-targeted GSystemGameEvent to remove each selected lobby player."
    ),
    "Game_Lobby/frmInner/btnBanPlayer": _multiplayer_lobby_unavailable_interaction(
        "The source sends a server-targeted GSystemGameEvent to ban each selected lobby player."
    ),
    "Game_Lobby/frmInner/btnStartGame": _multiplayer_lobby_unavailable_interaction(
        "The source raises the server-targeted GStartGameRequest to begin the hosted multiplayer session."
    ),
}


REMAINING_INTERACTION_BINDINGS = {
    "Game_Over_Window/frmTitle/btnExit": _build_interaction_binding(
        reference="GEndGameWindow::OnMouseClick routes the title Exit control through g_REFERENCEClient->StopGame().",
        surface="GameLayout._request_stop_game -> NavigationService.stop_game",
        effect="Queues local navigation to the main menu; GameView dispatches the pending stop-game request through NavigationService.",
        action="none (local session navigation; no GameAction)",
        status="verified_openpower",
        read_only_or_state_changing="local session navigation",
        validation="The dialog appears for victory, defeat, or draw when sandbox_continuation is false.",
        constraints="Sandbox continuation keeps the result out of the modal and leaves the campaign open.",
        confirmation="None; the source title Exit also stops the game directly.",
        mapping_notes="The title close button and Main Menu button share the existing StopGame navigation lifecycle.",
        action_required="Keep title close routed to the existing stop-game navigation and covered by the terminal-result journey.",
    ),
    "Connecting_Window/btnCancel": _multiplayer_workflow_interaction(
        reference="GConnectingWindow::OnMouseClick sends m_eCancelEvent to the active REFERENCE connection state machine.",
        surface="MultiplayerConnectionWorkflowUnavailable",
        action_required="Keep connection cancellation unavailable until OpenPower has an active multiplayer connection workflow.",
    ),
    "Covert_Actions_Mission_Outcome/frmTitle/btnApply": _build_interaction_binding(
        reference=(
            "GCovertActionsMissionOutcomeWindow::OnMouseClick handles only the title Exit control and returns Handled; "
            "the title Apply control has no source branch."
        ),
        surface="CovertOutcomeDialog / WindowManager GML title controls",
        effect="No Apply control is exposed for the read-only mission result; the dialog closes through its title Exit control.",
        action="none (no source Apply side effect)",
        status="verified_unavailable",
        read_only_or_state_changing="inert source title control",
        action_required="Keep the result dialog read-only and do not add an Apply action without a source or OpenPower result edit.",
    ),
    "Covert_Actions_New_Mission/frmInner/btnCancel": _build_interaction_binding(
        reference="GCovertActionsNewMissionWindow::OnMouseClick hides the local mission form when Cancel is clicked.",
        surface="CovertActionWindows mission form / covert.new_mission.cancel",
        effect="Closes the local mission form without dispatching ActionStartCovertMission.",
        action="none (local form cancellation)",
        status="verified_openpower",
        validation="The mission preparation form is open.",
        confirmation="Cancel discards local form state; Prepare is the explicit authoritative action boundary.",
        action_required="Keep Cancel separate from Prepare and preserve the no-GameAction route.",
    ),
    "Covert_Actions_Mission_Outcome/frmTitle/btnExit": _build_interaction_binding(
        reference="GCovertActionsMissionOutcomeWindow::OnMouseClick hides the read-only outcome window when Exit is clicked.",
        surface="CovertOutcomeDialog.render / WindowManager.window close",
        effect="Closes the local mission outcome view and clears its selected mission; no GameAction is dispatched.",
        action="none (read-only result dismissal)",
        status="verified_openpower",
        validation="A completed result mission is available to the current viewer.",
        confirmation="Dismissal only clears the local dialog selection.",
        action_required="Keep the own-result close route covered by the covert outcome journey.",
    ),
    "Covert_Actions_Mission_Outcome_Attacked/btnExit": _build_interaction_binding(
        reference="GCovertActionsMissionOutcomeAttackedWindow::OnMouseClick hides the attacked-result window when Exit is clicked.",
        surface="CovertOutcomeDialog.render / covert.outcome.attacked.close",
        effect="Closes the local attacked-operation result view and clears its selected mission; no GameAction is dispatched.",
        action="none (read-only result dismissal)",
        status="verified_openpower",
        validation="A completed operation result is visible to the current viewer.",
        confirmation="Dismissal only clears the local dialog selection.",
        constraints="The result view redacts attribution and effect details according to the viewer role.",
        action_required="Keep the attacked-result close route covered by the covert outcome journey.",
    ),
    "Covert_Actions_Window/frmInner/frmCell/btnNewCell": _build_interaction_binding(
        reference="GCovertActionsWindow::OnMouseClick spawns the cell creation window when needed and shows it.",
        surface="CovertOpsPanel._render_actions -> CovertActionWindows.open('create')",
        effect="Opens the local cell creation form; no action is sent until Create is pressed.",
        action="none (local form navigation; submit dispatches ActionCreateCovertCell)",
        status="verified_openpower",
        validation="The player must be commanding their own country with a network client available.",
        constraints="The form lists valid target countries and keeps its draft local until submission.",
        confirmation="Create is the explicit authoritative action boundary; closing the form does not create a cell.",
        action_required="Keep the button-to-form route and separate submit action covered by the cell creation journey.",
    ),
    "Covert_Actions_Window/frmInner/frmCell/btnTrainCell": _build_interaction_binding(
        reference="GCovertActionsWindow::OnMouseClick opens the training window and adds each selected cell to its draft.",
        surface="CovertOpsPanel._render_actions -> CovertActionWindows.open('train', cell_ids=...)",
        effect="Opens the local training form for the selected active cells; no action is sent until Train is pressed.",
        action="none (local form navigation; submit dispatches one ActionTrainCovertCell per selected cell)",
        status="verified_openpower",
        validation="The player must be commanding their own country; every selected cell must be active or idle and below Elite.",
        constraints="The training dialog preserves the selected cell IDs and disables submission if any selected cell becomes unavailable.",
        confirmation="Train is the explicit authoritative action boundary; closing the form does not change training state.",
        action_required="Keep the selected-group button-to-form route and per-cell submit actions covered by the covert training journeys.",
    ),
    "Covert_Actions_Cell_Training/frmInner/btnCancel": _build_interaction_binding(
        reference="GCovertActionsCellTrainingWindow::OnMouseClick hides the local form when Cancel is clicked.",
        surface="CovertActionWindows._render_train / covert.cell_training.cancel",
        effect="Closes the training form without dispatching ActionTrainCovertCell.",
        action="none (local form cancellation)",
        status="verified_openpower",
        validation="The training form is open.",
        confirmation="Cancel discards the local training draft; Train is the explicit authoritative action boundary.",
        action_required="Keep Cancel separate from Train and preserve the no-GameAction route.",
    ),
    "Covert_Actions_Cell_Training/frmTitle/btnExit": _build_interaction_binding(
        reference="The training window delegates title-bar close to the base handler; its GML btnExit rectangle starts at x=308.",
        surface="CovertActionWindows training modal / gml_popup_modal",
        effect="Closes the local training form without dispatching ActionTrainCovertCell.",
        action="none (local form close)",
        status="verified_openpower",
        validation="The training form is open.",
        constraints="The modal keeps its 304 px GML root; only the out-of-root title close hitbox is clamped to the visible popup bounds.",
        confirmation="The title close dismisses the local training form and sends no ActionTrainCovertCell.",
        mapping_notes="The popup uses the extracted GML title rectangle when it fits and clamps only the title close hitbox when the shared source slot exceeds a narrow modal root.",
        action_required="Keep the title-close route covered alongside explicit Cancel and Train actions.",
    ),
    "Covert_Actions_New_Mission/frmTitle/btnExit": _build_interaction_binding(
        reference="GCovertActionsNewMissionWindow delegates title-bar close to the base window behavior.",
        surface="gml_popup_modal / covert.new_mission.dialog.close",
        effect="Closes the local mission form without dispatching ActionStartCovertMission.",
        action="none (local form close)",
        status="verified_openpower",
        validation="The mission preparation form is open.",
        confirmation="The title close discards the mission draft; Prepare is the explicit authoritative action boundary.",
        action_required="Keep title-close dismissal separate from Prepare and cover the route in the mission journey.",
    ),
    "Covert_Actions_Window/frmInner/frmCell/lstCell": _build_interaction_binding(
        reference=(
            "GCovertActionsWindow::OnCustomEvent handles OnListItemSelected, updates the selected-cell set, "
            "and refreshes cell action availability."
        ),
        surface="CovertOpsPanel._render_content / CovertSelection",
        effect="Replace, Ctrl-toggle, and Shift-range selection update the local selected-cell set and mission controls; group commands stay on their explicit action controls.",
        action="none (local multi-cell selection; group commands dispatch existing per-cell actions)",
        status="verified_openpower",
        validation="Each selected row must remain in the visible, non-retired roster for the target country before a group command is submitted.",
        constraints="Private cell rows are shown only for the controlled country; foreign views remain redacted.",
        confirmation="Selection is local; mission actions require a separate explicit control.",
        mapping_notes="Matches the source MultiExtended list behavior. Group training, retirement, and mission preparation submit one existing authoritative action per selected cell, with each mission retaining that cell's target country.",
        action_required="Keep Ctrl-toggle/Shift-range selection and per-cell payload behavior covered by the multi-cell mission journey.",
    ),
    "Game_Over_Window/frmInner/btnMainMenu": _build_interaction_binding(
        reference="GEndGameWindow::OnMouseClick hides the end-game window and calls g_REFERENCEClient->StopGame().",
        surface="GameOverDialog.main_menu -> GameLayout._request_stop_game -> NavigationService.stop_game",
        effect="Queues local navigation to the main menu through the existing stop-game lifecycle; no GameAction is dispatched.",
        action="none (local session navigation; no GameAction)",
        status="verified_openpower",
        read_only_or_state_changing="local session navigation",
        validation="The dialog appears for victory, defeat, or draw when sandbox_continuation is false.",
        constraints="Sandbox continuation keeps the result out of the modal and leaves the campaign open.",
        mapping_notes="The local navigation route matches the source StopGame effect without inventing an authoritative campaign action.",
        action_required="Keep the Main Menu button routed through NavigationService.stop_game and covered by the terminal-result journey.",
    ),
    "Game_Over_Window/frmInner/frmObjectives/lstObjectives": _build_interaction_binding(
        reference=(
            "GEndGameWindow::AddObjective adds rows for completed or timed-out objectives with title, deadline, "
            "and reached/timeout status; the list has no row-selection callback."
        ),
        surface="GameOverDialog._render_objectives / CampaignPresenter",
        effect="Shows OpenPower campaign objective titles, deadline durations, and completed/failed/expired terminal statuses in the result dialog; rows are read-only.",
        action="none (read-only campaign objective display)",
        status="partial",
        validation="The dialog filters the current campaign to completed, failed, or expired objectives.",
        constraints="The list has no row-selection callback and dispatches no GameAction.",
        confirmation="none (read-only list)",
        mapping_notes="OpenPower uses campaign-native terminal states and deadline durations; source-localized status strings and exact deadline/result formulas remain unavailable.",
        action_required="Keep result rows grounded in OpenPower campaign state and retain explicit unavailable/source-difference notes for deadline and ranking semantics.",
    ),
    "Generic_Input_Window/edtAnswer": _build_interaction_binding(
        reference=(
            "GGenericInputWindow stores text in edtAnswer and passes its value to the caller's "
            "c_OnGenericInputWindowOk event when OK is pressed."
        ),
        surface="GenericInputDialog.render / multiplayer.input.answer",
        effect="Collects a local text or password draft and returns it to the request callback only after OK is pressed.",
        action="none on text edit (caller callback receives the value on OK)",
        status="verified_openpower",
        validation="The active input request supplies the prompt, initial value, and optional password masking.",
        constraints="The field itself does not submit a network or game action.",
        confirmation="The answer remains local until the dialog's OK control invokes the one-shot submit callback.",
        mapping_notes="The field uses the source GML edtAnswer rectangle; request-specific behavior remains with the caller.",
        action_required="Keep the field local and preserve caller-owned submit/cancel semantics.",
    ),
    "Join_Multiplayer_Game/frmTitle/btnExit": _multiplayer_workflow_interaction(
        reference="GJoinMPGameWindow::OnCreate hides the inherited title Exit control.",
        surface="MultiplayerConnectionWorkflowUnavailable",
        action_required="Keep the source-hidden title Exit absent and do not invent a multiplayer connection close action.",
    ),
    "Join_Multiplayer_Game/frmInner/tabGames/Tab1/lstServer": _multiplayer_workflow_interaction(
        reference="The source Internet server list selects a discovered server row for join and server-info actions.",
        surface="JoinMultiplayerWindow._render_content / Internet server list",
        action_required="Keep Internet server selection unavailable until OpenPower has a server-discovery and connection service.",
    ),
    "Join_Multiplayer_Game/frmInner/tabGames/Tab2/lstServer": _multiplayer_workflow_interaction(
        reference="The source LAN server list selects a discovered server row for join and server-info actions.",
        surface="JoinMultiplayerWindow._render_content / LAN server list",
        action_required="Keep LAN server selection unavailable until OpenPower has a LAN-discovery and connection service.",
    ),
    "Party_Selection_Window/frmInner/frmParties/lstParties": _build_interaction_binding(
        reference=(
            "GPartySelectionWindow::OnCustomEvent selects and highlights one party row, then enables Confirm; "
            "the party ID is sent to the caller only when Confirm is pressed."
        ),
        surface="PartySelectionWindow._render_content / new_game.party_selection.list",
        effect="Selects one country political-party row locally; Confirm returns its party_id to the new-game setup draft.",
        action="none on row selection (local party draft; new campaign action is sent later)",
        status="partial",
        validation="Only political-party rows for the selected country with a nonempty party_id are selectable.",
        constraints="The selected party is scoped to the country currently chosen in SinglePlayerSetupWindow.",
        confirmation="Selection remains local until Confirm; ActionStartCampaign is sent only after the remaining setup is valid.",
        error="If party data is absent, the list shows an empty state and Confirm remains disabled.",
        mapping_notes="OpenPower displays support share and defaults to the ruling or highest-support party; REFERENCE displays its approval field and applies its own party-list rules.",
        action_required="Keep country scoping and the local Confirm boundary; document the support-share versus source-approval presentation difference.",
    ),
    "Server_Info_Window/frmTitle/btnApply": _build_interaction_binding(
        reference=(
            "GServerInfoWindow delegates the title Apply click to GBaseWindow; the base Save implementation is empty, "
            "and the server-information fields are read-only."
        ),
        surface="ServerInfoWindow / WindowManager GML title controls",
        effect="No Apply control is exposed for the read-only server metadata view.",
        action="none (base Save is a no-op)",
        status="verified_unavailable",
        read_only_or_state_changing="inert source title control",
        action_required="Keep server metadata read-only and do not add an Apply action.",
    ),
    "Server_Info_Window/frmInner/frmInfo/togPassword": _build_interaction_binding(
        reference="GServerInfoWindow disables togPassword and sets its checked state from the selected server's password flag.",
        surface="ServerInfoWindow._render_content / read-only password indicator",
        effect="Draws a noninteractive password-required indicator from MultiplayerServerInfo.password_required.",
        action="none (read-only server metadata)",
        status="partial",
        validation="The source toggle is disabled; the OpenPower indicator is checked only when server metadata exists and requires a password.",
        constraints="No password value is exposed by this indicator.",
        mapping_notes="The Python view draws the GML toggle rectangle directly; server metadata remains unavailable in the current offline browser state.",
        action_required="Keep this indicator read-only and show a state only when backed by server metadata.",
    ),
    "Split_Group_Window/frmTitle/btnApply": _build_interaction_binding(
        reference="GGroupSplitWindow::OnMouseClick sends GEventGroupSplit with the selected group composition when CanSplit() is true.",
        surface="UnitReorganizationWindows._split / unit.split.apply",
        effect="Confirms the detached personnel quantity and sends ActionSplitUnit for the selected own unit.",
        action="ActionSplitUnit(player_id, unit_id, detached_strength)",
        status="partial",
        validation="The source split must leave positive personnel on both sides; OpenPower also requires an available stationary unit and a valid detached quantity.",
        constraints="The split is limited to a unit owned by the connected player.",
        confirmation="The quantity remains a local draft until the title Apply/OK control is pressed.",
        error="Unavailable or stale units cannot be split; authoritative rejection leaves the source unit unchanged.",
        mapping_notes="REFERENCE sends an explicit map of split group unit quantities; OpenPower's ActionSplitUnit splits one unit record by personnel strength and derives equipment proportionally.",
        action_required="Keep Apply as the split commit boundary and retain server-side ownership, availability, and quantity validation.",
    ),
    "Strategic_Missile_List_Window/frmInner/frmList/lstMissileList": _build_interaction_binding(
        reference="The source list hosts selectable missile rows; row toggles update the local selected-missile set until the list dialog is confirmed.",
        surface="StrategicPlanner._missiles / strategic.missiles.dialog",
        effect='Shows one selectable row per current-country strategic_weapons record in the source-sized GML list. Displays ready/quantity, the selected OpenPower payload profile yield in kt, and resolved origin and staged target region names. Selection remains local until Confirm.',
        action="none on list selection (local strategic launch draft)",
        status="partial",
        validation="Only systems returned by strategic_inventory_for_country for the plan's controlled country are listed.",
        constraints="The selected systems must pass ownership, readiness, authorization, range, and funding checks before launch.",
        confirmation="Selections are copied into the plan only when Confirm is pressed; launching remains a separate explicit action.",
        mapping_notes='OpenPower row fields use payload profile yield (kt), ready/quantity, origin region name, and staged target region name. The source C++ row aggregation and exact grouping remain unverified, so exact row parity is not claimed.',
        action_required='Keep the source-sized GML list and separate selection, confirmation, and launch phases; verify source row aggregation before claiming exact data parity.',
    ),
    "Strategic_Target_Multiple_Countries_Window/frmTitle/btnApply": _build_interaction_binding(
        reference=(
            "GStrategicTargetMultipleCountriesWindow::OnMouseClick does not call the base handler and has no Apply branch; "
            "the source title Apply control has no transition."
        ),
        surface="StrategicPlanner._multiple / GML title controls",
        effect="No generic title Apply control is exposed; the planner uses its explicit Prepare Launch and Launch actions.",
        action="none (no source title Apply transition)",
        status="verified_unavailable",
        read_only_or_state_changing="inert source title control",
        action_required="Keep Apply out of the planner and retain explicit launch confirmation.",
    ),
    "Strategic_Target_Multiple_Countries_Window/frmInner/frmList/lstAttackList": _build_interaction_binding(
        reference=(
            "The source dynamically fills lstAttackList with attack rows whose country/type selectors and missile meters "
            "update the local multi-target draft."
        ),
        surface="StrategicPlanner._multiple / strategic.target.multiple",
        effect="Renders a local weapon-and-target assignment list with per-system selection and target-region choices.",
        action="none on row selection (local multi-target draft)",
        status="partial",
        validation="Targets must remain foreign-owned and selected weapons must remain in the controlled country's strategic inventory.",
        constraints="Launch authorization and target-region eligibility are revalidated before ActionLaunchStrategicStrike is sent.",
        confirmation="Target and weapon assignments remain local until Prepare Launch, then require a separate Launch confirmation.",
        mapping_notes="OpenPower rows are keyed by weapon records and assign specific regions; the source rows are country/attack records with source missile-count meters.",
        action_required="Keep row assignments explicit and preserve launch-time validation; do not treat row selection as a launch request.",
    ),
    "Submenu_Multi/frmInner/btnLoad": _multiplayer_workflow_interaction(
        reference="GSubmenuMulti::OnCreate explicitly hides m_pObjLoad; the submenu click handler has no load branch.",
        surface="MultiplayerSubmenu / source-hidden control",
        action_required="Keep this source-hidden multiplayer submenu control unavailable; single-player LOAD GAME remains a separate route.",
    ),
    "Unit_List_Window_New/frmInner/frmList/frmAccuracy/btnUnfilled": _build_interaction_binding(
        reference="GUnitListWindowNew binds frmAccuracy as a read-only GGradientBar populated from AccuracyInformation(country_id).",
        surface="UnitListPanel._render_accuracy / GML accuracy meter",
        effect="Renders the aggregate confidence meter for foreign-force estimates; the unfilled segment has no independent input behavior.",
        action="none (read-only intelligence-confidence meter)",
        status="partial",
        validation="The source and OpenPower fragments are presentation-only; OpenPower displays an unknown state when no authorized estimate exists.",
        constraints="The meter is shown only for a foreign-country roster; individual foreign unit rows remain redacted.",
        mapping_notes="The source uses country AccuracyInformation; OpenPower averages confidence from current foreign-force estimate rows, so the metric is not numerically equivalent.",
        action_required="Keep both fragments noninteractive and label the OpenPower value as aggregate estimate confidence.",
        read_only_or_state_changing="read-only intelligence-confidence presentation",
    ),
    "Unit_List_Window_New/frmInner/frmList/frmAccuracy/btnFill": _build_interaction_binding(
        reference="GUnitListWindowNew binds frmAccuracy as a read-only GGradientBar populated from AccuracyInformation(country_id).",
        surface="UnitListPanel._render_accuracy / GML accuracy meter",
        effect="Renders the filled portion of the aggregate foreign-force confidence meter; it is not a user button.",
        action="none (read-only intelligence-confidence meter)",
        status="partial",
        validation="The source and OpenPower fragments are presentation-only; OpenPower displays an unknown state when no authorized estimate exists.",
        constraints="The meter is shown only for a foreign-country roster; individual foreign unit rows remain redacted.",
        mapping_notes="The source uses country AccuracyInformation; OpenPower averages confidence from current foreign-force estimate rows, so the metric is not numerically equivalent.",
        action_required="Keep both fragments noninteractive and label the OpenPower value as aggregate estimate confidence.",
        read_only_or_state_changing="read-only intelligence-confidence presentation",
    ),
    "Unit_Movement_Denial/lstDenialList": _build_interaction_binding(
        reference=(
            "GUnitMovementDenialWindow attaches lstDenialList but the supplied class has no row callback or list-population call; "
            "only btnClose is handled."
        ),
        surface="UnitOrderFeedback / GenericMessageDialog active movement-refusal route",
        effect=(
            "Groups each new local rejected movement batch by authoritative reason and displays a one-shot count notice; "
            "the source list has no row-population method or external spawn caller."
        ),
        action="none (read-only movement-refusal feedback)",
        status="verified_openpower",
        validation="Only rejected move and naval_invasion records owned by the local player produce notices.",
        constraints="Foreign-player refusal records are not shown to the local player.",
        confirmation="Not applicable; the notice reports a completed refusal and does not retry the order.",
        error="Unavailable refusal reasons use a generic movement-order message; each feedback record is shown at most once while present in the rolling table.",
        mapping_notes="The source mirror declares the list widget but contains no population path; OpenPower surfaces authoritative refusal records through a shared notice dialog.",
        action_required="Retain the verified active generic notice route; no Python list window is required for an unspawned source object.",
        read_only_or_state_changing="read-only movement refusal feedback",
    ),
}


MILITARY_STRATEGIC_RESEARCH_INTERACTION_BINDINGS = {
    "Military_Window/frmInner/frmStrategicWeapons/btnResearch": {
        "reference_side_effect": (
            "The source raises GMilitaryMainUpdate with StartAmdsResearch=true for the controlled country; "
            "the advisor checks affordability and requires confirmation before starting AMDS research."
        ),
        "openpower_surface": "MilitaryPanel strategic RESEARCH slot -> UnitResearchPanel",
        "openpower_effect": (
            "The button opens UnitResearchPanel, where research funding can be changed. It does not start the source AMDS program."
        ),
        "game_action": "none on click (opens UnitResearchPanel); funding Apply separately sends ActionUpdateResearchFunding",
        "read_only_or_state_changing": "local research navigation; funding changes are a separate authoritative action",
        "validation_condition": "The RESEARCH navigation is enabled for the player's country; funding Apply is validated by the research system.",
        "country_scope_restriction": "Research funding is limited to the player's country.",
        "confirmation_state": "REFERENCE confirms the AMDS expense; OpenPower only opens the research panel and uses its funding draft/apply flow.",
        "error_state": "No AMDS-start request is sent; rejected research-funding actions use the research panel's command feedback.",
        "restrictions_confirmation_error": (
            "The source event starts a costed, timed AMDS program. OpenPower's research-funding ratio and branch progress are not that program, "
            "so ActionUpdateResearchFunding is not a direct event mapping."
        ),
        "action_required": (
            "Keep the research-panel navigation covered and preserve the AMDS-start gap until OpenPower has matching program state, "
            "cost/time rules, and an authoritative start action."
        ),
        "status": "partial",
    },
    "Military_Window/frmInner/frmStrategicWeapons/btnNuclearProgram": {
        "reference_side_effect": (
            "The source raises GMilitaryMainUpdate with StartNuclearResearch=true for the controlled country; "
            "the advisor checks affordability and requires confirmation before starting nuclear research."
        ),
        "openpower_surface": "MilitaryPanel strategic forces summary",
        "openpower_effect": "No equivalent nuclear research-start control or action is exposed.",
        "game_action": "none (no OpenPower nuclear research-start action)",
        "read_only_or_state_changing": "unavailable source program action",
        "validation_condition": "No matching OpenPower action accepts a nuclear-research start request.",
        "country_scope_restriction": "The source uses the controlled country; the OpenPower strategic inventory has no corresponding research program state.",
        "confirmation_state": "REFERENCE confirms the nuclear research expense; OpenPower has no corresponding request to confirm.",
        "error_state": "No action is dispatched because the program is not modeled.",
        "restrictions_confirmation_error": (
            "OpenPower strategic weapon production, missile-defense layers, and research-funding ratios do not model the source's "
            "costed, timed nuclear research program."
        ),
        "action_required": (
            "Keep this source program explicitly unavailable until OpenPower has authoritative nuclear research state, "
            "cost/time rules, and a matching start action."
        ),
        "status": "verified_unavailable",
    },
}


def _military_navigation_interaction(
    *, reference: str, effect: str, destination: str, journey: str,
) -> dict[str, str]:
    return {
        "reference_side_effect": reference,
        "openpower_surface": "MilitaryPanel._render_actions / GameLayout panel navigation",
        "openpower_effect": effect,
        "game_action": "none (local panel navigation)",
        "read_only_or_state_changing": "local UI navigation",
        "validation_condition": "The game HUD is active; destination actions validate their own current state and authority.",
        "country_scope_restriction": "No persistent state changes on navigation; destination actions enforce country scope.",
        "confirmation_state": "No confirmation is required to open the destination.",
        "error_state": "No GameAction is sent by the navigation click.",
        "restrictions_confirmation_error": f"The tested OpenPower destination is {destination}; the route is covered by {journey}.",
        "action_required": f"Keep this source slot bound to {destination} and preserve the tested navigation route.",
        "status": "verified_openpower",
    }


MILITARY_NAVIGATION_INTERACTION_BINDINGS = {
    "Military_Window/frmInner/btnCovertActions": _military_navigation_interaction(
        reference="The source opens or raises Covert_Actions_Window.",
        effect="Opens the OpenPower covert-operations panel.",
        destination="CovertOpsPanel",
        journey="tests/ui/journeys/reference-military-covert.json",
    ),
    "Military_Window/frmInner/frmConventionalWarfare/btnConventionalForcesMore": _military_navigation_interaction(
        reference="The source opens Unit_List_Window_New for the conventional-force list.",
        effect="Opens UnitListPanel with the live own-unit roster or authorized foreign aggregate estimates.",
        destination="UnitListPanel",
        journey="tests/ui/journeys/reference-military-unit-list.json",
    ),
    "Military_Window/frmInner/frmConventionalWarfare/btnBuild": _military_navigation_interaction(
        reference="The source opens Unit_Production_Window for conventional production.",
        effect="Opens UnitProductionPanel with the conventional production category selected.",
        destination="UnitProductionPanel",
        journey="tests/ui/journeys/reference-military-production.json",
    ),
    "Military_Window/frmInner/frmConventionalWarfare/btnDesign": _military_navigation_interaction(
        reference="The source opens Unit_Design_New.",
        effect="Opens UnitDesignPanel for the current country's saved designs.",
        destination="UnitDesignPanel",
        journey="tests/ui/journeys/reference-military-design.json",
    ),
    "Military_Window/frmInner/frmConventionalWarfare/btnBuy": _military_navigation_interaction(
        reference="The source opens Unit_Buy_Used_Window.",
        effect="Opens UnitMarketPanel with available used-unit listings.",
        destination="UnitMarketPanel",
        journey="tests/ui/journeys/reference-military-market.json",
    ),
    "Military_Window/frmInner/frmConventionalWarfare/btnResearch": _military_navigation_interaction(
        reference="The source opens Unit_Research_Window.",
        effect="Opens UnitResearchPanel with branch funding and research details.",
        destination="UnitResearchPanel",
        journey="tests/ui/journeys/reference-military-research.json",
    ),
    "Military_Window/frmInner/frmConventionalWarfare/btnDeploy": _military_navigation_interaction(
        reference="The source opens Unit_Ground_Deployment_Window.",
        effect="Opens UnitReservesPanel with the current country's reserve and deployment rows.",
        destination="UnitReservesPanel",
        journey="tests/ui/journeys/reference-military-reserves.json",
    ),
    "Military_Window/frmInner/btnStrategicWarfare": _military_navigation_interaction(
        reference="The source toggles Strategic_Warfare visibility for the active country.",
        effect="Opens or raises StrategicWarfarePanel for the current country.",
        destination="StrategicWarfarePanel",
        journey="tests/ui/journeys/reference-military-strategic-warfare.json",
    ),
    "Military_Window/frmInner/btnWarList": _military_navigation_interaction(
        reference="The source opens or raises War_List_Window.",
        effect="Opens WarListPanel with the current wars and diplomacy controls.",
        destination="WarListPanel",
        journey="tests/ui/journeys/reference-military-war-list.json",
    ),
    "Military_Window/frmInner/frmStrategicWeapons/btnBuild": _military_navigation_interaction(
        reference="The source opens Unit_Production_Window with the Nuclear category selected.",
        effect="Opens UnitProductionPanel with strategic production selected.",
        destination="UnitProductionPanel strategic production category",
        journey="tests/ui/journeys/reference-military-strategic-production.json",
    ),
}


def _military_progress_meter_interaction(
    *, reference: str, effect: str, mapping_notes: str, action_required: str,
) -> dict[str, str]:
    return {
        "reference_side_effect": reference,
        "openpower_surface": "MilitaryPanel strategic forces display",
        "openpower_effect": effect,
        "game_action": "none (read-only progress meter component)",
        "read_only_or_state_changing": "read-only visual meter",
        "validation_condition": "The meter is informational and has no click callback.",
        "country_scope_restriction": "The parent values are shown from the current military summary.",
        "confirmation_state": "None.",
        "error_state": "No action is dispatched.",
        "restrictions_confirmation_error": mapping_notes,
        "action_required": action_required,
        "status": "partial",
    }


MILITARY_PROGRESS_METER_INTERACTION_BINDINGS = {}
for _part in ("btnUnfilled", "btnFill"):
    MILITARY_PROGRESS_METER_INTERACTION_BINDINGS[
        f"Military_Window/frmInner/frmStrategicWeapons/frmNuclearProgress/{_part}"
    ] = _military_progress_meter_interaction(
        reference="The source strategic-force readiness meter child is a visual component and has no click handler.",
        effect="OpenPower displays ready/total strategic-unit counts in the parent slot instead of the source progress meter.",
        mapping_notes="Strategic-unit readiness counts do not represent REFERENCE nuclear-program research progress.",
        action_required="Keep the OpenPower ready/total value explicit and do not present it as nuclear research progress.",
    )
    MILITARY_PROGRESS_METER_INTERACTION_BINDINGS[
        f"Military_Window/frmInner/frmStrategicWeapons/frmAmdsProgress/{_part}"
    ] = _military_progress_meter_interaction(
        reference="The source AMDS research progress meter child is a visual component and has no click handler.",
        effect="OpenPower renders a missile-defense coverage meter from its fielded defense layers.",
        mapping_notes="The OpenPower coverage percentage is an operational defense estimate, not the source AMDS research program's completion progress.",
        action_required="Keep the meter labeled as OpenPower coverage; do not claim AMDS research-progress parity.",
    )


MILITARY_TITLE_INTERACTION_BINDINGS = {
    "Military_Window/frmTitle/btnExit": {
        "reference_side_effect": "GBaseWindow::ExitWindow closes Military_Window without applying a game action.",
        "openpower_surface": "MilitaryPanel native title-bar close",
        "openpower_effect": "Closes the Military panel without sending a GameAction.",
        "game_action": "none (local panel close)",
        "read_only_or_state_changing": "local UI navigation",
        "validation_condition": "The Military panel is open.",
        "country_scope_restriction": "None.",
        "confirmation_state": "No pending panel draft; closing needs no confirmation.",
        "error_state": "None.",
        "restrictions_confirmation_error": "The Military summary has no local state to apply or discard.",
        "action_required": "Keep title close local and independent from military actions.",
        "status": "verified_openpower",
    },
    "Military_Window/frmTitle/btnApply": {
        "reference_side_effect": "GMilitaryWindow::OnCreate hides m_pObjApplyBtn; it is not a visible military-action control.",
        "openpower_surface": "MilitaryPanel / GML title-bar rules",
        "openpower_effect": "The hidden title Apply control is omitted; military changes are made from their destination panels.",
        "game_action": "none (hidden source title control)",
        "read_only_or_state_changing": "hidden local title control",
        "validation_condition": "The source hides the control during window initialization.",
        "country_scope_restriction": "None.",
        "confirmation_state": "None.",
        "error_state": "None.",
        "restrictions_confirmation_error": "Do not add a panel-wide Apply action that bypasses each destination panel's own confirmation and validation.",
        "action_required": "Keep the hidden title Apply control absent.",
        "status": "verified_openpower",
    },
}


SYSTEM_BAR_INTERACTION_BINDINGS = {
    "System_Bar_Window/btnF1": {
        "reference_side_effect": (
            "The source forwards VK_F1 to GClient::OnGlobalHotkey, then displays the button's tooltip text; "
            "the supplied OnGlobalHotkey implementation has no F1 branch."
        ),
        "openpower_surface": "GameLayout/SystemBar -> TOOLTIP_HELP",
        "openpower_effect": "Opens a read-only help panel describing current HUD controls and shortcuts.",
        "game_action": "none (read-only help)",
        "read_only_or_state_changing": "read-only local UI",
        "validation_condition": "The game HUD is active.",
        "country_scope_restriction": "None.",
        "confirmation_state": "None.",
        "error_state": "No action is dispatched.",
        "restrictions_confirmation_error": "OpenPower help text supplements the source tooltip; the source localization and help resources are absent.",
        "action_required": "Keep the help route identified as OpenPower-authored; restore exact source text only when the resource is available.",
        "status": "partial",
    },
    "System_Bar_Window/btnF2": {
        "reference_side_effect": "The source opens or hides GameLobby ChatRoom for multiplayer sessions while Playing; OnShow disables this button in single-player and scenario sessions.",
        "openpower_surface": "GameLayout/SystemBar F2 slot",
        "openpower_effect": "Displays the source F2 Chat slot disabled because OpenPower has no multiplayer lobby.",
        "game_action": "none (unsupported multiplayer lobby workflow)",
        "read_only_or_state_changing": "unavailable source workflow",
        "validation_condition": "The source route is multiplayer-only; OpenPower currently has no multiplayer game session.",
        "country_scope_restriction": "None.",
        "confirmation_state": "No chat window can be opened.",
        "error_state": "No action is dispatched.",
        "restrictions_confirmation_error": "The disabled source slot remains visible in its GML position.",
        "action_required": "Keep F2 disabled until an authoritative multiplayer lobby workflow exists.",
        "status": "verified_unavailable",
    },
    "System_Bar_Window/btnF3": {
        "reference_side_effect": "The source sends VK_F3 and toggles the Save_Game_Window in supported active game types.",
        "openpower_surface": "GameLayout/SaveGameDialog",
        "openpower_effect": "Opens or closes the save dialog; confirming a name dispatches ActionSaveGame and command feedback reports the result.",
        "game_action": "ActionSaveGame after explicit save confirmation",
        "read_only_or_state_changing": "window navigation, then authoritative save request on confirmation",
        "validation_condition": "The game HUD is active; save name validation and persistence are handled by the save dialog and game service.",
        "country_scope_restriction": "Uses the active local game session.",
        "confirmation_state": "The shortcut opens the dialog; the player confirms by submitting a save name.",
        "error_state": "Rejected save results are shown by CommandFeedback in GenericMessageDialog.",
        "restrictions_confirmation_error": "OpenPower's current game modes expose the local save route; multiplayer role limits from REFERENCE are not modeled.",
        "action_required": "Keep F3 dialog visibility and the confirmed server save outcome covered by the save journey.",
        "status": "verified_openpower",
    },
    "System_Bar_Window/btnF4": {
        "reference_side_effect": "The source sends VK_F4 and toggles Load_Game_Window for single-player or scenario play while Playing.",
        "openpower_surface": "GameLayout/SaveGameDialog load mode",
        "openpower_effect": "Opens or closes the load selection dialog; selecting a save follows the active navigation load route.",
        "game_action": "load_saved_game navigation task",
        "read_only_or_state_changing": "window navigation, then game-session replacement on selected load",
        "validation_condition": "The game HUD is active; only listed saves can be selected.",
        "country_scope_restriction": "Uses the active local game configuration.",
        "confirmation_state": "The shortcut only opens the dialog; choosing a save starts the load task.",
        "error_state": "Load failures are shown by LoadingView with the recoverable exception details.",
        "restrictions_confirmation_error": "The multiplayer load restriction from REFERENCE is inapplicable because OpenPower has no multiplayer load route.",
        "action_required": "Keep F4 dialog visibility and recoverable load outcomes covered by the load journeys.",
        "status": "verified_openpower",
    },
    "System_Bar_Window/btnF5": {
        "reference_side_effect": "The source sends VK_F5 and toggles Objectives_Window while the game is Playing.",
        "openpower_surface": "GameLayout/OBJECTIVES panel",
        "openpower_effect": "Toggles the current scenario objectives panel.",
        "game_action": "none (local panel visibility)",
        "read_only_or_state_changing": "local UI navigation",
        "validation_condition": "The game HUD is active; objectives are populated from the active scenario.",
        "country_scope_restriction": "None.",
        "confirmation_state": "None.",
        "error_state": "No action is dispatched.",
        "restrictions_confirmation_error": "The source objectives refresh call is represented by the current scenario-backed panel render.",
        "action_required": "Keep F5 button and keyboard visibility toggles covered by the system-bar journey.",
        "status": "verified_openpower",
    },
    "System_Bar_Window/btnF10": {
        "reference_side_effect": "The source sends VK_F10 and shows or hides GMainMenu unless a load, connection, or movie state is active.",
        "openpower_surface": "GameLayout/MainMenuContent in-game overlay",
        "openpower_effect": "Toggles the resumable 273x223 in-game menu overlay with the active-game source button slots.",
        "game_action": "none (local menu visibility)",
        "read_only_or_state_changing": "local UI navigation",
        "validation_condition": "The shortcut is available while GameLayout is active; loading, connection, and movie states have no game HUD.",
        "country_scope_restriction": "None.",
        "confirmation_state": "None; Return to Game closes the overlay.",
        "error_state": "No action is dispatched by opening or closing the overlay.",
        "restrictions_confirmation_error": "Restart and Stop remain disabled because OpenPower has no authoritative matching actions; source menu geometry and the resumable route are verified.",
        "action_required": "Keep active-game GML geometry and button/key toggle journeys passing at all supported viewports.",
        "status": "verified_openpower",
    },
    "System_Bar_Window/togMain": {
        "reference_side_effect": "GSystemBarWindow animates the source bar between its full width and a 36-pixel exposed toggle slot.",
        "openpower_surface": "GameLayout/SystemBar._render_toggle",
        "openpower_effect": "Slides between the full 577-pixel bar and the 36-pixel collapsed slot at the right viewport edge.",
        "game_action": "none (local HUD layout)",
        "read_only_or_state_changing": "local UI layout state",
        "validation_condition": "The game HUD is active.",
        "country_scope_restriction": "None.",
        "confirmation_state": "None.",
        "error_state": "No action is dispatched.",
        "restrictions_confirmation_error": "The source holds position for 0.26 seconds and then moves linearly for 0.5 seconds; GMLSlideTransition mirrors both timings.",
        "action_required": "Keep source timing, full/collapsed widths, right-edge anchoring, and reversal while in motion covered.",
        "status": "verified_openpower",
    },
}

MINI_MAP_INTERACTION_BINDINGS = {
    "Mini_Map/togMagnifier": {
        "openpower_surface": "GameLayout/MiniMapPanel/mini_map.magnifier",
        "openpower_effect": "Toggles ViewportController.show_all_units, which controls whether unit icons are shown globally.",
        "game_action": "none (local map presentation state)",
        "read_only_or_state_changing": "local viewport presentation state",
        "validation_condition": "The in-game HUD and region map are active.",
        "country_scope_restriction": "None; this changes which unit icons the client displays.",
        "confirmation_state": "Immediate toggle; no confirmation dialog.",
        "error_state": "No authoritative game action is sent.",
        "restrictions_confirmation_error": "OpenPower's unit-visibility flag drives the magnifier state; source icon art is replaced by a drawn magnifier glyph.",
        "action_required": "Keep the GML toggle slot and global unit-visibility state synchronized.",
        "status": "verified_openpower",
    },
    "Mini_Map/btnZoomRect": {
        "openpower_surface": "GameLayout/MiniMapPanel/mini_map.zoom",
        "openpower_effect": "Maps the vertical GML track position to normalized zoom and updates the active globe or planar camera.",
        "game_action": "none (local camera zoom)",
        "read_only_or_state_changing": "local viewport camera state",
        "validation_condition": "The in-game HUD and region map are active; zoom is clamped to the camera range.",
        "country_scope_restriction": "None.",
        "confirmation_state": "Immediate track or drag update; no confirmation dialog.",
        "error_state": "No authoritative game action is sent.",
        "restrictions_confirmation_error": "Zoom is represented by one GML track hit target and normalized across globe and planar projections.",
        "action_required": "Keep zoom bounded to the active camera's supported range.",
        "status": "verified_openpower",
    },
    "Mini_Map/frmMap/btnMap": {
        "openpower_surface": "GameLayout/MiniMapPanel/mini_map.map",
        "openpower_effect": "Clicking or dragging the map recenters the active viewport without changing country or region selection.",
        "game_action": "none (local camera focus)",
        "read_only_or_state_changing": "local viewport camera state",
        "validation_condition": "The region map is loaded; pointer coordinates are clamped to its normalized bounds.",
        "country_scope_restriction": "None.",
        "confirmation_state": "Immediate map focus; no confirmation dialog.",
        "error_state": "The panel is omitted until map data is available.",
        "restrictions_confirmation_error": "The crosshair is a visual camera-center marker; the map's full source hit area also handles dragging from the marker.",
        "action_required": "Keep map coordinates normalized and do not dispatch a selection action from a focus click.",
        "status": "verified_openpower",
    },
    "Mini_Map/frmMap/btnCrosshair": {
        "openpower_surface": "GameLayout/MiniMapPanel map-center marker",
        "openpower_effect": "Displays the current camera center; dragging the overlaid map hit target moves the same marker and camera focus.",
        "game_action": "none (local camera focus indicator)",
        "read_only_or_state_changing": "map-center indicator; drag delegates to the map hit target",
        "validation_condition": "Visible only while the map data and mini-map panel are available.",
        "country_scope_restriction": "None.",
        "confirmation_state": "No independent confirmation.",
        "error_state": "No authoritative game action is sent.",
        "restrictions_confirmation_error": "The marker follows camera state rather than maintaining separate crosshair state.",
        "action_required": "Keep the crosshair aligned with the camera center after map or Home focus changes.",
        "status": "partial",
    },
    "Mini_Map/btnHome": {
        "openpower_surface": "GameLayout/MiniMapPanel/mini_map.home",
        "openpower_effect": "Focuses and selects the controlled player's country through ViewportController.focus_on_country.",
        "game_action": "none (local country selection and camera focus)",
        "read_only_or_state_changing": "local selection and viewport state",
        "validation_condition": "The controlled country must have visible regions; ViewportController handles an absent country without sending a game action.",
        "country_scope_restriction": "Always targets the local player's country.",
        "confirmation_state": "Immediate focus; no confirmation dialog.",
        "error_state": "No authoritative game action is sent.",
        "restrictions_confirmation_error": "Uses OpenPower's controlled-country selection and focus behavior.",
        "action_required": "Keep Home targeting the local player instead of the currently selected foreign country.",
        "status": "verified_openpower",
    },
    "Mini_Map/btnHiding": {
        "openpower_surface": "GameLayout/MiniMapPanel zoom-track fill",
        "openpower_effect": "Draws the source zoom fill/hidden portion from the current normalized camera zoom; dragging is handled by btnZoomRect.",
        "game_action": "none (zoom track visual)",
        "read_only_or_state_changing": "read-only view of local camera state",
        "validation_condition": "The in-game HUD and region map are active.",
        "country_scope_restriction": "None.",
        "confirmation_state": "None.",
        "error_state": "No authoritative game action is sent.",
        "restrictions_confirmation_error": "OpenPower draws the fill dynamically because the GML object is a source skin element.",
        "action_required": "Keep the fill height synchronized with the normalized zoom value.",
        "status": "partial",
    },
    "Mini_Map/btnZoom": {
        "openpower_surface": "GameLayout/MiniMapPanel zoom rail",
        "openpower_effect": "Displays the full GML zoom rail; the overlaid btnZoomRect owns the pointer hit target.",
        "game_action": "none (zoom track visual)",
        "read_only_or_state_changing": "read-only view of local camera state",
        "validation_condition": "The in-game HUD and region map are active.",
        "country_scope_restriction": "None.",
        "confirmation_state": "None.",
        "error_state": "No authoritative game action is sent.",
        "restrictions_confirmation_error": "The source track and thumb occupy the same GML rectangle; one pointer target prevents overlapping hitboxes.",
        "action_required": "Keep the source track rectangle and separate pointer target aligned.",
        "status": "partial",
    },
}

TUTORIAL_MENU_INTERACTION_BINDINGS = {
    "Submenu_Single/frmInner/btnTutorial1": {
        "reference_side_effect": "Starts GTutorials::InterfaceTutorial, a stateful walkthrough that points to controls and opens panels as the player advances.",
        "openpower_surface": "MainMenuContent/TutorialGuideContent.interface",
        "openpower_effect": "Opens the tested 11-step OpenPower interface guide. Its menu preview provides read-only instructions.",
        "game_action": "none (read-only local guide)",
        "read_only_or_state_changing": "local UI navigation",
        "validation_condition": "The Singleplayer submenu is open; the guide begins at step 1 and can be navigated or closed.",
        "country_scope_restriction": "None.",
        "confirmation_state": "None.",
        "error_state": "No game action is dispatched.",
        "restrictions_confirmation_error": "The guide documents OpenPower controls and does not reproduce the source tutorial's event-gated progression or automatic panel openings.",
        "action_required": "Keep the local guide journey passing. Exact source progression requires a compatible tutorial scenario and its event-gated gameplay state.",
        "status": "partial",
    },
    "Submenu_Single/frmInner/btnTutorial2": {
        "reference_side_effect": "Starts GTutorials::MilitaryTutorial, which depends on a fixed country, unit group, battle and military assets to gate its steps.",
        "openpower_surface": "MainMenuContent/TutorialGuideContent.military",
        "openpower_effect": "Opens the tested 8-step OpenPower military guide. It describes supported panels and leaves unavailable source-only actions explicit.",
        "game_action": "none (read-only local guide)",
        "read_only_or_state_changing": "local UI navigation",
        "validation_condition": "The Singleplayer submenu is open; the guide begins at step 1 and can be navigated or closed.",
        "country_scope_restriction": "None.",
        "confirmation_state": "None.",
        "error_state": "No game action is dispatched.",
        "restrictions_confirmation_error": "OpenPower has no matching scripted tutorial battle/setup data; the guide does not invent units, countries or battle outcomes.",
        "action_required": "Keep the local guide journey passing. A source-equivalent tutorial requires an authoritative tutorial scenario and its fixed military fixtures.",
        "status": "partial",
    },
}

UNIT_MARKET_INTERACTION_BINDINGS = {}
for _metric in _UNIT_RESEARCH_METRICS:
    for _part in ("btnFill", "btnUnfilled"):
        UNIT_MARKET_INTERACTION_BINDINGS[
            f"Unit_Buy_Used_Window/frmDesignView/frmUnitSpecs/frmList/frmInner/frm{_metric}/{_part}"
        ] = _unit_market_interaction(
            reference="The owning GTechnologyMeterBlue is updated with the selected unit design and then disabled by GUsedUnitWindow::EnableMeters(false).",
            surface="UnitMarketPanel._render_capabilities",
            effect="Read-only OpenPower capability display; neither meter fragment changes a design or sends an action.",
            action="none (read-only source meter fragment)",
            status="verified_unavailable",
            validation="The source disables all used-unit capability meters after loading a design; OpenPower renders saved design capability fields as read-only progress values.",
            constraints="None; the meter is informational.",
            error="N/A is shown for missing fields and for combined speed/maneuverability, which OpenPower does not store as one value.",
            mapping_notes="The source has a 0-10 meter range; OpenPower capability bounds and units are role-specific and are not generally scale-equivalent.",
            action_required="Keep source fill/track fragments read-only; do not turn them into capability-edit controls in the used-unit market.",
        )

UNIT_MARKET_INTERACTION_BINDINGS.update({
    "Unit_Buy_Used_Window/frmBorder/frmTitle/btnExit": _unit_market_interaction(
        reference="The source titlebar exit hides GUsedUnitWindow.",
        surface="UnitMarketPanel.render / WindowManager title close",
        effect="Closes the used-unit market window.",
        action="none (local window close)",
        validation="The market window is visible.",
        action_required="Keep the GML title close control available and send no purchase action when closing.",
    ),
    "Unit_Buy_Used_Window/frmBorder/frmInner/frmDesignList/cboUnitType": _unit_market_interaction(
        reference="BuildUnitDesignCbo selects an REFERENCE unit type and rebuilds the associated unit list.",
        surface="UnitMarketPanel._render_type_selector",
        effect="Selects a canonical OpenPower class_name role and filters the current country-eligible listings.",
        status="partial",
        validation="Only roles represented by eligible OpenPower listings are selectable; an empty role set disables the combo.",
        constraints="Filtering uses the currently selected country; only the player's own country may submit a purchase.",
        error="Empty listing data displays No eligible unit types and does not expose a purchase.",
        mapping_notes="The selector preserves all 20 source type IDs/order and maps each to a canonical OpenPower role; source localization bundles are unavailable. OpenPower-only roles remain explicitly labeled extensions.",
        action_required="Keep the source-ID mapping tied to eligible listings and retain explicit localization/extension labels.",
    ),
    "Unit_Buy_Used_Window/frmBorder/frmInner/frmDesignList/lstUnits": _unit_market_interaction(
        reference="BuildUnitDesignLstFromId selects a for-sale foreign unit and updates the details view.",
        surface="UnitMarketPanel._render_listing_list",
        effect="Selects an OpenPower listing locally and updates its design, seller, price, capability values and available quantity.",
        status="partial",
        validation="Only listed positive-quantity records eligible under current OpenPower weapons-trade rules are shown.",
        constraints="The selected country's listing view is filtered by that country's trade permissions; purchase is own-country only.",
        error="No visible listing shows an explicit empty state; stale or unavailable listing purchases are rejected by the military system.",
        mapping_notes="OpenPower selects market listing IDs and stored listing quantities; the source list is keyed by unit IDs and source unit-type IDs.",
        action_required="Keep listing selection linked to the current market snapshot and preserve the source row geometry.",
    ),
    "Unit_Buy_Used_Window/frmBorder/frmInner/frmDesignList/btnBuy": _unit_market_interaction(
        reference="GUsedUnitWindow::OnMouseClick calls BuySelectedUnit for the selected unit and quantity.",
        surface="UnitMarketPanel._render_selection",
        effect="Sends the selected listing ID, buyer country and bounded quantity to ActionBuyMarketUnit.",
        action="ActionBuyMarketUnit(player_id, listing_id, buyer_country_tag, quantity)",
        status="partial",
        validation="Enabled for the own country with a connection, selected active listing and valid quantity. The server rechecks authority, listing state/quantity, demilitarization, trade permission, funds, source unit and transfer route.",
        constraints="Purchasing country must be controlled by the issuing player; source/destination may also be rejected by trade and movement-access rules.",
        confirmation="The request is sent once per selection; the UI shows REQUEST SENT while the server validates it.",
        error="A rejected authoritative request does not transfer units; not every server-side purchase rejection currently produces panel-specific feedback.",
        mapping_notes="OpenPower charges listing.price and processes a transfer route; REFERENCE computes design cost multiplied by its used-unit rebate and sends GTransfertUnit.",
        action_required="Keep the action fields exact and server-authoritative; preserve the explicit pricing/feedback differences until the purchase contract is unified.",
    ),
    "Unit_Buy_Used_Window/frmBorder/frmInner/frmDesignList/edtUnitName": _unit_market_interaction(
        reference="GUsedUnitWindow binds this source field to GLabel and displays the selected unit owner's country name.",
        surface="UnitMarketPanel._render_selection / _render_value_field",
        effect="Shows the selected listing's seller country as a read-only source-slot value.",
        action="none (read-only display)",
        validation="A selected listing is required for a seller value.",
        error="Em dash when no listing is selected; seller tag is used when no country name is present.",
        action_required="Keep the seller value read-only and resolve it from the selected listing's seller country.",
    ),
    "Unit_Buy_Used_Window/frmBorder/frmInner/frmDesignList/edtUnitName1": _unit_market_interaction(
        reference="GUsedUnitWindow binds this source field to GLabel and displays the selected design's used-unit price.",
        surface="UnitMarketPanel._render_selection / _render_value_field",
        effect="Shows the selected OpenPower listing's per-unit price as a read-only value.",
        action="none (read-only display)",
        status="partial",
        validation="A selected listing is required for a price value.",
        error="Em dash when no listing is selected.",
        mapping_notes="OpenPower uses listing.price; REFERENCE uses GUnitDesign::Cost multiplied by c_fUsedUnitsRebates.",
        action_required="Keep the price source explicit and avoid deriving an REFERENCE rebate from unrelated listing values.",
    ),
    "Unit_Buy_Used_Window/frmBorder/frmInner/frmDesignList/edtUnitName2": _unit_market_interaction(
        reference="GUsedUnitWindow binds this source field to GLabel and displays selected quantity multiplied by the rebated design cost.",
        surface="UnitMarketPanel._render_selection / _render_value_field",
        effect="Shows selected listing.price multiplied by the local quantity as a read-only total.",
        action="none (read-only display)",
        status="partial",
        validation="Recomputed from the selected listing and bounded quantity.",
        error="Em dash when no listing is selected.",
        mapping_notes="The total follows OpenPower listing price; it does not apply the REFERENCE used-unit rebate.",
        action_required="Keep the displayed total equal to the amount the ActionBuyMarketUnit server handler validates.",
    ),
    "Unit_Buy_Used_Window/frmDesignView/frmUnitName/edtUnitName": _unit_market_interaction(
        reference="GUsedUnitWindow binds this source field to GLabel and writes the selected design name.",
        surface="UnitMarketPanel._render_selection / _render_value_field",
        effect="Shows the selected listing's unit-design name as a read-only source-slot value.",
        action="none (read-only display)",
        validation="A selected listing with a saved design row is required.",
        error="Em dash when no design name is available.",
        action_required="Keep the design label synchronized with the selected listing's design ID.",
    ),
    "Unit_Buy_Used_Window/frmBorder/frmInner/frmDesignList/frmUpdatableValue1/edtText": _unit_market_interaction(
        reference="GUpdatableValue edits the purchase quantity; GUsedUnitWindow updates the selected-unit total when the value changes.",
        surface="UnitMarketPanel._render_quantity",
        effect="Edits the local purchase quantity within 1..the current listing quantity and recomputes the total price.",
        status="verified_openpower",
        validation="The quantity is clamped to the active listing's available units; the source disables it without a selection.",
        constraints="Local draft only; server rechecks current listing quantity and purchase authority.",
        error="Unavailable listing disables the field; invalid typed values are clamped to the current available range.",
        mapping_notes="Only digit characters are accepted. Focus removes grouping; blur, Enter, and Escape commit and restore three-digit space grouping. The 1..available clamp is verified by the quantity-editor journey.",
        action_required="Keep digit filtering, source commit keys, focus/blur formatting, and live-listing bounds covered by the quantity-editor journey.",
    ),
    "Unit_Buy_Used_Window/frmBorder/frmInner/frmDesignList/frmUpdatableValue1/btnDown": _unit_market_interaction(
        reference="GUpdatableValue immediately decrements by 1; while held, source repeat counts 1/9/99 select decrements of 1/10/100 after an initial 0.5-second delay.",
        surface="UnitMarketPanel._render_quantity",
        effect="Decreases the local quantity using GMLValueRepeat's source-matched 1/10/100 increments and recomputes total price.",
        status="verified_openpower",
        validation="Enabled only with a selected listing; quantity remains at least one.",
        mapping_notes="GMLValueRepeat matches the source 0.5-second initial delay, repeat thresholds, adaptive intervals, and 1/10/100 increments; tests/test_gml_value_repeat.py verifies each increment threshold.",
        action_required="Keep the source-sized arrow hitbox, minimum bound, and increment-threshold test passing.",
    ),
    "Unit_Buy_Used_Window/frmBorder/frmInner/frmDesignList/frmUpdatableValue1/btnUp": _unit_market_interaction(
        reference="GUpdatableValue immediately increments by 1; while held, source repeat counts 1/9/99 select increments of 1/10/100 after an initial 0.5-second delay.",
        surface="UnitMarketPanel._render_quantity",
        effect="Increases the local quantity using GMLValueRepeat's source-matched 1/10/100 increments and recomputes total price.",
        status="verified_openpower",
        validation="Enabled only with a selected listing; quantity never exceeds the listing's current quantity.",
        mapping_notes="GMLValueRepeat matches the source 0.5-second initial delay, repeat thresholds, adaptive intervals, and 1/10/100 increments; tests/test_gml_value_repeat.py verifies each increment threshold.",
        action_required="Keep the source-sized arrow hitbox, live-listing maximum, and increment-threshold test passing.",
    ),
})

# Each fill/track sprite receives input through its owning technology meter.
UNIT_DESIGN_INTERACTION_BINDINGS = {}
for _meter_component, _capability_key in _UNIT_DESIGN_METERS:
    for _meter_root, _editable in (
        (_UNIT_DESIGN_OVERVIEW_METER_ROOT, False),
        (_UNIT_DESIGN_BUILDER_METER_ROOT, True),
    ):
        _meter_path = f"{_meter_root}/frm{_meter_component}"
        for _meter_part in ("btnFill", "btnUnfilled"):
            _meter_part_path = f"{_meter_path}/{_meter_part}"
            if _editable:
                UNIT_DESIGN_INTERACTION_BINDINGS[_meter_part_path] = {
                    "reference_side_effect": (
                        "GTechnologyMeterBlue handles the clicked fill/track part; "
                        "GCreateDesignWindow::OnMouseUp then recalculates the displayed "
                        "unit cost from the meter values."
                    ),
                    "openpower_surface": "UnitDesignEditor.render_capability_rows",
                    "openpower_effect": (
                        f"The source meter is represented by the local {_capability_key} "
                        "capability slider. Its draft value is submitted on CREATE DESIGN."
                    ),
                    "game_action": f"ActionCreateUnitDesign.stats.{_capability_key}",
                    "read_only_or_state_changing": "local capability draft until CREATE DESIGN; then authoritative state-changing intent",
                    "validation_condition": "The editor requires the player's own country, a non-empty name, and a positive cost; the server validates design ownership and stats.",
                    "country_scope_restriction": "Own country only.",
                    "confirmation_state": "CREATE DESIGN submits the current role, name, cost, upkeep, and capability values.",
                    "error_state": "Rejected creation feedback uses GenericMessageDialog and retains the editable draft.",
                    "restrictions_confirmation_error": "OpenPower does not yet derive source research-based meter ceilings or calculate cost from capability values; cost remains a separate draft field.",
                    "action_required": "Keep capability editing, create acceptance, and rejection-retention journeys passing; implement a cost estimator only when an authoritative OpenPower formula is available.",
                    "status": "partial",
                }
            else:
                UNIT_DESIGN_INTERACTION_BINDINGS[_meter_part_path] = {
                    "reference_side_effect": (
                        "GDesignWindow disables the technology meter; this fill/track "
                        "child is visual only in the selected-design overview."
                    ),
                    "openpower_surface": "UnitDesignPanel.render_selected_design",
                    "openpower_effect": (
                        f"Decorative {_meter_part} part of the read-only "
                        f"{_capability_key} meter for the selected saved design."
                    ),
                    "game_action": "none (disabled visual meter component)",
                    "read_only_or_state_changing": "read-only selected-design indicator",
                    "validation_condition": "The selected design must resolve; missing capability values remain unavailable.",
                    "country_scope_restriction": "Displays the selected design in the current overview.",
                    "confirmation_state": "None.",
                    "error_state": "Missing values are omitted instead of treated as editable input.",
                    "restrictions_confirmation_error": "The source disables all overview meters in GDesignWindow::OnCreate; their child buttons do not dispatch an action.",
                    "action_required": "Keep the overview meters read-only and preserve the separate builder route for capability edits.",
                    "status": "verified_openpower",
                }
UNIT_DESIGN_INTERACTION_BINDINGS.update({
    "Unit_New_Design/frmAction/btnConfirm": {
        "reference_side_effect": "GCreateDesignWindow::OnMouseClick calls SaveDesign, which emits REFERENCE::Event::GAddUnitDesign when the source role's required values pass its minimums.",
        "openpower_surface": "UnitDesignEditor.submit and ResearchProgramSystem._create_design",
        "openpower_effect": "CREATE dispatches ActionCreateUnitDesign; the authoritative system verifies issuer control, country existence, research requirements, and source-mapped required capabilities before inserting a design.",
        "game_action": "ActionCreateUnitDesign",
        "read_only_or_state_changing": "state-changing OpenPower GameAction",
        "validation_condition": "The editor requires the player's own country, a non-empty name, and positive cost; the system rejects missing role capabilities and incomplete research with explicit reasons.",
        "country_scope_restriction": "The form submits only for the controlled country; ResearchProgramSystem verifies issuer authority and owner existence.",
        "confirmation_state": "No separate confirmation; an authoritative design row closes the builder. Rejection keeps the draft open.",
        "error_state": "CommandFeedback presents authoritative research or capability rejection reasons in GenericMessageDialog; the editable draft remains available.",
        "restrictions_confirmation_error": "OpenPower precision is stored as a fraction, so required precision values are tested for positivity rather than integer rounding. Source research-meter ceilings and capability-derived cost are unavailable.",
        "action_required": "Keep design creation, source-required capability validation, research rejection, and draft-retention journeys covered; keep unavailable research ceilings and cost formula explicit.",
        "status": "verified_openpower",
    },
    "Unit_New_Design/frmDesignSpecs/frmUnitInfo/edtName": {
        "reference_side_effect": "SaveDesign copies the edit text into GAddUnitDesign::m_sName; Confirm requires a non-empty value.",
        "openpower_surface": "UnitDesignEditor._name",
        "openpower_effect": "Edits the local display name included as ActionCreateUnitDesign.display_name.",
        "game_action": "ActionCreateUnitDesign.display_name",
        "read_only_or_state_changing": "local draft until CREATE DESIGN; then authoritative state-changing intent",
        "validation_condition": "The name must be non-empty; the server validates country ownership and design constraints.",
        "country_scope_restriction": "Own country only.",
        "confirmation_state": "CREATE DESIGN sends the current name with the design fields.",
        "error_state": "Rejected creation feedback uses GenericMessageDialog and retains the editable draft.",
        "restrictions_confirmation_error": "None identified for display-name transfer.",
        "action_required": "Keep create acceptance and rejection-retention journeys passing.",
        "status": "verified_openpower",
    },
    "Unit_New_Design/frmDesignSpecs/frmUnitInfo/cboUnitType": {
        "reference_side_effect": "OnUnitTypeChange clears meter values, loads that unit type's model, description, component list, research limits, and initial cost.",
        "openpower_surface": "UnitDesignEditor._role",
        "openpower_effect": "Selects an OpenPower role profile and its capability defaults; submitted as ActionCreateUnitDesign.class_name and branch.",
        "game_action": "ActionCreateUnitDesign.class_name and branch",
        "read_only_or_state_changing": "local role draft until CREATE DESIGN; then authoritative state-changing intent",
        "validation_condition": "Only configured OpenPower role profiles are selectable; the server validates the submitted role and capability values.",
        "country_scope_restriction": "Own country only for design creation.",
        "confirmation_state": "Role selection is local until CREATE DESIGN.",
        "error_state": "Rejected creation feedback uses GenericMessageDialog and retains the role draft.",
        "restrictions_confirmation_error": "The shared catalog maps each REFERENCE EUnitType ID and source order to an OpenPower role. Source descriptions, research ceilings, cost formula, model selection, and localized labels remain unavailable or non-equivalent.",
        "action_required": "Preserve source-ID-to-role mapping and OpenPower class submission; keep unavailable source descriptions, research limits, cost formula, and model assets explicit.",
        "status": "partial",
    },
    "Unit_New_Design/frmBuild/frmPage/cboType": {
        "reference_side_effect": "OnUnitPieceChange selects a model piece category, resets its variation index, and updates the displayed model parts.",
        "openpower_surface": "UnitDesignEditor._render_unavailable_model_controls",
        "openpower_effect": "The source piece-category slot is shown disabled because OpenPower has no equivalent design-part catalog or visual assets.",
        "game_action": "none (unavailable model-part selection)",
        "read_only_or_state_changing": "disabled visual-model control",
        "validation_condition": "No equivalent model-piece catalog is available.",
        "country_scope_restriction": "None; no state-changing action is exposed.",
        "confirmation_state": "None.",
        "error_state": "Disabled selector explains that model-part data and assets are unavailable.",
        "restrictions_confirmation_error": "This GML combo selects model pieces; it is distinct from the REFERENCE unit-type combo. The OpenPower role selector occupies the source cboUnitType slot.",
        "action_required": "Keep the source slot explicit and disabled until equivalent part data and assets are available.",
        "status": "verified_unavailable",
    },
    "Unit_Design_New/frmTitle/btnExit": {
        "reference_side_effect": "The base titlebar exit hides/closes the GDesignWindow.",
        "openpower_surface": "UnitDesignPanel.render",
        "openpower_effect": "The source-sized window close control closes the Unit Design panel.",
        "game_action": "none (local window close)",
        "read_only_or_state_changing": "local UI-only",
        "validation_condition": "The Unit Design window is visible.",
        "country_scope_restriction": "None.",
        "confirmation_state": "None.",
        "error_state": "None; closing the panel sends no GameAction.",
        "restrictions_confirmation_error": "The Python titlebar close is bound to the source GML exit slot.",
        "action_required": "Keep the close target at the source titlebar slot and send no action.",
        "status": "verified_openpower",
    },
    "Unit_Design_New/frmTitle/togLockWindow": {
        "reference_side_effect": "The base title lock toggle prevents the window from being dragged.",
        "openpower_surface": "UnitDesignPanel._locked",
        "openpower_effect": "Toggles imgui WindowFlags_.no_move for the source-sized overview.",
        "game_action": "none (local window-position setting)",
        "read_only_or_state_changing": "local UI-only",
        "validation_condition": "The Unit Design window is visible.",
        "country_scope_restriction": "None.",
        "confirmation_state": "None.",
        "error_state": "None.",
        "restrictions_confirmation_error": "The lock state is local to the overview panel and does not change game data.",
        "action_required": "Keep the toggle behavior and source anchor geometry.",
        "status": "verified_openpower",
    },
    "Unit_Design_New/frmTitle/btnApply": {
        "reference_side_effect": "GDesignWindow::OnCreate hides btnApply when the member exists; no active click workflow is exposed.",
        "openpower_surface": "UnitDesignPanel",
        "openpower_effect": "Not rendered because the source hides this control during initialization.",
        "game_action": "none (source control hidden)",
        "read_only_or_state_changing": "not interactive; hidden by source initialization",
        "validation_condition": "None; the source control is hidden.",
        "country_scope_restriction": "None.",
        "confirmation_state": "None.",
        "error_state": "None.",
        "restrictions_confirmation_error": "Do not expose an Apply action without source evidence that the control is shown.",
        "action_required": "Keep btnApply hidden.",
        "status": "verified_unavailable",
    },
    "Unit_Design_New/frmInner/frmUnitInfo/cboUnitType": {
        "reference_side_effect": "The source unit-type combo repopulates the design-name combo, refreshes its description and available meters, and selects a design for the chosen type.",
        "openpower_surface": "UnitDesignPanel._role",
        "openpower_effect": "Selects an OpenPower role profile and filters the saved designs to that canonical class.",
        "game_action": "none (local design filter)",
        "read_only_or_state_changing": "local selection and detail filter",
        "validation_condition": "Only configured OpenPower role profiles are selectable.",
        "country_scope_restriction": "Designs are scoped to the selected country; explicit design-detail routes may retain the selected design ID.",
        "confirmation_state": "None; selection is local.",
        "error_state": "An empty role catalog shows the no-saved-design state.",
        "restrictions_confirmation_error": "The shared catalog maps all 20 REFERENCE EUnitType IDs and source order to canonical OpenPower roles; labels use English enum names because the source localization bundle is unavailable. Missile Defense is an OpenPower-only extension.",
        "action_required": "Keep role aliases and source ID mappings canonicalized and preserve exact selected-design routes; load translated labels only when source language resources are available.",
        "status": "partial",
    },
    "Unit_Design_New/frmInner/frmUnitInfo/cboUnitName": {
        "reference_side_effect": "Selecting a design row updates the overview description, unit cost, model, and technology meters for that design.",
        "openpower_surface": "UnitDesignPanel._selection",
        "openpower_effect": "Selects a saved design ID and refreshes its description, cost, overview, and capability tab.",
        "game_action": "none (local design selection)",
        "read_only_or_state_changing": "local design selection and read-only details",
        "validation_condition": "The selected design must belong to the chosen country or be explicitly supplied by a unit-detail route.",
        "country_scope_restriction": "Default list contains only designs available to the selected country; direct detail routes retain the exact requested design ID.",
        "confirmation_state": "None; selection is local.",
        "error_state": "An empty role catalog shows 'No saved designs' and omits unavailable detail values.",
        "restrictions_confirmation_error": "OpenPower has no equivalent 3D design preview; source models remain unavailable.",
        "action_required": "Keep selection, role filtering, and direct Unit List/Production detail routes synchronized.",
        "status": "verified_openpower",
    },
    "Unit_Design_New/frmInner/btnNewDesign": {
        "reference_side_effect": "GDesignWindow::OnMouseClick shows or spawns GCreateDesignWindow when New Design is clicked.",
        "openpower_surface": "UnitDesignPanel._editor.open",
        "openpower_effect": "Opens the separate 666x618 Unit_New_Design builder with the currently selected role.",
        "game_action": "none (local window navigation)",
        "read_only_or_state_changing": "local UI navigation",
        "validation_condition": "The active country must be the player's own country and a connection must be available before creation is enabled.",
        "country_scope_restriction": "Design creation is enabled for the player's own country only.",
        "confirmation_state": "None; the builder is opened without submitting a design.",
        "error_state": "The control is disabled when the player cannot create designs.",
        "restrictions_confirmation_error": "The builder opens in its own source-sized window and receives the selected OpenPower role.",
        "action_required": "Keep the overview-to-builder route and selected role handoff covered by the military design journey.",
        "status": "verified_openpower",
    },
})
for _model_control, _model_effect in (
    ("frmBuild/frmPage/btnLeft", "Cycles to the previous visual variation for the selected model piece."),
    ("frmBuild/frmPage/btnRight", "Cycles to the next visual variation for the selected model piece."),
    ("frmBuild/frmParts/btnLeft", "Selects the left model-part variation when it is compatible with its parent piece."),
    ("frmBuild/frmParts/btnMiddle", "Selects the middle model-part variation when it is compatible with its parent piece."),
    ("frmBuild/frmParts/btnRight", "Selects the right model-part variation when it is compatible with its parent piece."),
):
    UNIT_DESIGN_INTERACTION_BINDINGS[f"Unit_New_Design/{_model_control}"] = {
        "reference_side_effect": _model_effect,
        "openpower_surface": "UnitDesignEditor._render_unavailable_model_controls",
        "openpower_effect": "The source-sized control is disabled because OpenPower has no equivalent model variation data or visual assets.",
        "game_action": "none (unavailable model presentation control)",
        "read_only_or_state_changing": "disabled visual-model control",
        "validation_condition": "No equivalent model variation data is available.",
        "country_scope_restriction": "None; no state-changing action is exposed.",
        "confirmation_state": "None.",
        "error_state": "Hover text explains visual part selection is unavailable in OpenPower.",
        "restrictions_confirmation_error": "Source selection updates GCreateDesignWindow's local model view and is saved as GAddUnitDesign::m_Variations; OpenPower has no variation payload field.",
        "action_required": "Keep these source controls disabled until OpenPower has equivalent model variation data and action fields.",
        "status": "verified_unavailable",
    }
for _texture_index in range(1, 9):
    UNIT_DESIGN_INTERACTION_BINDINGS[
        f"Unit_New_Design/frmBuild/frmTextures/btn{_texture_index}"
    ] = {
        "reference_side_effect": "OnColorButton changes the local model ColorIndex and refreshes the model and part previews; SaveDesign stores it in m_Variations.",
        "openpower_surface": "UnitDesignEditor._render_unavailable_model_controls",
        "openpower_effect": "The source-sized color swatch is disabled because OpenPower has no equivalent model-color or variation field.",
        "game_action": "none (unavailable visual design color)",
        "read_only_or_state_changing": "disabled visual-model control",
        "validation_condition": "No equivalent model color data is available.",
        "country_scope_restriction": "None; no state-changing action is exposed.",
        "confirmation_state": "None.",
        "error_state": "Hover text explains visual texture assets are unavailable in OpenPower.",
        "restrictions_confirmation_error": "Source swatches only modify the model preview and saved visual variation; OpenPower has no corresponding design field.",
        "action_required": "Keep color selection disabled until OpenPower has equivalent visual assets and a persisted variation field.",
        "status": "verified_unavailable",
    }
def _politics_meter_interaction(
    path: str,
    *,
    meter_name: str,
    source_drag_enabled: bool,
    openpower_binding: str,
    openpower_status: str = "verified_openpower",
) -> dict[str, str]:
    if source_drag_enabled:
        reference_side_effect = (
            "GCursorMeter permits dragging btnFill and raises c_OnMeterChangeEvent with the new local meter value. "
            "GPoliticWindow has no OnCustomEvent receiver and does not dispatch a game event for this value."
        )
        reference_event = "c_OnMeterChangeEvent (local presentation event; no server game event)"
        transition = "The meter's local Value changes; GPoliticWindow defines no OnCustomEvent handler or GameAction."
        openpower_effect = (
            f"{meter_name} is rendered read-only from {openpower_binding}. OpenPower does not reproduce the source-only "
            "cursor drag because it changes only the meter widget and has no political-state effect."
        )
        game_action = "none (source-only local meter value; no authoritative game action)"
        read_only = "source presentation-only meter drag; OpenPower metric is read-only"
        status = "verified_unavailable"
        action_required = (
            "Keep the OpenPower meter read-only unless an authoritative political action is identified; "
            "the source drag has no GPoliticWindow receiver or game-state effect."
        )
    else:
        reference_side_effect = (
            "The source meter cursor is locked or non-draggable; the button fragment only paints the meter track/value."
        )
        reference_event = "None (locked display fragment)"
        transition = "GCursorMeter::OnMouseDown handles the disabled fragment without changing a game value."
        openpower_effect = f"{meter_name} is represented by the read-only GML meter bound to {openpower_binding}."
        game_action = "none (read-only meter display)"
        read_only = "read-only political metric"
        status = openpower_status
        action_required = (
            "Keep the source-sized read-only meter and its model binding; do not attach an action to a visual fragment."
        )

    return {
        "reference_callback": "GCursorMeter::OnMouseDown/OnDrag@reference_frame_cursor_meter.cpp",
        "reference_game_event": reference_event,
        "reference_side_effect": reference_side_effect,
        "verified_cpp_transition": transition,
        "validation_condition": "The political window and meter are enabled; the source fill cursor is draggable only where noted.",
        "openpower_surface": "PoliticsPanel._render_content / GMLWidgets.meter",
        "openpower_effect": openpower_effect,
        "game_action": game_action,
        "read_only_or_state_changing": read_only,
        "country_scope_restriction": "The displayed value belongs to the currently selected country; no write is issued.",
        "confirmation_state": "None; the source cursor gesture does not confirm a game action.",
        "error_state": "No game-action error state exists for a source-only meter gesture.",
        "restrictions_confirmation_error": (
            "GPoliticWindow::Update reloads these values from the selected-country data; "
            "the cursor gesture is not persisted or sent to the server."
        ),
        "action_required": action_required,
        "status": status,
    }


def _relations_country_selector_interaction(country_side: str) -> dict[str, str]:
    return {
        "reference_callback": "OnCustomEvent@reference_relations_window.cpp:114",
        "reference_side_effect": (
            f"Selecting cboCountry{country_side} updates the directional country pair; "
            "OnComboBoxSelectionEvent requests relation history when both selected countries are non-empty and distinct."
        ),
        "verified_cpp_transition": (
            "OnCustomEvent handles OnComboBoxSelectionEvent, reads both Selected_Content values, "
            "resolves country IDs, and calls StartRequestRelationHistory@reference_relations_window.cpp:134."
        ),
        "validation_condition": "Both country selections must resolve and must refer to different countries before history is requested.",
        "openpower_panel_spec": "RELATIONS",
        "openpower_surface": f"RelationsPanel._country_selector(relations.country_{country_side.lower()})",
        "openpower_effect": (
            f"Updates Country {country_side} and rebuilds the directional relation summary and read-only history from the current OpenPower snapshot."
        ),
        "game_action": "none (read-only relation history lookup)",
        "read_only_or_state_changing": "local country-pair selection and read-only history display",
        "country_scope_restriction": "Any two distinct countries present in the current countries snapshot can be selected.",
        "confirmation_state": "None; changing the pair only updates the displayed relation view.",
        "error_state": "Selecting the same country for both sides shows a prompt; missing pair data shows an unavailable message.",
        "restrictions_confirmation_error": (
            "REFERENCE requests the pair's relation history on selection; OpenPower derives history from its event journal and current snapshot."
        ),
        "action_required": "Keep both directional selectors GML-bound and the relation view read-only; preserve same-country and missing-data feedback.",
        "status": "verified_openpower",
    }


RELATIONS_INTERACTION_BINDINGS = {
    f"Relations_Window/frmInner/frmRelations/cboCountry{side}":
        _relations_country_selector_interaction(side)
    for side in ("A", "B")
}


POLITICS_INTERACTION_BINDINGS = {
    "Politic_Window/frmTitle/btnExit": {
        "reference_side_effect": (
            "GPoliticWindow::OnMouseClick hides the politics window, calls KillWindowsPoliticLv2(), "
            "and turns off the Main Bar politics toggle. KillWindowsPoliticLv2 removes only already-hidden "
            "secondary politics windows."
        ),
        "openpower_surface": "PoliticsPanel title close / PanelManager.render_all",
        "openpower_effect": (
            "Closes POL through the shared WindowManager path; visible secondary panels remain visible, "
            "and hidden panel instances are retained for reuse."
        ),
        "game_action": "none (local window close)",
        "read_only_or_state_changing": "local UI visibility change",
        "validation_condition": "The politics panel is visible.",
        "country_scope_restriction": "None.",
        "confirmation_state": "None.",
        "error_state": "None; closing the panel does not submit a game action.",
        "restrictions_confirmation_error": (
            "The REFERENCE cleanup call only destroys secondary windows that are already hidden; "
            "OpenPower retains their hidden panel instances without changing visible routes."
        ),
        "action_required": "Keep the existing politics close journey and Main Bar visibility behavior.",
        "status": "verified_openpower",
    },
    "Politic_Window/frmTitle/btnApply": {
        "reference_side_effect": "GPoliticWindow::OnCreate hides m_pObjApplyBtn; the source control is not available at runtime.",
        "openpower_surface": "PoliticsPanel GML titlebar rules",
        "openpower_effect": "No Apply control is shown, matching the source-hidden control.",
        "game_action": "none (source control hidden)",
        "read_only_or_state_changing": "non-interactive hidden source control",
        "validation_condition": "The REFERENCE politics window has completed OnCreate.",
        "country_scope_restriction": "None.",
        "confirmation_state": "None.",
        "error_state": "None; no Apply action is exposed.",
        "restrictions_confirmation_error": "OnCreate explicitly hides the inherited Apply button.",
        "action_required": "Continue omitting the Apply control from the politics panel.",
        "status": "verified_openpower",
    },
}

_POLITICS_METERS = {
    "frmPressure/frmGradient": ("political pressure", True, "unavailable: no equivalent OpenPower country field"),
    "frmCorruption/frmGradient": ("government corruption", True, "countries.gvt_corruption"),
    "frmIdeology/frmIdeologyCursor": ("political ideology", False, "country_governments.ideology_balance"),
    "frmStability/frmGradient": ("government stability", True, "countries.gvt_stability"),
    "frmApproval/frmGradient": ("government approval", True, "countries.gvt_approval"),
}
for _meter_path, (_meter_name, _drag_enabled, _binding) in _POLITICS_METERS.items():
    _pressure_unavailable = _meter_path.startswith("frmPressure/")
    for _fragment in ("btnFill", "btnUnfilled"):
        _source_drag_enabled = _drag_enabled and _fragment == "btnFill"
        _interaction_binding = _politics_meter_interaction(
            f"Politic_Window/frmInner/{_meter_path}/{_fragment}",
            meter_name=_meter_name,
            source_drag_enabled=_source_drag_enabled,
            openpower_binding=_binding,
            openpower_status="partial" if _pressure_unavailable else "verified_openpower",
        )
        if _pressure_unavailable:
            _interaction_binding.update({
                "openpower_effect": (
                    "The source pressure track is retained as an empty disabled rail with an adjacent N/A label; "
                    "OpenPower has no authoritative pressure value, so no numeric fill is fabricated."
                ),
                "action_required": (
                    "Keep the source-sized empty rail and explicit N/A fallback until an authoritative pressure field exists."
                ),
                "status": "partial",
            })
        POLITICS_INTERACTION_BINDINGS[
            f"Politic_Window/frmInner/{_meter_path}/{_fragment}"
        ] = _interaction_binding


COUNTRY_PROFILE_INTERACTION_BINDINGS = {
    "Country_Profile_Window/frmTitle/btnExit": {
        "reference_side_effect": "GCountryProfileWindow::OnMouseClick hides the profile window when its title exit is clicked.",
        "openpower_surface": "CountryProfileWindow title close / CountryProfileWindow.close",
        "openpower_effect": "Closes the pre-game dialog and clears its current candidate selection without changing the parent country selection.",
        "game_action": "none (local dialog close)",
        "read_only_or_state_changing": "local UI close",
        "validation_condition": "The country-profile dialog is open.",
        "country_scope_restriction": "None; closing does not change the chosen country.",
        "confirmation_state": "None.",
        "error_state": "None.",
        "restrictions_confirmation_error": "The source title exit and Cancel both hide the dialog without dispatching the country-selection callback.",
        "action_required": "Keep title close and Cancel as local close paths that preserve the previous parent selection.",
        "status": "verified_openpower",
    },
    "Country_Profile_Window/frmTitle/btnApply": {
        "reference_side_effect": "GCountryProfileWindow::OnCreate hides the inherited Apply button.",
        "openpower_surface": "CountryProfileWindow GML titlebar rules",
        "openpower_effect": "No Apply control is shown, matching the source-hidden button.",
        "game_action": "none (source control hidden)",
        "read_only_or_state_changing": "non-interactive hidden source control",
        "validation_condition": "The source window has completed OnCreate.",
        "country_scope_restriction": "None.",
        "confirmation_state": "None.",
        "error_state": "None; no Apply action exists on this dialog.",
        "restrictions_confirmation_error": "The C++ source explicitly hides m_pObjApplyBtn.",
        "action_required": "Continue omitting the source-hidden Apply control.",
        "status": "verified_openpower",
    },
    "Country_Profile_Window/frmInner/btnConfirm": {
        "reference_side_effect": "With a selected row, GCountryProfileWindow::OnMouseClick emits c_iOnCountryProfileWindowSelection with the country ID and hides the dialog; without a selected row it disables Confirm.",
        "openpower_surface": "CountryProfileWindow._render_content / NewGameView country selection",
        "openpower_effect": "Enabled only after candidate selection; passes the selected OpenPower country tag to the singleplayer setup callback and closes the dialog.",
        "game_action": "none (pre-game local country selection)",
        "read_only_or_state_changing": "local setup selection; no running-game action",
        "validation_condition": "A current suggestion is selected.",
        "country_scope_restriction": "The current OpenPower route is singleplayer setup; it does not implement the source multiplayer-lobby callback.",
        "confirmation_state": "The Select button is disabled until a candidate is selected; selecting it immediately updates the parent setup country and closes.",
        "error_state": "No selection means the callback is not sent and the button remains disabled.",
        "restrictions_confirmation_error": "OpenPower returns a country tag; REFERENCE sends an integer country ID. The source multiplayer RGAPI route has no OpenPower lobby equivalent.",
        "action_required": "Keep the singleplayer Select route and selection requirement; retain the multiplayer-lobby profile route as an explicit unsupported workflow.",
        "status": "partial",
    },
    "Country_Profile_Window/frmInner/frmSuggested/lstCountries": {
        "reference_side_effect": "OnListItemSelected reads the chosen source row, refreshes its economic, political, and military rank bars, and enables Confirm for a valid country.",
        "openpower_surface": "CountryProfileWindow._render_country_list / _render_suggestion_ranks",
        "openpower_effect": "Selecting a candidate refreshes its rank bars and the selected country tag; Confirm becomes available.",
        "game_action": "none (local candidate selection until Confirm)",
        "read_only_or_state_changing": "local candidate selection",
        "validation_condition": "The selected row has a valid current candidate country tag.",
        "country_scope_restriction": "Candidates are restricted to the eligible countries supplied by the singleplayer setup view.",
        "confirmation_state": "Candidate selection is separate from the final Select confirmation.",
        "error_state": "An empty or invalid candidate set leaves Select disabled and the profile panel open.",
        "restrictions_confirmation_error": "OpenPower recomputes candidates from its available GDP, government-approval, and personnel fields; exact REFERENCE lobby rank arrays and criteria are unavailable.",
        "action_required": "Keep row selection local and preserve the OpenPower-data ranking limitation until source rank inputs are mapped.",
        "status": "partial",
    },
    "Country_Profile_Window/frmInner/btnCancel": {
        "reference_side_effect": "GCountryProfileWindow::OnMouseClick hides the profile window when Cancel is clicked.",
        "openpower_surface": "CountryProfileWindow._render_content / CountryProfileWindow.close",
        "openpower_effect": "Closes the dialog and leaves the previous parent country selection unchanged.",
        "game_action": "none (local dialog cancel)",
        "read_only_or_state_changing": "local UI close",
        "validation_condition": "The country-profile dialog is open.",
        "country_scope_restriction": "None; the candidate has not been committed to the parent setup.",
        "confirmation_state": "None.",
        "error_state": "None.",
        "restrictions_confirmation_error": "Cancel hides the profile without invoking c_iOnCountryProfileWindowSelection.",
        "action_required": "Keep Cancel from changing the parent setup country.",
        "status": "verified_openpower",
    },
}

_COUNTRY_PROFILE_METRICS = {
    "economic": ("Economic (GDP)", "Economic"),
    "political": ("Political (government approval)", "Politic"),
    "military": ("Military (personnel)", "Military"),
}
for _metric, (_metric_label, _metric_slot) in _COUNTRY_PROFILE_METRICS.items():
    _profile_source = "Client/Source/reference_country_profile.cpp; Client/Source/reference_frame_cursor_meter.cpp"
    for _fragment in ("btnFill", "btnUnfilled"):
        COUNTRY_PROFILE_INTERACTION_BINDINGS[
            f"Country_Profile_Window/frmInner/frmDesired/frm{_metric_slot}/{_fragment}"
        ] = {
            "reference_callback": "GCountryProfileWindow::OnCustomEvent(c_OnMeterChangeEvent)",
            "reference_game_event": "c_OnMeterChangeEvent (local candidate recomputation only)",
            "reference_side_effect": (
                f"The source {_metric_label.lower()} desired meter updates its local value, then "
                "GCountryProfileWindow::OnCustomEvent calls CalculatePossibleCountries."
            ),
            "verified_cpp_transition": "The source meter drag clears the current candidate and recalculates the suggested-country ranks.",
            "validation_condition": "The desired meter is enabled; the selected metric is included only when its matching toggle is on.",
            "openpower_surface": "CountryProfileWindow._render_content / GMLWidgets.meter_slider",
            "openpower_effect": (
                f"Dragging the {_metric_label.lower()} source slot updates the local desired ratio, clears the current selection, "
                "and recalculates the candidate list."
            ),
            "game_action": "none (local profile preference and candidate ranking)",
            "read_only_or_state_changing": "local recommendation criteria; no game state is changed",
            "country_scope_restriction": "The slider ranks only the eligible pre-game country set.",
            "confirmation_state": "No game confirmation; country selection remains separate.",
            "error_state": "No action rejection state; an empty candidate set leaves Confirm disabled.",
            "restrictions_confirmation_error": "The OpenPower control recomputes against native GDP, approval, and personnel rankings rather than the source-provided rank vectors.",
            "action_required": "Keep the local slider behavior; exact rank-vector parity requires the source rank inputs, not a fabricated GameAction.",
            "status": "partial",
        }
    COUNTRY_PROFILE_INTERACTION_BINDINGS[
        f"Country_Profile_Window/frmInner/frmDesired/tog{_metric_slot}"
    ] = {
        "reference_callback": "GCountryProfileWindow::OnMouseClick",
        "reference_game_event": "None (local filter selection)",
        "reference_side_effect": "Clicking an Economic, Political, or Military toggle calls CalculatePossibleCountries and clears the current candidate selection.",
        "openpower_surface": "CountryProfileWindow._render_content / new_game.profile.filter checkbox",
        "openpower_effect": f"Toggles whether {_metric_label.lower()} rank contributes to the desired-profile comparison, then recalculates candidates.",
        "game_action": "none (local filter selection)",
        "read_only_or_state_changing": "local recommendation filter",
        "validation_condition": "The profile dialog is open.",
        "country_scope_restriction": "Only filters the eligible pre-game candidate list.",
        "confirmation_state": "None; Select remains separate.",
        "error_state": "No action error state; an empty candidate set leaves Select disabled.",
        "restrictions_confirmation_error": "OpenPower applies the same enabled-metric filter to its native ranking values; exact REFERENCE rank inputs are unavailable.",
        "action_required": "Keep each filter independently switchable and document the native OpenPower ranking inputs.",
        "status": "partial",
    }
    for _fragment in ("btnFill", "btnUnfilled"):
        COUNTRY_PROFILE_INTERACTION_BINDINGS[
            f"Country_Profile_Window/frmInner/frmSuggested/frm{_metric_slot}/{_fragment}"
        ] = {
            "reference_side_effect": "The suggested rank meter is disabled in GCountryProfileWindow::OnCreate and cannot be edited by the user.",
            "openpower_surface": "CountryProfileWindow._render_suggestion_ranks / GMLWidgets.meter",
            "openpower_effect": "Displays the selected candidate's read-only rank fraction; it does not accept input.",
            "game_action": "none (disabled rank display)",
            "read_only_or_state_changing": "disabled read-only rank meter",
            "validation_condition": "A candidate is selected to display a rank; otherwise the meter is empty.",
            "country_scope_restriction": "Shows only the selected eligible candidate's OpenPower rank.",
            "confirmation_state": "None.",
            "error_state": "No action error state; unavailable candidates render an empty bar.",
            "restrictions_confirmation_error": "The source meter is disabled; the OpenPower bar is likewise non-interactive. Underlying rank inputs remain OpenPower-native.",
            "action_required": "Keep suggested-rank bars read-only and retain the rank-data limitation in the display contract.",
            "status": "verified_openpower",
        }


TREATY_PARTICIPANT_INTERACTION_BINDINGS = {
    "Treaty_Details_Window/frmInner/frmEligibleCountries/lstEligibleCountries": {
        "openpower_effect": "Read-only grid of countries that currently satisfy the selected treaty's membership conditions; selecting a list row does not dispatch an action.",
        "game_action": "none (informational list)",
        "read_only_or_state_changing": "read-only country eligibility display",
        "validation_condition": "Countries are filtered through the active treaty's current eligibility rules.",
        "country_scope_restriction": "Displays public country tags and flags; it does not expose private country state.",
        "confirmation_state": "None.",
        "error_state": "An empty result displays 'No eligible countries.'; unavailable names fall back to their country tag and unavailable flag images use FlagRenderer's fallback.",
        "restrictions_confirmation_error": "List rows are informational. The separate Remove Not Eligible action stages participant changes and Apply performs server validation.",
        "action_required": "Keep the treaty-details journey asserting eligible and excluded country rows at source grid geometry.",
        "status": "verified_openpower",
    },
    "Treaty_Details_Window/frmInner/frmEligibleCountries/btnRemoveNotEligible": {
        "openpower_effect": "Stage removal of current ineligible members in the participant draft and show the generic notice; no treaty action is sent until Apply.",
        "game_action": "ActionUpdateTreatyParticipants on participant-editor Apply",
        "read_only_or_state_changing": "local participant draft until Apply; then authoritative state-changing action",
        "validation_condition": "The active treaty must have ineligible members and permit participant editing; Apply revalidates the saved treaty eligibility conditions on the server.",
        "country_scope_restriction": "Only the connected player's own treaty sponsor may edit participants.",
        "confirmation_state": "The source Remove Not Eligible control opens the participant editor with invalid members removed from its draft; the generic notice explains Apply is required.",
        "error_state": "A rejected participant update is shown through GenericMessageDialog; the invalid draft stays open and is marked for correction.",
        "restrictions_confirmation_error": "Removal is staged locally; sponsorship, side validity, and treaty eligibility are checked again by DiplomacySystem when Apply dispatches the action.",
        "action_required": "Keep the native remove-ineligible and rejection journeys plus authoritative treaty eligibility tests passing.",
        "status": "verified_openpower",
    }
}
def _participant_interaction_binding(
    *, reference: str, surface: str, effect: str, action: str,
    validation: str, restriction: str, confirmation: str, error: str,
    limitation: str, status: str = "partial",
) -> dict[str, str]:
    return {
        "reference_side_effect": reference,
        "openpower_surface": surface,
        "openpower_effect": effect,
        "game_action": action,
        "read_only_or_state_changing": (
            "local participant draft" if action.startswith("none")
            else "state-changing through the owning treaty workflow"
        ),
        "validation_condition": validation,
        "country_scope_restriction": restriction,
        "confirmation_state": confirmation,
        "error_state": error,
        "restrictions_confirmation_error": limitation,
        "action_required": limitation,
        "status": status,
    }


_PARTICIPANT_TRANSFER_BINDINGS = {
    "btnRightA": ("Move selected active-country rows from Available to Side A.", "Move each selected available country into the Side A draft.", "At least one available row is selected.", "Sponsor-protected Side A members are not removable."),
    "btnLeftA": ("Move selected Side A rows back to Available.", "Move each selected removable Side A country back to the available draft list.", "At least one unprotected Side A row is selected.", "The controlled treaty sponsor cannot be removed from required Side A membership."),
    "btnRightB": ("Move selected active-country rows from Available to Side B.", "Move each selected available country into the Side B draft.", "The treaty type is two-sided and at least one available row is selected.", "Hidden for one-sided treaty definitions; required Side B participants stay on their side."),
    "btnLeftB": ("Move selected Side B rows back to Available.", "Move each selected removable Side B country back to the available draft list.", "The treaty type is two-sided and at least one unprotected Side B row is selected.", "Hidden for one-sided treaty definitions; required counterpart participants cannot be removed."),
    "btnRightAB": ("Move selected Side A rows to Side B.", "Move each selected removable Side A country to Side B in the local draft.", "The treaty type is two-sided and at least one removable Side A row is selected.", "Disabled for one-sided treaty definitions; required sponsor members stay on Side A."),
    "btnLeftAB": ("Move selected Side B rows to Side A.", "Move each selected removable Side B country to Side A in the local draft.", "The treaty type is two-sided and at least one removable Side B row is selected.", "Disabled for one-sided treaty definitions; required counterpart members stay on Side B."),
}
for _button, (_reference, _effect, _validation, _limitation) in _PARTICIPANT_TRANSFER_BINDINGS.items():
    TREATY_PARTICIPANT_INTERACTION_BINDINGS[f"Add_Remove_Window/frmInner/frmItems/{_button}"] = _participant_interaction_binding(
        reference=_reference,
        surface="TreatyParticipantDialog._render_transfer_buttons",
        effect=_effect,
        action="none (local draft); ActionCreateTreaty or ActionUpdateTreatyParticipants on Apply",
        validation=_validation,
        restriction="Available in a new multi-member proposal or to the connected sponsor editing an active multi-member treaty.",
        confirmation="The transfer is local; the owner submits the resulting sides through its treaty Apply or proposal action.",
        error="Transfer does not change authoritative state; a rejected Apply retains the draft for correction.",
        limitation=_limitation,
    )

TREATY_PARTICIPANT_INTERACTION_BINDINGS.update({
    "Add_Remove_Window/frmTitle/btnExit": _participant_interaction_binding(
        reference="The source exit control hides Add_Remove_Window without raising the participant-selection event.",
        surface="TreatyParticipantDialog / WindowManager GML title close",
        effect="Closes the editor and discards its local participant draft.",
        action="none (local dialog dismissal)",
        validation="The participant editor is open.",
        restriction="A caller may open the dialog only for a new proposal or a sponsor-authorized active treaty edit.",
        confirmation="Closing does not apply or dispatch the local draft.",
        error="None; the owning treaty remains unchanged.",
        limitation="Keep title close as a local discard path and do not submit a treaty action implicitly.",
        status="verified_openpower",
    ),
    "Add_Remove_Window/frmTitle/btnApply": _participant_interaction_binding(
        reference="The source Apply control copies both side lists to its caller and hides the participant editor.",
        surface="TreatyParticipantDialog.render / LiveTreatiesPanel._resolve_participant_update / LiveTreatyEditorPanel",
        effect="Returns selected side sets to the owner; active-treaty edits dispatch ActionUpdateTreatyParticipants, while proposal edits remain local until ActionCreateTreaty is sent.",
        action="ActionUpdateTreatyParticipants or ActionCreateTreaty according to the owning workflow",
        validation="At least two participants are required; the owner and server validate treaty type, required sides, sponsorship, eligibility, and stale state.",
        restriction="Only the connected sponsor may edit an active treaty; proposals use active OpenPower countries.",
        confirmation="Dialog Apply returns the draft; active treaty Apply sends the update, while proposal submission sends the create action later.",
        error="An authoritative rejection keeps the participant draft open for correction and displays the existing generic notice.",
        limitation="The source caller callback is represented by the OpenPower action workflow; exact source localization remains unavailable.",
    ),
    "Add_Remove_Window/frmInner/frmItems/frmUnselected/lstUnselected": _participant_interaction_binding(
        reference="Selecting source available-list rows changes only list selection; rows are active countries not assigned to either side.",
        surface="TreatyParticipantDialog._render_country_list(available)",
        effect="Shows active OpenPower countries absent from both sides with flag, tag, and localized name; Ctrl and Shift extend selection.",
        action="none (local list selection)",
        validation="Rows come from countries.active and exclude current Side A and Side B members.",
        restriction="Inactive countries cannot be newly added; an inactive current member remains marked ineligible so it can be removed.",
        confirmation="Selection changes no treaty state; transfer controls stage additions.",
        error="An empty catalog leaves the available list empty without synthesizing countries.",
        limitation="OpenPower's active country catalog is authoritative; source localization and exact flag art are unavailable.",
    ),
    "Add_Remove_Window/frmInner/frmItems/frmSideA/lstSelectedA": _participant_interaction_binding(
        reference="Selecting source Side A rows changes only list selection; Apply later reads the selected Side A rows.",
        surface="TreatyParticipantDialog._render_country_list(side_a)",
        effect="Shows the Side A draft with flag, tag, localized name, and ineligible marking; Ctrl and Shift extend selection.",
        action="none (local list selection)",
        validation="Rows reflect the selected treaty or proposal draft; the required sponsor is protected from removal.",
        restriction="Only the connected sponsor may edit an active treaty; the controlled sponsor stays on its required side.",
        confirmation="Selection changes no treaty state; transfer controls stage moves or removals.",
        error="An empty side displays an empty list; rejected server updates retain the open draft.",
        limitation="OpenPower's treaty-side fields preserve the selected treaty's current member data.",
    ),
    "Add_Remove_Window/frmInner/frmItems/frmSideB/lstSelectedB": _participant_interaction_binding(
        reference="Selecting source Side B rows changes only list selection; Apply later reads the selected Side B rows.",
        surface="TreatyParticipantDialog._render_country_list(side_b)",
        effect="Shows the Side B draft with flag, tag, localized name, and ineligible marking; Ctrl and Shift extend selection.",
        action="none (local list selection)",
        validation="Rows reflect a two-sided treaty draft; one-sided definitions clear and hide Side B.",
        restriction="Only the connected sponsor may edit an active treaty; required counterpart members stay on Side B.",
        confirmation="Selection changes no treaty state; transfer controls stage moves or removals.",
        error="An empty side displays an empty list; rejected server updates retain the open draft.",
        limitation="OpenPower's treaty-side fields preserve the selected treaty's current member data.",
    ),
})

CONSTITUTIONAL_FORM_INTERACTION_BINDINGS = {
    "Constitutional_Form/frmTitle/btnExit": {
        "reference_side_effect": "The source titlebar exit hides GConstitutionalFormWindow.",
        "openpower_surface": "ConstitutionalFormPanel / WindowManager GML title close",
        "openpower_effect": "Closes the panel; a pending capital draft first enters the shared Apply/Discard confirmation.",
        "game_action": "none (local window close)",
        "read_only_or_state_changing": "local UI close; draft disposition is confirmed before closing",
        "validation_condition": "The constitutional form panel is visible.",
        "country_scope_restriction": "None for closing; a capital draft can only be applied to the connected player's country.",
        "confirmation_state": "DirtyCloseConfirmation offers Apply or Discard when a capital draft is pending.",
        "error_state": "A rejected capital action keeps the panel open and the authoritative capital unchanged.",
        "restrictions_confirmation_error": "Close never changes the capital implicitly; it requires an explicit Apply choice.",
        "action_required": "Keep the source-sized close control and pending-draft confirmation available.",
        "status": "verified_openpower",
    },
    "Constitutional_Form/frmTitle/togLockWindow": {
        **_hidden_base_window_lock_interaction("Constitutional_Form"),
    },
    "Constitutional_Form/frmTitle/btnApply": {
        "reference_side_effect": "GConstitutionalFormWindow::Save sends GConstitutionalFormUpdate with the selected form, optional capital, and martial-law state; foreign-country changes first ask for a release-country confirmation.",
        "openpower_surface": "ConstitutionalFormPanel._apply_changes",
        "openpower_effect": "Domestic Apply sends ActionSetCountryCapital for a staged capital and ActionSetGovernmentForm for compatible form and/or martial-law changes. Foreign Apply is restricted to a changed government form when at least 75% of the target's political regions are under the player's military control and the target is not hostile; GenericQuestionDialog Yes confirms and dispatches the action while No keeps the draft. The server revalidates control, threshold, diplomatic status and confirmation, then releases the controlled regions, grants military access, and sets both relation directions to 100. OpenPower calculates threshold by regional count because the published REFERENCE proportion formula is unavailable.",
        "game_action": "Domestic: ActionSetCountryCapital(...) and/or ActionSetGovernmentForm(...). Qualified foreign: ActionSetGovernmentForm(player_id, country_tag, expected_form_id, target_form_id, expected_martial_law, target_martial_law, confirmed_foreign_change=True)",
        "read_only_or_state_changing": "authoritative state-changing action",
        "validation_condition": "Requires a changed supported draft and net client; the server rechecks domestic authority or, for foreign form changes, non-hostile status, at least 75% regional control and explicit confirmation; it also validates expected capital/form/martial-law state, regional control, party-count limits, crisis status, and target election rules.",
        "country_scope_restriction": "Domestic capital, form, override and martial-law edits are available to the controlled country. Foreign targets expose only the form selector and Apply when the non-hostile 75% regional-control rule passes; capital, override and martial-law controls stay disabled.",
        "confirmation_state": "Qualified foreign form Apply opens GenericQuestionDialog; Yes dispatches the confirmed action and No sends no action while retaining the draft. Domestic Apply submits directly; closing a dirty draft offers Apply or Discard.",
        "error_state": "Invalid, foreign, stale, or uncontrolled requests are rejected without changing the affected government fields.",
        "restrictions_confirmation_error": "REFERENCE numeric form IDs are not mapped one-to-one; the exact gained-proportion formula is unavailable, so OpenPower uses a documented region-count proxy. Broader source-specific martial-law effects are not inferred.",
        "action_required": "Keep the domestic route and qualified foreign-form 75% threshold, confirmation, release/access effects, and stale-state checks covered; preserve the exact REFERENCE proportion formula and government-type mapping as open gaps.",
        "status": "partial",
    },
    "Constitutional_Form/frmInner/frmCapital/cboCapital": {
        "reference_side_effect": "GConstitutionalFormWindow::OnCustomEvent stages m_iCapitalId and marks the source window dirty; Save later includes the capital in GConstitutionalFormUpdate.",
        "openpower_surface": "ConstitutionalFormPanel._render_content / ActionSetCountryCapital",
        "openpower_effect": "Stages a region selection; only the controlled country's Apply dispatches ActionSetCountryCapital. Foreign capital changes are disabled in the source-aligned panel and rejected by server authority checks.",
        "game_action": "ActionSetCountryCapital(player_id, country_tag, expected_capital_region_id, target_region_id)",
        "read_only_or_state_changing": "local selection draft until Apply, then authoritative state change",
        "validation_condition": "The issuer must control the country; the target region must exist and be controlled by that country; the submitted expected capital must still match the server row.",
        "country_scope_restriction": "Domestic only; the selector is disabled for foreign country targets.",
        "confirmation_state": "No foreign confirmation is offered because REFERENCE disables the foreign capital control. Domestic Apply submits directly; dirty close still offers Apply or Discard.",
        "error_state": "Unauthorized, stale, unknown, or uncontrolled targets are rejected and leave the capital unchanged.",
        "restrictions_confirmation_error": "REFERENCE may list cities; OpenPower provides region-level capitals and uses its authoritative region control data.",
        "action_required": "Keep the selector region-based until an authoritative OpenPower city-to-region capital model exists.",
        "status": "partial",
    },
    "Constitutional_Form/frmInner/frmConstitutionalForm/cboConstitutionalForm": {
        "reference_side_effect": "Selecting a source government form marks the window dirty and updates election/override presentation; Save includes the selected government type.",
        "openpower_surface": "ConstitutionalFormPanel._render_content",
        "openpower_effect": "Stages a compatible OpenPower government form; domestic Apply sends ActionSetGovernmentForm directly. A foreign form can be staged only when at least 75% of target political regions are under player control and the target is non-hostile; Apply then requires GenericQuestionDialog confirmation.",
        "game_action": "ActionSetGovernmentForm(player_id, country_tag, expected_form_id, target_form_id, confirmed_foreign_change=True for qualified foreign targets)",
        "read_only_or_state_changing": "local selection draft until Apply, then authoritative government transition",
        "validation_condition": "Only compatible forms are shown; the server rechecks own-country authority or the foreign non-hostile 75% regional-control threshold plus confirmation, stale form state, political crises, eligible-party limits, and target election rules.",
        "country_scope_restriction": "Domestic form changes are enabled for the controlled country. Foreign form changes are enabled only at the non-hostile 75% regional-control threshold; foreign capital, override and martial-law changes remain disabled.",
        "confirmation_state": "Qualified foreign Apply opens GenericQuestionDialog; Yes submits the draft and No preserves it. Closing a domestic draft offers Apply or Discard.",
        "error_state": "Invalid, unauthorized, stale, crisis-blocked, or party-incompatible form changes are rejected without changing political state.",
        "restrictions_confirmation_error": "OpenPower form IDs and labels do not have a verified one-to-one mapping to REFERENCE government type IDs 1-9; the server uses OpenPower form rules.",
        "action_required": "Keep the rules-based form selector and its server checks covered; complete source type mapping separately from martial-law and foreign-country workflows.",
        "status": "partial",
    },
    "Constitutional_Form/frmInner/frmNextElection/btnOverride": {
        "reference_side_effect": "The source override control selects military dictatorship in the form combo; Apply later sends the constitutional update.",
        "openpower_surface": "ConstitutionalFormPanel._render_content",
        "openpower_effect": "When the controlled country remains on a supported multi-party/single-party democratic form, has no martial law or pending form change, and exactly one eligible military-led form is available, the control stages that form in the selector. Regular Apply then sends ActionSetGovernmentForm; the button itself sends no action.",
        "game_action": "ActionSetGovernmentForm(player_id, country_tag, expected_form_id, target_form_id) on Apply",
        "read_only_or_state_changing": "local form draft until Apply; then authoritative government transition",
        "validation_condition": "Requires the controlled country, a mapped electoral source form, no martial law or pending form change, and exactly one valid military-led target; Apply/server validation rechecks authority, expected form, active crisis, party count and target-form rules.",
        "country_scope_restriction": "Domestic only; the override button is disabled for foreign targets.",
        "confirmation_state": "The button stages the military-led form for the controlled country; Apply submits it after the normal local review.",
        "error_state": "An invalid or stale form transition is rejected by the server and surfaced through GenericMessageDialog.",
        "restrictions_confirmation_error": "The source callback's regime change is not OpenPower ActionSetElectionOverride; it is represented by the validated government-form transition. OpenPower's form IDs are not a complete numeric mapping for REFERENCE types 1-9.",
        "action_required": "Keep the supported-form guards and the staged-then-Apply journey covered; extend the mapping only when authoritative form equivalence is established.",
        "status": "verified_openpower",
    },
    "Constitutional_Form/frmInner/btnDeclareMartialLaw": {
        "reference_side_effect": "The source button toggles martial law in the dirty constitutional profile; Apply later sends the value to the server.",
        "openpower_surface": "ConstitutionalFormPanel._render_content / _apply_changes",
        "openpower_effect": "Stages a domestic martial-law toggle in the constitutional draft; title Apply sends ActionSetGovernmentForm with expected and target status. The server validates authority and stale state, then persists the flag and records history and a domain event. Foreign targets cannot toggle martial law. The active status disables election override.",
        "game_action": "ActionSetGovernmentForm(player_id, country_tag, expected_form_id, target_form_id, expected_martial_law, target_martial_law)",
        "read_only_or_state_changing": "local draft until Apply; then authoritative country-government status change",
        "validation_condition": "The issuer must control the country; the submitted form and expected martial-law value must still match, and the target value must be a boolean.",
        "country_scope_restriction": "Domestic only; the martial-law control is disabled for foreign targets.",
        "confirmation_state": "The button toggles the local draft; domestic Apply submits it. The user can also discard it through the shared close confirmation.",
        "error_state": "Stale or unauthorized requests are rejected and surfaced through the generic message dialog.",
        "restrictions_confirmation_error": "The status transition is authoritative; broader source-specific effects outside the tracked government flag and election controls remain unmapped.",
        "action_required": "Keep the staged toggle, Apply submission, history/event record, and stale-state regression covered.",
        "status": "verified_openpower",
    },
}


def _treaty_detail_interaction(
    *,
    reference: str,
    surface: str,
    effect: str,
    action: str,
    validation: str,
    limitation: str,
    status: str,
) -> dict[str, str]:
    return {
        "reference_side_effect": reference,
        "openpower_surface": surface,
        "openpower_effect": effect,
        "game_action": action,
        "read_only_or_state_changing": "read-only or local UI state" if action.startswith("none") else "state-changing through the listed action when submitted",
        "validation_condition": validation,
        "country_scope_restriction": "Treaty details are scoped to the selected treaty and connected player's controlled country.",
        "confirmation_state": "Create, response, join, leave, and participant changes are dispatched through their listed OpenPower action; dismissing the window sends no action.",
        "error_state": "Authoritative action rejection leaves treaty state unchanged and is surfaced by the existing notice route.",
        "restrictions_confirmation_error": limitation,
        "action_required": limitation,
        "status": status,
    }


TREATY_DETAILS_INTERACTION_BINDINGS = {
    "Treaty_Details_Window/frmTitle/btnExit": _treaty_detail_interaction(
        reference="The base-window title exit hides GTreatyDetailsWindow.",
        surface="LiveTreatiesPanel._render_details_window / WindowManager close control",
        effect="Closes treaty details locally without sending a treaty action.",
        action="none (local window close)",
        validation="The treaty details window is visible.",
        limitation="Keep the title close control bound to local dismissal.",
        status="verified_openpower",
    ),
    "Treaty_Details_Window/frmTitle/btnApply": _treaty_detail_interaction(
        reference="GTreatyDetailsWindow::OnCreate hides the inherited title Apply control.",
        surface="No OpenPower control; the source-hidden button is omitted.",
        effect="No Apply action is exposed in the title bar; proposal submission is a separate editor action.",
        action="none (source control hidden)",
        validation="The source hides this inherited control during window creation.",
        limitation="Keep the hidden source Apply slot from appearing as an active control.",
        status="verified_unavailable",
    ),
    "Treaty_Details_Window/frmInner/frmConditions/cboRelations": _treaty_detail_interaction(
        reference="The source relation combo selection is converted to RelationsNotAtWar when conditions are saved.",
        surface="LiveTreatyEditorPanel._render_content / ActionCreateTreaty.conditions.minimum_relation",
        effect="OpenPower exposes a numeric minimum relation slider in proposal creation; treaty details render the saved treaty read-only.",
        action="ActionCreateTreaty.conditions.minimum_relation",
        validation="Only long-term treaty definitions expose editable proposal conditions.",
        limitation="REFERENCE's relation enum is represented by an OpenPower numeric threshold; the detail window does not edit an existing treaty condition.",
        status="partial",
    ),
    "Treaty_Details_Window/frmInner/frmConditions/cboGeographicProximity": _treaty_detail_interaction(
        reference="The source geographic combo selection is converted to a geographic-region condition when conditions are saved.",
        surface="LiveTreatyEditorPanel._render_content / ActionCreateTreaty.conditions.maximum_geographic_distance_km",
        effect="OpenPower exposes a numeric maximum-distance slider in proposal creation; treaty details render the saved treaty read-only.",
        action="ActionCreateTreaty.conditions.maximum_geographic_distance_km",
        validation="Only long-term treaty definitions expose editable proposal conditions.",
        limitation="REFERENCE uses named geographic regions; OpenPower uses a distance threshold, so the values are not one-to-one.",
        status="partial",
    ),
    "Treaty_Details_Window/frmInner/frmConditions/cboPoliticalStrength": _treaty_detail_interaction(
        reference="The source political-similitude combo stores an REFERENCE political-status criterion.",
        surface="LiveTreatyEditorPanel._render_content / ActionCreateTreaty.conditions.government_type",
        effect="OpenPower exposes a government-type text condition in proposal creation; treaty details render saved conditions read-only.",
        action="ActionCreateTreaty.conditions.government_type",
        validation="Only long-term treaty definitions expose editable proposal conditions.",
        limitation="The source political rank/status choices have no exact OpenPower enum mapping; a government-type string is only a proxy.",
        status="partial",
    ),
    "Treaty_Details_Window/frmInner/frmConditions/cboEconomicStrength": _treaty_detail_interaction(
        reference="The source economic-similitude combo stores an REFERENCE rank threshold.",
        surface="LiveTreatyEditorPanel._render_content / ActionCreateTreaty.conditions.max_economic_strength_ratio",
        effect="OpenPower exposes a numeric economic-strength ratio in proposal creation; treaty details render saved conditions read-only.",
        action="ActionCreateTreaty.conditions.max_economic_strength_ratio",
        validation="Only long-term treaty definitions expose editable proposal conditions.",
        limitation="REFERENCE's Top 10/25/50/100 rank choices are not equivalent to an OpenPower strength ratio.",
        status="partial",
    ),
    "Treaty_Details_Window/frmInner/frmConditions/cboMilitaryStrength": _treaty_detail_interaction(
        reference="The source military-similitude combo stores an REFERENCE rank threshold.",
        surface="LiveTreatyEditorPanel._render_content / ActionCreateTreaty.conditions.max_military_strength_ratio",
        effect="OpenPower exposes a numeric military-strength ratio in proposal creation; treaty details render saved conditions read-only.",
        action="ActionCreateTreaty.conditions.max_military_strength_ratio",
        validation="Only long-term treaty definitions expose editable proposal conditions.",
        limitation="REFERENCE's Top 10/25/50/100 rank choices are not equivalent to an OpenPower strength ratio.",
        status="partial",
    ),
    "Treaty_Details_Window/frmInner/frmConditions/cboResearchLevel": _treaty_detail_interaction(
        reference="The source research-similitude combo stores an REFERENCE research-level criterion.",
        surface="LiveTreatyEditorPanel._render_content / ActionCreateTreaty.conditions.max_research_ratio",
        effect="OpenPower exposes a numeric research ratio in proposal creation; treaty details render saved conditions read-only.",
        action="ActionCreateTreaty.conditions.max_research_ratio",
        validation="Only long-term treaty definitions expose editable proposal conditions.",
        limitation="The source research-level choices do not map one-to-one to OpenPower's numeric research ratio.",
        status="partial",
    ),
    "Treaty_Details_Window/frmInner/frmPressure/frmGradient/btnFill": _treaty_detail_interaction(
        reference="The source pressure gradient fill is a display fragment updated from pressure totals; it has no independent click action.",
        surface="LiveTreatiesPanel._render_pressure_fallback / GMLWidgets.meter",
        effect="Shows an empty source-sized meter because OpenPower has no treaty-pressure total field.",
        action="none (display-only meter; source pressure value unavailable)",
        validation="The treaty details window is visible.",
        limitation="Keep the meter empty and pair it with the explicit N/A value; do not infer pressure from ordinary members.",
        status="verified_unavailable",
    ),
    "Treaty_Details_Window/frmInner/frmPressure/frmGradient/btnUnfilled": _treaty_detail_interaction(
        reference="The source pressure gradient unfilled segment is a display fragment updated from pressure totals; it has no independent click action.",
        surface="LiveTreatiesPanel._render_pressure_fallback / GMLWidgets.meter",
        effect="Shows the empty remainder of the source-sized meter because OpenPower has no treaty-pressure total field.",
        action="none (display-only meter; source pressure value unavailable)",
        validation="The treaty details window is visible.",
        limitation="Keep the meter empty and pair it with the explicit N/A value; do not infer pressure from ordinary members.",
        status="verified_unavailable",
    ),
    "Treaty_Details_Window/frmInner/frmPressure/btnSponsor": _treaty_detail_interaction(
        reference="The source sponsor button sends GTreatyJoin or GTreatyLeave with special pressure side 3.",
        surface="LiveTreatiesPanel._render_pressure_fallback",
        effect="Preserves the source button slot as disabled and explains that pressure sponsorship is not modeled.",
        action="none (pressure sponsorship unavailable)",
        validation="OpenPower has no separate treaty pressure-membership side or total.",
        limitation="Ordinary ActionJoinTreaty membership is not a substitute for the source pressure side; keep this control disabled.",
        status="verified_unavailable",
    ),
    "Treaty_Details_Window/frmInner/frmPressure/lstPressure": _treaty_detail_interaction(
        reference="The source pressure list displays countries sponsoring a treaty outside its ordinary membership sides.",
        surface="LiveTreatiesPanel._render_pressure_fallback",
        effect="Shows an explicit no-data explanation in the source list slot.",
        action="none (read-only list; pressure-country data unavailable)",
        validation="The treaty details window is visible.",
        limitation="OpenPower does not store source pressure-country totals or membership; keep the list explicitly unavailable.",
        status="verified_unavailable",
    ),
    "Treaty_Details_Window/frmInner/frmMain/frmModify/btnRefuse": _treaty_detail_interaction(
        reference="The source Refuse button sends GTreatyLeave for the controlled country in refusal-capable treaty states.",
        surface="LiveTreatiesPanel._render_proposal_response_actions / treaties.details.reject",
        effect="Rejects the pending proposal for the controlled country.",
        action="ActionRespondTreaty(player_id, proposal_id, country_tag, accept=False)",
        validation="Shown only when the local country is a required responder to the selected pending proposal.",
        limitation="OpenPower's response action rejects the pending proposal; it does not reproduce every REFERENCE inactive-member refusal state.",
        status="partial",
    ),
    "Treaty_Details_Window/frmInner/frmMain/frmModify/btnModify": _treaty_detail_interaction(
        reference="Modify opens Add_Remove_Window; Join and Leave dispatch GTreatyJoin or GTreatyLeave for the controlled country.",
        surface="LiveTreatiesPanel._render_details_window and _render_actions / TreatyParticipantDialog",
        effect="Pending responder actions use Accept/Reject; sponsor participant editing uses the local member editor and ActionUpdateTreatyParticipants; ordinary Join/Leave is available from the selected active treaty actions.",
        action="ActionUpdateTreatyParticipants, ActionJoinTreaty, or ActionLeaveTreaty depending on the selected state",
        validation="Requires a pending response, sponsor-authorized multi-member edit, or an eligible controlled country for Join/Leave.",
        limitation="The source reuses one button for several states; OpenPower splits some actions between details and treaty-list controls.",
        status="partial",
    ),
    "Treaty_Details_Window/frmInner/frmMain/btnCancel": _treaty_detail_interaction(
        reference="The source Cancel button hides the window without sending a game event.",
        surface="LiveTreatiesPanel._render_details_window / treaties.details.close",
        effect="Closes the details window locally.",
        action="none (local window close)",
        validation="The treaty details window is visible.",
        limitation="Keep Cancel as a local close action.",
        status="verified_openpower",
    ),
    "Treaty_Details_Window/frmInner/frmMain/cboType": _treaty_detail_interaction(
        reference="The source type combo selects one of 17 REFERENCE treaty types for proposal creation.",
        surface="LiveTreatyEditorPanel._render_content / TREATY_DEFINITIONS",
        effect="Proposal creation selects from OpenPower treaty definitions, including source analogues and the OpenPower-only mobility agreement.",
        action="ActionCreateTreaty(treaty_type=selected_definition)",
        validation="A supported treaty definition and eligible counterpart must be selected.",
        limitation="OpenPower supports the source treaty analogues plus mobility_agreement; IDs, labels, and order are not one-to-one.",
        status="partial",
    ),
    "Treaty_Details_Window/frmInner/frmMain/edtName": _treaty_detail_interaction(
        reference="The source treaty-name edit box supplies the proposal name; edits are committed through Confirm.",
        surface="LiveTreatyEditorPanel._render_content / treaty.proposal.title",
        effect="Edits the local proposal title and submits it through ActionCreateTreaty.",
        action="ActionCreateTreaty(title=proposal_title)",
        validation="The title is checked for non-empty and duplicate treaty names before submission.",
        limitation="OpenPower supports proposal titles; existing treaty titles are read-only.",
        status="partial",
    ),
    "Treaty_Details_Window/frmInner/frmMain/lstCountriesB": _treaty_detail_interaction(
        reference="The source side B list displays or edits treaty participants through Add_Remove_Window.",
        surface="LiveTreatiesPanel._render_details_member_list / TreatyParticipantDialog",
        effect="Displays side B members in GML geometry; authorized participant changes are staged in TreatyParticipantDialog and submitted with Apply.",
        action="ActionUpdateTreatyParticipants on Apply when editing an active multi-member treaty",
        validation="Editing is restricted to the connected sponsor of an active multi-member treaty.",
        limitation="OpenPower keeps membership side editing in a separate draft dialog; the detail list itself is read-only.",
        status="partial",
    ),
    "Treaty_Details_Window/frmInner/frmMain/lstCountriesA": _treaty_detail_interaction(
        reference="The source side A list displays or edits treaty participants through Add_Remove_Window.",
        surface="LiveTreatiesPanel._render_details_member_list / TreatyParticipantDialog",
        effect="Displays side A members in GML geometry; authorized participant changes are staged in TreatyParticipantDialog and submitted with Apply.",
        action="ActionUpdateTreatyParticipants on Apply when editing an active multi-member treaty",
        validation="Editing is restricted to the connected sponsor of an active multi-member treaty.",
        limitation="OpenPower keeps membership side editing in a separate draft dialog; the detail list itself is read-only.",
        status="partial",
    ),
    "Treaty_Details_Window/frmInner/frmMain/btnConfirm": _treaty_detail_interaction(
        reference="Source Confirm assembles the treaty and sends GTreatyDetailsTreatyAdd to the server.",
        surface="LiveTreatyEditorPanel._render_content / treaty.proposal.submit",
        effect="Submits validated proposal data and conditions through ActionCreateTreaty.",
        action="ActionCreateTreaty(...) ",
        validation="Requires an eligible counterpart, valid title, allowed proposal type, and valid participant sides; the server revalidates diplomacy and treaty restrictions.",
        limitation="OpenPower uses a separate proposal form and its native treaty conditions; source localization, exact IDs, and condition taxonomies remain different.",
        status="partial",
    ),
    "Treaty_Details_Window/frmInner/frmMain/togOpen": _treaty_detail_interaction(
        reference="The source open toggle is inverted into GTreaty.Private when the proposal is confirmed.",
        surface="LiveTreatyEditorPanel._render_content / ActionCreateTreaty.open_to_new_members",
        effect="Controls whether eligible new members may join a long-term OpenPower treaty proposal; the details toggle is read-only.",
        action="ActionCreateTreaty(open_to_new_members=selected_value)",
        validation="Only long-term treaty definitions expose the proposal membership toggle.",
        limitation="OpenPower stores open_to_new_members directly; this does not reproduce REFERENCE's private-flag inversion or active treaty edit behavior.",
        status="partial",
    ),
    "Treaty_Details_Window/frmInner/frmMain/edtNameOver": _treaty_detail_interaction(
        reference="The source overlay edit box is hidden until a name-edit interaction begins, then copies the edit back to the base name field.",
        surface="Treaty details title is read-only; proposal title editing is in LiveTreatyEditorPanel.",
        effect="No inline rename action exists for an already-created OpenPower treaty.",
        action="none (existing treaty title is read-only)",
        validation="The selected treaty is already created.",
        limitation="Keep the details title read-only; a server-authoritative treaty rename action is not available.",
        status="verified_unavailable",
    ),
}

TREATY_DETAILS_INTERACTION_BINDINGS.update(TREATY_PARTICIPANT_INTERACTION_BINDINGS)


def _treaty_detail_display(
    state_binding: str,
    units: str,
    fallback: str,
    update_rule: str,
    meaning: str,
    *,
    status: str = "partial",
    action_required: str = "Keep the REFERENCE slot documented while preserving the OpenPower data semantics.",
) -> DisplayBinding:
    return DisplayBinding(
        state_binding,
        units,
        fallback,
        update_rule,
        "src/client/ui/panels/politics/treaties_live.py; src/client/ui/panels/politics/treaty_editor_live.py; modules/base/systems/world/treaty_diplomacy.py",
        meaning,
        status,
        action_required,
    )


def _treaty_detail_caption(text: str, meaning: str) -> DisplayBinding:
    return _treaty_detail_display(
        f"literal English caption: {text}",
        "caption",
        f"{text}; source localization resource is unavailable.",
        "Constant while the treaty details window is open.",
        meaning,
        status="partial",
        action_required="Keep the text in its source GML slot; use a localized token when the verified source language bundle is available.",
    )


DISPLAY_BINDINGS_BY_WINDOW["Treaty_Details_Window"].update({
    "frmTitle/lblTitle": _treaty_detail_display(
        "literal English panel caption",
        "title label",
        "TREATIES; source localization resource is unavailable.",
        "Constant while treaty details are open.",
        "Treaty-details title caption.",
    ),
    "frmInner/frmMain/lblType": _treaty_detail_caption("TYPE", "Treaty-type field caption."),
    "frmInner/frmMain/lblName": _treaty_detail_caption("NAME", "Treaty-name field caption."),
    "frmInner/frmMain/lblName1": _treaty_detail_caption("STATUS", "Treaty lifecycle-status caption."),
    "frmInner/frmMain/lblSideA": _treaty_detail_caption("SIDE A", "First treaty membership side caption."),
    "frmInner/frmMain/lblSideB": _treaty_detail_caption("SIDE B", "Second treaty membership side caption."),
    "frmInner/frmPressure/lblTitle": _treaty_detail_caption("PRESSURE", "Pressure-membership section caption."),
    "frmInner/frmEligibleCountries/lblTitle": _treaty_detail_caption("ELIGIBLE COUNTRIES", "Current treaty eligibility section caption."),
    "frmInner/frmConditions/lblRelations": _treaty_detail_caption("RELATIONS", "Source relationship-condition caption."),
    "frmInner/frmConditions/lblGeographicProximity": _treaty_detail_caption("GEOGRAPHIC PROXIMITY", "Source geographic-condition caption."),
    "frmInner/frmConditions/lblPoliticalStr": _treaty_detail_caption("POLITICAL STRENGTH", "Source political-condition caption."),
    "frmInner/frmConditions/lblEconomicStr": _treaty_detail_caption("ECONOMIC STRENGTH", "Source economic-condition caption."),
    "frmInner/frmConditions/lblMilitaryStr": _treaty_detail_caption("MILITARY STRENGTH", "Source military-condition caption."),
    "frmInner/frmConditions/lblResearchLvl": _treaty_detail_caption("RESEARCH LEVEL", "Source research-condition caption."),
    "frmInner/frmMain/lblOpen": _treaty_detail_display(
        "countries_treaties.open_to_new_members / pending_treaties.open_to_new_members",
        "boolean state caption",
        "OPEN TO NEW MEMBERS or CLOSED TO NEW MEMBERS from the selected treaty row; false when absent.",
        "Read from the current treaty row each frame; proposal editor stores its draft with ActionCreateTreaty.",
        "Whether eligible countries may join the treaty.",
        action_required="Keep the toggle read-only in treaty details and use the proposal editor for new treaty settings.",
    ),
    "frmInner/frmMain/cboType": _treaty_detail_display(
        "countries_treaties.type / pending_treaties.treaty_type",
        "OpenPower treaty type ID",
        "Unknown when the row has no supported treaty type; display title-cased OpenPower ID otherwise.",
        "Read from the selected treaty or proposal row each frame.",
        "Selected treaty type; OpenPower has source analogues plus mobility_agreement.",
        action_required="Preserve the OpenPower type ID while documenting source ID and label differences.",
    ),
    "frmInner/frmMain/txtStatus": _treaty_detail_display(
        "countries_treaties.status / pending_treaties.status",
        "lifecycle status",
        "Unknown when the selected row has no status.",
        "Read from the selected treaty or proposal row each frame.",
        "Selected treaty lifecycle status.",
    ),
    "frmInner/frmMain/frmDescription/txtDetail": _treaty_detail_display(
        "pending_treaties.terms and treaty_effects filtered by treaty_id",
        "terms and effect descriptions",
        "No additional treaty details are recorded when terms and effects are absent.",
        "Read from the selected treaty row and matching treaty_effects rows each frame; lifecycle notices replace the description after a transition.",
        "Treaty terms, recorded effects, or lifecycle information.",
        action_required="Keep terms and recorded effects tied to the selected treaty ID; do not synthesize absent effect details.",
    ),
    "frmInner/frmMain/lstCountriesA": _treaty_detail_display(
        "countries_treaties.side_a / pending_treaties.side_a",
        "country tags and names",
        "No members recorded when the selected row has no side A tags; country tags remain visible if localized names are missing.",
        "Read and normalized from the selected treaty or proposal row each frame.",
        "Read-only side A member list; edits occur through the participant draft dialog.",
        action_required="Keep the displayed tags bound to the selected row and preserve side membership separately from pressure sponsors.",
    ),
    "frmInner/frmMain/lstCountriesB": _treaty_detail_display(
        "countries_treaties.side_b / pending_treaties.side_b",
        "country tags and names",
        "No members recorded when the selected row has no side B tags; country tags remain visible if localized names are missing.",
        "Read and normalized from the selected treaty or proposal row each frame.",
        "Read-only side B member list; edits occur through the participant draft dialog.",
        action_required="Keep the displayed tags bound to the selected row and preserve side membership separately from pressure sponsors.",
    ),
    "frmInner/frmEligibleCountries/lstEligibleCountries": DisplayBinding(
        "countries.id filtered by DiplomacySystem.eligible_treaty_countries(state, current_treaty)",
        "country flags, tags, and localized names",
        "Empty-state label when no country is eligible; missing names fall back to country tags and missing flags use FlagRenderer's fallback.",
        "Recomputed from current treaty conditions and diplomacy state on each visible detail render.",
        "src/client/ui/panels/politics/treaties_live.py; modules/base/systems/world/treaty_diplomacy.py; modules/base/systems/world/treaty_geography.py; src/shared/treaties.py",
        "Countries that satisfy the selected active treaty's current membership conditions.",
        "verified_openpower",
        "Keep eligibility derived from the current state and do not expose private country fields.",
    ),
    "frmInner/frmConditions/lblTitle": _treaty_detail_display(
        "literal English caption",
        "section label",
        "CONDITIONS; source localization resource is unavailable.",
        "Caption is constant; its tooltip discloses the OpenPower-only allow_members_at_war value from the selected row.",
        "Treaty condition section heading and tooltip for the additional OpenPower admission condition.",
    ),
    "frmInner/frmConditions/cboRelations": _treaty_detail_display(
        "decode_conditions(countries_treaties.conditions_json / pending_treaties.conditions_json).minimum_relation; ActionCreateTreaty.conditions.minimum_relation",
        "OpenPower relation points, -100 to 100",
        "REFERENCE relation enum values are not mapped; proposal editor starts at -100.",
        "Stored with the pending proposal; details read the current treaty row each frame.",
        "Source relationship-category chooser; OpenPower uses a numeric threshold in proposal creation.",
        action_required="Keep the numeric proxy labeled as OpenPower-native; exact REFERENCE relation-category mapping remains open.",
    ),
    "frmInner/frmConditions/cboGeographicProximity": _treaty_detail_display(
        "decode_conditions(countries_treaties.conditions_json / pending_treaties.conditions_json).maximum_geographic_distance_km; ActionCreateTreaty.conditions.maximum_geographic_distance_km",
        "kilometers",
        "REFERENCE region labels are not mapped; 0 means no distance limit in OpenPower.",
        "Stored with the pending proposal; details read the current treaty row each frame.",
        "Source named-region chooser; OpenPower uses a maximum-distance threshold.",
        action_required="Keep distance units explicit; source region-to-distance conversion is unavailable.",
    ),
    "frmInner/frmConditions/cboPoliticalStrength": _treaty_detail_display(
        "decode_conditions(countries_treaties.conditions_json / pending_treaties.conditions_json).government_type; ActionCreateTreaty.conditions.government_type",
        "government-type identifier",
        "Empty string means no government-type restriction; REFERENCE political rank taxonomy is unavailable.",
        "Stored with the pending proposal; details read the current treaty row each frame.",
        "Source political-similitude chooser; OpenPower uses a government-type condition.",
        action_required="Keep government type as a documented proxy rather than an asserted REFERENCE equivalent.",
    ),
    "frmInner/frmConditions/cboEconomicStrength": _treaty_detail_display(
        "decode_conditions(countries_treaties.conditions_json / pending_treaties.conditions_json).max_economic_strength_ratio; ActionCreateTreaty.conditions.max_economic_strength_ratio",
        "ratio",
        "0 means no ratio limit; source Top 10/25/50/100 choices are not convertible without REFERENCE rank data.",
        "Stored with the pending proposal; details read the current treaty row each frame.",
        "Source economic-rank chooser; OpenPower uses a numeric economic-strength ratio.",
        action_required="Keep the ratio clearly identified as OpenPower-native; exact rank parity requires source rank arrays.",
    ),
    "frmInner/frmConditions/cboMilitaryStrength": _treaty_detail_display(
        "decode_conditions(countries_treaties.conditions_json / pending_treaties.conditions_json).max_military_strength_ratio; ActionCreateTreaty.conditions.max_military_strength_ratio",
        "ratio",
        "0 means no ratio limit; source Top 10/25/50/100 choices are not convertible without REFERENCE rank data.",
        "Stored with the pending proposal; details read the current treaty row each frame.",
        "Source military-rank chooser; OpenPower uses a numeric military-strength ratio.",
        action_required="Keep the ratio clearly identified as OpenPower-native; exact rank parity requires source rank arrays.",
    ),
    "frmInner/frmConditions/cboResearchLevel": _treaty_detail_display(
        "decode_conditions(countries_treaties.conditions_json / pending_treaties.conditions_json).max_research_ratio; ActionCreateTreaty.conditions.max_research_ratio",
        "ratio",
        "0 means no ratio limit; source research-level categories are not mapped to an OpenPower ratio.",
        "Stored with the pending proposal; details read the current treaty row each frame.",
        "Source research-level chooser; OpenPower uses a numeric research-strength ratio.",
        action_required="Keep the ratio clearly identified as OpenPower-native; exact source research categories are unavailable.",
    ),
    "frmInner/frmPressure/txtValue": _treaty_detail_display(
        "unavailable: no treaty pressure total in OpenPower state",
        "source pressure percentage unavailable",
        "N/A; OpenPower does not track REFERENCE treaty pressure-country totals.",
        "Constant unavailable fallback while treaty details are open.",
        "Pressure total; no authoritative OpenPower source field.",
        status="verified_unavailable",
        action_required="Retain N/A until an authoritative pressure model exists; do not derive it from regular members.",
    ),
    "frmInner/frmPressure/frmGradient": _treaty_detail_display(
        "unavailable: no treaty pressure total in OpenPower state",
        "source gradient meter unavailable",
        "Empty source-sized meter paired with N/A.",
        "Constant empty fallback while treaty details are open.",
        "Visual pressure total meter; no authoritative OpenPower source field.",
        status="verified_unavailable",
        action_required="Keep the source geometry but leave the meter empty until pressure totals are modeled.",
    ),
    "frmInner/frmPressure/lstPressure": _treaty_detail_display(
        "unavailable: no pressure-country membership set in OpenPower state",
        "country list unavailable",
        "Explicit no-data explanation in the source list slot.",
        "Constant unavailable fallback while treaty details are open.",
        "Countries sponsoring the treaty on REFERENCE pressure side 3.",
        status="verified_unavailable",
        action_required="Keep the no-data explanation; ordinary membership rows are not pressure sponsors.",
    ),
})


def _economic_health_caption(text: str, meaning: str) -> DisplayBinding:
    return DisplayBinding(
        f"literal source-style caption: {text}",
        "caption",
        f"English caption; the verified REFERENCE localization string for token text is unavailable.",
        "Constant while the source economic-health panel is visible.",
        "src/client/ui/panels/economic_health_panel.py; .codex/layout_catalog.gml",
        meaning,
        status="partial",
        action_required="Keep the caption in its GML slot and use a verified localization token when the source language bundle is available.",
    )


DISPLAY_BINDINGS_BY_WINDOW["Economic_Window"] = {
    "frmTitle/lblTitle": _economy_caption_binding("100002", "ECONOMY", "Window title."),
    "frmInner/frmResources/lblTitle": _economy_caption_binding(
        "100047", "RESOURCES", "Resource-health section title."
    ),
    "frmInner/frmEconomicModel/lblTitle": _economy_caption_binding(
        "100165", "ECONOMIC MODEL", "Economic-model section title."
    ),
    "frmInner/frmEconomicModel/lblStateControlled": _economy_caption_binding(
        "100039", "State", "State-controlled economic-model endpoint."
    ),
    "frmInner/frmEconomicModel/lblFreeMarket": _economy_caption_binding(
        "100040", "Market", "Free-market economic-model endpoint."
    ),
    "frmInner/frmBudget/lblTitle": _economy_caption_binding(
        "100042", "BUDGET", "Budget section title."
    ),
    "frmInner/frmEconomicHealth/lblTitle": _economy_caption_binding(
        "100166", "ECONOMIC HEALTH", "Economic-health section title."
    ),
}


DISPLAY_BINDINGS_BY_WINDOW["Resources_Window"] = {
    "frmTitle/lblTitle": _resources_caption_binding(
        "100047", "RESOURCES MENU", "Window title."
    ),
    "frmInner/frmResources/lblMarketShare": _resources_caption_binding(
        "100343", "MKT SHARE", "Market-share percentage label."
    ),
    "frmInner/frmResources/lblGlobalTaxMod": _resources_caption_binding(
        "100341", "GLOBAL TAX", "Global resource-tax label; the associated modifier has no OpenPower field."
    ),
    "frmInner/frmResources/lblDesired": _resources_caption_binding(
        "100345", "DESIRED", "Desired import/export amount label; its input stays unavailable in OpenPower."
    ),
    "frmInner/frmResources/lblTrade": _resources_caption_binding(
        "100066", "MARKET FLOW", "Resource-ledger trade-value column header."
    ),
    "frmInner/frmResources/lblProduction": _resources_caption_binding(
        "100064", "PRODUCTION", "Resource-ledger production column header."
    ),
    "frmInner/frmResources/lblActual": _resources_caption_binding(
        "100346", "ACTUAL", "Recorded per-resource trade value label."
    ),
    "frmInner/frmResources/lblSectorTax": _resources_caption_binding(
        "100078", "RESOURCE TAX", "Per-resource tax label."
    ),
    "frmInner/frmResources/lblMeetConsumption": _resources_caption_binding(
        "100347", "Meet consumption", "Source policy caption; OpenPower keeps the unsupported toggle disabled."
    ),
    "frmInner/frmResources/lblStatus": _resources_caption_binding(
        "100077", "LEGAL STATUS", "Per-resource legal-status label."
    ),
    "frmInner/frmResources/lblAvailable": DisplayBinding(
        "No direct stock-availability binding; ResourcesPanel renders resource_ledger.balance_usd as net flow.",
        "OpenPower resource-ledger balance in USD",
        "REFERENCE's available-stock quantity is not present in OpenPower's resource-ledger schema.",
        "Read from the active country's current resource_ledger snapshot while ResourcesPanel is visible.",
        "src/client/ui/panels/resources_panel.py; modules/base/schema.py; .codex/layout_catalog.gml",
        "The source label requests available stock. OpenPower's BALANCE is a net flow, not stock availability, so the values are not equivalent.",
        status="partial",
        action_required="Keep this source slot explicitly unmatched until OpenPower exposes an authoritative stock-availability field; do not relabel net flow as available stock.",
        surface="resources.panel",
    ),
    "frmInner/frmResources/lblManagement": _resources_caption_binding(
        "100076", "MANAGEMENT", "Per-resource management-mode label."
    ),
    "frmInner/frmResources/lblMarketAvailability": _resources_caption_binding(
        "100344", "NET BALANCE", "Source availability slot; OpenPower labels its net balance explicitly."
    ),
    "frmInner/frmResources/lblResource": DisplayBinding(
        "ResourcesPanel._render_controls selected_resource converted from its OpenPower resource id",
        "Selected OpenPower resource display name",
        "Select a Resource when no resource row is selected.",
        "Updated when a row is selected from the active country's resource_ledger-backed list.",
        "src/client/ui/panels/resources_panel.py; modules/base/schema.py; .codex/layout_catalog.gml",
        "OpenPower resolves the selected resource through its own resource catalog and displays its id-derived name; it does not substitute the REFERENCE resource list or localization.",
        status="partial",
        action_required="Keep the selected OpenPower resource catalog and row selection as the source of this value; do not import REFERENCE resource identities.",
        surface="resources.panel",
    ),
    "frmInner/frmResources/lblConsumption": _resources_caption_binding(
        "100340", "CONSUMPTION", "Resource-ledger consumption column header."
    ),
    "frmInner/frmResources/lblGdp": _resources_caption_binding(
        "100342", "SHARE OF GDP", "Resource production as a share of country GDP label."
    ),
    "frmInner/frmResources/lblTrade2": _resources_caption_binding(
        "100066", "TRADE", "Import/export target label; OpenPower has no matching target action."
    ),
    "frmInner/frmResources/txtMarketShare": DisplayBinding(
        "resource_ledger.production_usd for the selected resource / world production_usd for that resource * 100",
        "OpenPower production share of world production (percent)",
        "-- % when the resource, country ledger row, or world production is unavailable.",
        "Recomputed from the selected resource and current country/world resource_ledger rows while the panel is visible.",
        "src/client/ui/panels/resources_panel.py; modules/base/schema.py; .codex/layout_catalog.gml",
        "REFERENCE reads m_fMarketShare; OpenPower derives a production share from its own ledger and resource catalog, so the source formula is not asserted to be identical.",
        status="partial",
        action_required="Keep the OpenPower production-share calculation explicit and preserve the -- % fallback when ledger data is missing.",
        surface="resources.panel",
    ),
    "frmInner/frmResources/txtAvailability": DisplayBinding(
        "resource_ledger.balance_usd for the selected resource, formatted in abbreviated USD",
        "OpenPower net resource-ledger balance (USD)",
        "Unavailable when the selected row or ledger is unavailable.",
        "Recomputed from the selected country's current resource_ledger row while the panel is visible.",
        "src/client/ui/panels/resources_panel.py; modules/base/schema.py; .codex/layout_catalog.gml",
        "REFERENCE displays m_fMarketAvailability as an available-stock quantity. OpenPower's balance_usd is a net flow, not stock availability.",
        status="partial",
        action_required="Keep the net balance label and missing-data fallback; do not claim stock equivalence.",
        surface="resources.panel",
    ),
    "frmInner/frmResources/cboTrade": DisplayBinding(
        "Disabled OpenPower trade selector; no per-resource import/export target action exists.",
        "Unavailable option; selector is disabled.",
        "Unavailable on all OpenPower resource rows.",
        "Rendered disabled while the selected-resource controls are visible.",
        "src/client/ui/panels/resources_panel.py; src/shared/actions.py; .codex/layout_catalog.gml",
        "REFERENCE offers import/export targets. OpenPower records trade flows but has no matching per-resource desired-trade command.",
        status="partial",
        action_required="Keep the selector disabled until an authoritative per-resource trade-target action exists.",
        surface="resources.panel",
    ),
    "frmInner/frmResources/txtGdp": DisplayBinding(
        "selected resource production_usd / selected country's GDP * 100",
        "OpenPower resource production share of country GDP (percent)",
        "-- % when the country GDP or selected-resource ledger row is unavailable.",
        "Recomputed from the active country's GDP and selected-resource ledger row while the panel is visible.",
        "src/client/ui/panels/resources_panel.py; modules/base/schema.py; .codex/layout_catalog.gml",
        "REFERENCE reads m_fPartGdp; OpenPower derives the value from its GDP and production fields, so the source calculation is not asserted to be identical.",
        status="partial",
        action_required="Keep the OpenPower formula and missing-data fallback explicit until source-side DAL semantics are available.",
        surface="resources.panel",
    ),
}


DISPLAY_BINDINGS_BY_WINDOW["System_Bar_Window"] = {
    "txtF1": _system_bar_caption_binding("102211", "Help", "Exact source localization is unavailable."),
    "txtF2": _system_bar_caption_binding("102212", "Chat", "The source lobby route is unavailable in OpenPower."),
    "txtF3": _system_bar_caption_binding("102210", "Save", "Exact source localization is unavailable."),
    "txtF4": _system_bar_caption_binding("102209", "Load", "Exact source localization is unavailable."),
    "txtF5": _system_bar_caption_binding("101596", "Objectives", "Exact source localization is unavailable."),
    "txtF10": _system_bar_caption_binding("102208", "Menu", "Exact source localization is unavailable."),
}


DISPLAY_BINDINGS_BY_WINDOW["Relations_Window"] = {
    "frmTitle/lblTitle": _relations_caption_binding(
        "100153", "RELATIONS", "window title"
    ),
    "frmInner/frmRelations/lblTitle": DisplayBinding(
        "RelationsPresenter._current_value from countries_relations where source=country_a and target=country_b",
        "OpenPower directed relation points, formatted to one decimal place",
        "The word 'unavailable' when the selected directed pair has no current relation row.",
        "Recomputed from the selected country pair each visible frame; timeline data is queried separately for the graph.",
        "src/client/ui/panels/politics/relations_panel.py; src/client/ui/panels/politics/relations_presenter.py; modules/base/schema.py; .codex/layout_catalog.gml",
        "REFERENCE's relation scale is not proven equivalent to OpenPower's directed countries_relations value.",
        status="partial",
        action_required="Keep direction and OpenPower relation-point units explicit; do not claim the source and OpenPower numeric scales are equivalent.",
        surface="relations.panel",
    ),
    "frmInner/frmRelations/lblCountryA": _relations_caption_binding(
        "101031", "Country A", "first selected country control label"
    ),
    "frmInner/frmRelations/lblCountryB": _relations_caption_binding(
        "101030", "Country B", "second selected country control label"
    ),
}


DISPLAY_BINDINGS_BY_WINDOW["Treaties_Window"] = {
    "frmTitle/lblTitle": _treaties_caption_binding("100023", "Treaties", "Window title."),
    "frmInner/frmFilters/lblTitle": _treaties_caption_binding(
        "100586", "FILTERS", "Treaty-list filter section title."
    ),
    "frmInner/frmFilters/lblType": _treaties_caption_binding(
        "100585", "TYPE", "Treaty-type filter label."
    ),
    "frmInner/frmFilters/lblMember": _treaties_caption_binding(
        "100587", "MEMBER", "Treaty-member filter label."
    ),
    "frmInner/frmPendingTreaties/lblTitle": _treaties_caption_binding(
        "100590", "PENDING PROPOSALS", "Pending treaty proposals section title."
    ),
    "frmInner/frmPendingTreaties/lblType": _treaties_caption_binding(
        "100585", "TYPE", "Pending-proposal table type column header."
    ),
    "frmInner/frmPendingTreaties/lblName": _treaties_caption_binding(
        "100584", "NAME", "Pending-proposal table name column header."
    ),
    "frmInner/frmActiveTreaties/lblTitle": _treaties_caption_binding(
        "100583", "ACTIVE TREATIES", "Active treaties section title."
    ),
    "frmInner/frmActiveTreaties/lblType": _treaties_caption_binding(
        "100585", "TYPE", "Active-treaty table type column header."
    ),
    "frmInner/frmActiveTreaties/lblName": _treaties_caption_binding(
        "100584", "NAME", "Active-treaty table name column header."
    ),
}


DISPLAY_BINDINGS_BY_WINDOW["Internal_Laws"] = {
    "frmTitle/lblTitle": _internal_laws_caption_binding(
        "100016", "INTERNAL LAWS", "Window title."
    ),
    "frmInner/frmOrganizations/lblTitle": _internal_laws_caption_binding(
        "100099", "POLITICAL PARTIES", "Political-party section title."
    ),
    "frmInner/frmLaws/lblTitle": _internal_laws_caption_binding(
        "100097", "CIVIL AND FAMILY LAWS", "Law-policy section title."
    ),
    "frmInner/frmDemographicGroups/lblTitle": _internal_laws_caption_binding(
        "100100", "DEMOGRAPHIC GROUPS", "Identity-group section title."
    ),
    "frmInner/frmHumanMigration/lblTitle": _internal_laws_caption_binding(
        "100098", "HUMAN MIGRATION", "Migration-policy section title."
    ),
    "frmInner/frmHumanMigration/lblImmigration": _internal_laws_caption_binding(
        "100122", "Immigration", "Immigration rate label."
    ),
    "frmInner/frmHumanMigration/lblEmigration": _internal_laws_caption_binding(
        "100121", "Emigration", "Emigration rate label."
    ),
    "frmInner/frmDemographicGroups": DisplayBinding(
        "IdentityPolicyView.render for the selected country using identity_group_profiles",
        "identity-group rows with population-share percent, grouped by religion or language",
        "A no-profile message when the selected country's bundled identity profile is unavailable.",
        "Rendered from the selected-country profile and current policy draft each visible frame.",
        "src/client/ui/panels/politics/internal_laws_panel.py; src/client/ui/panels/politics/identity_policy_view.py; modules/base/data/countries/identity_group_profiles.tsv; .codex/layout_catalog.gml",
        "OpenPower uses bundled, source-attributed identity shares in the GML section frame. The REFERENCE demographic chart values are not asserted to use the same data or calculation.",
        status="partial",
        action_required="Keep OpenPower's data source and read-only profile details explicit; do not claim the bundled shares reproduce REFERENCE chart calculations.",
        surface="laws.panel",
    ),
    "frmInner/frmHumanMigration/txtImmigrationValue": DisplayBinding(
        "MigrationPresenter.present_country(state, selected_country).entry_rate",
        "fraction × 100; percentage with one decimal digit",
        "— when the selected country has no migration-policy row or summary.",
        "Read from the selected country's current migration_policies table; MigrationPresenter cache keys include table revisions.",
        "src/client/ui/panels/politics/internal_laws_panel.py; src/client/ui/panels/migration_presenter.py; modules/base/schema.py; .codex/Client/Source/reference_internal_laws_window.cpp",
        "The source displays m_fImmigration × 100 to one decimal. OpenPower displays its continuous entry_rate in the same unit and precision; its migration-policy model is not equivalent to the source's two-choice status combo.",
        status="partial",
        action_required="Preserve one-decimal percentage formatting and label the value as OpenPower's entry rate; do not imply source binary-policy equivalence.",
        surface="laws.panel",
    ),
    "frmInner/frmHumanMigration/txtEmigrationValue": DisplayBinding(
        "MigrationPresenter.present_country(state, selected_country).exit_rate",
        "fraction × 100; percentage with one decimal digit",
        "— when the selected country has no migration-policy row or summary.",
        "Read from the selected country's current migration_policies table; MigrationPresenter cache keys include table revisions.",
        "src/client/ui/panels/politics/internal_laws_panel.py; src/client/ui/panels/migration_presenter.py; modules/base/schema.py; .codex/Client/Source/reference_internal_laws_window.cpp",
        "The source displays m_fEmigration × 100 to one decimal. OpenPower displays its continuous exit_rate in the same unit and precision; its migration-policy model is not equivalent to the source's two-choice status combo.",
        status="partial",
        action_required="Preserve one-decimal percentage formatting and label the value as OpenPower's exit rate; do not imply source binary-policy equivalence.",
        surface="laws.panel",
    ),
}


DISPLAY_BINDINGS_BY_WINDOW["Economic_Health_Window"] = {
    "frmTitle/lblTitle": _economic_health_caption("ECONOMIC HEALTH", "Window title."),
    "frmInner/frmGdp/lblTitle": _economic_health_caption("GDP", "Gross domestic product section."),
    "frmInner/frmGdp/lblTotal": _economic_health_caption("TOTAL", "Total GDP label."),
    "frmInner/frmGdp/lblCapita": _economic_health_caption("PER CAPITA", "GDP-per-person label."),
    "frmInner/frmGdp/lblTax": _economic_health_caption("PERSONAL INCOME TAX", "Personal income tax editor label."),
    "frmInner/frmPopulation/lblTitle": _economic_health_caption("POPULATION", "Population indicators section."),
    "frmInner/frmPopulation/lblUnemployment": _economic_health_caption("UNEMPLOYMENT RATE", "Unemployment indicator label."),
    "frmInner/frmPopulation/lblPoverty": _economic_health_caption("POVERTY RATE", "Poverty indicator label."),
    "frmInner/frmInflation/lblTitle": _economic_health_caption("INFLATION", "Inflation section."),
    "frmInner/frmInflation/lblInterest": _economic_health_caption("INTEREST RATE", "Interest-rate editor label."),
    "frmInner/frmInflation/txtTransparentLabel3": _economic_health_caption("−12%", "Minimum bound on the inflation meter."),
    "frmInner/frmInflation/txtTransparentLabel1": _economic_health_caption("3%", "Interior scale mark on the inflation meter."),
    "frmInner/frmInflation/txtTransparentLabel2": _economic_health_caption("+18%", "Maximum bound on the inflation meter."),
    "frmInner/frmGdp/txtTotal": DisplayBinding(
        "countries.gdp for the selected country",
        "currency; whole-dollar grouping",
        "0 when GDP is absent or not finite.",
        "EconomicHealthPanel reads the selected country row each render; authoritative economic updates refresh the country snapshot.",
        "src/client/ui/panels/economic_health_panel.py; src/client/ui/panels/economy_presenter.py; modules/base/systems/economy/internal_economy_system.py",
        "Selected country's GDP.",
    ),
    "frmInner/frmGdp/txtCapita": DisplayBinding(
        "countries.gdp divided by the sum of pop_14, pop_15_64 and pop_65 in regions currently owned by the selected country",
        "currency per person; whole-dollar grouping",
        "N/A when no positive owned-region population is available; this avoids the source's zero-population division.",
        "Recomputed from the selected country row and its currently owned region rows each render.",
        "src/client/ui/panels/economic_health_panel.py; modules/base/systems/economy/internal_economy_system.py; modules/base/schema.py",
        "GDP per capita using the population data OpenPower exposes.",
        status="partial",
        action_required="Keep this formula labeled as an OpenPower population-derived value; source cached population and country snapshots are not the same data contract.",
    ),
    "frmInner/frmPopulation/txtUnemployment": DisplayBinding(
        "selected country unemployment_rate",
        "fraction × 100; one decimal percent",
        "0.0% when the field is missing or not finite.",
        "Reads the selected country's current EconomyPresenter view each render.",
        "src/client/ui/panels/economic_health_panel.py; src/client/ui/panels/economy_presenter.py; modules/base/schema.py",
        "Selected country's reported unemployment rate.",
    ),
    "frmInner/frmPopulation/txtPoverty": DisplayBinding(
        "selected country poverty_rate",
        "fraction × 100; one decimal percent",
        "0.0% when the field is missing or not finite.",
        "Reads the selected country's current EconomyPresenter view each render.",
        "src/client/ui/panels/economic_health_panel.py; src/client/ui/panels/economy_presenter.py; modules/base/schema.py",
        "Selected country's reported poverty rate.",
    ),
    "frmInner/frmInflation/txtInflation": DisplayBinding(
        "selected country inflation_rate",
        "fraction × 100; one decimal percent",
        "0.0% when the field is missing or not finite.",
        "Reads the selected country's current EconomyPresenter view each render.",
        "src/client/ui/panels/economic_health_panel.py; src/client/ui/panels/economy_presenter.py; modules/base/schema.py",
        "Selected country's reported inflation rate; the delimiter uses the source −12% to +18% range.",
    ),
    "frmInner/frmInflation/frmInterest/edtText": DisplayBinding(
        "selected country interest_rate, staged in EconomicHealthPanel._draft_interest_rate",
        "fraction stored by OpenPower; edited and shown as percent with one decimal",
        "Current value when absent; bounded by the scenario's economic_health_terms before dispatch.",
        "Editable only for the controlled country; changes stay local until title Apply is activated.",
        "src/client/ui/panels/economic_health_panel.py; src/shared/actions.py; modules/base/systems/economy/economic_health_system.py",
        "Draft interest rate.",
        status="partial",
        action_required="Keep the local draft and server validation; REFERENCE submits both values in one GEconomicHealthUpdate event, while OpenPower sends a policy action.",
    ),
    "frmInner/frmGdp/frmTax/edtText": DisplayBinding(
        "countries.personal_income_tax_rate, staged in EconomicHealthPanel._draft_tax_rate",
        "fraction stored by OpenPower; edited and shown as percent with one decimal",
        "Current value when absent; bounded by the scenario's economic_health_terms before dispatch.",
        "Editable only for the controlled country; changes stay local until title Apply is activated.",
        "src/client/ui/panels/economic_health_panel.py; src/shared/actions.py; modules/base/systems/economy/economic_health_system.py",
        "Draft personal income-tax rate.",
        status="partial",
        action_required="Keep the local draft and server validation; REFERENCE submits both values in one GEconomicHealthUpdate event, while OpenPower sends a tax action.",
    ),
}


def _economic_health_interaction(
    *, reference: str, surface: str, effect: str, action: str,
    validation: str, confirmation: str, error: str, limitation: str,
    country_scope: str = "Economic rate edits are enabled only for the controlled country; EconomicHealthSystem rechecks player_controls_country.",
    status: str = "verified_openpower",
) -> dict[str, str]:
    return {
        "reference_side_effect": reference,
        "openpower_surface": surface,
        "openpower_effect": effect,
        "game_action": action,
        "read_only_or_state_changing": "read-only or local UI state" if action.startswith("none") else "state-changing through the listed action when applied",
        "validation_condition": validation,
        "country_scope_restriction": country_scope,
        "confirmation_state": confirmation,
        "error_state": error,
        "restrictions_confirmation_error": limitation,
        "action_required": limitation,
        "status": status,
    }


ECONOMIC_HEALTH_INTERACTION_BINDINGS = {
    "Economic_Health_Window/frmTitle/btnExit": _economic_health_interaction(
        reference="GBaseWindow::ExitWindow hides a clean window; a dirty window uses the save-confirmation preference or opens the shared Apply/Discard prompt.",
        surface="EconomicHealthPanel._render_source_window / DirtyCloseConfirmation",
        effect="Closes locally when clean; dirty drafts require Apply or Discard, and cancelling leaves the panel open.",
        action="ActionChangeEconomicPolicy and ActionSetTax only when Apply is chosen for dirty drafts; none for Discard or clean close",
        validation="Apply is available only when the controlled country still matches the draft country and a network client exists.",
        confirmation="Dirty close presents Apply/Discard; a clean close is immediate.",
        error="Server-side policy rejection is recorded by EconomicHealthSystem; the dialog itself does not mutate country data.",
        limitation="Preserve dirty-close confirmation and keep dismissing the panel free of implicit changes.",
    ),
    "Economic_Health_Window/frmTitle/btnApply": _economic_health_interaction(
        reference="GBaseWindow::Apply calls GEconomicHealthWindow::Save; Save emits GEconomicHealthUpdate only when Dirty and submits both edited rates.",
        surface="EconomicHealthPanel._apply_policy_changes",
        effect="Dispatches only changed staged values as OpenPower policy actions, then records the applied local baseline.",
        action="ActionChangeEconomicPolicy(policy_name='interest_rate') and ActionSetTax",
        validation="Only controlled-country drafts with a network client are enabled; the server checks authority, finite values, scenario bounds, cooldown and transition cost.",
        confirmation="Apply sends immediately without a confirmation prompt.",
        error="EconomicHealthSystem records rejected policy transitions and leaves the country value unchanged.",
        limitation="REFERENCE sends one GEconomicHealthUpdate event; OpenPower routes interest and tax through separate, server-validated actions.",
        status="partial",
    ),
    "Economic_Health_Window/frmInner/frmInflation/frmInterest/btnDown": _economic_health_interaction(
        reference="GUpdatableValue::OnMouseDown decrements the interest editor by 0.1 percentage points and starts the delayed accelerating hold timer; the panel becomes Dirty.",
        surface="EconomicHealthPanel._render_source_rate_control",
        effect="Decreases the local interest draft by 0.1 percentage points; Apply is required to dispatch it.",
        action="none (local draft until title Apply)",
        validation="Enabled only for the controlled country with a network client; clamped to scenario bounds.",
        confirmation="No prompt until the user applies or closes a dirty panel.",
        error="An applied value rejected by the server leaves authoritative data unchanged.",
        limitation="The source repeats after a half-second hold and accelerates its step and cadence; the Python control uses the same source timing and step thresholds.",
    ),
    "Economic_Health_Window/frmInner/frmInflation/frmInterest/btnUp": _economic_health_interaction(
        reference="GUpdatableValue::OnMouseDown increments the interest editor by 0.1 percentage points and starts the delayed accelerating hold timer; the panel becomes Dirty.",
        surface="EconomicHealthPanel._render_source_rate_control",
        effect="Increases the local interest draft by 0.1 percentage points; Apply is required to dispatch it.",
        action="none (local draft until title Apply)",
        validation="Enabled only for the controlled country with a network client; clamped to scenario bounds.",
        confirmation="No prompt until the user applies or closes a dirty panel.",
        error="An applied value rejected by the server leaves authoritative data unchanged.",
        limitation="The source repeats after a half-second hold and accelerates its step and cadence; the Python control uses the same source timing and step thresholds.",
    ),
    "Economic_Health_Window/frmInner/frmInflation/frmInterest/edtText": _economic_health_interaction(
        reference="GEditBoxNumeric value changes update GUpdatableValue and mark the window Dirty; edit begin/end prevents background Update from overwriting active input.",
        surface="EconomicHealthPanel._render_source_content / GMLWidgets.input_float",
        effect="Edits a local interest-rate draft displayed in percent; no action is sent until Apply.",
        action="ActionChangeEconomicPolicy(policy_name='interest_rate') on Apply",
        validation="Only controlled-country drafts are editable; scenario rate bounds are applied before sending and checked again by the server.",
        confirmation="Dirty close prompts for Apply or Discard.",
        error="Invalid or out-of-bounds requests are rejected by EconomicHealthSystem.",
        limitation="OpenPower uses a plain numeric input instead of the source GEditBoxNumeric and sends an OpenPower action on Apply.",
        status="partial",
    ),
    "Economic_Health_Window/frmInner/frmGdp/frmTax/btnDown": _economic_health_interaction(
        reference="GUpdatableValue::OnMouseDown decrements personal income tax by 0.1 percentage points and starts the delayed accelerating hold timer; the panel becomes Dirty.",
        surface="EconomicHealthPanel._render_source_rate_control",
        effect="Decreases the local personal-income-tax draft by 0.1 percentage points; Apply is required to dispatch it.",
        action="none (local draft until title Apply)",
        validation="Enabled only for the controlled country with a network client; clamped to scenario bounds.",
        confirmation="No prompt until the user applies or closes a dirty panel.",
        error="An applied value rejected by the server leaves authoritative data unchanged.",
        limitation="The source repeats after a half-second hold and accelerates its step and cadence; the Python control uses the same source timing and step thresholds.",
    ),
    "Economic_Health_Window/frmInner/frmGdp/frmTax/btnUp": _economic_health_interaction(
        reference="GUpdatableValue::OnMouseDown increments personal income tax by 0.1 percentage points and starts the delayed accelerating hold timer; the panel becomes Dirty.",
        surface="EconomicHealthPanel._render_source_rate_control",
        effect="Increases the local personal-income-tax draft by 0.1 percentage points; Apply is required to dispatch it.",
        action="none (local draft until title Apply)",
        validation="Enabled only for the controlled country with a network client; clamped to scenario bounds.",
        confirmation="No prompt until the user applies or closes a dirty panel.",
        error="An applied value rejected by the server leaves authoritative data unchanged.",
        limitation="The source repeats after a half-second hold and accelerates its step and cadence; the Python control uses the same source timing and step thresholds.",
    ),
    "Economic_Health_Window/frmInner/frmGdp/frmTax/edtText": _economic_health_interaction(
        reference="GEditBoxNumeric value changes update GUpdatableValue and mark the window Dirty; edit begin/end prevents background Update from overwriting active input.",
        surface="EconomicHealthPanel._render_source_content / GMLWidgets.input_float",
        effect="Edits a local personal-income-tax draft displayed in percent; no action is sent until Apply.",
        action="ActionSetTax on Apply",
        validation="Only controlled-country drafts are editable; scenario rate bounds are applied before sending and checked again by the server.",
        confirmation="Dirty close prompts for Apply or Discard.",
        error="Invalid or out-of-bounds requests are rejected by EconomicHealthSystem.",
        limitation="OpenPower uses a plain numeric input instead of the source GEditBoxNumeric and sends an OpenPower action on Apply.",
        status="partial",
    ),
}

for _economic_health_meter_path, _economic_health_meter_name in (
    ("frmInner/frmPopulation/frmUnemployment", "unemployment"),
    ("frmInner/frmPopulation/frmPoverty", "poverty"),
):
    for _economic_health_part in ("btnFill", "btnUnfilled"):
        ECONOMIC_HEALTH_INTERACTION_BINDINGS[
            f"Economic_Health_Window/{_economic_health_meter_path}/{_economic_health_part}"
        ] = _economic_health_interaction(
            reference="GCursorMeter permits dragging the local cursor; GEconomicHealthWindow::Update resets it from the country snapshot, and GEconomicHealthWindow::Save submits only tax and interest.",
            surface="EconomicHealthPanel._draw_population_meter",
            effect=f"Shows the reported {_economic_health_meter_name} rate with a draggable local cursor; dragging changes no country data or percentage readout.",
            action="none (statistical indicator; no economic action exists for dragging it)",
            validation="The country rate is always read from the current selected-country snapshot; the local cursor resets when that value changes or the window closes.",
            confirmation="None; the meter is not a draft economic policy.",
            error="Not applicable; the indicator does not submit an action.",
            limitation="Preserve the transient source cursor drag without presenting it as a change to the authoritative population statistic.",
            country_scope="The meter follows the currently selected country; dragging changes only the local visual cursor.",
        )


DISPLAY_BINDINGS_BY_WINDOW["Add_Remove_Window"] = {
    "frmTitle/lblTitle": DisplayBinding(
        "literal English title: TREATY PARTICIPANTS",
        "window title",
        "TREATY PARTICIPANTS; exact REFERENCE localization is unavailable.",
        "Static while the participant editor is open.",
        "src/client/ui/panels/politics/treaty_participant_dialog.py; .codex/layout_catalog.gml",
        "Title of the treaty-side membership editor.",
        status="partial",
        action_required="Keep the title in the source title slot; use the exact source translation if its language bundle is recovered.",
    ),
    "frmInner/frmItems/txtTransparentLabel1": DisplayBinding(
        "literal English caption: AVAILABLE COUNTRIES",
        "section caption",
        "AVAILABLE COUNTRIES; exact REFERENCE localization is unavailable.",
        "Static above the active available-country list.",
        "src/client/ui/panels/politics/treaty_participant_dialog.py; .codex/layout_catalog.gml",
        "Countries not currently assigned to either draft side.",
        status="partial",
        action_required="Keep the caption in its source GML slot and use the source translation when available.",
    ),
    "frmInner/frmItems/txtTransparentLabel2": DisplayBinding(
        "literal English caption: SIDE A",
        "section caption",
        "SIDE A; exact REFERENCE localization is unavailable.",
        "Static above the current Side A draft list.",
        "src/client/ui/panels/politics/treaty_participant_dialog.py; .codex/layout_catalog.gml",
        "First treaty membership side.",
        status="partial",
        action_required="Keep the caption in its source GML slot and use the source translation when available.",
    ),
    "frmInner/frmItems/txtTransparentLabel3": DisplayBinding(
        "literal English caption: SIDE B",
        "section caption",
        "SIDE B; visible for two-sided treaties only; exact REFERENCE localization is unavailable.",
        "Static above the current Side B draft list when the treaty type is two-sided.",
        "src/client/ui/panels/politics/treaty_participant_dialog.py; .codex/layout_catalog.gml",
        "Second treaty membership side.",
        status="partial",
        action_required="Keep the caption in its source GML slot and hide it when the OpenPower treaty type has no Side B.",
    ),
    "frmInner/frmItems/frmUnselected/lstUnselected": DisplayBinding(
        "countries.id where active=true, excluding local side_a and side_b draft tags",
        "country flag, tag, and localized name",
        "Empty list when no active country remains available; missing names fall back to the tag and missing flags use FlagRenderer's fallback.",
        "Recomputed from the current OpenPower country catalog and local participant draft each render; rows sort by displayed country name.",
        "src/client/ui/panels/politics/treaty_participant_dialog.py; src/client/ui/panels/shared/panel_data.py; modules/base/schema.py",
        "Active countries available to assign to a treaty side; Ctrl and Shift support extended selection.",
        status="partial",
        action_required="Keep inactive countries out of new selections while retaining existing inactive members as visibly ineligible until removed.",
    ),
    "frmInner/frmItems/frmSideA/lstSelectedA": DisplayBinding(
        "local participant draft side_a initialized from countries_treaties.side_a or proposal participants",
        "country flag, tag, and localized name",
        "Empty list when no Side A members are recorded; inactive existing members remain visible with an ineligible marker.",
        "Updated locally as rows move between lists; returned to the owner on dialog Apply and revalidated by the server.",
        "src/client/ui/panels/politics/treaty_participant_dialog.py; src/client/ui/panels/politics/treaties_live.py; modules/base/systems/world/treaty_diplomacy.py",
        "Current Side A participant draft, sorted by displayed country name.",
        status="partial",
        action_required="Keep the required sponsor on Side A and preserve the draft until the authoritative owner accepts the update.",
    ),
    "frmInner/frmItems/frmSideB/lstSelectedB": DisplayBinding(
        "local participant draft side_b initialized from countries_treaties.side_b or proposal participants",
        "country flag, tag, and localized name",
        "Empty list when no Side B members are recorded; hidden for one-sided treaty definitions.",
        "Updated locally as rows move between lists; returned to the owner on dialog Apply and revalidated by the server.",
        "src/client/ui/panels/politics/treaty_participant_dialog.py; src/client/ui/panels/politics/treaties_live.py; modules/base/systems/world/treaty_diplomacy.py",
        "Current Side B participant draft, sorted by displayed country name.",
        status="partial",
        action_required="Keep required counterpart membership on Side B and hide the pane when the current treaty type is one-sided.",
    ),
}


COUNTRY_INFO_INTERACTION_BINDINGS = {
    "Country_Information_Window/frmTitle/btnExit": {
        "openpower_effect": "Hide CountryMoreInfoPanel through the standard titlebar close, matching GCountryInformationWindow::OnMouseClick -> Hide().",
        "game_action": "none (local window close)",
        "read_only_or_state_changing": "local UI-only",
        "validation_condition": "The country information panel is visible.",
        "country_scope_restriction": "None; the current panel closes without changing country state.",
        "confirmation_state": "None.",
        "error_state": "None; closing the panel sends no GameAction.",
        "restrictions_confirmation_error": "The source btnExit only hides the window; Python's titlebar close has the same effect.",
        "action_required": "Keep the country information close route available and ensure it sends no state-changing action.",
        "status": "verified_openpower",
    },
    **{
        f"Country_Information_Window/frmTitle/{control}": {
            "openpower_effect": f"No interaction: GCountryInformationWindow::OnCreate hides {control}, matching the Python panel which does not render it.",
            "game_action": "none (source control is hidden)",
            "read_only_or_state_changing": "not interactive; hidden during source initialization",
            "validation_condition": "None; the control is hidden by the source window.",
            "country_scope_restriction": "None.",
            "confirmation_state": "None.",
            "error_state": "None.",
            "restrictions_confirmation_error": "Do not add a visible action for this source control without evidence that it is shown.",
            "action_required": "None; retain the source hidden state.",
            "status": "verified_openpower",
        }
        for control in ("togLockWindow", "btnApply")
    },
    **{
        f"Country_Information_Window/frmInner/frmLand/{meter}/{part}": {
            "openpower_effect": f"Decorative {part} subcontrol of the {meter} percentage meter; the source configures it as the meter fill/track and defines no click action.",
            "game_action": "none (visual meter component)",
            "read_only_or_state_changing": "read-only indicator; not an input control",
            "validation_condition": "None; the parent meter supplies its visual value.",
            "country_scope_restriction": "Displays only the selected panel's current value or its unavailable state.",
            "confirmation_state": "None.",
            "error_state": "Unavailable values display an em dash and an empty neutral meter.",
            "restrictions_confirmation_error": "The source sets the meter fill image in OnCreate and handles no meter subcontrol in OnMouseClick.",
            "action_required": "None; keep the meter subcontrols non-interactive.",
            "status": "verified_openpower",
        }
        for meter in ("frmNationalParks", "frmArableLand", "frmForests", "frmUnusable")
        for part in ("btnUnfilled", "btnFill")
    },
}


def _options_interaction_binding(
    *,
    reference_side_effect: str,
    openpower_effect: str,
    game_action: str,
    read_only_or_state_changing: str,
    action_required: str,
    status: str,
    validation_condition: str = "None identified in the source control path.",
    country_scope_restriction: str = "Client-local setting; no country-scoped game action.",
    confirmation_state: str = "None.",
    error_state: str = "No matching OpenPower action is available.",
    restrictions_confirmation_error: str = "Keep the control unavailable unless an equivalent OpenPower setting or action is implemented.",
) -> dict[str, str]:
    return {
        "reference_side_effect": reference_side_effect,
        "openpower_effect": openpower_effect,
        "game_action": game_action,
        "read_only_or_state_changing": read_only_or_state_changing,
        "validation_condition": validation_condition,
        "country_scope_restriction": country_scope_restriction,
        "confirmation_state": confirmation_state,
        "error_state": error_state,
        "restrictions_confirmation_error": restrictions_confirmation_error,
        "action_required": action_required,
        "status": status,
    }


def _options_bind(paths: tuple[str, ...], **binding: str) -> dict[str, dict[str, str]]:
    return {path: dict(binding) for path in paths}


def _options_unavailable_display(
    source_binding: str,
    units: str,
    meaning: str,
    update_rule: str,
) -> DisplayBinding:
    return DisplayBinding(
        f"unavailable: {source_binding}",
        units,
        "No matching OpenPower setting field exists; do not substitute an unrelated value.",
        update_rule,
        ".codex/Client/Source/reference_game_options_window.cpp; src/client/services/game_settings_service.py",
        meaning,
        status="verified_unavailable",
        action_required="Keep this REFERENCE value unavailable until OpenPower defines an equivalent setting and persistence contract.",
    )


def _options_localization_binding(token: str) -> DisplayBinding:
    return DisplayBinding(
        f"source localization token {token}",
        "localized caption",
        "The supplied GML records the token ID, but the reference REFERENCE language table is unavailable.",
        "Static source label; it does not refresh from game state.",
        ".codex/layout_catalog.gml; no REFERENCE language table is present in the supplied source mirror",
        f"REFERENCE localized caption token {token}; its reference wording is unavailable.",
        status="partial",
        action_required="Use the exact source string only if its language table is recovered; do not infer a translation from the control name.",
    )


_OPTIONS_LOCALIZED_CAPTIONS = {
    "frmTitle/lblTitle": "100010",
    "frmInner/tabOptions/Tab1/lblAutosaveName1": "102347",
    "frmInner/tabOptions/Tab1/lblName": "100581",
    "frmInner/tabOptions/Tab1/frmAutosave/lblIncremental": "102268",
    "frmInner/tabOptions/Tab1/frmAutosave/lblAutosavelabel": "102274",
    "frmInner/tabOptions/Tab1/frmAutosave/lblAutosaveEach": "102272",
    "frmInner/tabOptions/Tab1/frmAutosave/lblAutosaveName": "102275",
    "frmInner/tabOptions/Tab1/lblAutosave": "102270",
    "frmInner/tabOptions/Tab3/lblSound": "101648",
    "frmInner/tabOptions/Tab3/lblMusic": "101647",
    "frmInner/tabOptions/Tab2/lblResolution6": "101644",
    "frmInner/tabOptions/Tab2/lblResolution7": "101645",
    "frmInner/tabOptions/Tab2/lblResolution4": "101642",
    "frmInner/tabOptions/Tab2/lblResolution5": "101643",
    "frmInner/tabOptions/Tab2/lblResolution2": "101640",
    "frmInner/tabOptions/Tab2/lblResolution3": "101641",
    "frmInner/tabOptions/Tab2/lblResolution": "101638",
    "frmInner/tabOptions/Tab2/lblResolution8": "101646",
    "frmInner/tabOptions/Tab2/lblQuality": "101639",
}
DISPLAY_BINDINGS_BY_WINDOW["Options_Window"] = {
    **{
        path: _options_localization_binding(token)
        for path, token in _OPTIONS_LOCALIZED_CAPTIONS.items()
    },
    "frmInner/tabOptions/Tab1/frmAIAggressivenessMtr": _options_unavailable_display(
        "GGameOptionsWindow.m_pData->m_fAIAggressiveness",
        "source meter value; exact scale is unresolved",
        "REFERENCE numeric AI aggressiveness; OpenPower advisor policy modes are not this value.",
        "Loaded from the client options record on Show and persisted on Confirm.",
    ),
    "frmInner/tabOptions/Tab3/frmSoundVolume": _options_unavailable_display(
        "GGameOptionsWindow.m_pData->m_fSoundVolume",
        "source sound-volume meter value",
        "REFERENCE sound-effects volume; the source plays IncomingMail when the meter is released.",
        "Loaded from the client options record on Show and persisted on Confirm.",
    ),
    "frmInner/tabOptions/Tab3/frmMusicVolume": _options_unavailable_display(
        "GGameOptionsWindow.m_pData->m_fMusicVolume",
        "source music-volume meter value",
        "REFERENCE music volume, stored separately from sound effects.",
        "Loaded from the client options record on Show and persisted on Confirm.",
    ),
    "frmInner/tabOptions/Tab2/cboZoomLevel": _options_unavailable_display(
        "GGameOptionsWindow.m_pData->m_eZoomLevel and EZoomLevel enum choices",
        "REFERENCE atlas-detail enum",
        "All, elevation, elevation and water, or none; this controls atlas layers rather than camera magnification.",
        "Selection applies atlas zoom immediately and is persisted on Confirm.",
    ),
    "frmInner/tabOptions/Tab2/cboTextureDetail": _options_unavailable_display(
        "GGameOptionsWindow.m_pData->m_eTextureQuality",
        "REFERENCE quality enum (Low/High)",
        "Texture rendering quality; the source control offers Low and High.",
        "Loaded from the client options record; renderer changes are persisted on Confirm.",
    ),
    "frmInner/tabOptions/Tab2/cboGeometricDetail": _options_unavailable_display(
        "GGameOptionsWindow.m_pData->m_eGeometricDetail",
        "REFERENCE quality enum (Low/Medium/High)",
        "Geometric rendering quality; the source control offers Low, Medium, and High.",
        "Loaded from the client options record; renderer changes are persisted on Confirm.",
    ),
    "frmInner/tabOptions/Tab2/cboResolution": DisplayBinding(
        "partial: GameSettingsService windowed/fullscreen display choices; source current renderer mode differs",
        "current display mode",
        "OpenPower display options remain available in GameSettingsContent; the source control itself is disabled.",
        "OpenPower reads current window/display configuration; REFERENCE reads the current renderer mode during OnCreate.",
        "src/client/services/game_settings_service.py; .codex/Client/Source/reference_game_options_window.cpp",
        "REFERENCE shows the current resolution in a disabled combo; OpenPower has editable windowed/fullscreen mode settings rather than this source display.",
        status="partial",
        action_required="Keep OpenPower display choices in their validated settings workflow; do not claim they reproduce the disabled source combo.",
    ),
    "frmInner/tabOptions/Tab2/cboColorDepth": DisplayBinding(
        "unavailable: source renderer color depth is not a GameSettingsService field",
        "bits per pixel",
        "The source combo is disabled; OpenPower does not expose a color-depth setting.",
        "REFERENCE reads the current renderer mode during OnCreate and does not apply a changed depth.",
        ".codex/Client/Source/reference_game_options_window.cpp; src/client/services/game_settings_service.py",
        "Current REFERENCE renderer color depth; no editable color-depth workflow exists in OpenPower.",
        status="verified_unavailable",
        action_required="Keep color depth unavailable; do not infer it from the selected OpenPower display mode.",
    ),
}


def _politics_caption_binding(token: str, caption: str) -> DisplayBinding:
    return DisplayBinding(
        f"literal: OpenPower caption corresponding to GML text token {token}",
        "static English caption",
        f"{caption}; the reference REFERENCE localization table is not present in the source mirror.",
        "Rendered from the Python politics panel while the panel is open.",
        "src/client/ui/panels/politics_panel.py; .codex/layout_catalog.gml",
        f"Current English caption for the source {caption.lower()} slot; exact localized wording is unavailable.",
        status="partial",
        action_required="Use the exact reference localization only if the REFERENCE language tables are recovered.",
    )


_POLITICS_CAPTIONS = {
    "frmTitle/lblTitle": ("100000", "POLITICS"),
    "frmInner/frmConstitutionalForm/lblTitle": ("100013", "CONSTITUTIONAL FORM"),
    "frmInner/frmIdeology/lblTitle": ("100015", "IDEOLOGY"),
    "frmInner/frmIdeology/lblLeft": ("100170", "Left"),
    "frmInner/frmIdeology/lblRight": ("100171", "Right"),
    "frmInner/frmApproval/lblTitle": ("100018", "APPROVAL"),
    "frmInner/frmPressure/lblTitle": ("100019", "POLITICAL PRESSURE"),
    "frmInner/frmStability/lblTitle": ("100021", "STABILITY"),
    "frmInner/frmCorruption/lblTitle": ("100022", "CORRUPTION"),
}
_POLITICS_SOURCE = (
    "src/client/ui/panels/politics_panel.py; src/client/ui/panels/politics/presenter.py; "
    "modules/base/schema.py; .codex/Client/Source/reference_politic_window.cpp"
)
DISPLAY_BINDINGS_BY_WINDOW["Politic_Window"] = {
    **{
        path: _politics_caption_binding(token, caption)
        for path, (token, caption) in _POLITICS_CAPTIONS.items()
    },
    "frmInner/frmConstitutionalForm/txtValue": DisplayBinding(
        "country_governments.government_type; when martial_law is true display 'Martial law'",
        "government-form label",
        "Transitional republic when no government type is stored.",
        "Read from the selected country's government row each render; martial law takes display precedence, matching GPoliticWindow::Update.",
        _POLITICS_SOURCE,
        "REFERENCE resolves its numeric government type to localized text and replaces it with Martial law when the martial-law flag is set; OpenPower uses its own government-form catalog.",
        status="partial",
        action_required="Keep martial-law precedence and add an explicit REFERENCE-to-OpenPower government-type map only if authoritative IDs become available.",
    ),
    "frmInner/frmIdeology/frmIdeologyCursor": DisplayBinding(
        "country_governments.ideology_balance",
        "normalized ideology ratio (0–1)",
        "0.5 when the government row or ideology value is absent.",
        "PoliticsPresenter reads and normalizes the selected country's government row each render.",
        _POLITICS_SOURCE,
        "OpenPower displays its normalized ideology balance on the source left-to-right meter; exact REFERENCE ideology scale semantics are not independently mapped.",
        status="partial",
        action_required="Keep the current normalized meter and leave the REFERENCE political-ideology scale crosswalk explicit.",
    ),
    "frmInner/frmApproval/txtValue": DisplayBinding(
        "countries.gvt_approval",
        "percent",
        "50% when the country row or value is absent.",
        "PoliticsPresenter converts the selected country's approval value to percent on each render.",
        _POLITICS_SOURCE,
        "REFERENCE formats GvtApproval as a percent; OpenPower uses the named country field, but the underlying approval formula is not proven identical.",
        status="partial",
        action_required="Keep the value sourced from authoritative country state and reconcile formulas only with a verified REFERENCE-to-OpenPower field crosswalk.",
    ),
    "frmInner/frmApproval/frmGradient": DisplayBinding(
        "countries.gvt_approval",
        "normalized ratio (0–1)",
        "50% when the country row or value is absent.",
        "PoliticsPresenter converts the selected country's approval value to a ratio on each render.",
        _POLITICS_SOURCE,
        "OpenPower's read-only fill bar corresponds to the REFERENCE approval meter; exact calculation parity remains unverified.",
        status="partial",
        action_required="Keep the approval meter bound to authoritative state and preserve the calculation-parity note.",
    ),
    "frmInner/frmStability/txtValue": DisplayBinding(
        "countries.gvt_stability",
        "percent",
        "50% when the country row or value is absent.",
        "PoliticsPresenter converts the selected country's stability value to percent on each render.",
        _POLITICS_SOURCE,
        "REFERENCE formats GvtStability as a percent; OpenPower uses the named country field, but the underlying stability formula is not proven identical.",
        status="partial",
        action_required="Keep the value sourced from authoritative country state and reconcile formulas only with a verified REFERENCE-to-OpenPower field crosswalk.",
    ),
    "frmInner/frmStability/frmGradient": DisplayBinding(
        "countries.gvt_stability",
        "normalized ratio (0–1)",
        "50% when the country row or value is absent.",
        "PoliticsPresenter converts the selected country's stability value to a ratio on each render.",
        _POLITICS_SOURCE,
        "OpenPower's read-only fill bar corresponds to the REFERENCE stability meter; exact calculation parity remains unverified.",
        status="partial",
        action_required="Keep the stability meter bound to authoritative state and preserve the calculation-parity note.",
    ),
    "frmInner/frmCorruption/txtValue": DisplayBinding(
        "countries.gvt_corruption",
        "percent",
        "40% when the country row or value is absent.",
        "PoliticsPresenter converts the selected country's corruption value to percent on each render.",
        _POLITICS_SOURCE,
        "REFERENCE formats CorruptionLevel as a percent; OpenPower uses the named country field, but the underlying corruption formula is not proven identical.",
        status="partial",
        action_required="Keep the value sourced from authoritative country state and reconcile formulas only with a verified REFERENCE-to-OpenPower field crosswalk.",
    ),
    "frmInner/frmCorruption/frmGradient": DisplayBinding(
        "countries.gvt_corruption",
        "normalized ratio (0–1)",
        "40% when the country row or value is absent.",
        "PoliticsPresenter converts the selected country's corruption value to a ratio on each render.",
        _POLITICS_SOURCE,
        "OpenPower's read-only fill bar corresponds to the REFERENCE corruption meter; exact calculation parity remains unverified.",
        status="partial",
        action_required="Keep the corruption meter bound to authoritative state and preserve the calculation-parity note.",
    ),
    "frmInner/frmPressure/txtValue": DisplayBinding(
        "unavailable: OpenPower has no political-pressure field equivalent to GDataPoliticWindow.Pressure",
        "REFERENCE political-pressure percent",
        "N/A; do not substitute zero or infer pressure from another political metric.",
        "The REFERENCE pressure value comes from the politic update; OpenPower explicitly presents N/A while no equivalent field exists.",
        _POLITICS_SOURCE,
        "OpenPower preserves the source value slot and fallback, but the simulation does not provide an authoritative political-pressure value.",
        status="verified_unavailable",
        action_required="Keep the N/A fallback until OpenPower gains an authoritative equivalent field.",
    ),
    "frmInner/frmPressure/frmGradient": DisplayBinding(
        "unavailable: OpenPower has no political-pressure field equivalent to GDataPoliticWindow.Pressure",
        "REFERENCE political-pressure meter ratio",
        "Empty disabled rail beside N/A; never represent missing pressure as a measured zero.",
        "The source-sized track is drawn without a cursor or fill because no OpenPower pressure value is available.",
        _POLITICS_SOURCE,
        "The empty track preserves source geometry while the adjacent N/A label communicates missing data.",
        status="partial",
        action_required="Keep the empty source-sized track and N/A fallback until an authoritative equivalent field exists.",
    ),
}


def _country_profile_caption_binding(token: str, caption: str) -> DisplayBinding:
    return DisplayBinding(
        f"literal: OpenPower English caption for GML token {token}",
        "static caption",
        f"{caption}; exact REFERENCE localized wording is unavailable without its language tables.",
        "Rendered in the matching Country_Profile_Window GML slot.",
        "src/client/ui/components/shared/country_profile_window.py; .codex/layout_catalog.gml",
        f"Current OpenPower caption for the {caption.lower()} slot; the numeric source token is unresolved.",
        status="partial",
        action_required="Use the reference caption only if the REFERENCE localization tables are recovered.",
    )


_COUNTRY_PROFILE_CAPTIONS = {
    "frmTitle/lblTitle": ("100575", "Country Profile"),
    "frmInner/frmDesired/lblTitle": ("100576", "DESIRED PROFILE"),
    "frmInner/frmDesired/lblGoals": ("100017", "MATCH"),
    "frmInner/frmSuggested/lblTitle": ("100577", "SUGGESTED COUNTRIES"),
    "frmInner/frmSuggested/lblGoals2": ("100578", "SELECTED COUNTRY RANKS"),
}
_COUNTRY_PROFILE_SOURCE = (
    "src/client/ui/components/shared/country_profile_window.py; src/client/services/country_profile.py; "
    "Client/Source/reference_country_profile.cpp; .codex/layout_catalog.gml"
)
DISPLAY_BINDINGS_BY_WINDOW["Country_Profile_Window"] = {
    **{
        path: _country_profile_caption_binding(token, caption)
        for path, (token, caption) in _COUNTRY_PROFILE_CAPTIONS.items()
    },
    "frmInner/frmDesired/frmEconomic": DisplayBinding(
        "CountryProfileWindow._desired_values['economic']",
        "local preference ratio (0–1)",
        "0.5 when the profile window is created.",
        "Updated locally by dragging the source-sized bar; it is applied to suggestions only while the Economic filter is enabled.",
        _COUNTRY_PROFILE_SOURCE,
        "Matches the source desired-value meter range; source rank vectors are not the same as OpenPower's GDP ranking.",
        status="partial",
        action_required="Keep the local ratio control and reconcile the GDP rank input only if the reference rank source becomes available.",
    ),
    "frmInner/frmDesired/frmPolitic": DisplayBinding(
        "CountryProfileWindow._desired_values['political']",
        "local preference ratio (0–1)",
        "0.5 when the profile window is created.",
        "Updated locally by dragging the source-sized bar; it is applied to suggestions only while the Political filter is enabled.",
        _COUNTRY_PROFILE_SOURCE,
        "OpenPower uses government approval as its political ranking field; the source rank vector's exact metric is not established.",
        status="partial",
        action_required="Keep the local ratio control and preserve the source-rank-input gap.",
    ),
    "frmInner/frmDesired/frmMilitary": DisplayBinding(
        "CountryProfileWindow._desired_values['military']",
        "local preference ratio (0–1)",
        "0.5 when the profile window is created.",
        "Updated locally by dragging the source-sized bar; it is applied to suggestions only while the Military filter is enabled.",
        _COUNTRY_PROFILE_SOURCE,
        "OpenPower uses military personnel as its military ranking field; the source rank vector's exact metric is not established.",
        status="partial",
        action_required="Keep the local ratio control and preserve the source-rank-input gap.",
    ),
    "frmInner/frmSuggested/frmEconomic": DisplayBinding(
        "suggest_country_profiles(...).rank_for('economic')",
        "rank fraction (0–1)",
        "0 with no selected candidate or no eligible country rows.",
        "Selected rank is converted with (country_count + 1 - rank) / country_count, matching the source display formula.",
        _COUNTRY_PROFILE_SOURCE,
        "The display formula matches REFERENCE; OpenPower's rank is GDP-based rather than the unprovided source economic-rank vector.",
        status="partial",
        action_required="Keep the fraction conversion and map the native economic-rank input only if the source vector is recovered.",
    ),
    "frmInner/frmSuggested/frmPolitic": DisplayBinding(
        "suggest_country_profiles(...).rank_for('political')",
        "rank fraction (0–1)",
        "0 with no selected candidate or no eligible country rows.",
        "Selected rank is converted with (country_count + 1 - rank) / country_count, matching the source display formula.",
        _COUNTRY_PROFILE_SOURCE,
        "The display formula matches REFERENCE; OpenPower uses government approval rather than the unprovided source political-rank vector.",
        status="partial",
        action_required="Keep the fraction conversion and map the native political-rank input only if the source vector is recovered.",
    ),
    "frmInner/frmSuggested/frmMilitary": DisplayBinding(
        "suggest_country_profiles(...).rank_for('military')",
        "rank fraction (0–1)",
        "0 with no selected candidate or no eligible country rows.",
        "Selected rank is converted with (country_count + 1 - rank) / country_count, matching the source display formula.",
        _COUNTRY_PROFILE_SOURCE,
        "The display formula matches REFERENCE; OpenPower uses military personnel rather than the unprovided source military-rank vector.",
        status="partial",
        action_required="Keep the fraction conversion and map the native military-rank input only if the source vector is recovered.",
    ),
    "frmInner/frmSuggested/lstCountries": DisplayBinding(
        "suggest_country_profiles(eligible country rows, desired ratios, enabled metric filters)[:10]",
        "ranked eligible country rows",
        "Empty list displays 'No eligible countries.'; invalid country IDs are filtered before ranking.",
        "Recomputed after desired-slider or filter changes; selection is cleared when criteria change.",
        _COUNTRY_PROFILE_SOURCE,
        "OpenPower ranks by the average absolute distance to selected target ranks using GDP, approval, and personnel; source rank inputs and exact tie ordering are not available.",
        status="partial",
        action_required="Keep the current OpenPower ranking explicitly labeled as native and reconcile only when the exact source rank vectors are recovered.",
    ),
    "frmInner/frmSuggested/lblRank": DisplayBinding(
        "CountryProfileWindow._selected_country_id",
        "selected country tag",
        "Empty until a suggestion is selected.",
        "Updated by selecting a candidate; cleared when the dialog opens or desired criteria change.",
        _COUNTRY_PROFILE_SOURCE,
        "OpenPower shows the selected country's tag in the source rank-label slot; the exact localized source label is unavailable.",
        status="partial",
        action_required="Keep the selected tag visible and use the reference localized caption only if its language resource is recovered.",
    ),
    "frmInner/frmSuggested/picPolitic": DisplayBinding(
        "Font Awesome building-columns glyph in the political source picture slot",
        "political metric icon",
        "The OpenPower icon font is available; the REFERENCE picture asset is not.",
        "Static icon identifies the political rank bar.",
        _COUNTRY_PROFILE_SOURCE,
        "OpenPower substitutes its political icon for the source texture while preserving the 17×16 picture slot.",
        status="partial",
        action_required="Use the reference source art only if its texture resources become available.",
    ),
    "frmInner/frmSuggested/picPolitic1": DisplayBinding(
        "Font Awesome military-rifle glyph in the military source picture slot",
        "military metric icon",
        "The OpenPower icon font is available; the REFERENCE picture asset is not.",
        "Static icon identifies the military rank bar.",
        _COUNTRY_PROFILE_SOURCE,
        "OpenPower substitutes its military icon for the source texture while preserving the 17×16 picture slot.",
        status="partial",
        action_required="Use the reference source art only if its texture resources become available.",
    ),
    "frmInner/frmSuggested/picPolitic2": DisplayBinding(
        "Font Awesome sack-dollar glyph in the economic source picture slot",
        "economic metric icon",
        "The OpenPower icon font is available; the REFERENCE picture asset is not.",
        "Static icon identifies the economic rank bar.",
        _COUNTRY_PROFILE_SOURCE,
        "OpenPower substitutes its economic icon for the source texture while preserving the 17×16 picture slot.",
        status="partial",
        action_required="Use the reference source art only if its texture resources become available.",
    ),
    "frmInner/frmSuggested/picSep": DisplayBinding(
        "GMLWidgets.rule in the 228×4 source separator slot",
        "horizontal separator",
        "Visible divider between the candidate list and selected-rank details.",
        "Rendered at the static GML separator rectangle.",
        _COUNTRY_PROFILE_SOURCE,
        "The OpenPower horizontal rule preserves source geometry while using native theme colors instead of the source texture.",
        status="partial",
        action_required="Use the source separator texture only if the reference picture assets are recovered.",
    ),
}


OPTIONS_INTERACTION_BINDINGS = {
    **_options_bind(
        (
            "Options_Window/frmTitle/btnExit",
            "Options_Window/frmInner/btnCancel",
        ),
        **_options_interaction_binding(
            reference_side_effect="GGameOptionsWindow::OnMouseClick hides the settings window for btnExit and btnCancel.",
            openpower_effect="The source-anchored title close and Cancel buttons discard the active GameSettingsContent draft, then close the settings page.",
            game_action="none (local window close)",
            read_only_or_state_changing="local draft discard and UI close",
            action_required="Keep both source close routes at their anchored GML rectangles and verify that neither persists a draft.",
            status="verified_openpower",
            error_state="The persisted settings are unchanged on discard.",
            restrictions_confirmation_error="The source exit and cancel callbacks hide without calling Save; OpenPower resets the draft to the persisted settings.",
        ),
    ),
    **_options_bind(
        ("Options_Window/frmInner/btnConfirm",),
        **_options_interaction_binding(
            reference_side_effect="Save persists player name, renderer, audio, zoom, and autosave settings; a changed AI aggressiveness additionally raises GChangeAIAggressiveness to the server; then the window hides.",
            openpower_effect="The anchored Confirm button commits the supported OpenPower settings draft to GameSettingsRepository, applies any staged display change, and closes. REFERENCE-only fields and server AI controls remain unavailable.",
            game_action="none (local OpenPower settings commit); REFERENCE GChangeAIAggressiveness has no matching OpenPower GameAction",
            read_only_or_state_changing="local settings persistence and conditional display-mode update",
            action_required="Keep Apply limited to supported OpenPower settings and retain explicit unavailable status for source-only values.",
            status="partial",
            country_scope_restriction="AI aggressiveness is sent to the server and is not scoped to the local country; other source values are client settings.",
            confirmation_state="Confirm saves all edited source values and closes the window; it is not a second confirmation dialog.",
            error_state="The settings repository persists the normalized draft; OpenPower has no server AI-settings response path.",
            restrictions_confirmation_error="The source Confirm control saves and hides; OpenPower applies the settings fields its local service supports.",
        ),
    ),
    **_options_bind(
        ("Options_Window/frmTitle/btnApply",),
        **_options_interaction_binding(
            reference_side_effect="GGameOptionsWindow::OnShow hides m_pObjApplyBtn; no active Apply click workflow is exposed.",
            openpower_effect="No separate Apply button is rendered; supported OpenPower settings are applied by their individual controls.",
            game_action="none (source Apply control is hidden)",
            read_only_or_state_changing="not interactive; hidden during source display",
            action_required="Keep the source Apply button hidden and avoid adding a dead control.",
            status="verified_cpp",
            validation_condition="GGameOptionsWindow::OnShow hides btnApply.",
            error_state="None; the source hides the control.",
            restrictions_confirmation_error="Base-window titlebar behavior must not make this source-hidden button visible.",
        ),
    ),
    **_options_bind(
        ("Options_Window/frmInner/tabOptions/Tab1/btnClearBan",),
        **_options_interaction_binding(
            reference_side_effect="Only the admin sees this button; it raises a server-targeted GSystemGameEvent with BANNED_PLAYER_LIST_COMMAND and command data 1.",
            openpower_effect="OpenPower has no multiplayer admin ban-list workflow or equivalent server action.",
            game_action="none (no OpenPower banned-player-list GameAction)",
            read_only_or_state_changing="state-changing multiplayer server command",
            action_required="Keep this source-only command unavailable until OpenPower has a multiplayer admin ban-list model and server action.",
            status="verified_unavailable",
            validation_condition="Visible only when the local player ID matches the REFERENCE admin player ID.",
            country_scope_restriction="Admin-scoped multiplayer server command; not country-scoped.",
            confirmation_state="No confirmation in the source callback.",
            error_state="No explicit callback error branch; server response is outside this client handler.",
            restrictions_confirmation_error="Do not expose this command to non-admin users or map it to unrelated moderation behavior.",
        ),
    ),
    **_options_bind(
        (
            "Options_Window/frmInner/tabOptions/Tab1/frmAIAggressivenessMtr/btnUnfilled",
            "Options_Window/frmInner/tabOptions/Tab1/frmAIAggressivenessMtr/btnFill",
        ),
        **_options_interaction_binding(
            reference_side_effect="The cursor meter stages AI aggressiveness; Save persists it locally and raises GChangeAIAggressiveness to the server when the client is connected.",
            openpower_effect="OpenPower advisor settings control policy modes and confirmations, not REFERENCE's numeric AI aggressiveness value.",
            game_action="none (no matching OpenPower AI aggressiveness GameAction)",
            read_only_or_state_changing="source client setting plus conditional server event",
            action_required="Keep numeric aggressiveness unavailable until OpenPower defines its authoritative policy field and update action; do not substitute advisor mode settings.",
            status="verified_unavailable",
            country_scope_restriction="The REFERENCE event targets the server and has no country field.",
            confirmation_state="Applied with the source Confirm button; no separate confirmation dialog.",
            error_state="The source callback has no explicit error branch; no OpenPower equivalent action exists.",
            restrictions_confirmation_error="Do not translate a numeric aggression value into manual/automatic advisor modes.",
        ),
    ),
    **_options_bind(
        (
            "Options_Window/frmInner/tabOptions/Tab1/togAutosave",
            "Options_Window/frmInner/tabOptions/Tab1/frmAutosave/edtAutosaveEach",
            "Options_Window/frmInner/tabOptions/Tab1/frmAutosave/edtAutosaveName",
            "Options_Window/frmInner/tabOptions/Tab1/frmAutosave/togIncremental",
        ),
        **_options_interaction_binding(
            reference_side_effect="Save writes autosave enabled, incremental-save mode, save frequency, and save filename to the client config; changing the filename also resets and persists the save counter. The autosave frame is shown only when autosave is enabled.",
            openpower_effect="REFERENCEOptionsWindowContent stages the source-slot enabled, incremental, interval, and save-name controls in GameSettingsContent. Confirm persists the policy through GameSettingsService/Repository; AutosaveScheduler later sends ActionSaveGame through the client, waits for its result, and uses an incremented suffix when incremental mode is enabled.",
            game_action="ActionSaveGame (scheduled by AutosaveScheduler and executed through the client/session save path)",
            read_only_or_state_changing="persisted client autosave policy plus periodic authoritative save action",
            action_required="None for these controls; retain the source-slot geometry and regression coverage for persistence, safe naming, interval clamping, and a real save slot.",
            status="verified_openpower",
            validation_condition="The autosave fields are shown only while autosave is enabled. Enabled autosave names pass validate_save_name before Confirm; invalid names keep the draft open with an inline error. Intervals are clamped to at least one minute.",
            confirmation_state="Confirm commits the staged autosave settings; Back/title close discard the draft. The scheduler waits for each save result before scheduling another.",
            error_state="An unsafe enabled save name blocks Confirm and shows an inline validation message. The scheduler does not issue another save while one is pending.",
            restrictions_confirmation_error="Use the OpenPower ActionSaveGame save-slot path; do not route autosave through unrelated settings or an untracked background write.",
        ),
    ),
    **_options_bind(
        ("Options_Window/frmInner/tabOptions/Tab1/edtName",),
        **_options_interaction_binding(
            reference_side_effect="Save writes a changed player name to the REFERENCE client XML configuration.",
            openpower_effect="OpenPower's local game settings have no player profile-name field.",
            game_action="none (no OpenPower player-name setting)",
            read_only_or_state_changing="client profile configuration",
            action_required="Keep player-name editing unavailable until OpenPower defines a player profile and persistence contract.",
            status="verified_unavailable",
            confirmation_state="Applied with the source Confirm button.",
        ),
    ),
    **_options_bind(
        (
            "Options_Window/frmInner/tabOptions/Tab3/frmSoundVolume/btnUnfilled",
            "Options_Window/frmInner/tabOptions/Tab3/frmSoundVolume/btnFill",
            "Options_Window/frmInner/tabOptions/Tab3/frmMusicVolume/btnUnfilled",
            "Options_Window/frmInner/tabOptions/Tab3/frmMusicVolume/btnFill",
        ),
        **_options_interaction_binding(
            reference_side_effect="Save persists separate sound and music volume values; releasing the sound meter also previews IncomingMail through the REFERENCE sound box.",
            openpower_effect="OpenPower exposes a single transient AudioService volume and no separate persisted sound/music controls or source sound preview route.",
            game_action="none (client audio settings only; no GameAction)",
            read_only_or_state_changing="local audio configuration",
            action_required="Keep source volume controls unavailable until OpenPower has persistent sound and music channels; do not claim the single runtime volume is equivalent.",
            status="verified_unavailable",
            confirmation_state="Applied with the source Confirm button; source sound preview occurs on meter release.",
            error_state="No explicit error branch in the source callback.",
            restrictions_confirmation_error="Keep sound and music channels distinct if a matching OpenPower audio settings model is added.",
        ),
    ),
    **_options_bind(
        ("Options_Window/frmInner/tabOptions/Tab2/cboZoomLevel",),
        **_options_interaction_binding(
            reference_side_effect="Zoom-level selection immediately calls BackgroundEarth::SetAtlasZoomLevel and Save persists the selected enum to the client config.",
            openpower_effect="OpenPower camera zoom changes viewport scale; it does not expose REFERENCE's atlas-detail modes (All, elevation, elevation plus water, or none).",
            game_action="none (no matching atlas-detail setting)",
            read_only_or_state_changing="local rendering preference applied immediately",
            action_required="Keep the REFERENCE atlas-detail profile unavailable until OpenPower exposes equivalent renderer layers; do not equate it with camera zoom.",
            status="verified_unavailable",
            confirmation_state="Atlas detail changes immediately; the selected preference is persisted when Confirm is clicked.",
            error_state="No explicit source error branch.",
            restrictions_confirmation_error="Camera zoom is not a substitute for atlas elevation/water visibility modes.",
        ),
    ),
    **_options_bind(
        (
            "Options_Window/frmInner/tabOptions/Tab2/cboTextureDetail",
            "Options_Window/frmInner/tabOptions/Tab2/cboGeometricDetail",
            "Options_Window/frmInner/tabOptions/Tab2/togMoon",
            "Options_Window/frmInner/tabOptions/Tab2/togDayCycle",
            "Options_Window/frmInner/tabOptions/Tab2/togClouds",
            "Options_Window/frmInner/tabOptions/Tab2/togSun",
        ),
        **_options_interaction_binding(
            reference_side_effect="Save writes the selected texture/geometric quality or cloud, sun, moon, and day-cycle setting to the client config; quality/visibility changes mark the corresponding renderer state dirty.",
            openpower_effect="OpenPower has no matching persisted graphics-quality or celestial/cloud visibility settings in GameSettingsService.",
            game_action="none (no matching OpenPower renderer setting or GameAction)",
            read_only_or_state_changing="local renderer configuration",
            action_required="Keep these controls unavailable until matching OpenPower renderer settings and persistence are implemented.",
            status="verified_unavailable",
            confirmation_state="Applied with the source Confirm button.",
            error_state="No explicit source error branch.",
            restrictions_confirmation_error="Do not present unsupported visual toggles as if they change the OpenPower renderer.",
        ),
    ),
    **_options_bind(
        (
            "Options_Window/frmInner/tabOptions/Tab2/cboResolution",
            "Options_Window/frmInner/tabOptions/Tab2/cboColorDepth",
        ),
        **_options_interaction_binding(
            reference_side_effect="The source reads the current renderer mode into these fields and explicitly disables both combo boxes during OnCreate; Save does not apply a new mode.",
            openpower_effect="OpenPower has separate windowed/fullscreen display settings; the source resolution and color-depth selectors are not editable controls.",
            game_action="none (source controls disabled)",
            read_only_or_state_changing="read-only current renderer information",
            action_required="Keep the source controls disabled. Map editable OpenPower display controls only to GameSettingsService's validated window/display APIs.",
            status="verified_cpp",
            validation_condition="GGameOptionsWindow::OnCreate calls Enabled(false) for both combo boxes.",
            error_state="None; the source prevents user selection.",
            restrictions_confirmation_error="Do not treat the disabled source controls as an editable resolution or color-depth workflow.",
        ),
    ),
}


DISPLAY_BINDINGS_BY_WINDOW["Objectives_Window"] = {
    "frmTitle/lblTitle": _objectives_caption_binding(
        "102096", "OBJECTIVES", "ObjectivesPanel.render / WindowManager title"
    ),
    "frmInner/frmInner/frmInfo/lblTitle": _objectives_caption_binding(
        "101081", "SCENARIO", "ObjectivesWindowContent._render_campaign_header"
    ),
    "frmInner/frmInner/frmInfo/lblCountry": _objectives_caption_binding(
        "100068", "COUNTRY", "ObjectivesWindowContent._render_campaign_header"
    ),
    "frmInner/frmInner/frmInfo/txtTitle": DisplayBinding(
        "CampaignOverview.scenario.title, falling back to campaign scenario_id",
        "campaign scenario title",
        "Scenario title, scenario ID when its title is empty, or No active campaign.",
        "Recomputed from the selected campaign overview on every visible panel render.",
        "src/client/ui/panels/service/objectives_window_content.py; src/client/ui/panels/service/campaign_presenter.py; .codex/layout_catalog.gml",
        "OpenPower binds the GML header slot to its active scenario; source localization and source-specific result copy are unavailable.",
        status="partial",
        action_required="Keep the current campaign title and explicit empty fallback in the source slot; add source-specific outcome copy only with matching OpenPower lifecycle data.",
        surface="ObjectivesWindowContent._render_campaign_header",
    ),
    "frmInner/frmInner/frmInfo/txtCountry": DisplayBinding(
        "PanelRenderContext.target_tag",
        "country tag",
        "The selected campaign country tag or an em dash when none is selected.",
        "Updated from the current panel render context.",
        "src/client/ui/panels/service/objectives_window_content.py; src/client/ui/core/panel_context.py; .codex/layout_catalog.gml",
        "OpenPower shows the active country tag in the GML country slot; it does not claim equivalence with the source localized country-name format.",
        status="partial",
        action_required="Keep the selected country explicit; use a localized full name only when the source display contract and OpenPower locale lookup match.",
        surface="ObjectivesWindowContent._render_campaign_header",
    ),
    "frmInner/frmInner/tabInfo/Tab1/frmInner/txtDescription": DisplayBinding(
        "CampaignOverview.scenario.description",
        "scenario-authored campaign description",
        "The configured scenario description, or an explicit no-description message.",
        "Rendered from the selected scenario when the Description tab is active.",
        "src/client/ui/panels/service/objectives_window_content.py; src/client/ui/panels/service/campaign_presenter.py; .codex/layout_catalog.gml",
        "OpenPower binds scenario-authored description text into the source page slot; source narrative and localized copy remain different.",
        status="partial",
        action_required="Keep scenario description text bounded to the GML page; do not invent a source-equivalent campaign narrative.",
        surface="ObjectivesWindowContent._render_description_tab / Tab1/frmInner child",
    ),
    "frmInner/frmInner/tabInfo/Tab2/frmObjectives/lblGoals": _objectives_caption_binding(
        "100174", "OBJECTIVES", "ObjectivesWindowContent._render_goals_tab"
    ),
    "frmInner/frmInner/tabInfo/Tab2/frmObjectives/lblTimeLimit": DisplayBinding(
        "scenario.max_duration_minutes + campaign.started_at_minute + current game minute",
        "campaign time limit and remaining duration",
        "TIME LIMIT and remaining duration when configured; NO TIME LIMIT when the scenario has no positive duration.",
        "Recomputed from the active scenario and campaign clock when the Objectives tab renders.",
        "src/client/ui/panels/service/objectives_window_content.py; src/client/ui/panels/service/campaign_presenter.py; .codex/layout_catalog.gml",
        "The source slot is populated from OpenPower campaign timing; exact source deadline and localization semantics are not asserted.",
        status="partial",
        action_required="Keep the explicit no-limit fallback and remaining-time value in the source slot; add end-game deadline behavior only with an equivalent lifecycle contract.",
        surface="ObjectivesWindowContent._render_goals_tab",
    ),
    "frmInner/frmInner/tabInfo/Tab3/frmInner/txtTips": DisplayBinding(
        "ObjectivesPanel._render_advice_controls via render_openpower_advice callback",
        "OpenPower advisor recommendations and delegated-scope controls",
        "An explicit no-scenario-tips message followed by available OpenPower advice, or a no-advice message.",
        "Rendered only while the Tips tab is active and reflects current campaign recommendations and delegations.",
        "src/client/ui/panels/service/objectives_window_content.py; src/client/ui/panels/service/objectives_panel.py; .codex/layout_catalog.gml",
        "OpenPower fills the GML Tips page with its own advisor content; the supplied scenario schema has no authored tips field.",
        status="partial",
        action_required="Keep scenario tips explicitly unavailable and show only current OpenPower advice; add source-authored tips only if the scenario data model gains that field.",
        surface="ObjectivesWindowContent._render_tips_tab / Tab3/frmInner child",
    ),
}


def _component_kind(node: dict[str, Any]) -> str:
    name = str(node.get("name") or "").lower()
    type_name = str(node.get("type") or "").lower()
    combined = f"{name} {type_name}"
    if "graph" in combined or "plot" in combined:
        return "graph"
    if "meter" in combined or "progress" in combined:
        return "meter"
    if "buttn" in type_name or "button" in type_name or name.startswith("btn"):
        return "button"
    if "toggl" in type_name or name.startswith("tog"):
        return "toggle"
    if "edtbx" in type_name or name.startswith(("ed", "txtbox")):
        return "input"
    if "combo" in type_name or name.startswith("cbo"):
        return "combobox"
    if "lstbx" in type_name or name.startswith("lst"):
        return "list"
    if "label" in type_name or name.startswith(("txt", "lbl")):
        return "label"
    if "frame" in type_name or name.startswith("frm"):
        return "frame"
    return "custom"


def _window_candidates(templates: dict[str, Any], source_index: dict[str, Any]) -> list[str]:
    """Find likely user-facing windows from GML naming and registered C++ types.

    Some real windows use template names such as ``Unit_List_Window_New`` or
    ``Covert_Actions_New_Mission``. Requiring a ``_Window`` suffix silently
    dropped those screens and cut off their outgoing navigation paths.
    """
    candidates = {
        name for name in templates
        if name.lower().endswith("_window") or name in WINDOW_SPECIALS
    }
    reviewed_windows = set(PARTIALLY_IMPLEMENTED_WINDOW_GAPS)
    reviewed_windows.update(DISPLAY_BINDINGS_BY_WINDOW)
    for registry_name, registry in globals().items():
        if registry_name.endswith("_INTERACTION_BINDINGS") and isinstance(registry, dict):
            reviewed_windows.update(path.split("/", 1)[0] for path in registry)
    candidates.update(reviewed_windows.intersection(templates))
    window_root_types = {"frmbasewindow", "g_def_frame"}
    spawn_targets = set(source_index["spawn_templates"].values())
    methods_by_template: dict[str, set[str]] = defaultdict(set)
    for method, template in source_index["spawn_templates"].items():
        methods_by_template[template].add(method)

    for template, type_row in source_index["type_by_template"].items():
        root = templates.get(template)
        if root is None or str(root.get("type", "")).lower() not in window_root_types:
            continue
        class_name = type_row.get("class", "")
        registered = class_name in source_index["registered_classes"]
        spawn_methods = methods_by_template.get(template, set())
        has_window_signal = bool(
            re.search(r"Window|Submenu", class_name, re.I)
            or class_name.lower().endswith("menu")
            or any(re.search(r"Window|Submenu", method, re.I) for method in spawn_methods)
            or any(method.lower().endswith("menuspawn") for method in spawn_methods)
        )
        if has_window_signal and (registered or template in spawn_targets):
            candidates.add(template)

    return sorted(candidates)


def _inherits_base_window(source_index: dict[str, Any], class_name: str) -> bool:
    pending = [class_name]
    visited: set[str] = set()
    bases = source_index.get("base_classes", {})
    while pending:
        current = pending.pop()
        if current == "GBaseWindow":
            return True
        if current in visited:
            continue
        visited.add(current)
        pending.extend(bases.get(current, ()))
    return False


def _base_window_mouse_click_is_reachable(
    source_index: dict[str, Any],
    class_functions: dict[str, list[dict[str, Any]]],
    class_name: str,
    visited: set[str] | None = None,
) -> bool:
    """Follow only click handlers that inherit or explicitly delegate to the base handler."""
    if class_name == "GBaseWindow":
        return True
    checked = visited or set()
    if class_name in checked:
        return False
    checked.add(class_name)
    handlers = [
        function for function in class_functions.get(class_name, [])
        if function["method"] == "OnMouseClick"
    ]
    if handlers and not all(
        re.search(r"(?:__super|GBaseWindow)::OnMouseClick\s*\(", function["body"])
        for function in handlers
    ):
        return False
    return any(
        _base_window_mouse_click_is_reachable(source_index, class_functions, base, checked.copy())
        for base in source_index.get("base_classes", {}).get(class_name, ())
    )


def _member_bindings(functions: list[dict[str, Any]], template: str) -> dict[str, str]:
    bindings: dict[str, str] = {}
    for function in functions:
        if function["method"] != "OnCreate":
            continue
        body = function["body"]
        for assignment in re.finditer(
            r"\b([A-Za-z_]\w*)\s*(?<![=!<>])=(?!=)\s*([^;]+);", body, re.S
        ):
            member, expression = assignment.group(1), assignment.group(2)
            children = re.findall(r'Child\s*\(\s*L"([^"]+)"\s*\)', expression)
            if not children:
                continue
            parent_match = re.search(
                r"\b([A-Za-z_]\w*)\s*(?:->|\.)\s*Child", expression
            )
            if parent_match:
                parent_path = bindings.get(parent_match.group(1))
                if not parent_path:
                    continue
                bindings[member] = parent_path + "/" + "/".join(children)
            else:
                bindings[member] = template + "/" + "/".join(children)
    return bindings


def _condition_for_call(body: str, position: int) -> str:
    candidates: list[str] = []
    for match in re.finditer(r"\bif\s*\(", body[:position]):
        open_paren = body.find("(", match.start())
        close_paren = _find_matching(body, open_paren, "(", ")")
        if close_paren < 0 or close_paren >= position:
            continue
        condition = body[open_paren + 1:close_paren].strip()
        if "in_pCaller" not in condition:
            continue
        after = close_paren + 1
        while after < len(body) and body[after].isspace():
            after += 1
        if after < len(body) and body[after] == "{":
            block_end = _find_matching(body, after, "{", "}")
            if block_end > position:
                candidates.append(condition)
        else:
            statement_end = body.find(";", after)
            if statement_end >= position:
                candidates.append(condition)
    return candidates[-1] if candidates else ""


def _helper_closure(
    function: dict[str, Any],
    functions_by_name: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    discovered: list[dict[str, Any]] = []
    visited: set[str] = set()
    pending = [function["body"]]
    while pending:
        body = pending.pop()
        for match in re.finditer(r"(?<![.>\w])([A-Za-z_]\w*)\s*\(", body):
            name = match.group(1)
            if name in visited or name.startswith("On") or name not in functions_by_name:
                continue
            visited.add(name)
            helpers = functions_by_name[name]
            for helper in helpers:
                discovered.append(helper)
                pending.append(helper["body"])
    return discovered


def _display_target(index, method):
    # reference_data_display_layer.cpp:4100-4114 creates and shows this TypeName
    # through CREATE_GUI_OBJECT, bypassing the WindowSpawn naming convention.
    return index["spawn_templates"].get(method, "Generic_Question_Window" if method == "GenericQuestion" else "")


def _window_actions(text: str, index: dict[str, Any]) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    for match in re.finditer(r"g_ClientDDL\.(\w+WindowSpawn|GenericQuestion)\s*\(", text):
        target = _display_target(index, match.group(1))
        if target:
            actions.append({"target": target, "method": match.group(1), "action": "spawn"})
    for match in re.finditer(r"g_ClientDDL\.(\w+)\s*\(\s*\)\s*->\s*(Show|Hide|Toggle)\s*\(", text):
        getter = match.group(1)
        target = index["spawn_templates"].get(getter + "Spawn", "")
        if target:
            actions.append({"target": target, "method": getter, "action": match.group(2).lower()})
    return actions


def _position_visibility_references(
    body: str,
    *,
    variable: str = "",
    window_getter: str = "",
) -> list[tuple[int, str]]:
    receiver = re.escape(variable) if variable else ""
    if window_getter:
        receiver = rf"(?:g_ClientDDL\.)?{re.escape(window_getter)}\s*\(\s*\)"
    if not receiver:
        return []
    pattern = re.compile(
        rf"\b{receiver}\s*(?:->|\.)\s*"
        r"(Position|SetPosition|Size|SetSize|SetVisible|Visible|SetEnabled|Enabled|Show|Hide|Toggle|BringToFront)"
        r"\s*\("
    )
    references = []
    for match in pattern.finditer(body):
        open_paren = body.find("(", match.start(), match.end())
        close_paren = _find_matching(body, open_paren, "(", ")")
        if close_paren < 0:
            continue
        arguments = " ".join(body[open_paren + 1:close_paren].split())[:120]
        references.append((
            body.count("\n", 0, match.start()),
            f"{match.group(1)}({arguments})",
        ))
    return references


def _receiver_state_evidence(
    functions: list[dict[str, Any]],
    *,
    variable: str = "",
    window_getter: str = "",
) -> tuple[str, str]:
    calls: list[str] = []
    evidence: list[str] = []
    for function in functions:
        references = _position_visibility_references(
            function["body"], variable=variable, window_getter=window_getter,
        )
        for relative_line, call in references:
            source_line = function["body_line"] + relative_line
            calls.append(call)
            evidence.append(
                f"Client/Source/{function['file']}#L{source_line} "
                f"{function['class']}::{function['method']}"
            )
    return "; ".join(dict.fromkeys(calls)), "; ".join(dict.fromkeys(evidence))


def _component_geometry_visibility_expressions(member: str, code: str) -> list[str]:
    if not member:
        return []
    allowed = {
        "Position", "SetPosition", "Size", "SetSize", "Visible", "SetVisible",
        "Enabled", "SetEnabled", "BringToFront", "Show", "Hide", "Toggle",
    }
    expressions = []
    pattern = re.compile(rf"\b{re.escape(member)}\s*->\s*(\w+)\s*\(([^;]*)\)", re.S)
    for match in pattern.finditer(code):
        if match.group(1) not in allowed:
            continue
        line = code.count("\n", 0, match.start()) + 1
        arguments = " ".join(match.group(2).split())[:220]
        expressions.append(f"{match.group(1)}({arguments})@{line}")
    return expressions


def _caller_branch_evidence(
    functions: list[dict[str, Any]],
    member: str,
    functions_by_name: dict[str, list[dict[str, Any]]],
    source_index: dict[str, Any],
) -> list[dict[str, str]]:
    """Extract callback conditions and side-effect evidence for one bound control."""
    if not member:
        return []
    evidence: list[dict[str, str]] = []
    event_methods = {
        "OnMouseClick", "OnCustomEvent", "OnMouseDown", "OnMouseUp",
        "OnKeyDown", "OnKeyUp", "OnChar", "OnGlobalHotkey",
        "OnAddRemoveCountrySelection", "OnClickFromEarth", "OnColorButton",
        "OnLeftButton", "OnRightButton", "OnPartClick", "On_List_Items_Selected",
    }
    for function in functions:
        if function["method"] not in event_methods:
            continue
        body = function["body"]
        for condition_match in re.finditer(r"\bif\s*\(", body):
            open_paren = body.find("(", condition_match.start())
            close_paren = _find_matching(body, open_paren, "(", ")")
            if close_paren < 0:
                continue
            condition = body[open_paren + 1:close_paren].strip()
            caller_members = re.findall(r"in_pCaller\s*==\s*(m_\w+)", condition)
            if member not in caller_members:
                continue
            block_start = close_paren + 1
            while block_start < len(body) and body[block_start].isspace():
                block_start += 1
            if block_start >= len(body) or body[block_start] != "{":
                continue
            block_end = _find_matching(body, block_start, "{", "}")
            if block_end < 0:
                continue
            branch = body[block_start + 1:block_end]
            branch_function = {**function, "body": branch}
            helpers = _helper_closure(branch_function, functions_by_name)
            expanded = branch + "\n" + "\n".join(helper["body"] for helper in helpers)
            game_events = sorted(set(re.findall(
                r"CREATE_GAME_EVENT\s*\(\s*([A-Za-z_][\w:]*)\s*\)", expanded
            )))
            window_actions = _window_actions(expanded, source_index)
            side_effects = []
            if game_events:
                side_effects.append("reference game event(s): " + ", ".join(game_events))
            if "g_Joshua.RaiseEvent" in expanded:
                side_effects.append("raises an reference server-targeted game event")
            if "g_ClientDDL." in expanded and window_actions:
                side_effects.append("window/navigation: " + ", ".join(
                    f"{item['action']} {item['target']}" for item in window_actions
                ))
            if re.search(r"->\s*(?:Hide|Close|Kill)\s*\(", expanded):
                side_effects.append("closes or hides a UI window")
            if not side_effects:
                side_effects.append("callback body resolved; no recognized game-event dispatch")
            validation_conditions = []
            for nested_if in re.finditer(r"\bif\s*\(", branch):
                nested_open = branch.find("(", nested_if.start())
                nested_close = _find_matching(branch, nested_open, "(", ")")
                if nested_close >= 0:
                    nested_condition = branch[nested_open + 1:nested_close].strip()
                    if "in_pCaller" not in nested_condition:
                        validation_conditions.append(nested_condition)
            country_scope_evidence = "; ".join(
                " ".join(line.split())[:240]
                for line in expanded.splitlines()
                if re.search(r"ControlledCountry|CountryID|country_tag|isOwnCountry|foreign", line, re.I)
            )
            line = function["body_line"] + body[:block_start].count("\n")
            evidence.append({
                "event": function["method"],
                "condition": condition,
                "source_file": function.get("file", ""),
                "source_line": str(line),
                "game_events": ";".join(game_events),
                "side_effect": "; ".join(dict.fromkeys(side_effects)),
                "validation_evidence": "; ".join(dict.fromkeys(validation_conditions)) or "No nested validation condition identified in this callback branch.",
                "country_scope_evidence": country_scope_evidence or "unknown",
                "confirmation_evidence": "Generic_Message_Window acknowledgement routes are crosswalked in docs/ui/reference/generic_message_callback_map.csv" if "GenericMessageWindow" in expanded else "unknown",
                "error_evidence": "Generic_Message_Window message purpose and OpenPower route are crosswalked in docs/ui/reference/generic_message_callback_map.csv" if "GenericMessageWindow" in expanded else "unknown",
            })
    return evidence


def _source_control_path_status(
    source_widget: str,
    source_template: str,
    all_paths: dict[str, set[str]],
) -> str:
    if source_widget and source_template in all_paths and source_widget in all_paths[source_template]:
        return "verified_gml"
    return "verified_cpp"


def _window_edges(index: dict[str, Any], catalog: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, dict[str, str]]]:
    class_bindings: dict[str, dict[str, str]] = {}
    class_functions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    file_functions: dict[Path, list[dict[str, Any]]] = {}
    for path, text in index["texts"].items():
        functions = list(cpp_functions(text))
        for function in functions:
            function["file"] = path.name
        file_functions[path] = functions
        for function in functions:
            class_functions[function["class"]].append(function)
    for class_name, type_row in index["type_by_class"].items():
        class_bindings[class_name] = _member_bindings(class_functions.get(class_name, []), type_row["template"])

    all_paths = {
        template: {row["path"] for row in _walk(template, tree)}
        for template, tree in catalog["templates"].items()
    }
    edges: list[dict[str, Any]] = []
    event_names = {"OnMouseClick", "OnCustomEvent", "OnMouseDown", "OnMouseUp", "OnKeyDown", "OnKeyUp", "OnChar"}
    for path, functions in file_functions.items():
        source_text = index["texts"][path]
        functions_by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for candidate in functions:
            functions_by_name[candidate["method"]].append(candidate)
        for function in functions:
            if function["method"] not in event_names:
                continue
            source_type = index["type_by_class"].get(function["class"], {})
            source_template = source_type.get("template", "")
            for call in re.finditer(r"g_ClientDDL\.(\w+WindowSpawn|GenericQuestion)\s*\(", function["body"]):
                spawn_method = call.group(1)
                target_template = _display_target(index, spawn_method)
                condition = _condition_for_call(function["body"], call.start())
                caller_members = re.findall(r"in_pCaller\s*==\s*(m_\w+)", condition)
                member = caller_members[0] if len(caller_members) == 1 else ""
                source_widget = class_bindings.get(function["class"], {}).get(member, "")
                mode = "show"
                context = function["body"][call.start():call.start() + 520]
                getter = spawn_method.removesuffix("Spawn")
                if "ToggleState" in context and re.search(r"->\s*(?:Hide|Show)\s*\(", context):
                    mode = "toggle"
                elif re.search(rf"{re.escape(getter)}\s*\(\s*\)\s*->\s*Hide\s*\(", context):
                    mode = "close"
                line = function["body_line"] + function["body"][:call.start()].count("\n")
                source_url = f"{SOURCE_REPOSITORY}/Client/Source/{path.name}#L{line}"
                target_resolved = (
                    target_template in catalog["templates"]
                    or spawn_method in index["non_gml_spawn_targets"]
                )
                status = "verified_cpp" if target_resolved else "assumption/unknown"
                edges.append({
                    "source_window": source_template or function["class"],
                    "source_widget_path": source_widget or f"handler:{function['class']}::{function['method']}",
                    "control_path_status": _source_control_path_status(
                        source_widget, source_template, all_paths
                    ),
                    "event": function["method"],
                    "spawn_method": spawn_method,
                    "target_window": target_template or spawn_method,
                    "mode": mode,
                    "context": condition,
                    "passed_context": context.strip().splitlines()[0][:180],
                    "source_file": f"Client/Source/{path.name}",
                    "source_line": line,
                    "source_url": source_url,
                    "status": status,
                })

            if function["method"] not in {"OnMouseClick", "OnCustomEvent", "OnMouseDown", "OnMouseUp"}:
                continue
            caller_conditions: list[tuple[str, int, int]] = []
            for condition_match in re.finditer(r"\bif\s*\(", function["body"]):
                open_paren = function["body"].find("(", condition_match.start())
                close_paren = _find_matching(function["body"], open_paren, "(", ")")
                if close_paren < 0:
                    continue
                condition = function["body"][open_paren + 1:close_paren].strip()
                if "in_pCaller" not in condition:
                    continue
                block_start = close_paren + 1
                while block_start < len(function["body"]) and function["body"][block_start].isspace():
                    block_start += 1
                if block_start < len(function["body"]) and function["body"][block_start] == "{":
                    block_end = _find_matching(function["body"], block_start, "{", "}")
                    if block_end > block_start:
                        caller_conditions.append((condition, block_start, block_end))
            for condition, block_start, block_end in caller_conditions:
                branch = function["body"][block_start + 1:block_end]
                members = re.findall(r"in_pCaller\s*==\s*(m_\w+)", condition)
                if len(members) != 1:
                    continue
                member = members[0]
                source_widget = class_bindings.get(function["class"], {}).get(member, "")
                source_template = index["type_by_class"].get(function["class"], {}).get("template", "")
                branch_function = {**function, "body": branch}
                helpers = _helper_closure(branch_function, functions_by_name)
                helper_text = "\n".join(helper["body"] for helper in helpers)
                expanded = branch + "\n" + helper_text
                actions = _window_actions(expanded, index)
                target_actions: dict[str, set[str]] = defaultdict(set)
                for action in actions:
                    target_actions[action["target"]].add(action["action"])
                for target, action_types in target_actions.items():
                    key = (source_widget, target, function["method"])
                    if any(
                        (edge["source_widget_path"], edge["target_window"], edge["event"]) == key
                        for edge in edges
                    ):
                        continue
                    if "ToggleState" in expanded and {"show", "hide"}.issubset(action_types):
                        mode = "toggle"
                    elif "show" in action_types or "spawn" in action_types:
                        mode = "show"
                    elif "hide" in action_types:
                        mode = "close"
                    else:
                        mode = "show"
                    line = function["body_line"] + function["body"][:block_start].count("\n")
                    action_helper = next((
                        helper for helper in helpers
                        if any(action["target"] == target for action in _window_actions(helper["body"], index))
                    ), function)
                    action_method = next((
                        action["method"] for action in actions if action["target"] == target
                    ), "")
                    action_pattern = re.search(
                        rf"g_ClientDDL\.{re.escape(action_method)}(?:Spawn)?\s*\(",
                        action_helper["body"],
                    ) if action_method else None
                    action_line = action_helper["body_line"] + action_helper["body"][:action_pattern.start()].count("\n") if action_pattern else line
                    source_url = f"{SOURCE_REPOSITORY}/Client/Source/{path.name}#L{line}"
                    action_url = f"{SOURCE_REPOSITORY}/Client/Source/{path.name}#L{action_line}"
                    status = "verified_cpp" if (
                        target in catalog["templates"]
                        or target in index["non_gml_spawn_targets"].values()
                    ) else "assumption/unknown"
                    edges.append({
                        "source_window": source_template or function["class"],
                        "source_widget_path": source_widget or f"handler:{function['class']}::{function['method']}",
                        "control_path_status": _source_control_path_status(
                            source_widget, source_template, all_paths
                        ),
                        "event": function["method"],
                        "spawn_method": action_method,
                        "target_window": target,
                        "mode": mode,
                        "context": condition,
                        "passed_context": "local helper call; see action source line",
                        "source_file": f"Client/Source/{path.name}",
                        "source_line": line,
                        "source_url": source_url,
                        "action_source_file": f"Client/Source/{path.name}",
                        "action_source_line": action_line,
                        "action_source_url": action_url,
                        "status": status,
                    })
    for route in STATE_MACHINE_MENU_ROUTES:
        source_template = route["source_window"]
        source_widget = route["source_widget_path"]
        edges.append({
            **route,
            "control_path_status": _source_control_path_status(
                source_widget, source_template, all_paths
            ),
            "spawn_method": "FSM state transition",
            "mode": "show",
            "source_url": f"{SOURCE_REPOSITORY}/{route['source_file']}#L{route['source_line']}",
            "action_source_url": f"{SOURCE_REPOSITORY}/{route['action_source_file']}#L{route['action_source_line']}",
            "status": "verified_cpp",
        })

    edges.sort(key=lambda row: (row["source_window"], row["source_widget_path"], row["source_line"]))

    # Keep callback-driven and programmatic window opens visible in the graph.
    # The click-branch pass above supplies an exact GML control when available;
    # this pass accounts for the remaining source call sites without guessing a
    # widget path or treating initialization as user navigation.
    represented_calls = set()
    for edge in edges:
        source_file = Path(edge["source_file"]).name
        represented_calls.add((source_file, edge["source_line"], edge["target_window"]))
        if edge.get("action_source_file"):
            represented_calls.add((
                Path(edge["action_source_file"]).name,
                edge["action_source_line"],
                edge["target_window"],
            ))

    lifecycle_methods = {"OnCreate", "OnDestroy", "OnShow", "OnHide"}
    for path, functions in file_functions.items():
        for function in functions:
            for call in re.finditer(r"g_ClientDDL\.(\w+WindowSpawn|GenericQuestion)\s*\(", function["body"]):
                line = function["body_line"] + function["body"][:call.start()].count("\n")
                target_template = _display_target(index, call.group(1))
                if (
                    (path.name, line, target_template) in represented_calls
                    or function["method"] in lifecycle_methods
                ):
                    continue
                spawn_method = call.group(1)
                source_type = index["type_by_class"].get(function["class"], {})
                source_template = source_type.get("template", "")
                handler_path = f"handler:{function['class']}::{function['method']}"
                is_callback = function["method"].startswith("On")
                edge = {
                    "source_window": source_template or f"callback:{function['class']}",
                    "source_widget_path": handler_path,
                    "control_path_status": "verified_cpp",
                    "event": function["method"],
                    "spawn_method": spawn_method,
                    "trigger_type": "callback" if is_callback else "programmatic_callback",
                    "target_window": target_template or spawn_method,
                    "mode": "show",
                    "context": "",
                    "passed_context": function["body"][call.start():call.start() + 240].strip().splitlines()[0][:180],
                    "source_file": f"Client/Source/{path.name}",
                    "source_line": line,
                    "source_url": f"{SOURCE_REPOSITORY}/Client/Source/{path.name}#L{line}",
                    "status": "verified_cpp" if (
                        target_template in catalog["templates"]
                        or spawn_method in index["non_gml_spawn_targets"]
                    ) else "assumption/unknown",
                }
                edges.append(edge)
                represented_calls.add((path.name, line, target_template))

    return edges, class_bindings


def _panel_specs(registry_path: Path) -> tuple[dict[str, dict[str, str]], dict[str, str]]:
    text = registry_path.read_text(encoding="utf-8")
    specs: dict[str, dict[str, str]] = {}
    id_by_class: dict[str, str] = {}
    for match in re.finditer(r"PanelSpec\s*\(", text):
        open_paren = text.find("(", match.start())
        close_paren = _find_matching(text, open_paren, "(", ")")
        if close_paren < 0:
            continue
        block = text[open_paren + 1:close_paren]
        id_match = re.search(r'id\s*=\s*"([^"]+)"', block)
        if not id_match:
            continue
        class_match = re.search(r"\b(\w+Panel)\s*\(", block)
        factory_class = class_match.group(1) if class_match else ""
        panel_id = id_match.group(1)
        specs[panel_id] = {"factory_class": factory_class, "source": "src/client/ui/layouts/game_panel_registry.py"}
        if factory_class:
            id_by_class[factory_class] = panel_id
    return specs, id_by_class


def _layout_geometry_crosswalk(
    edges: list[dict[str, Any]],
    journey_rows: list[dict[str, Any]],
    component_rows: list[dict[str, Any]],
    window_rows: list[dict[str, Any]],
    journey_suite: dict[str, Any],
    *,
    viewport: tuple[int, int] = (1280, 720),
) -> list[dict[str, Any]]:
    return _build_layout_geometry_crosswalk(
        edges, journey_rows, component_rows, window_rows, journey_suite,
        viewport=viewport, repo_root=REPO_ROOT, latest_reports=LATEST_JOURNEY_REPORTS,
        edge_bindings=NAVIGATION_EDGE_BINDINGS,
    )


def _journey_execution_coverage_status(suite_status: str) -> str:
    return {
        "failed": "journey_failed",
        "not_run": "journey_not_run",
    }.get(suite_status, "journey_not_passed")


def _navigation_gap_status(coverage_status: str) -> str:
    return {
        "tested": "verified_openpower",
        "tested_unavailable_workflow": "verified_unavailable",
        "blocked_missing_workflow": "verified_unavailable",
        "explicitly_unimplemented": "verified_unavailable",
        "tested_equivalent_validation": "partial",
        "tested_equivalent_alternate_feedback": "partial",
        "tested_shared_component_contract": "partial",
        "tested_equivalent_guided_tutorial": "partial",
        "partial_window": "partial",
        "lifecycle_initialization": "verified_cpp",
        "inactive_source_code": "verified_cpp",
        "unreachable_source_branch": "verified_cpp",
    }.get(coverage_status, "assumption/unknown")


def _seed_transition_journey_rows(
    seed: dict[str, Any], journeys_dir: Path, suite_path: Path,
) -> list[dict[str, Any]]:
    suite_results: dict[str, dict[str, Any]] = {}
    if suite_path.is_file():
        suite = json.loads(suite_path.read_text(encoding="utf-8-sig"))
        for result in suite.get("results", []):
            suite_results[Path(result.get("journey", "")).name] = result

    rows: list[dict[str, Any]] = []
    for transition in seed.get("transitions", []):
        source = transition.get("source", "")
        journey_mapping = SEED_JOURNEY_MAP.get(source)
        if journey_mapping is None:
            destination = transition.get("destination", "")
            status = (
                "partially_implemented" if destination in PARTIALLY_IMPLEMENTED_WINDOW_GAPS else
                "explicitly_unimplemented" if destination in UNIMPLEMENTED_WINDOW_GAPS else
                "unmapped"
            )
            rows.append({
                "source_widget_path": source,
                "destination_window": destination,
                "source_file": transition.get("source_file", ""),
                "source_line": transition.get("source_line", ""),
                "journey_file": "",
                "openpower_click_test_id": "",
                "expected_openpower_region": "",
                "journey_has_source_click": False,
                "journey_asserts_target_region": False,
                "journey_suite_status": "not_applicable",
                "coverage_status": status,
            })
            continue

        filename, click_target, region_target = journey_mapping
        journey_path = journeys_dir / filename
        has_click = False
        asserts_region = False
        if journey_path.is_file():
            journey = json.loads(journey_path.read_text(encoding="utf-8-sig"))
            has_click = any(
                step.get("op") == "click" and step.get("target") == click_target
                for step in journey.get("steps", [])
            )
            asserts_region = any(
                step.get("op") == "assert_region" and step.get("target") == region_target
                and step.get("visible", True)
                for step in journey.get("steps", [])
            )
        suite_result = suite_results.get(filename)
        latest_report = LATEST_JOURNEY_REPORTS.get(filename)
        if latest_report is not None:
            latest_report_path = REPO_ROOT / latest_report
            if latest_report_path.is_file():
                try:
                    latest_report_data = json.loads(latest_report_path.read_text(encoding="utf-8-sig"))
                except (OSError, json.JSONDecodeError):
                    latest_report_data = {}
                suite_result = {"passed": latest_report_data.get("result") == "passed"}
        suite_status = (
            "passed" if suite_result and suite_result.get("passed") else
            "failed" if suite_result else "not_run"
        )
        if not journey_path.is_file():
            coverage_status = "journey_missing"
        elif not has_click:
            coverage_status = "source_click_missing"
        elif not asserts_region:
            coverage_status = "target_assertion_missing"
        elif suite_status != "passed":
            coverage_status = _journey_execution_coverage_status(suite_status)
        else:
            coverage_status = "tested"
        rows.append({
            "source_widget_path": source,
            "destination_window": transition.get("destination", ""),
            "source_file": transition.get("source_file", ""),
            "source_line": transition.get("source_line", ""),
            "journey_file": f"tests/ui/journeys/{filename}",
            "openpower_click_test_id": click_target,
            "expected_openpower_region": region_target,
            "journey_has_source_click": has_click,
            "journey_asserts_target_region": asserts_region,
            "journey_suite_status": suite_status,
            "coverage_status": coverage_status,
        })
    return rows


def _navigation_journey_coverage_rows(
    edges: list[dict[str, Any]],
    window_rows: list[dict[str, Any]],
    seed_rows: list[dict[str, Any]],
    journeys_dir: Path,
    suite_path: Path,
) -> list[dict[str, Any]]:
    suite_results: dict[str, dict[str, Any]] = {}
    bindings_path = REPO_ROOT / "docs/ui/reference/navigation_route_bindings.json"
    reviewed_routes = json.loads(bindings_path.read_text(encoding="utf-8")) if bindings_path.exists() else []
    reviewed_by_site = {(r["source_file"], int(r["source_line"]), r["target_window"]): r
                        for r in reviewed_routes}
    if suite_path.is_file():
        suite = json.loads(suite_path.read_text(encoding="utf-8-sig"))
        suite_results = {
            Path(result.get("journey", "")).name: result
            for result in suite.get("results", [])
        }

    reachability = {row["window_id"]: row["status"] for row in window_rows}
    surfaces = {row["window_id"]: row["openpower_surface"] for row in window_rows}
    seed_by_route = {
        (row["source_widget_path"], row["destination_window"]): row
        for row in seed_rows
    }
    rows: list[dict[str, Any]] = []
    for edge in edges:
        source = edge["source_widget_path"]
        target = edge["target_window"]
        mode = edge["mode"]
        seed = seed_by_route.get((source, target))
        binding = ADDITIONAL_NAVIGATION_JOURNEY_MAP.get((source, target, mode))
        reviewed = reviewed_by_site.get((edge["source_file"], int(edge["source_line"]), target))
        if reviewed and reviewed.get("journey_file"):
            binding = NavigationJourneyBinding(
                Path(reviewed["journey_file"]).name, reviewed["operation"], reviewed["control_id"],
                reviewed["expected_region"], reviewed.get("expected_visible", True),
                reviewed.get("expected_present", True))
        if seed is not None:
            filename = Path(seed["journey_file"]).name
            operation = "click"
            control_id = seed["openpower_click_test_id"]
            expected_region = seed["expected_openpower_region"]
            expected_visible = True
            expected_present = True
            binding_source = "seed transition crosswalk"
        elif binding is not None:
            filename = binding.journey_file
            operation = binding.operation
            control_id = binding.control_id
            expected_region = binding.expected_region
            expected_visible = binding.expected_visible
            expected_present = binding.expected_present
            binding_source = "source-reviewed route mapping"
        else:
            filename = operation = control_id = expected_region = ""
            expected_visible = expected_present = None
            binding_source = ""

        journey_path = journeys_dir / filename if filename else None
        journey_has_operation = False
        journey_asserts_region = False
        if journey_path is not None and journey_path.is_file():
            journey = json.loads(journey_path.read_text(encoding="utf-8-sig"))
            steps = journey.get("steps", [])
            journey_has_operation = any(
                step.get("op") == operation
                and step.get("key" if operation in {"key", "key_down", "key_up"} else
                             "fixture" if operation == "server_snapshot" else "target") == control_id
                for step in steps
            )
            journey_asserts_region = any(
                step.get("op") == "assert_region"
                and step.get("target") == expected_region
                and step.get("visible", True) == expected_visible
                and (
                    expected_present is None
                    or step.get("present", True) == expected_present
                )
                for step in steps
            )

        suite_result = suite_results.get(filename) if filename else None
        latest_report = LATEST_JOURNEY_REPORTS.get(filename) if filename else None
        if latest_report is not None:
            latest_report_path = REPO_ROOT / latest_report
            if latest_report_path.is_file():
                try:
                    latest_report_data = json.loads(latest_report_path.read_text(encoding="utf-8-sig"))
                except (OSError, json.JSONDecodeError):
                    latest_report_data = {}
                suite_result = {"passed": latest_report_data.get("result") == "passed"}
        suite_status = (
            "passed" if suite_result and suite_result.get("passed") else
            "failed" if suite_result else
            "not_run" if filename else "not_mapped"
        )
        if filename and journey_path is not None and not journey_path.is_file():
            coverage_status = "journey_missing"
        elif filename and not journey_has_operation:
            coverage_status = "source_operation_missing"
        elif filename and not journey_asserts_region:
            coverage_status = "destination_assertion_missing"
        elif filename and suite_status != "passed":
            coverage_status = _journey_execution_coverage_status(suite_status)
        elif filename:
            verification_kind = reviewed.get("verification_kind") if reviewed else None
            coverage_status = {
                "equivalent_validation": "tested_equivalent_validation",
                "equivalent_alternate_feedback": "tested_equivalent_alternate_feedback",
                "shared_component_contract": "tested_shared_component_contract",
                "guided_tutorial_equivalent": "tested_equivalent_guided_tutorial",
                "unavailable_workflow": "tested_unavailable_workflow",
            }.get(verification_kind, "tested")
        elif reviewed:
            coverage_status = reviewed["status"]
        elif target in PARTIALLY_IMPLEMENTED_WINDOW_GAPS:
            coverage_status = "partial_window"
        elif target in UNIMPLEMENTED_WINDOW_GAPS:
            coverage_status = "explicitly_unimplemented"
        elif reachability.get(edge["source_window"]) == "reachable":
            coverage_status = "reachable_route_test_missing"
        else:
            coverage_status = "conditional_source_not_tested"

        if filename and journey_has_operation and journey_asserts_region and suite_status == "passed":
            action_required = (
                reviewed["reason"]
                if reviewed and reviewed.get("verification_kind") == "unavailable_workflow"
                else ""
            )
        elif reviewed and not filename:
            action_required = reviewed["reason"]
        elif target in PARTIALLY_IMPLEMENTED_WINDOW_GAPS:
            action_required = PARTIALLY_IMPLEMENTED_WINDOW_GAPS[target]["action_required"]
        elif target in UNIMPLEMENTED_WINDOW_GAPS:
            action_required = UNIMPLEMENTED_WINDOW_GAPS[target]["action_required"]
        elif coverage_status == "reachable_route_test_missing":
            action_required = (
                "Add a Python journey for this verified source transition and assert its destination region "
                "or dispatched GameAction."
            )
        elif coverage_status == "conditional_source_not_tested":
            action_required = (
                "Resolve the conditional or callback trigger to a testable Python route, or document why "
                "the source path has no OpenPower equivalent."
            )
        else:
            action_required = ""

        rows.append({
            "source_window": edge["source_window"],
            "source_reachability": reachability.get(edge["source_window"], "unknown"),
            "source_widget_path": source,
            "source_gml_component_path": reviewed.get("source_gml_component_path", "") if reviewed else "",
            "control_path_status": edge["control_path_status"],
            "event": edge["event"],
            "target_window": target,
            "effective_target_window": reviewed.get("effective_target_window", target) if reviewed else target,
            "openpower_surface": (reviewed.get("openpower_surface", surfaces.get(target, "missing"))
                                  if reviewed else surfaces.get(target, "missing")),
            "mode": mode,
            "condition": edge["context"],
            "journey_file": f"tests/ui/journeys/{filename}" if filename else "",
            "journey_operation": operation,
            "journey_control_id": control_id,
            "expected_openpower_region": expected_region,
            "expected_visible": expected_visible if expected_visible is not None else "",
            "expected_present": expected_present if expected_present is not None else "",
            "journey_has_source_operation": journey_has_operation,
            "journey_asserts_destination": journey_asserts_region,
            "journey_suite_status": suite_status,
            "coverage_status": coverage_status,
            "mapping_source": binding_source,
            "route_review": (
                reviewed.get("reason", "") if reviewed else
                NAVIGATION_EDGE_BINDINGS.get(source, {}).get("route_review", "")
            ),
            "action_required": action_required,
            "source_file": edge["source_file"],
            "source_line": edge["source_line"],
        })
    return rows


def generate(source_root: Path, output_dir: Path, journey_suite_path: Path | None = None) -> dict[str, Any]:
    catalog_path = resolve_reference_file(source_root, "reference_ui_catalog.json")
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    seed_navigation = json.loads(
        resolve_reference_file(source_root, "reference_ui_navigation_verified.json").read_text(encoding="utf-8")
    )
    templates = catalog["templates"]
    validation = _validate_gml(source_root / "layout_catalog.gml", catalog)
    source_index = _source_index(source_root / "Client" / "Source")
    edges, bindings = _window_edges(source_index, catalog)
    panel_specs, _ = _panel_specs(REPO_ROOT / "src/client/ui/layouts/game_panel_registry.py")
    candidates = _window_candidates(templates, source_index)
    paths_by_template = {
        template: list(_walk(template, tree))
        for template, tree in templates.items()
    }

    reached = reachable_windows(edges, candidates, ('Main_Bar', 'Main_Menu'))

    panel_by_window: dict[str, str] = {}
    for window, (panel_id, _) in PANEL_ALIASES.items():
        if panel_id in panel_specs:
            panel_by_window[window] = panel_id
    surface_by_window = {
        window: f"PanelSpec/{panel_id}"
        for window, panel_id in panel_by_window.items()
    }
    surface_by_window.update({window: surface for window, (surface, _) in LAYOUT_SURFACES.items()})

    window_rows: list[dict[str, Any]] = []
    template_usage = source_index["all_code"]
    type_by_template = source_index["type_by_template"]
    for window in candidates:
        type_row = (
            {}
            if window in INACTIVE_SOURCE_TEMPLATE_WINDOWS
            else type_by_template.get(window, {})
        )
        spawn_calls = [
            call for calls in source_index["spawn_calls"].values()
            for call in calls if call.get("target") == window
        ]
        registered = type_row.get("class", "") in source_index["registered_classes"]
        has_runtime_reference = bool(re.search(rf"\b{re.escape(window)}\b", template_usage))
        if window in reached:
            status = "reachable"
        elif spawn_calls:
            status = "conditional"
        elif window in INACTIVE_SOURCE_TEMPLATE_WINDOWS:
            status = "unused"
        elif registered or type_row:
            status = "unknown"
        elif not has_runtime_reference:
            status = "unused"
        else:
            status = "unknown"
        root = templates[window]
        props = root.get("properties") or {}
        sections = [child["name"] for child in root.get("children", []) if _component_kind(child) == "frame"]
        direct_spawns = [
            method for method, target in source_index["spawn_templates"].items() if target == window
        ]
        discovery_evidence = ["GML name"] if (
            window.lower().endswith("_window") or window in WINDOW_SPECIALS
        ) else []
        if type_row:
            discovery_evidence.append("C++ TypeName")
        if registered:
            discovery_evidence.append("REGISTER_GUI_OBJECT")
        if direct_spawns:
            discovery_evidence.append("WindowSpawn/ObjectSpawn method")
        panel_id = panel_by_window.get(window, "")
        surface = surface_by_window.get(window, "missing")
        if window in PANEL_ALIASES:
            equivalence = PANEL_ALIASES[window][1]
        elif window in LAYOUT_SURFACES:
            equivalence = LAYOUT_SURFACES[window][1]
        else:
            equivalence = "assumption/unknown"
        if panel_id not in panel_specs:
            if window in PANEL_ALIASES:
                panel_id = ""
                surface = "missing"
                equivalence = "assumption/unknown"
            elif window not in LAYOUT_SURFACES:
                panel_id = ""
                surface = "missing"
                equivalence = "missing"
        if window in PARTIALLY_IMPLEMENTED_WINDOW_GAPS:
            if window not in PANEL_ALIASES:
                panel_id = ""
            surface = PARTIALLY_IMPLEMENTED_WINDOW_GAPS[window]["current_implementation"]
            equivalence = "partial"
        gml_line = root.get("line", "")
        cpp_source = f"Client/Source/{type_row['file']}#L{type_row['line']}" if type_row else f"layout_catalog.gml#L{gml_line}"
        window_rows.append({
            "window_id": window,
            "name_or_purpose": window,
            "gml_template": window,
            "discovery_evidence": ";".join(discovery_evidence),
            "source_path": cpp_source,
            "status": status,
            "width": props.get("Width", ""),
            "height": props.get("Height", ""),
            "sections": ";".join(sections),
            "cpp_type": type_row.get("class", ""),
            "registered_gui_object": registered,
            "window_spawn_methods": ";".join(direct_spawns),
            "window_spawn_call_count": len(spawn_calls),
            "openpower_panel_spec": panel_id,
            "openpower_surface": surface,
            "mapping_status": equivalence,
        })

    component_rows: list[dict[str, Any]] = []
    data_rows: list[dict[str, Any]] = []
    interaction_rows: list[dict[str, Any]] = []
    edge_by_widget: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in edges:
        edge_by_widget[edge["source_widget_path"]].append(edge)

    file_functions = {}
    for path, text in source_index["texts"].items():
        functions = list(cpp_functions(text))
        for function in functions:
            function["file"] = path.name
        file_functions[path] = functions
    class_functions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for functions in file_functions.values():
        for function in functions:
            class_functions[function["class"]].append(function)

    for window in candidates:
        type_row = (
            {}
            if window in INACTIVE_SOURCE_TEMPLATE_WINDOWS
            else type_by_template.get(window, {})
        )
        class_name = type_row.get("class", "")
        class_bindings = bindings.get(class_name, {})
        reverse_bindings = {path: member for member, path in class_bindings.items()}
        code = source_index["texts"].get(source_index["files"][0], "")
        if type_row:
            source_path = source_index["texts"].get(source_index["files"][0], "")
            matching_path = next((p for p in source_index["files"] if p.name == type_row["file"]), None)
            code = source_index["texts"].get(matching_path, "") if matching_path else ""
        else:
            code = ""
        all_paths = {record["path"]: record for record in paths_by_template[window]}
        for record in paths_by_template[window]:
            node = record["node"]
            path = record["path"]
            props = node.get("properties") or {}
            member = reverse_bindings.get(path, "")
            usages = []
            display_writes = []
            geometry_visibility = _component_geometry_visibility_expressions(member, code)
            if member and code:
                for use in re.finditer(rf"\b{re.escape(member)}\s*->\s*(\w+)\s*\(([^;]*)\)", code, re.S):
                    line = code.count("\n", 0, use.start()) + 1
                    method_name = use.group(1)
                    arguments = " ".join(use.group(2).split())[:220]
                    usages.append(f"{method_name}(...)@{line}")
                    if method_name in {
                        "Text", "Value", "Current_Value", "MeterValue", "Selected_Content",
                        "Visible", "Enabled", "Width", "Add_Item", "SetValue", "SetText", "Set_Data",
                    } and arguments:
                        display_writes.append(f"{method_name}({arguments})@{line}")
            kind = _component_kind(node)
            display_binding = next(
                (
                    mapped
                    for suffix_key, mapped in DISPLAY_BINDINGS_BY_WINDOW.get(window, {}).items()
                    if path.removeprefix(window + "/") == suffix_key
                ),
                None,
            )
            component_rows.append({
                "window_id": window,
                "component_path": path,
                "component_id": node.get("name", ""),
                "type": node.get("type", ""),
                "kind": kind,
                "parent_path": record["parent"],
                "sibling_order": record["order"],
                "left": props.get("Left", ""),
                "top": props.get("Top", ""),
                "width": props.get("Width", ""),
                "height": props.get("Height", ""),
                "anchor": props.get("Anchor", ""),
                "z_order": props.get("ZORDER", node.get("z_order", "")),
                "text_token": props.get("Text", ""),
                "tooltip_token": props.get("ToolTipText", ""),
                "gml_enabled": props.get("Enabled", ""),
                "gml_visible": props.get("Visible", ""),
                "cpp_member_binding": member,
                "cpp_member_operations": ";".join(usages),
                "cpp_member_value_expressions": ";".join(display_writes),
                "cpp_member_geometry_visibility": ";".join(geometry_visibility),
                "gml_line": node.get("line", ""),
                "status": "verified_gml" if node.get("line") else "assumption/unknown",
            })

            if kind in {"label", "meter", "graph", "list", "combobox"} or display_binding is not None or (
                window == "History_Window"
                and path == "History_Window/frmInner/frmHistory/frmGraph/Container"
            ):
                hint = ""
                unit = "unknown"
                if display_binding is not None:
                    hint = display_binding.state_binding
                    unit = display_binding.units
                is_generic_message_text = (
                    window == "Generic_Message_Window"
                    and path == "Generic_Message_Window/lblMessage"
                )
                is_region_control_text = (
                    window == "Region_Control_Change_Window"
                    and path == "Region_Control_Change_Window/frmClip/lblMessage"
                )
                if is_generic_message_text:
                    hint = "MessageDialogContent.message"
                    unit = "localized message text"
                if is_region_control_text:
                    hint = "region_control_dispatches(state, country_tag)"
                    unit = "localized region-name list"
                if hint:
                    meaning = f"{display_binding.meaning} " if display_binding and display_binding.meaning else ""
                    if is_generic_message_text:
                        what_is_displayed = "Message text supplied by each Generic_Message_Window caller and passed to GenericMessageDialog.show(message)."
                    elif is_region_control_text:
                        what_is_displayed = (
                            "TERRITORY GAINED or TERRITORY LOST followed by the names of regions "
                            "whose latest ownership transition affects the local country."
                        )
                    elif display_binding and display_binding.meaning:
                        what_is_displayed = f"{meaning}OpenPower binding {hint}."
                    else:
                        what_is_displayed = f"OpenPower binding {hint}; GML display meaning remains token-based."
                elif member and usages:
                    what_is_displayed = (
                        f"Display member {member}; operations are listed below, but its semantic value is unresolved."
                    )
                elif props.get("Text", "") != "":
                    what_is_displayed = (
                        f"GML text token {props.get('Text')!r}; localization/placeholder meaning is unresolved."
                    )
                else:
                    what_is_displayed = "Unresolved; no literal GML text token or C++ display member was found."
                data_rows.append({
                    "window_id": window,
                    "component_path": path,
                    "gml_line": node.get("line", ""),
                    "kind": kind,
                    "gml_type": node.get("type", ""),
                    "gml_text_token": props.get("Text", ""),
                    "what_is_displayed": what_is_displayed,
                    "cpp_source": f"Client/Source/{type_row['file']}" if type_row else "",
                    "cpp_member_binding": member,
                    "cpp_member_operations": ";".join(usages),
                    "cpp_display_expressions": ";".join(display_writes),
                    "cpp_geometry_visibility_expressions": ";".join(geometry_visibility),
                    "openpower_panel_spec": panel_by_window.get(window, ""),
                    "openpower_surface": (
                        "GameLayout/GenericMessageDialog"
                        if is_generic_message_text else
                        "GameLayout/MAIL → region-control dispatch → TextNotificationDialog"
                        if is_region_control_text else
                        display_binding.surface
                        if display_binding and display_binding.surface else
                        surface_by_window.get(window, "missing")
                    ),
                    "openpower_state_binding": hint or "unmapped/missing",
                    "openpower_binding_source": (
                        "src/client/ui/components/shared/generic_message_dialog.py::GenericMessageDialog.show(message)"
                        if is_generic_message_text else
                        "src/client/ui/panels/service/region_control_dispatches.py::region_control_dispatches"
                        if is_region_control_text else
                        display_binding.openpower_source if display_binding else ""
                    ),
                    "openpower_binding_status": (
                        display_binding.status if display_binding else
                        "verified_openpower"
                        if is_generic_message_text or is_region_control_text else
                        "assumption/unknown"
                    ),
                    "units": unit,
                    "fallback": (
                        "Empty message bodies are ignored by GenericMessageDialog.show."
                        if is_generic_message_text else
                        "Unknown region IDs display as 'Region <id>'; missing names do not create numeric data."
                        if is_region_control_text else
                        display_binding.fallback if display_binding else
                        "unavailable/unknown; do not substitute a numeric value"
                    ),
                    "update_rule": (
                        "Replaced whenever a caller invokes show(...); no polling cadence."
                        if is_generic_message_text else
                        "Recomputed from the authoritative event journal when the local inbox is rendered; the latest local ownership transition determines each region's gained/lost group."
                        if is_region_control_text else
                        display_binding.update_rule if display_binding else
                        f"C++ member operations are listed at source lines; refresh cadence is unresolved."
                        if usages else
                        "No C++ member operation was found; refresh cadence is unresolved."
                    ),
                    "action_required": (
                        "Keep every active caller and acknowledgement route crosswalked in generic_message_callback_map.csv; preserve source-only workflows as explicit gaps."
                        if is_generic_message_text else
                        "Preserve local-country scoping, latest-transition grouping, and the source-sized message dialog."
                        if is_region_control_text else
                        display_binding.action_required
                        if display_binding and display_binding.action_required else
                        "Keep this value explicitly unavailable until an authoritative OpenPower field is added; do not infer it from unrelated data."
                        if display_binding and display_binding.status == "verified_unavailable" else
                        "Compare the source expression meaning against this OpenPower binding before claiming data-level parity."
                        if hint else
                        "Trace the C++ value expression to a model/column; map it in OpenPower or record that the data is absent, then specify units, fallback, and refresh cadence."
                    ),
                    "status": (
                        display_binding.status if display_binding else
                        "verified_cpp" if usages else "assumption/unknown"
                    ),
                })

            if kind in {"button", "toggle", "input", "combobox", "list"}:
                paths = edge_by_widget.get(path, [])
                source_functions = class_functions.get(class_name, [])
                inherited_exit = (
                    not member
                    and path.endswith("/frmTitle/btnExit")
                    and _inherits_base_window(source_index, class_name)
                )
                interaction_member = "m_pObjExitBtn" if inherited_exit else member
                functions_by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
                for candidate_function in source_functions:
                    functions_by_name[candidate_function["method"]].append(candidate_function)
                branch_evidence = _caller_branch_evidence(
                    source_functions,
                    interaction_member,
                    functions_by_name,
                    source_index,
                )
                if (
                    inherited_exit
                    and not branch_evidence
                    and _base_window_mouse_click_is_reachable(
                        source_index,
                        class_functions,
                        class_name,
                    )
                ):
                    base_functions = class_functions.get("GBaseWindow", [])
                    base_functions_by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
                    for base_function in base_functions:
                        base_functions_by_name[base_function["method"]].append(base_function)
                    branch_evidence = _caller_branch_evidence(
                        base_functions,
                        interaction_member,
                        base_functions_by_name,
                        source_index,
                    )
                    for branch in branch_evidence:
                        branch["side_effect"] = (
                            "GBaseWindow::ExitWindow checks dirty state and save authority; "
                            "it hides a clean window or opens SaveConfirmationWindow for a dirty one."
                        )
                        branch["validation_evidence"] = (
                            "Dirty-save handling requires the controlled country to match the selected "
                            "country or NeedCountryCheckToSave() to be false."
                        )
                        branch["country_scope_evidence"] = (
                            "ControlledCountryID() == SelectedCountryID() or !NeedCountryCheckToSave()."
                        )
                        branch["confirmation_evidence"] = (
                            "A dirty authorized exit opens SaveConfirmationWindow unless the preference "
                            "suppresses it; AlwaysApply saves and hides."
                        )
                        branch["error_evidence"] = (
                            "Closing itself dispatches no server action; Save() may have panel-specific effects."
                        )
                route_summary = "; ".join(
                    f"{edge['mode']} {edge['target_window']} ({edge['status']})" for edge in paths
                )
                callback_summary = "; ".join(
                    f"{branch['condition']} at {branch['source_file']}:{branch['source_line']}: "
                    f"{branch['side_effect']}"
                    for branch in branch_evidence
                )
                verified_transition = "; ".join(
                    value for value in (route_summary, callback_summary) if value
                )
                reference_events = sorted({
                    event
                    for branch in branch_evidence
                    for event in branch["game_events"].split(";")
                    if event
                })
                reference_side_effects = "; ".join(dict.fromkeys(
                    branch["side_effect"] for branch in branch_evidence
                ))
                validation_evidence = "; ".join(dict.fromkeys([
                    *(edge["context"] for edge in paths if edge["context"]),
                    *(branch["validation_evidence"] for branch in branch_evidence if branch["validation_evidence"]),
                ]))
                confirmation_evidence = "; ".join(dict.fromkeys(
                    branch["confirmation_evidence"] for branch in branch_evidence if branch["confirmation_evidence"]
                )) or "unknown"
                error_evidence = "; ".join(dict.fromkeys(
                    branch["error_evidence"] for branch in branch_evidence if branch["error_evidence"]
                )) or "unknown"
                openpower_action = (
                    "unknown; reference C++ event(s) require an explicit OpenPower GameAction mapping: " + ", ".join(reference_events)
                    if reference_events else
                    "none (window navigation only)" if paths else
                    "unknown; callback effect must be classified as read-only or mapped to a GameAction"
                )
                if reference_events:
                    interaction_action_required = (
                        "Map the reference server event to an existing GameAction or document the missing action; verify ownership restrictions and confirmation/error states."
                    )
                elif paths:
                    interaction_action_required = "Verify the exact OpenPower click route and destination visibility."
                else:
                    interaction_action_required = (
                        "Trace the callback effect; classify it as read-only or map it to a GameAction, and record restrictions/confirmation/error states."
                    )
                interaction_row = {
                    "window_id": window,
                    "component_path": path,
                    "input": kind,
                    "cpp_member_binding": interaction_member,
                    "cpp_source": f"Client/Source/{type_row['file']}" if type_row else "",
                    "reference_callback": ";".join(
                        f"{branch['event']}@{branch['source_file']}:{branch['source_line']}" for branch in branch_evidence
                    ),
                    "reference_game_event": ";".join(reference_events),
                    "reference_side_effect": reference_side_effects or (route_summary if paths else "unknown"),
                    "verified_cpp_transition": verified_transition,
                    "validation_condition": validation_evidence or "unknown",
                    "openpower_panel_spec": panel_by_window.get(window, ""),
                    "openpower_surface": surface_by_window.get(window, "missing"),
                    "openpower_effect": "route mapped; see navigation graph" if paths and surface_by_window.get(window) else "unmapped or requires field-level audit",
                    "game_action": openpower_action,
                    "read_only_or_state_changing": (
                        "state-changing reference server event" if reference_events else
                        "window navigation" if paths else
                        "unknown"
                    ),
                    "country_scope_restriction": "; ".join(dict.fromkeys(
                        branch["country_scope_evidence"] for branch in branch_evidence
                    )) or "unknown",
                    "confirmation_state": confirmation_evidence,
                    "error_state": error_evidence,
                    "restrictions_confirmation_error": "unknown unless explicitly described by linked implementation",
                    "action_required": interaction_action_required,
                    "status": (
                        "verified_cpp"
                        if any(edge["status"] == "verified_cpp" for edge in paths) or branch_evidence
                        else "assumption/unknown"
                    ),
                }
                if window == "Generic_Message_Window" and path.endswith("/btnOk"):
                    interaction_row.update({
                        "reference_side_effect": (
                            "Hide the dialog; dispatch c_OnGenericMessageWindowAnswerEvent to the stored caller when present; "
                            "then notify observers with c_OnGenericMessageWindowOk."
                        ),
                        "openpower_effect": (
                            "GenericMessageDialog.acknowledge clears the dialog and invokes the optional on_acknowledge callback."
                        ),
                        "openpower_surface": "GameLayout/GenericMessageDialog.acknowledge",
                        "game_action": "none (acknowledgement and caller callback only)",
                        "read_only_or_state_changing": "UI acknowledgement and caller-specific follow-up",
                        "confirmation_state": "Acknowledgement; it does not authorize or confirm a game action.",
                        "error_state": "Caller-specific behavior and OpenPower disposition are listed in generic_message_callback_map.csv.",
                        "action_required": "Keep caller-specific follow-up explicit; do not treat OK as confirmation of a game action.",
                    })
                if window == "Region_Control_Change_Window" and path.endswith("/btnOk"):
                    interaction_row.update({
                        "reference_side_effect": "Hide the region-change message window.",
                        "openpower_effect": (
                            "TextNotificationDialog._dismiss clears the acknowledged report and advances any queued notice."
                        ),
                        "openpower_surface": "GameLayout/TextNotificationDialog._dismiss",
                        "game_action": "none (read-only acknowledgement)",
                        "read_only_or_state_changing": "read-only acknowledgement",
                        "confirmation_state": "No game action is confirmed by this button.",
                        "error_state": "No action rejection state; the report content is event-derived.",
                        "restrictions_confirmation_error": "The report button only dismisses the displayed notice.",
                        "action_required": "Keep the report route read-only and preserve queued-notice behavior.",
                        "status": "verified_openpower",
                    })
                openpower_binding = (TRADE_INTERACTION_BINDINGS.get(path)
                                     or BATTLE_SUMMARY_INTERACTION_BINDINGS.get(path)
                                     or BATTLE_INFO_INTERACTION_BINDINGS.get(path)
                                     or SYSTEM_BAR_INTERACTION_BINDINGS.get(path)
                                     or MINI_MAP_INTERACTION_BINDINGS.get(path)
                                     or WAR_LIST_INTERACTION_BINDINGS.get(path)
                                     or HISTORY_INTERACTION_BINDINGS.get(path)
                                     or EVENT_LOG_INTERACTION_BINDINGS.get(path)
                                     or MAIL_INTERACTION_BINDINGS.get(path)
                                     or RESOURCE_POLICY_INTERACTION_BINDINGS.get(path)
                                     or RESOURCE_UNAVAILABLE_INTERACTION_BINDINGS.get(path)
                                     or BUDGET_RESOURCES_TITLE_INTERACTION_BINDINGS.get(path)
                                     or THEMATIC_MAP_LEGEND_INTERACTION_BINDINGS.get(path)
                                     or BATTLE_OVERVIEW_SMALL_UNIT_INFO_INTERACTION_BINDINGS.get(path)
                                     or ECONOMIC_WINDOW_METER_INTERACTION_BINDINGS.get(path)
                                     or INTERNAL_LAWS_INTERACTION_BINDINGS.get(path)
                                     or TREATIES_WINDOW_INTERACTION_BINDINGS.get(path)
                                     or TUTORIAL_MENU_INTERACTION_BINDINGS.get(path)
                                     or ADVISOR_PLAN_INTERACTION_BINDINGS.get(path)
                                     or _ADVISOR_SETTINGS_WINDOW_ACTIONS.get(path)
                                     or INCREASE_PRODUCTION_INTERACTION_BINDINGS.get(path)
                                     or UNIT_ATTACK_INTERACTION_BINDINGS.get(path)
                                     or UNIT_PRODUCTION_INTERACTION_BINDINGS.get(path)
                                     or UNIT_RESEARCH_INTERACTION_BINDINGS.get(path)
                                     or UNIT_MARKET_INTERACTION_BINDINGS.get(path)
                                     or UNIT_SPLIT_INTERACTION_BINDINGS.get(path)
                                     or UNIT_RESERVES_INTERACTION_BINDINGS.get(path)
                                     or UNIT_LIST_INTERACTION_BINDINGS.get(path)
                                     or MAIN_BAR_INTERACTION_BINDINGS.get(path)
                                     or START_SINGLE_PLAYER_INTERACTION_BINDINGS.get(path)
                                     or SCENARIO_SELECTION_INTERACTION_BINDINGS.get(path)
                                     or OBJECTIVES_INTERACTION_BINDINGS.get(path)
                                     or BATTLE_INSPECTION_INTERACTION_BINDINGS.get(path)
                                     or STRATEGIC_TARGET_SELECTION_INTERACTION_BINDINGS.get(path)
                                     or STRATEGIC_WARFARE_INTERACTION_BINDINGS.get(path)
                                     or MULTIPLAYER_WORKFLOW_UNAVAILABLE_INTERACTION_BINDINGS.get(path)
                                     or MULTIPLAYER_LOBBY_UNAVAILABLE_INTERACTION_BINDINGS.get(path)
                                     or UNUSED_SOURCE_TEMPLATE_INTERACTION_BINDINGS.get(path)
                                     or MILITARY_STRATEGIC_RESEARCH_INTERACTION_BINDINGS.get(path)
                                     or MILITARY_TITLE_INTERACTION_BINDINGS.get(path)
                                     or MILITARY_NAVIGATION_INTERACTION_BINDINGS.get(path)
                                     or MILITARY_PROGRESS_METER_INTERACTION_BINDINGS.get(path)
                                     or UNIT_DESIGN_INTERACTION_BINDINGS.get(path)
                                     or COVERT_MISSION_FORM_INTERACTION_BINDINGS.get(path)
                                     or COVERT_FORM_ACTION_INTERACTION_BINDINGS.get(path)
                                     or COVERT_CONTROL_INTERACTION_BINDINGS.get(path)
                                     or GENERIC_QUESTION_INTERACTION_BINDINGS.get(path)
                                     or ECONOMIC_HEALTH_INTERACTION_BINDINGS.get(path)
                                     or TREATY_DETAILS_INTERACTION_BINDINGS.get(path)
                                     or RELATIONS_INTERACTION_BINDINGS.get(path)
                                     or POLITICS_INTERACTION_BINDINGS.get(path)
                                     or COUNTRY_PROFILE_INTERACTION_BINDINGS.get(path)
                                     or OPTIONS_INTERACTION_BINDINGS.get(path)
                                     or CONSTITUTIONAL_FORM_INTERACTION_BINDINGS.get(path)
                                     or COUNTRY_INFO_INTERACTION_BINDINGS.get(path)
                                     or SAVE_LOAD_INTERACTION_BINDINGS.get(path)
                                     or SAVE_CONFIRMATION_INTERACTION_BINDINGS.get(path)
                                     or REMAINING_INTERACTION_BINDINGS.get(path))
                if openpower_binding:
                    interaction_row.update(openpower_binding)
                elif path.endswith("/frmTitle/btnApply"):
                    hidden_apply_line = _hidden_apply_source_line(source_functions)
                    if hidden_apply_line is not None:
                        interaction_row.update(_hidden_title_apply_interaction(
                            window,
                            f"Client/Source/{type_row['file']}",
                            hidden_apply_line,
                            surface_by_window.get(window, "missing"),
                        ))
                if (
                    path.endswith("/frmTitle/togLockWindow")
                    and window != "Battle_Summary_Window"
                    and _inherits_base_window(source_index, class_name)
                ):
                    interaction_row.update(_hidden_base_window_lock_interaction(window))
                interaction_rows.append(interaction_row)

        if window == "Unit_Ground_Deployment_Window":
            tab_button_path = "Unit_Ground_Deployment_Window/frmInner/tabGroups/@tabButtons"
            tab_button_binding = UNIT_RESERVES_INTERACTION_BINDINGS[tab_button_path]
            interaction_rows.append({
                "window_id": window,
                "component_path": tab_button_path,
                "input": "runtime-generated GTabbed category buttons",
                "cpp_member_binding": "m_objTabGroup.m_vTabButtons[0..3]",
                "cpp_source": "Client/Source/reference_unit_ground_deployment_window.cpp",
                "reference_callback": "OnMouseClick@reference_unit_ground_deployment_window.cpp:337",
                "reference_game_event": "",
                "reference_side_effect": tab_button_binding["reference_side_effect"],
                "verified_cpp_transition": "OnMouseClick tab-button branch clears the previous row selection.",
                "validation_condition": tab_button_binding["validation_condition"],
                "openpower_panel_spec": panel_by_window.get(window, ""),
                "openpower_surface": tab_button_binding["openpower_surface"],
                "openpower_effect": tab_button_binding["openpower_effect"],
                "game_action": tab_button_binding["game_action"],
                "read_only_or_state_changing": tab_button_binding["read_only_or_state_changing"],
                "country_scope_restriction": tab_button_binding["country_scope_restriction"],
                "confirmation_state": tab_button_binding["confirmation_state"],
                "error_state": tab_button_binding["error_state"],
                "restrictions_confirmation_error": tab_button_binding["restrictions_confirmation_error"],
                "action_required": tab_button_binding["action_required"],
                "status": tab_button_binding["status"],
            })
        if window == "Main_Bar":
            speed_path = "Main_Bar/frmTimeSelection/@openpowerSpeed5"
            speed_binding = _build_interaction_binding(
                reference="No source GML control exists for this extra OpenPower speed level.",
                surface="CentralBar._draw_speed_controls",
                effect="Exposes OpenPower's native speed level 5 in the unused right-edge gutter of the Main_Bar frame.",
                action="ActionSetGameSpeed(player_id, speed_level=5)",
                status="partial",
                validation="Enabled for the local single-player administrator and uses the native OpenPower speed model.",
                mapping_notes="OpenPower supports five active speeds; REFERENCE's Main_Bar has four non-paused speed toggles. This fifth button has no REFERENCE control counterpart; it sits at x=94 relative to frmTimeSelection, immediately to the right of the source 92x22 frame and within the 689px Main_Bar root.",
                action_required="Keep the OpenPower-only speed level identified as an extension; do not attribute it to a source toggle.",
            )
            interaction_rows.append({
                "window_id": window,
                "component_path": speed_path,
                "input": "OpenPower-only speed button",
                "cpp_member_binding": "none; no source GML child",
                "cpp_source": "",
                "reference_callback": "none; no source callback",
                "reference_game_event": "",
                "reference_side_effect": speed_binding["reference_side_effect"],
                "verified_cpp_transition": "No source control or callback exists.",
                "validation_condition": speed_binding["validation_condition"],
                "openpower_panel_spec": "",
                "openpower_surface": speed_binding["openpower_surface"],
                "openpower_effect": speed_binding["openpower_effect"],
                "game_action": speed_binding["game_action"],
                "read_only_or_state_changing": speed_binding["read_only_or_state_changing"],
                "country_scope_restriction": speed_binding["country_scope_restriction"],
                "confirmation_state": speed_binding["confirmation_state"],
                "error_state": speed_binding["error_state"],
                "restrictions_confirmation_error": speed_binding["restrictions_confirmation_error"],
                "action_required": speed_binding["action_required"],
                "status": speed_binding["status"],
            })

    dynamic_rows: list[dict[str, Any]] = []
    lifecycle_methods = {"OnCreate", "OnDestroy", "OnShow", "OnHide"}
    for path, functions in file_functions.items():
        for function in functions:
            source_type = source_index["type_by_class"].get(function["class"], {})
            object_pattern = re.compile(r"\b(ObjectSpawn|CREATE_GUI_OBJECT\w*)\s*(\([^;]*\))", re.S)
            for match in object_pattern.finditer(function["body"]):
                line = function["body_line"] + function["body"][:match.start()].count("\n")
                prefix = function["body"][max(0, match.start() - 120):match.start()]
                variable_match = re.search(r"\b([A-Za-z_]\w*)\s*=\s*$", prefix)
                args = match.group(2)
                spawn_binding = re.search(r"&\s*(m_\w+|l_\w+)", args)
                variable = variable_match.group(1) if variable_match else (spawn_binding.group(1) if spawn_binding else "")
                receiver_functions = (
                    class_functions.get(function["class"], [])
                    if variable.startswith("m_")
                    else [function]
                )
                state_calls, state_evidence = _receiver_state_evidence(
                    receiver_functions, variable=variable,
                )
                target_class_match = re.search(r"\b(\w+)::TypeName\b", args)
                if target_class_match:
                    target_class = target_class_match.group(1)
                else:
                    gui_class_match = re.search(r"\bGUI::(\w+)", args)
                    target_class = gui_class_match.group(1) if gui_class_match else ""
                target_type = source_index["type_by_class"].get(target_class, {})
                target_template = target_type.get("template", f"non-GML/{target_class}" if target_class else "")
                dynamic_rows.append({
                    "source_window": source_type.get("template", function["class"]),
                    "function": function["method"],
                    "creation_api": match.group(1),
                    "target_template": target_template,
                    "object_binding": variable,
                    "call_excerpt": " ".join(match.group(0).split())[:240],
                    "position_and_visibility": state_calls or "No same-class receiver-specific geometry/visibility call resolved.",
                    "position_visibility_calls": state_calls,
                    "position_visibility_evidence": state_evidence,
                    "action_required": "Review the same-class calls and their read/write roles against the dynamic object's GML/type and access rules." if state_calls else "Trace creator and target OnCreate/update methods for exact dynamic geometry and visibility rules.",
                    "source_file": f"Client/Source/{path.name}",
                    "source_line": line,
                    "source_url": f"{SOURCE_REPOSITORY}/Client/Source/{path.name}#L{line}",
                    "status": "verified_cpp",
                })
            if function["method"] in lifecycle_methods:
                for match in re.finditer(r"g_ClientDDL\.(\w+WindowSpawn)\s*(\([^;]*\))", function["body"], re.S):
                    line = function["body_line"] + function["body"][:match.start()].count("\n")
                    spawn_method = match.group(1)
                    target_template = source_index["spawn_templates"].get(spawn_method, "")
                    getter = spawn_method.removesuffix("Spawn")
                    state_calls, state_evidence = _receiver_state_evidence(
                        class_functions.get(function["class"], []), window_getter=getter,
                    )
                    dynamic_rows.append({
                        "source_window": source_type.get("template", function["class"]),
                        "function": function["method"],
                        "creation_api": f"g_ClientDDL.{spawn_method}",
                        "target_template": target_template,
                        "object_binding": f"g_ClientDDL.{getter}()",
                        "call_excerpt": " ".join(match.group(0).split())[:240],
                        "position_and_visibility": state_calls or "No same-class receiver-specific geometry/visibility call resolved.",
                        "position_visibility_calls": state_calls,
                        "position_visibility_evidence": state_evidence,
                        "action_required": "Review the same-class calls and their read/write roles against the dynamic object's GML/type and access rules." if state_calls else "Trace creator and target OnCreate/update methods for exact dynamic geometry and visibility rules.",
                        "source_file": f"Client/Source/{path.name}",
                        "source_line": line,
                        "source_url": f"{SOURCE_REPOSITORY}/Client/Source/{path.name}#L{line}",
                        "status": "verified_cpp",
                    })

    edge_rows: list[dict[str, Any]] = []
    for edge in edges:
        edge_rows.append(edge)
    graph_call_sites = set()
    for edge in edges:
        graph_call_sites.add((Path(edge["source_file"]).name, edge["source_line"], edge["target_window"]))
        if edge.get("action_source_file"):
            graph_call_sites.add((
                Path(edge["action_source_file"]).name,
                edge["action_source_line"],
                edge["target_window"],
            ))
    dynamic_call_sites = {
        (Path(row["source_file"]).name, row["source_line"], row["target_template"])
        for row in dynamic_rows
        if row["creation_api"].startswith("g_ClientDDL.")
    }
    raw_window_spawn_calls = []
    for path, functions in file_functions.items():
        for function in functions:
            for match in re.finditer(r"g_ClientDDL\.(\w+WindowSpawn)\s*\(", function["body"]):
                line = function["body_line"] + function["body"][:match.start()].count("\n")
                target = source_index["spawn_templates"].get(match.group(1), "")
                site = (path.name, line, target)
                if site in graph_call_sites:
                    classification = "navigation/callback graph"
                elif site in dynamic_call_sites:
                    classification = "lifecycle dynamic component"
                else:
                    classification = "unaccounted"
                raw_window_spawn_calls.append({
                    "source_file": path.name,
                    "source_line": line,
                    "spawn_method": match.group(1),
                    "target_template": target,
                    "classification": classification,
                })
    callsite_accounting = {
        "raw_window_spawn_calls": len(raw_window_spawn_calls),
        "graph_call_sites": sum(row["classification"] == "navigation/callback graph" for row in raw_window_spawn_calls),
        "lifecycle_dynamic_call_sites": sum(row["classification"] == "lifecycle dynamic component" for row in raw_window_spawn_calls),
        "unaccounted_call_sites": [row for row in raw_window_spawn_calls if row["classification"] == "unaccounted"],
    }
    nav_path = resolve_reference_file(source_root, "reference_ui_navigation_verified.json")
    seed = json.loads(nav_path.read_text(encoding="utf-8"))
    scanner_keys = {
        (edge["source_widget_path"], edge["target_window"])
        for edge in edges
    }
    seed_unmatched = [
        transition for transition in seed.get("transitions", [])
        if (transition.get("source"), transition.get("destination")) not in scanner_keys
    ]

    journey_suite_path = journey_suite_path or REPO_ROOT / "artifacts/ui/reference/journeys-final/suite.json"
    seed_journey_rows = _seed_transition_journey_rows(
        seed,
        REPO_ROOT / "tests/ui/journeys",
        journey_suite_path,
    )
    navigation_journey_rows = _navigation_journey_coverage_rows(
        edges,
        window_rows,
        seed_journey_rows,
        REPO_ROOT / "tests/ui/journeys",
        journey_suite_path,
    )
    navigation_coverage_by_site = {
        (row["source_file"], int(row["source_line"]), row["target_window"]): row
        for row in navigation_journey_rows
    }

    gaps: list[dict[str, Any]] = []
    for row in window_rows:
        panel_id = row["openpower_panel_spec"]
        surface = row["openpower_surface"]
        unimplemented = UNIMPLEMENTED_WINDOW_GAPS.get(row["window_id"])
        partial = PARTIALLY_IMPLEMENTED_WINDOW_GAPS.get(row["window_id"])
        reviewed = VERIFIED_WINDOW_NOTES.get(row["window_id"])
        window_gap = unimplemented or partial
        gaps.append({
            "gml_node_or_behavior": row["window_id"],
            "reference_behavior": f"GML template {row['gml_template']} ({row['width']}×{row['height']}); sections: {row['sections']}",
            "openpower_current_implementation": (
                partial["current_implementation"] if partial else
                reviewed["current_implementation"] if reviewed else
                surface if surface != "missing" else "missing PanelSpec/layout surface"
            ),
            "action_required": (
                window_gap["action_required"] if window_gap else
                reviewed["action_required"] if reviewed else
                "Compare every component/data/action contract; document remaining gaps" if surface != "missing" else
                "Implement the reachable window or keep this entry explicitly marked unimplemented"
            ),
            "status": row["mapping_status"] if surface != "missing" else "assumption/unknown",
            "evidence": row["source_path"],
        })
    for data in data_rows:
        current_binding = data["openpower_state_binding"]
        gaps.append({
            "gml_node_or_behavior": data["component_path"],
            "reference_behavior": (
                f"{data['kind']} display; {data['what_is_displayed']}; units: {data['units']}; "
                f"fallback: {data['fallback']}; cadence: {data['update_rule']}"
            ),
            "openpower_current_implementation": (
                f"{data['openpower_surface']} → {current_binding}"
                if data["openpower_surface"] != "missing" else "missing panel/data binding"
            ),
            "action_required": data["action_required"],
            "status": data["openpower_binding_status"],
            "evidence": f"layout_catalog.gml#L{data['gml_line']}; {data['cpp_source']} "
            f"{data['cpp_display_expressions'] or data['cpp_member_operations']}; "
            f"OpenPower: {data['openpower_binding_source']}",
        })
    for edge in edges:
        destination = edge["target_window"]
        panel_id = panel_by_window.get(destination, "")
        surface = surface_by_window.get(destination, "")
        reviewed_route = NAVIGATION_EDGE_BINDINGS.get(edge["source_widget_path"])
        military_route = MILITARY_NAVIGATION_INTERACTION_BINDINGS.get(
            edge["source_widget_path"]
        )
        navigation_route = navigation_coverage_by_site.get(
            (edge["source_file"], int(edge["source_line"]), destination),
            {},
        )
        route_gap_status = _navigation_gap_status(
            navigation_route.get("coverage_status", "")
        )
        if reviewed_route:
            route_implementation = reviewed_route["openpower_current_implementation"]
            route_action_required = reviewed_route["action_required"]
            route_implementation_status = reviewed_route["status"]
        elif military_route:
            route_implementation = (
                f"{military_route['openpower_surface']}: {military_route['openpower_effect']}"
            )
            route_action_required = military_route["action_required"]
            route_implementation_status = military_route["status"]
        else:
            route_implementation = (
                navigation_route.get("openpower_surface") or surface or
                "no verified destination route"
            )
            route_action_required = navigation_route.get("action_required", "")
            if not route_action_required and route_gap_status == "partial":
                route_action_required = navigation_route.get("route_review", "")
            if not navigation_route:
                route_action_required = (
                    "Verify click journey and destination data" if surface else
                    "Add a route or record the missing action"
                )
            route_implementation_status = route_gap_status
        gaps.append({
            "gml_node_or_behavior": edge["source_widget_path"],
            "reference_behavior": f"{edge['event']} → {edge['mode']} {destination}; condition: {edge['context']}",
            "openpower_current_implementation": route_implementation,
            "action_required": route_action_required,
            "status": route_implementation_status,
            "evidence": f"{edge['source_file']}#L{edge['source_line']}",
        })

    for interaction in interaction_rows:
        template = interaction["window_id"]
        component_path = interaction["component_path"]
        node = next(
            (row["node"] for row in paths_by_template[template] if row["path"] == component_path),
            {},
        )
        routes = interaction["verified_cpp_transition"]
        evidence = f"layout_catalog.gml#L{node.get('line', '')}"
        is_generic_message_ack = (
            template == "Generic_Message_Window"
            and component_path == "Generic_Message_Window/btnOk"
        )
        route_evidence = next(
            (
                f"{edge['source_file']}#L{edge['source_line']}"
                for edge in edge_by_widget.get(component_path, [])
            ),
            "",
        )
        if route_evidence:
            evidence += f"; {route_evidence}"
        if component_path == "Unit_Ground_Deployment_Window/frmInner/tabGroups/@tabButtons":
            parent = next(
                (row["node"] for row in paths_by_template[template]
                 if row["path"] == "Unit_Ground_Deployment_Window/frmInner/tabGroups"),
                {},
            )
            evidence = (
                f"layout_catalog.gml#L{parent.get('line', '')}; "
                "Client/Source/reference_unit_ground_deployment_window.cpp#L337; "
                "src/client/ui/layouts/gml_layout.py::GMLTabLayout"
            )
        if component_path == "Main_Bar/frmTimeSelection/@openpowerSpeed5":
            parent = next(
                (row["node"] for row in paths_by_template[template]
                 if row["path"] == "Main_Bar/frmTimeSelection"),
                {},
            )
            evidence = (
                f"layout_catalog.gml#L{parent.get('line', '')}; "
                "OpenPower-only control: src/client/ui/components/hud/central_bar.py::_draw_speed_controls"
            )
        gaps.append({
            "gml_node_or_behavior": component_path,
            "reference_behavior": (
                "OK acknowledgement hides the dialog; invokes the caller event when supplied; then notifies observers."
                if is_generic_message_ack else
                "Runtime-generated category buttons from the GTabbed TabNames list; a click changes the active page and clears selection."
                if component_path == "Unit_Ground_Deployment_Window/frmInner/tabGroups/@tabButtons" else
                f"{interaction['input']} control; transition: {routes or 'not traced'}"
            ),
            "openpower_current_implementation": (
                "GameLayout/GenericMessageDialog.acknowledge with optional on_acknowledge callback"
                if is_generic_message_ack else
                f"{interaction['openpower_surface']}: {interaction['openpower_effect']}"
                if interaction.get("openpower_surface") and interaction.get("openpower_effect") else
                surface_by_window.get(template, "no identified equivalent")
            ),
            "action_required": interaction["action_required"],
            "status": interaction["status"],
            "evidence": evidence,
        })

    unimplemented_window_rows: list[dict[str, Any]] = []
    reviewed_routes = json.loads(
        (REPO_ROOT / "docs/ui/reference/navigation_route_bindings.json").read_text(encoding="utf-8")
    )
    non_route_sites = {
        (route["source_file"], int(route["source_line"]), route["target_window"])
        for route in reviewed_routes
        if route.get("status") in {
            "lifecycle_initialization",
            "inactive_source_code",
            "unreachable_source_branch",
        }
    }
    for row in window_rows:
        gap = UNIMPLEMENTED_WINDOW_GAPS.get(row["window_id"])
        partial = PARTIALLY_IMPLEMENTED_WINDOW_GAPS.get(row["window_id"])
        window_gap = gap or partial
        if (
            not window_gap
            or row["status"] != "reachable"
            or row["mapping_status"] not in {"missing", "partial"}
        ):
            continue
        inbound = [
            edge for edge in edges
            if edge["target_window"] == row["window_id"]
            and (edge["source_file"], int(edge["source_line"]), edge["target_window"]) not in non_route_sites
        ]
        if not inbound:
            inbound = [{"source_window": "", "source_widget_path": "", "event": "", "mode": "", "context": "", "source_file": "", "source_line": ""}]
        for edge in inbound:
            unimplemented_window_rows.append({
                "window_id": row["window_id"],
                "inbound_transition": (
                    f"{edge['source_window']}/{edge['source_widget_path']} --{edge['event']}--> {row['window_id']} ({edge['mode']})"
                    if edge["source_window"] else "No inbound transition extracted"
                ),
                "source_file": edge["source_file"] or row["source_path"],
                "source_line": edge["source_line"],
                "current_implementation": (
                    partial["current_implementation"] if partial else "missing"
                ),
                "reason": window_gap["reason"],
                "action_required": window_gap["action_required"],
                "missing_action": window_gap["missing_action"],
                "coverage_status": "partial" if partial else "unimplemented",
                "status": "verified_cpp" if edge["source_file"] else "assumption/unknown",
            })

    output_dir.mkdir(parents=True, exist_ok=True)
    journey_suite = (
        json.loads(journey_suite_path.read_text(encoding="utf-8-sig"))
        if journey_suite_path.is_file() else {}
    )
    surface_suite_path = REPO_ROOT / "artifacts/ui/reference/matrix-final/suite.json"
    surface_suite = (
        json.loads(surface_suite_path.read_text(encoding="utf-8-sig"))
        if surface_suite_path.is_file() else {}
    )
    seed_journey_counts = Counter(row["coverage_status"] for row in seed_journey_rows)
    navigation_journey_counts = Counter(
        row["coverage_status"] for row in navigation_journey_rows
    )
    geometry_crosswalk_rows = _layout_geometry_crosswalk(
        edges,
        navigation_journey_rows,
        component_rows,
        window_rows,
        journey_suite,
    )
    geometry_crosswalk_measured = sum(
        row["geometry_status"] == "source_widget_and_python_destination_measured"
        for row in geometry_crosswalk_rows
    )
    journey_action_assertions = 0
    for result in journey_suite.get("results", []):
        journey_path = REPO_ROOT / result.get("journey", "")
        if journey_path.is_file():
            journey = json.loads(journey_path.read_text(encoding="utf-8-sig"))
            journey_action_assertions += sum(
                step.get("op") == "assert_action"
                for step in journey.get("steps", [])
            )
    functional_matrix_runs: list[dict[str, Any]] = []
    for name in FUNCTIONAL_MATRIX_SUITE_NAMES:
        matrix_path = REPO_ROOT / "artifacts/ui/reference" / name / "suite.json"
        if matrix_path.is_file():
            matrix = json.loads(matrix_path.read_text(encoding="utf-8-sig"))
            functional_matrix_runs.extend(matrix.get("runs", []))
    write_csv_tables(output_dir, {
        'window_registry.csv': window_rows,
        'component_tree.csv': component_rows,
        'dynamic_components.csv': dynamic_rows,
        'data_contracts.csv': data_rows,
        'interaction_contracts.csv': interaction_rows,
        'gap_table.csv': gaps,
        'unimplemented_windows.csv': unimplemented_window_rows,
        'seed_transition_coverage.csv': seed_journey_rows,
        'navigation_journey_coverage.csv': navigation_journey_rows,
        'layout_geometry_crosswalk.csv': geometry_crosswalk_rows,
    })
    component_paths = {(row["window_id"], row["component_path"]) for row in component_rows}
    exact_widget_path_edges = sum(
        (edge["source_window"], edge["source_widget_path"]) in component_paths
        for edge in edges
    )
    dynamic_geometry_resolved = sum(bool(row["position_visibility_calls"]) for row in dynamic_rows)
    reachable_mapping_counts = Counter(
        row["mapping_status"] for row in window_rows if row["status"] == "reachable"
    )
    (output_dir / "navigation_graph.json").write_text(
        json.dumps({
            "source": "REFERENCE-HDM local source mirror",
            "scope": "Direct/helper WindowSpawn transitions, verified GenericQuestion display factories, and the two traced disconnected-menu FSM transitions; lifecycle spawns are tracked as dynamic components.",
            "gml_validation": validation,
            "window_spawn_callsite_accounting": callsite_accounting,
            "seed_transitions_unmatched_by_scanner": seed_unmatched,
            "transitions": edge_rows,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    status_counts = Counter(row["status"] for row in window_rows)
    report = {
        "gml_validation": validation,
        "gml_window_candidates": len(candidates),
        "window_status_counts": dict(status_counts),
        "window_mapping_status_counts": dict(Counter(row["mapping_status"] for row in window_rows)),
        "component_rows": len(component_rows),
        "dynamic_component_calls": len(dynamic_rows),
        "navigation_edges": len(edges),
        "navigation_verified_cpp": sum(edge["status"] == "verified_cpp" for edge in edges),
        "navigation_exact_gml_widget_path_edges": exact_widget_path_edges,
        "navigation_handler_only_edges": len(edges) - exact_widget_path_edges,
        "window_spawn_callsite_accounting": callsite_accounting,
        "dynamic_sites_with_receiver_geometry_or_visibility": dynamic_geometry_resolved,
        "dynamic_sites_requiring_creator_or_update_trace": len(dynamic_rows) - dynamic_geometry_resolved,
        "reachable_window_mapping_status_counts": dict(reachable_mapping_counts),
        "unimplemented_reachable_window_count": len({row["window_id"] for row in unimplemented_window_rows}),
        "unimplemented_reachable_window_inbound_rows": len(unimplemented_window_rows),
        "data_contract_rows": len(data_rows),
        "data_contract_status_counts": dict(Counter(row["status"] for row in data_rows)),
        "interaction_contract_rows": len(interaction_rows),
        "interaction_contract_status_counts": dict(Counter(row["status"] for row in interaction_rows)),
        "gap_rows": len(gaps),
        "gap_status_counts": dict(Counter(row["status"] for row in gaps)),
        "seed_transitions_unmatched_by_scanner": seed_unmatched,
        "seed_transition_journey_rows": len(seed_journey_rows),
        "seed_transition_journey_coverage_counts": dict(seed_journey_counts),
        "navigation_journey_coverage_rows": len(navigation_journey_rows),
        "navigation_journey_coverage_counts": dict(navigation_journey_counts),
        "layout_geometry_crosswalk_rows": len(geometry_crosswalk_rows),
        "layout_geometry_crosswalk_measured_routes": geometry_crosswalk_measured,
        "journey_suite_total": journey_suite.get("journeys", 0),
        "journey_suite_passed": journey_suite.get("passed", 0),
        "journey_action_assertions": journey_action_assertions,
        "surface_matrix_runs": len(surface_suite.get("runs", [])),
        "surface_matrix_passed": sum(bool(row.get("passed")) for row in surface_suite.get("runs", [])),
        "surface_matrix_count": len({row.get("surface") for row in surface_suite.get("runs", [])}),
        "functional_matrix_suite_count": len(FUNCTIONAL_MATRIX_SUITE_NAMES),
        "functional_matrix_runs": len(functional_matrix_runs),
        "functional_matrix_passed": sum(bool(row.get("passed")) for row in functional_matrix_runs),
        "output_dir": str(output_dir.resolve()),
    }
    (output_dir / "audit_summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_readme(output_dir, report)
    return report


def _write_readme(output_dir: Path, report: dict[str, Any]) -> None:
    validation = report["gml_validation"]
    lines = [
        "# reference implementation UI functional mapping",
        "",
        "Generated from the local `layout_catalog.gml`, resolved UI catalog, and REFERENCE-HDM C++ source mirror. OpenPower mappings are read from the current `PanelSpec` registry plus explicit review aliases in `utils/reference_ui_audit.py`.",
        "",
        "The OpenPower implementation is Python under `src/client/ui`. GML and C++ are read-only reference evidence; they are not implementation targets.",
        "",
        "## Audit result",
        "",
        f"- GML definitions: {validation['definition_count']}; object nodes including children: {validation['raw_object_count']}; resolved catalog nodes: {validation['resolved_catalog_node_count']}.",
        f"- Candidate window roots: {report['gml_window_candidates']}; status counts: `{json.dumps(report['window_status_counts'], ensure_ascii=False)}`.",
        f"- OpenPower window mapping evidence: `{json.dumps(report['window_mapping_status_counts'], ensure_ascii=False)}`.",
        f"- Component rows: {report['component_rows']}; dynamic C++ creation sites: {report['dynamic_component_calls']}.",
        f"- Window-spawn navigation edges: {report['navigation_edges']} C++-verified call paths; {report['navigation_exact_gml_widget_path_edges']} map to an exact GML widget path and {report['navigation_handler_only_edges']} are handler-level only.",
        f"- Reachable-window mapping evidence: `{json.dumps(report['reachable_window_mapping_status_counts'], ensure_ascii=False)}`; reachable windows with missing or partial contracts: {report['unimplemented_reachable_window_count']} ({report['unimplemented_reachable_window_inbound_rows']} inbound-transition evidence rows in `unimplemented_windows.csv`).",
        f"- Dynamic creation sites with same-class receiver-specific geometry/visibility evidence: {report['dynamic_sites_with_receiver_geometry_or_visibility']}/{report['dynamic_component_calls']}; detailed source locations are in `dynamic_components.csv`, and the rest need creator/update tracing.",
        f"- WindowSpawn call-site accounting: {report['window_spawn_callsite_accounting']['raw_window_spawn_calls']} total = {report['window_spawn_callsite_accounting']['graph_call_sites']} navigation/callback + {report['window_spawn_callsite_accounting']['lifecycle_dynamic_call_sites']} lifecycle; unaccounted: {len(report['window_spawn_callsite_accounting']['unaccounted_call_sites'])}.",
        f"- Data contracts: {report['data_contract_rows']}; interaction contracts: {report['interaction_contract_rows']}.",
        f"- Data evidence: `{json.dumps(report['data_contract_status_counts'], ensure_ascii=False)}`; interaction evidence: `{json.dumps(report['interaction_contract_status_counts'], ensure_ascii=False)}`.",
        f"- Gap rows: {report['gap_rows']} (candidate windows, display data, navigation edges, and interactive controls).",
        f"- Gap evidence: `{json.dumps(report['gap_status_counts'], ensure_ascii=False)}`.",
        f"- Transition journey coverage: {report['navigation_journey_coverage_rows']} extracted C++ edges; statuses: `{json.dumps(report['navigation_journey_coverage_counts'], ensure_ascii=False)}`.",
        f"- Fixed-viewport geometry crosswalk: {report['layout_geometry_crosswalk_measured_routes']}/{report['layout_geometry_crosswalk_rows']} source-widget routes have GML control coordinates plus measured Python destination geometry at 1280×720; see `layout_geometry_crosswalk.csv`.",
        f"- Unknown GML type references: {len(validation['unknown_gml_types'])}; inheritance cycles: {len(validation['inheritance_cycles'])}.",
        "",
        "## Files",
        "",
        "- `window_registry.csv`: candidate window roots, reachability evidence, GML size/sections, and OpenPower PanelSpec or layout-surface mapping.",
        "- `component_tree.csv`: full resolved paths, parent/order, GML geometry, static enable/visibility, source binding and C++ member operations.",
        "- `dynamic_components.csv`: `ObjectSpawn`/`CREATE_GUI_OBJECT` sites omitted from static GML trees, with same-class receiver-specific geometry/visibility calls and source locations where found.",
        "- `navigation_graph.json`: extracted C++ window-spawn edges, exact conditions, mode, and source lines; only `verified_cpp` edges are treated as verified.",
        "- `navigation_journey_coverage.csv`: journey or explicit gap status for every extracted C++ navigation edge.",
        "- `layout_geometry_crosswalk.csv`: source GML widget/window geometry paired with tested Python control and destination rectangles at the fixed 1280×720 viewport, or an explicit unresolved status.",
        "- `data_contracts.csv`: display components with GML tokens, C++ source/member operations, OpenPower binding and Python/schema source files, units, fallback, and update cadence status.",
        "- `interaction_contracts.csv`: all GML interactive controls, C++ source, route, GameAction status, restrictions, and confirmation/error gaps.",
        "- `generic_message_callback_map.csv`: every active Generic_Message_Window display call, its OK callback effects, OpenPower counterpart, and unsupported or partial routes.",
        "- `gap_table.csv`: one row per candidate window, display-data contract, extracted transition, and interactive control, with its current OpenPower target and remaining action.",
        "- `unimplemented_windows.csv`: inbound C++ evidence, current Python implementation, and remaining action for each incomplete reachable-window contract.",
        f"- `seed_transition_coverage.csv`: crosswalk for the {report['seed_transition_journey_rows']} manually verified source transitions to Python UI journeys, clicks, destination assertions, and suite status. It covers this seed set only, not every extracted C++ edge.",
        "- `audit_summary.json`: counts and parser validation diagnostics.",
        "- `requirements_coverage.md`: implementation status, verification evidence, and requirements that remain open.",
        "",
        "## Evidence policy",
        "",
        "`verified_gml` means the node and its static geometry/token come from the resolved catalog and were checked against `layout_catalog.gml` counts. `verified_cpp` means the C++ class/event/member path or call site resolves to the local source mirror. In navigation rows, a handler-level `verified_cpp` route has no exact GML widget path; geometry remains unresolved unless the crosswalk measures it. `verified_openpower` means a concrete current panel/model binding is identified. `verified_unavailable` means the source value is known but no authoritative OpenPower field exists, so the implementation shows an explicit unavailable fallback. `assumption/unknown` marks unresolved or candidate equivalence. Numeric GML `Text` values are preserved as tokens and are not interpreted as visible copy.",
        "",
        "`unused` means the window candidate has no active matching C++ `TypeName`, GUI registration, spawn method/call, or source reference in this mirror. Commented-out declarations do not count as runtime evidence. It does not claim the reference commercial game has no external resource path. `conditional` means active C++ creates/spawns the window but it was not reached from the Main Bar/Main Menu click graph. `reachable` means a click-graph path from one of those roots was found.",
        "",
        "The generated CSVs preserve unknown bindings as gaps. They do not invent missing game data, actions, restrictions, or error states. Geometry is GML-local and does not assert pixel-perfect equivalence in OpenPower.",
        "",
        "## UI verification",
        "",
        f"- Historical surface matrix: {report.get('surface_matrix_passed', 0)}/{report.get('surface_matrix_runs', 0)} runs across {report.get('surface_matrix_count', 0)} surfaces and four requested viewport sizes. Earlier runs did not validate the actual native viewport; see navigation_verification.md for the correction and current evidence. The merged `suite.json` points to the latest reports for surfaces rerun after layout fixes.",
        f"- Current journey suite: {report.get('journey_suite_passed', 0)}/{report.get('journey_suite_total', 0)} JSON journeys, including {report.get('journey_action_assertions', 0)} exact GameAction assertions. {report.get('functional_matrix_suite_count', 0)} historical focused functional journeys passed their requested-size matrices ({report.get('functional_matrix_passed', 0)}/{report.get('functional_matrix_runs', 0)} runs).",
        f"- Manually verified seed-transition journey coverage: `{json.dumps(report['seed_transition_journey_coverage_counts'], ensure_ascii=False)}`.",
        "- Crosswalk click IDs are OpenPower controls reviewed as equivalents for the source paths; they are not GML widget IDs.",
        "- Journey fixtures cover directed Relations values/history, treaty details, and covert-cell workflows; reviewed runs include action dispatch and geometry evidence.",
        "- Raw screenshots, logs, and reports are temporary run artifacts; the generated audit tables preserve the reviewed results.",
        "- See `requirements_coverage.md` for remaining evidence and parity gaps; passing geometry tests do not establish functional equivalence for unresolved contracts.",
        "",
    ]
    (output_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=REPO_ROOT / ".codex")
    parser.add_argument("--output", type=Path, default=REPO_ROOT / "docs/ui/reference")
    parser.add_argument("--journey-suite", type=Path, help="Use current scenario evidence instead of the legacy suite.")
    args = parser.parse_args()
    report = generate(args.source_root, args.output, args.journey_suite)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
