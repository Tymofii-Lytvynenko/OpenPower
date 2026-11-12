# Freeplay System Inventory and Research

## Current System Inventory

`modules/base/registration.py` explicitly contributes **34 concrete systems** to the base module. A directory inventory found **164 Python files** under `modules/base/systems`; this includes policies, helpers, and nested AI components, so it is not a system count.

| Gameplay area | Registered systems and supporting mechanics | Player-facing surfaces | Assessment for freeplay |
| --- | --- | --- | --- |
| Time and world | `TimeSystem`, `BootstrapSystem`, `TerritorySystem`, `InfrastructureSystem`, `HistorySystem`, `RandomEventsSystem` | Central HUD clock/date, map, region inspector, infrastructure, event feed, history | Core simulation and controls exist. Confirm the freeplay session becomes playable from world readiness without campaign state. |
| Economy and trade | `InternalEconomySystem`, `BudgetSystem`, `EconomicHealthSystem`, `TradeSystem`, `BilateralTradeSystem`, `DiplomaticAidSystem` | Economy, budget, resources, economic health, trade panels | Existing economic levers and reports are available. Polish discoverability and verify a player decision leads to a visible authoritative consequence. |
| Politics and society | `PoliticsSystem`, `PoliticalLifecycleSystem`, `IdentityPolicySystem`, `PopulationSystem`, `MigrationSystem` | Politics, political overview, laws, constitutional form, demographics, migration | Existing policy and population systems are available. Ensure freeplay does not hide them behind scenario-specific setup. |
| Military | `MilitarySystem`, `BattleStrategySystem`, `MilitaryCapabilitySystem`, `ResearchProgramSystem`, `CombatSystem`, `CovertOperationsSystem`, `StrategicWarfareSystem`, `ForeignOrderSystem` | Military, unit list, reserves, production, research, design, battles, wars, covert operations, strategic warfare | Broad military coverage exists. The MVP should verify a representative order/production path and useful rejection feedback, then polish only gaps surfaced by automation. |
| Diplomacy and international relations | `AdvancedDiplomacySystem`, `DiplomacySystem`, `DiplomaticBalanceSystem`, `RecognitionSystem`; treaty, war, peace, annexation, trade, and authority policies | Politics, treaties, treaty editor, relations, war list, messages and news | Substantial rules and panels exist. Verify one supported diplomatic action from UI dispatch to authoritative result. |
| AI, advisor, and campaign support | `AISystem`, `AdvisorRecommendationSystem`, `AdvisorSettingsSystem`, `CampaignSetupSystem`, `CampaignSystem` | Advisor settings, objectives, history, mail, event feed | AI/advisor provide ongoing context. Campaign setup/objective/outcome systems are registered but must not be prerequisites for open-ended freeplay. |

System list source: `modules/base/registration.py`. The entries above are grouped by gameplay responsibility; cross-cutting systems may serve more than one area.

## Existing Player Loop and Evidence

1. **Country setup** — `src/client/views/new_game_view.py` creates `CampaignScenarioSelectionWindow` and starts in `setup_stage = "scenario"`; the country list is filtered using the selected scenario. `SinglePlayerSetupWindow` already exposes country and party selection.
2. **Session startup** — `NewGameView._start_game` requires both a country and scenario. `src/client/tasks/new_game_task.py::NewGameTask.run` creates a session, sends `ActionStartCampaign`, then waits for a matching `campaigns` row before returning a ready context. This is the direct coupling to remove.
3. **Time control** — `src/client/ui/components/hud/central_bar.py` displays the date and sends `ActionSetPaused` and `ActionSetGameSpeed`; `modules/base/systems/world/time_system.py` owns simulation time.
4. **Domain actions and panels** — `src/shared/actions.py` defines the semantic command contracts. `src/client/ui/layouts/game_panel_registry.py` composes existing economy, politics, military, diplomacy, demographics, trade, history, news, mail, and advisor panels into the HUD.
5. **Command feedback** — `CommandFeedback` and `UnitOrderFeedback` in `src/client/ui/components/shared/` project authoritative command and movement rejections into notices. `GameLayout` composes them without allowing the UI to mutate server state.
6. **Save and load** — `SaveGameDialog` uses injected save/load callbacks; `GameLayout` exposes in-game saving, `LoadGameView` routes to the existing session loader, and `src/server/io/` owns save serialization and restoration.
7. **Automated UI workflows** — `src/client/ui/testing/` already supports registered surfaces, fixtures, JSON journeys, screenshot/report output, suite recovery, and a live Arcade smoke workflow. `specs/121-ui-journey-test-harness/` records those contracts. The harness does not by itself prove the full new-game-to-simulation-to-save loop; this feature must add that journey or an equivalent automated session acceptance flow.

