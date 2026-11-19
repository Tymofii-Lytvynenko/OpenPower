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

## Final Audit Evidence — 2026-11-18

The attached `OpenPower_First_Playable_Audit.md` is the acceptance baseline. Its public `main` snapshot predates this working tree; the results below apply to the current local tree, not to a published commit. English is the agreed first-release language.

### Freeplay MVP

- Direct country-to-freeplay launch and failure/cancellation handling are implemented. `tests/test_freeplay_start_integration.py` also starts the real local session, waits for the client snapshot, checks the selected country with empty `campaigns` and `objectives`, saves and reloads through a process restart, and shuts the server down. The focused launch set reported **127 passed** (agent run; see the individual command in its execution report).
- The main-menu `CUSTOM GAME` entry had remained disabled with a stale tooltip despite the freeplay setup already existing. It now calls the same direct route as the Singleplayer entry; `tests/test_main_menu_content_coverage.py` verifies it is enabled and wired to that callback. A live menu click reaches country setup and starts a USA `GameView` with `campaigns=0`, `objectives=0`, and no system errors.
- The deterministic session loop asserts pause/speed, AI/world/event and scheduled demographic progress, and authoritative state consequences for tax, government form, movement, and treaty actions. An unsupported budget allocation now produces an actionable rejection. The freeplay core-loop set reported **44 passed**.
- The live client accepted speed 3, pause, and resume; its game report showed the authoritative speed/pause fields and an advancing tick/date. The economic-health UI scheduled a 35% tax change, and the selected-country snapshot changed from 0.39 to 0.35 after the configured default delay of 1,440 game minutes. The policy page displayed the effective time for a separately scheduled interest-rate change.
- The UI harness journey exercises country selection, time controls, representative core-panel dispatch, and report/screenshot output. Its standard 1280×720 report records **17/17 steps**, zero layout findings, and no component render errors. The four-viewport matrix (800×600, 1024×768, 1280×720, 1920×1080) passed. Reports are under `artifacts/ui/freeplay-core-loop/` and `artifacts/ui/audit/freeplay-matrix/`.
- The feedback tests verify accepted/rejected notices, movement-order notices, and actor filtering. The engine's generic `EXECUTED` record still reports successful tick execution; effect assertions and owning-system rejection records are the evidence of action outcomes.
- No persistence schema change was needed: a no-campaign process-restart round trip passed and the next session tick continued.

### Wider audit coverage

- The P2 UI audit suites under `artifacts/ui/audit/p2/` contain **44/44 passed journeys across 10 suite reports**, including battles, covert operations, multi-cell missions, event results, load-game, map information/legend, politics, and treaty authoring/lifecycle. Earlier broader UI runs also produced a final **253/253** journey report at `artifacts/ui/reference/goal-2001-journeys-final-20261115/suite.json`.
- The live GameView save dialog wrote `codex-live-audit-20261118-usa`; Parquet inspection confirmed zero `campaigns` and `objectives` rows plus USA tax `0.35`. Loading that slot through the live dialog restored the saved tick/date and resumed unpaused at speed 3 with no system errors. The snapshot had no scenario metadata. Its test save remains under `user_data/saves/` because automatic review rejected recursive cleanup.
- Live map input changed the selected country context by picking CAN, and selecting USA in the HUD restored player context. Right-button drag rotated the globe, mouse-wheel input visibly changed zoom, and a live resize to a 1280×720 logical viewport returned GameView to ready with zero system errors and zero layout findings after transient panels were closed. Stable frames are in `artifacts/ui/live-screen-diagnosis/actual-freeplay-current-1684x970.png` and `actual-after-zoom-1280x720.png`.
- A separate live graphical launch with `base + energy_crisis` resolved that load order, loaded three `energy_crises` rows, registered `energy_crisis.simulation`, and reached USA GameView with `campaigns=0`, `objectives=0`, no system errors, and no layout findings. The stable frame is `artifacts/ui/live-screen-diagnosis/actual-energy-crisis-freeplay-1684x970.png`; `mods.json` was restored to base-only after the run.
- In that temporary live session, a Canada-bound covert cell was created, trained from Recruit to Regular, used to prepare and execute a Low Military Espionage mission, and returned to Active with New Mission available. The frame `artifacts/ui/live-screen-diagnosis/actual-covert-workflow-after-execution-1684x970.png` shows the resulting panel state; the game reported zero system errors. This is partial live workflow evidence only: it is untimed, does not validate mission outcome quality, and leaves T014 open.
- Strategic overview/target planner, Battle Overview, and History Analytics were opened live. The strategic planner correctly reported its program/research prerequisite and disabled launch; Battle Overview showed its no-active-battle state; History Analytics exposed its controls. These screen-open checks do not close T019, T017, or T013 manual criteria.
- The map/cache test set reported **76 passed, 2 skipped**. The opt-in live globe/planar renderer 4K budget case reported **1 passed**. `python -m tools.architecture_check` passed after the map implementation (546 files, 1,981 dependencies, 11 contracts, zero broken contracts).
- The broader world, save/load, and UI/domain regression set reported **314 passed, 3 skipped, 21 subtests**. A separate targeted data-integrity/loader validation reported **146 passed**. These establish schema, loader, selected cross-file integrity, and domain invariants; they do not independently fact-check every historical observation.

### Runtime measurements and acceptance limits

- A clean 1,800-frame client profile (60 warmup frames) measured render frame CPU **p50 10.77 ms / p95 14.65 ms / max 116.06 ms** and map rendering **p50 0.26 ms / p95 0.37 ms / max 4.70 ms**. On the same run, 24 authoritative engine steps measured **p50 632.56 ms / p95 1,353.49 ms / max 2,151.98 ms**; the highest mean system costs were history (172.88 ms), military capabilities (151.34 ms), combat (112.43 ms), infrastructure (74.00 ms), and migration (66.51 ms). This is a local base-module profile, not a target-machine guarantee or a 100-battle benchmark.
- The separate clean process-tree monitor reached **3,032.4 MiB peak working set** during the 1,800-frame run; its steady working set settled around **1.55–1.56 GiB** before shutdown. The transient startup peak and hardware-specific steady sample are both retained as risks for low-memory machines.
- The live client's `OPENPOWER_UI_ARTIFACTS` framebuffer capture shows the actual OpenGL globe, country fill, units, HUD, and minimap. The Computer Use / Windows Graphics Capture path returned a blank image for the OpenGL window; this was a capture-path limitation. App-owned framebuffer capture and the semantic live-input bridge worked. This confirms local rendering and basic navigation, not the complete target-hardware visual matrix.
- HiDPI and target-hardware acceptance, combinations beyond `base + energy_crisis`, a long-run soak, and the 100-battle in-client profile remain unverified. The audit's independent historical fact-check and participant-based blinded study also require external review/participants.

### Exact acceptance commands and artifacts

Commands below exited with code 0; the focused pytest command emitted the existing Pyglet deprecation warnings.

```powershell
uv run --locked --group dev python -m pytest -q tests/test_new_game_view_coverage.py tests/test_freeplay_start_task.py tests/test_freeplay_start_integration.py tests/test_freeplay_core_loop.py tests/test_freeplay_save_load.py tests/test_central_bar_coverage.py tests/test_command_feedback.py tests/test_unit_order_feedback.py
# 44 passed; exit 0

uv run --locked --group dev python -m pytest -q tests/test_freeplay_start_integration.py tests/test_bootstrap_system_coverage.py tests/test_campaign_system.py tests/test_campaign_system_branch_coverage.py tests/test_campaign_presenter.py tests/test_campaign_persistence.py
# 127 passed; exit 0

uv run --locked --group dev pytest tests/test_main_menu_content_coverage.py -q
# 45 passed; exit 0

uv run --locked --group dev python -m pytest -q tests/test_map_rendering_pipeline.py tests/test_map_renderer_coverage.py tests/test_texture_manager_branch_coverage.py tests/test_map_visual_encoding.py tests/test_cache_service_coverage.py
# 76 passed, 2 skipped; exit 0

$env:RUN_MAP_RENDERER_PERFORMANCE_CHECKS='1'; uv run --locked --group dev python -m pytest -q tests/test_map_rendering_pipeline.py::test_live_globe_and_planar_map_renderers_meet_4k_frame_budget
# 1 passed; exit 0

uv run --locked --group dev python -m tools.architecture_check
# 546 files, 1,981 dependencies, 11 contracts, 0 broken; exit 0

openpower ui-test run freeplay-core-loop --fixture tests/ui/fixtures/freeplay_core_loop.json --journey tests/ui/journeys/freeplay_core_loop.json --output artifacts/ui/freeplay-core-loop --width 1280 --height 720
# 17/17 steps; exit 0; report: artifacts/ui/freeplay-core-loop/report.json

uv run --locked --group dev python utils/profile_client_frames.py 1800 --telemetry
# 1,800 measured frames after 60 warmup frames; exit 0
```

Four-viewport reports are in `artifacts/ui/audit/freeplay-matrix/`; the final domain UI suite reports are in `artifacts/ui/audit/p2/`. The P2 suites include 44 passing journeys across ten `suite.json` files. The full UI-harness evidence is not native desktop acceptance.

Exact commands, status mapping, and remaining external gates are summarized in `docs/first-playable-audit-closure.md`.

Live interaction evidence is in `artifacts/ui/live-screen-diagnosis/report.json` and `actual.png`; the game was launched with `$env:OPENPOWER_UI_ARTIFACTS='C:\ProgramData\DEV\OpenPower\artifacts\ui\live-screen-diagnosis'` and `uv run --locked --group dev python main.py`.