## Gaps to Address

- The default new-game flow is scenario-first, scenario-filters countries, and requires a scenario id to start.
- Session readiness is tied to a campaign record; a normal freeplay session must instead be ready when its authoritative base world and player context are ready.
- The HUD contains the needed domain panels, but a single automated acceptance path has not yet been documented that exercises one action from each core domain and observes its consequence.
- Save/load mechanisms exist, but freeplay continuation without campaign metadata needs explicit automated evidence.
- The objectives panel may remain available as optional content, but it must not become a required goal or stop condition for freeplay.

These are integration and acceptance gaps; they are not evidence that the underlying economy, military, politics, diplomacy, or persistence systems need replacement.

For a stable, representative freeplay acceptance path, use existing commands: `ActionSetTax` (`src/client/ui/panels/economic_health_panel.py` → `modules/base/systems/economy/economic_health_system.py`), `ActionSetGovernmentForm` (`src/client/ui/panels/politics/constitutional_form_panel.py` → `modules/base/systems/politics/political_lifecycle_system.py`), `ActionMoveUnit` (`src/client/controllers/unit_interaction_controller.py` → `modules/base/systems/military/military_system.py`), and `ActionCreateTreaty` (`src/client/ui/panels/politics/treaty_editor_live.py` → `modules/base/systems/world/treaty_diplomacy.py`). Use deterministic fixtures for validity and make the resulting state change the assertion; do not add parallel mechanics.

## Risk and Design Notes

- Repowise's stored health scores at the current source revision identify `src/client/views/new_game_view.py` as a hotspot (7.5/10), `src/client/tasks/new_game_task.py` as a hotspot (6.32/10), and `src/client/ui/layouts/game_layout.py` as a broader hotspot (4.52/10). The panel registry scores 9.7/10. Treat these as prioritization signals, not probabilities. Keep changes focused and do not fold a broad UI rewrite into the freeplay launch fix.
- Keep action contracts in `src/shared`, gameplay policy in the system that owns each table, and persistence in the server/save boundary.
- Do not add new economic, combat, or campaign rules to make the vertical slice appear playable. Reuse existing actions and inspect the owning system when an automated journey demonstrates a gap.
- Keep campaign setup/outcomes intact for optional scenario play; route default freeplay around that lifecycle. Keep the new freeplay setup surface separate from the scenario-oriented `SinglePlayerSetupWindow`, composing reusable country/party selection components instead of inheriting campaign behavior.
- The repository's UI journey harness distinguishes headless fixture coverage from live Arcade execution. Both modes produce artifacts; neither requires a human desktop acceptance task in this plan.

## Decisions

1. **Freeplay is the default launch path.** Country selection is required; scenario/campaign selection is optional. The game remains open-ended unless the player explicitly chooses a scenario.
2. **Polish before expanding systems.** Start with integration, command discoverability, outcome feedback, and save continuation across the registered systems.
3. **No new persistent model by default.** Existing state and save contracts remain authoritative unless evidence reveals a missing freeplay-specific invariant.
4. **Automated acceptance replaces the campaign manual gate.** A simulation/session flow plus UI journey reports must cover the player loop; manual desktop checks are outside the active task list.
5. **Composition at startup boundaries.** Reuse existing session-startup and navigation collaborators. Do not inherit campaign behavior into a freeplay-specific subclass.

## Verification Status

This is a source and documentation inventory. No application, test, build, or UI journey command was run while writing this plan. Future task completion must be backed by automated run output.
