# Navigation verification, updated 2026-11-01

## Advisor-message presentation callback (2026-11-01)

Persisted inbox messages now send their subject and body through
`PanelRenderContext.on_notice`, which `GameLayout` connects to the shared
`GenericMessageDialog`. The `reference-advisor-message-view` journey passes **9/9**
steps at 800×600 and 1280×720, with zero geometry findings or render errors.
The 265×90 dialog and wrapped body were visually reviewed at both sizes.
Evidence: `tests/ui/journeys/reference-advisor-message-view.json`,
`artifacts/ui/reference/advisor-message-gml-800x600-20261101/checkpoints/004.png`,
and `artifacts/ui/reference/advisor-message-gml-1280x720-20261101/checkpoints/004.png`.

This verifies the reusable message presentation and OK acknowledgement route.
It does not create the source EHE advisor producer or its in-memory pending
queue, so `GClientAdvisor::DisplayAdvisorMsg` remains blocked as a complete
source workflow. The inbox item is a user-triggered persisted OpenPower message.

## Tutorial callback recheck (2026-11-01)

The full in-game interface guide passes **93/93** steps at 800×600 and
1280×720, with zero geometry findings and render errors. Screenshot review
processed 50 captures with zero geometry errors; four representative Relations
and Country Information captures were visually inspected. Evidence is in
`artifacts/ui/reference/interface-callback-recheck-800x600-20261101/`,
`artifacts/ui/reference/interface-callback-recheck-1280x720-20261101/`,
`artifacts/ui/reference/interface-callback-review-suite-20261101.json`, and
`artifacts/ui/reference/interface-callback-review-20261101/`.

The source scripted tutorial still requires its dedicated tutorial game type,
fixed country and battle fixtures, and event-gated state machine. The local
guide verifies reachable OpenPower panels and callbacks without standing in
for those missing source scenario behaviors.

## Singleplayer tutorial entries (2026-10-28)

The two Singleplayer tutorial buttons now open local eight-step guides for the
OpenPower interface and supported military panels. Their Back, Previous, Next,
Finish, and submenu-return controls are covered by the main-menu journey. The
guide content does not dispatch game actions. In a running campaign, F1 Help
also opens event-gated Interface and Military tours. The Interface tour waits
for the real Relations and Country Information panels to open and close. The
Military tour waits for Military, Unit List, Unit Research, Unit Design, Unit
Production, Reserves, and War List to reach the requested visible state. These
routes use the current OpenPower campaign and its authoritative country data;
the tour never fabricates a tutorial country or battle.

The seven source callback-to-window routes now have executable journeys. The
Interface journey passes **24/24** steps at 1280×720 and 800×600; the Military
journey passes **33/33** steps at both viewports. Both report zero geometry
findings and no render errors. The refreshed 241-route navigation suite passes
**241/241**, including 214 exact GameAction assertions at 1517×835. The geometry crosswalk links each callback row to its measured
OpenPower destination, journey report, and screenshot evidence. At widths below 1000 px, the guide yields while
the larger Country Information window is open, then resumes after it closes.
The main-menu read-only guide also passes its refreshed route. The source's
fixed-USA tutorial setup and scripted battle/research state are separate source
scenario behaviors that remain unsupported by OpenPower campaign data.

Evidence: `tests/ui/journeys/reference-main-menu-navigation.json` and
`tests/ui/journeys/reference-interface-guided-tour.json`,
`tests/ui/journeys/reference-military-guided-tour.json`,
`docs/ui/reference-title/layout_geometry_crosswalk.csv`,
`artifacts/ui/reference/navigation-final-continuation-20261028/suite.json`, and
`artifacts/ui/reference/interface-guided-tour-1280x720/checkpoints/017.png`,
`artifacts/ui/reference/interface-guided-tour-800x600/checkpoints/017.png`,
`artifacts/ui/reference/military-guided-tour-1280x720/checkpoints/016.png`, and
`artifacts/ui/reference/military-guided-tour-800x600/checkpoints/016.png`.

### GML tutorial pointer (2026-10-29)

`Tutorial_Arrow_Window` now has a Python `TutorialArrowWindow` implementation
with the GML 50×50 frame. `GuidedTutorialWindow` watches the current step's
target control, places the pointer 25 px left of the target's top-center and
50 px above it, draws it in the foreground, and hides it when the guide closes.
The interface and military tours target their actual viewport, HUD, panel, and
modal controls using current-frame geometry. This implements the pointer
window contract, not the source tutorial's fixed-country/battle setup or its
scripted state machine. The source atlas asset `Picture_Normal=783` is not in
the supplied workspace, so Python currently draws a vector arrow.

The focused anchor and arrow tests pass **22/22**. The interface pointer journey
passes **32/32** at 1280×720; the military compact placement journey passes
**14/14** at 800×600, and the all-step military journey passes **50/50** at
800×600. The reviewed captures show the pointer landing on the viewport,
country control, panel controls, modal controls, and Country Information close
button.

Evidence: `tests/test_ui_anchor_registry.py`,
`tests/test_tutorial_arrow_window.py`,
`tests/ui/journeys/reference-interface-guided-tour.json`,
`tests/ui/journeys/reference-military-tutorial-compact-placement.json`,
`tests/ui/journeys/reference-military-tutorial-unit-list-compact.json`,
`tests/ui/journeys/reference-military-tutorial-modals-compact.json`,
`artifacts/ui/reference/tutorial-arrow-interface-verified-20261029/checkpoints/005.png`,
`artifacts/ui/reference/tutorial-arrow-interface-verified-20261029/checkpoints/026.png`,
`artifacts/ui/reference/tutorial-arrow-military-all-steps-20261029/checkpoints/025.png`,
and `artifacts/ui/reference/tutorial-arrow-military-all-steps-20261029/checkpoints/046.png`.

## Unit design source-required capability validation (2026-10-28)

`ResearchProgramSystem` now rejects design actions with missing reference-required
capabilities or incomplete research and records a user-facing reason. Precision
is stored by OpenPower as a 0–1 fraction, so a positive fraction such as 0.5
meets the source's nonzero precision requirement without integer rounding.
`CommandFeedback` routes the authoritative rejection through
`GenericMessageDialog`; the builder keeps the submitted draft open for repair.

The regression journey selects Tank, sets Gun Range to zero, verifies the
`ActionCreateUnitDesign` payload and specific rejection notice, then acknowledges
the dialog and confirms the draft remains. It passes at 1280×720, 800×600, and
1517×835 with zero geometry findings and no render errors. I reviewed all three rejection
captures. The military system and capability catalog tests pass 18 tests plus
38 subtests.

Evidence: `tests/test_research_program_system.py`,
`tests/test_capability_catalog.py`,
`tests/ui/journeys/reference-design-create-capability-rejection-feedback.json`,
`artifacts/ui/reference/unit-design-capability-rejection-20261028/1280x720/checkpoints/011.png`,
`artifacts/ui/reference/unit-design-capability-rejection-20261028/800x600/checkpoints/011.png`,
and `artifacts/ui/reference/navigation-final-continuation-20261028/reference-design-create-capability-rejection-feedback/checkpoints/011.png`.

## Covert operation form actions (2026-10-28)

The three covert-form Confirm buttons now have explicit action mappings in the
audit source and interaction contract: Create Cell dispatches
`ActionCreateCovertCell`, Train dispatches `ActionTrainCovertCell`, and Prepare
dispatches `ActionStartCovertMission`. `CovertOperationsSystem` checks issuer
authority and the selected cell/country state before changing simulation data.
Mission preparation sets `requires_execution_confirmation=True`; mission
execution stays a separate explicit action.

The create, train, and mission journeys pass in the 241/241 master suite at
1517×835. I reviewed each modal capture. The routes report no render errors;
each retains the existing 1 px overlap between assigned-country and status
controls in the covert roster row.

Evidence: `tests/test_covert_operations_system.py`,
`tests/test_reference_navigation_coverage.py`,
`artifacts/ui/reference/navigation-final-continuation-20261028/reference-military-covert-create/checkpoints/005.png`,
`artifacts/ui/reference/navigation-final-continuation-20261028/reference-military-covert-train/checkpoints/005.png`,
and `artifacts/ui/reference/navigation-final-continuation-20261028/reference-military-covert-mission/checkpoints/005.png`.

## reference unit-type crosswalk and design detail geometry (2026-10-28)

The shared Python catalog in `src/client/ui/panels/military/unit_type_options.py`
maps all 20 reference `EUnitType` values and string IDs, in source order, to
canonical OpenPower roles. Unit Design preview, the Create Design editor, the
used-unit market, and Unit List filtering use the same order. Missile Defense
remains an explicitly labeled OpenPower extension; market choices still come
from eligible OpenPower listings. Recognized roster types use the matching
reference English enum label, while unknown or aggregate type names and all other row
values remain bound to OpenPower data. The source localization bundle is absent,
so labels use English enum names.

The Unit List operations journey opens the complete filter, selects a reference type
that has no row in the current OpenPower fixture, then returns to present
OpenPower rows. Its **51/51** steps pass at 1280×720 with zero layout findings.
The refreshed master suite reports **222/222** journeys and **201** exact action
assertions. All design, market, and roster journeys affected by the catalog
were refreshed. The Unit Design detail BACK button now sits in the model
container's upper row, clearing the unavailable-model message; both list and
production detail routes pass with zero geometry findings.

Evidence:

- `tests/test_unit_type_options.py` and `tests/ui/journeys/reference-unit-list-operations.json`
- `artifacts/ui/reference/navigation-full-221-20261027/suite.json`
- `artifacts/ui/reference/unit-type-catalog-20261028/unit-list-operations/checkpoints/007.png`
- `artifacts/ui/reference/navigation-full-221-20261027/reference-unit-list-operations/checkpoints/007.png`
- `artifacts/ui/reference/unit-type-catalog-20261028/unit-list-foreign-estimates/checkpoints/005.png`
- `artifacts/ui/reference/navigation-full-221-20261027/reference-unit-list-design-details/checkpoints/006.png`
- `artifacts/ui/reference/navigation-full-221-20261027/reference-unit-production-design-details/checkpoints/005.png`

Source localization text, 3D model assets, reference research ceilings, and the used-unit rebate/meter semantics remain unavailable or non-equivalent; the crosswalk does not claim those behaviors are implemented.

## Direct government-form changes (2026-10-24)

The Constitutional Form panel now enables its GML-anchored government-form
selector when the selected country is the player's country and compatible
OpenPower rules exist. It filters target forms against the current eligible
party count and political-crisis state, keeps the selected form as a local
draft, and dispatches `ActionSetGovernmentForm` on Apply or Apply-on-close.
The political lifecycle system checks issuer authority, the expected current
form, target uniqueness, active crises, the ruling party, party-count limits,
and election-rule ranges. A valid transition updates the form and election
schedule, cancels replaced election entries and regime-sensitive law
transitions, records history, emits `EventGovernmentFormChanged`, and clears
stored martial law when the target is not a military form.

Six focused journeys verify the enabled selector, staged choice, direct Apply,
dirty-close Apply, pending server state, rejected-action recovery, and martial-law
staging. All six pass with zero geometry findings. The targeted political server
tests pass 38/38. The merged 1280×720 suite passes 222/222 with 201 action
assertions. Four affected journeys were refreshed after the latest UI changes;
the final screenshot review covers 93 captures with zero geometry errors.
The override button now follows the source callback: for supported
multi-party or single-party democratic forms, it stages the unique valid
`military-led state` option in the form selector; the regular Apply button
submits the transition through the validated `ActionSetGovernmentForm` route.
The control is guarded for country authority, martial law, pending form
changes, and target availability. The focused override journey and server
transition test pass. Martial law now uses the staged constitutional Apply flow:
`ActionSetGovernmentForm` carries expected and target status, rejects stale or
unauthorized changes, updates the government table, and records political
history plus `EventMartialLawChanged`. The toggle, Apply state, and final
screenshot were reviewed. Numeric reference government-type mapping, broader
martial-law effects beyond the tracked status and election controls, and
foreign-country release confirmation remain open.

The Constitutional Form lock toggle is hidden by the inherited
`GBaseWindow::OnCreate`; the Python panel omits it to match source runtime
visibility. `GBaseWindow::OnCreate` also moves the title Apply button into the
hidden lock slot, which the GML layout session reproduces per panel instance.

Evidence:

- `artifacts/ui/reference/navigation-after-gml-base-title-runtime-1280x720/`
- `artifacts/ui/reference/navigation-after-gml-base-title-runtime-1280x720/screenshot-review/`
- `tests/ui/journeys/reference-government-form-martial-law.json`
- `artifacts/ui/reference/navigation-after-gml-base-title-runtime-1280x720/reference-government-form-martial-law/actual.png`
- `tests/test_government_form_changes.py`
- `tests/test_ui_testability.py`
- `tests/ui/journeys/reference-government-form-override.json`

## Foreign constitutional routes (2026-10-27)

The Poland target fixture has four political regions, with three under
Ukrainian military occupation. That is exactly 75% by OpenPower's regional
count proxy. At this threshold, while the countries are non-hostile, the form
selector is enabled; capital, override, and martial-law controls remain
disabled. Apply opens the source-sized Generic Question. No preserves the form
draft and sends no action. Yes dispatches a confirmed `ActionSetGovernmentForm`.
The server rechecks the threshold, non-hostile status and confirmation, then
releases the occupied regions, grants military access, and sets both relation
directions to 100. The region-count calculation is an OpenPower-native proxy;
the checked reference source declares but does not publish the reference proportion
formula. The separate neutral/below-threshold journey remains disabled.

The qualified journey passes **18/18 steps** at 1280×720. It captures both
confirmation states; both screenshots have zero geometry findings. The
focused government-form and capital suites pass **21/21 tests**, covering the
75% release/access transition, missing confirmation, hostile targets,
below-threshold control, and foreign capital rejection. Numeric reference
government-type mapping, the exact source proportion formula, city-level
capital semantics, and broader source-specific martial-law effects remain
open.

Evidence: `tests/ui/journeys/reference-foreign-constitutional-qualified-confirm.json`,
`artifacts/ui/reference/foreign-constitutional-qualified-20261027/reference-foreign-constitutional-qualified-confirm/checkpoints/009.png`,
`artifacts/ui/reference/foreign-constitutional-qualified-20261027/reference-foreign-constitutional-qualified-confirm/checkpoints/014.png`,
`tests/ui/journeys/reference-foreign-constitutional-unavailable.json`, and
`artifacts/ui/reference/foreign-constitutional-20261027/reference-foreign-constitutional-unavailable/checkpoints/006.png`.

The production Arcade/OpenGL3 renderer was separately exercised with the current
panel code at the running game's 1518×836 client size, 96 DPI, and pixel ratio
1.0. Politics, Military, Economy, Treaties, Resources, and the central HUD bar
were visually reviewed; their labels align within the rendered panels. These
captures use isolated deterministic UI fixtures, not the active campaign.
Evidence: `artifacts/ui/reference/opengl3-runtime-panels-1518x836/`.

## First-open placement for simultaneous main panels (2026-10-24)

The 1280x720 layout kept the four main pillars in separate columns, but the
Treaties window opened over most of Military and crossed the top system bar.
Python now chooses viewport-aware first-open positions while preserving GML
window sizes. At 1518x836, Politics, Treaties, Military, Demographics and Economy
open in five separate columns. On a 1280x720 viewport, the four main pillars
remain in their compact row; the journey closes Demographics before opening the
large Treaty window in the free column. The Treaty frame stays clear of the
system and central bars. Existing user-moved positions remain managed by
WindowManager's placement cache.

The compact journey passes 20/20 steps at 1280x720. The wide journey passes
11/11 steps at 1518x836 with all five panels visible together. Sixteen captured
checkpoints were reviewed with zero geometry errors; the full-frame Treaty
checkpoints show that it no longer obscures Military or either HUD bar.

Evidence:

- `tests/ui/journeys/reference-main-pillars-no-overlap.json`
- `tests/ui/journeys/reference-wide-main-panels-no-overlap.json`
- `artifacts/ui/reference/pillar-overlap-fix-review/screenshots/inventory.json`
- `artifacts/ui/reference/pillar-overlap-fix-1280x720/reference-main-pillars-no-overlap/checkpoints/018.png`
- `artifacts/ui/reference/pillar-overlap-fix-wide-1518x836/reference-wide-main-panels-no-overlap/checkpoints/011.png`

## Load saved game from the multiplayer browser (2026-10-24)

The Join Multiplayer frame keeps its Load Game control available even when
server discovery is unavailable. The callback navigates from `MainMenuView`
through `NavigationService.show_load_game_screen` to `LoadGameView`, which opens
the existing 774×290 GML-sized `SaveGameDialog`. The journey fixture follows
that transition and renders the same dialog after the recorded navigation
request; with an empty save list, the Load action correctly remains disabled.

The seven-step journey opens the Internet browser, checks its 566×454 frame,
clicks Load Game, verifies the standalone save selector and its disabled submit
button, then asserts exactly one `load_game` navigation request. It passes at
1280×720. Both C++ call sites for the Load button (window creation and show)
are mapped to this verified route. Screenshot review of the browser and save
selector shows both frames within the viewport with zero geometry errors.

Evidence:

- `tests/ui/journeys/reference-main-menu-load-from-multiplayer.json`
- `artifacts/ui/reference/gml-new-game-20261022/full-suite-final/reference-main-menu-load-from-multiplayer/`
- `artifacts/ui/reference/gml-new-game-20261022/full-review-final-214/sheet-66.png`

## F10 in-game menu geometry and callback map integrity (2026-10-24)

## F10 in-game menu geometry and callback map integrity (2026-10-24)

The F10 overlay was reusing the disconnected main-menu runtime layout. That
layout shortens the frame to 196 px and moves Settings, Credits, and Exit up by
27 px. In a running game, reference keeps the source `Main_Menu` slots at their GML
positions and expands the frame to 273×223; the old Python overlay therefore
made Stop Game overlap Settings. `MainMenuContent` now selects the in-game
geometry explicitly, while the disconnected menu keeps its 273×196 layout.

The system-bar journey now asserts the exact source rectangles for Return to
Game, Restart, Stop, Settings, Credits, and Exit, plus F10-button and F10-key
open/close behavior. The main bar toggle follows the source 0.26-second hold
and 0.5-second linear slide, including reversal from its current position. It
passes all 56 steps at 800×600, 1024×768, 1280×720, and 1920×1080, with zero
geometry findings in every viewport. The reviewed
1280×720 checkpoint is
`artifacts/ui/reference/generic-message-callback-csv-integrity/system-bar-matrix/game-hud/1280x720/checkpoints/033.png`.
Disconnected main-menu Options and Credits close journeys also pass.

The generic-message callback map had two rows whose unquoted commas shifted
CSV columns. SHOW-07 now keeps its movement-refusal description and evidence in
their correct fields. SHOW-25 records the source acknowledgement behavior,
OpenPower rejection route, and verification note separately. A regression
check validates the column count, unique route IDs, and all 28 active display
rows; the message, treaty-ineligible, and movement-refusal journeys pass.

The System Bar callback audit now binds F3/F4/F5/F10 and the animated toggle to
their tested OpenPower routes, and records the F2 lobby slot as unavailable.
F1's expanded help panel stays partial because reference only shows the button
tooltip, while OpenPower adds an authored HUD help view.

## Used-unit market quantity repeat (2026-10-24)

The used-unit market arrow handlers already use `GMLValueRepeat`, which mirrors
`GUpdatableValue`: one immediate unit, a 0.5-second initial hold delay, then
increments of 1, 10, and 100 starting at repeat counts 0, 9, and 99. Its
adaptive repeat intervals also match `GDataDisplayLayer::IterateUpdateCursor`.
The audit had kept both arrows partial based on an outdated note that Python
only stepped by one. The arrow contracts now record verified parity; the
editable number field stays partial because exact `GEditBoxNumeric` input and
cursor behavior is not fully crosswalked.

The unit test now checks all 100 repeat increments across the source step
thresholds. The existing hold-repeat journey passes on all four viewport sizes.
Evidence: `artifacts/ui/reference/unit-market-source-repeat-20261024/`.

## Current continuation: History source metrics (2026-10-24)

All seventeen reference history metric slots now have OpenPower-backed series in
reference enum order. Conventional Forces sums non-strategic unit strength;
Strategic Forces sums `strategic_weapons.quantity`; Upkeep reads annual
`countries.expense_military_upkeep`; Research sums `research_tracks.research_level`;
and Resource Balance sums complete annual `resource_ledger.balance_usd` rows.
The resource total is unavailable if any recorded resource row lacks a numeric
balance. These are OpenPower model values; displayed units and formulas do not
claim identical reference simulation outputs. The reference localization strings are
absent from the supplied mirror.

The selector presents all seventeen source concepts with source-style English
labels. The 52-step journey checks all five mappings, axis values, selected
ranges, chart screenshots, and the reference Population default. It passes at
800×600, 1024×768, 1280×720, and 1920×1080. History system and panel tests pass 30/30.
The current combined UI suite passes 222/222 with 201 action assertions. The
398-capture review belongs to the earlier 214-journey run; the four-viewport
History review covers 36 captures with zero geometry errors.

Current evidence:

- Four-viewport History suite and screenshots: `artifacts/ui/reference/gml-new-game-20261022/history-source-metrics-matrix/`.
- Four-viewport History screenshot review: `artifacts/ui/reference/gml-new-game-20261022/history-source-metrics-matrix/review/`.
- Combined navigation suite and screenshot review: `artifacts/ui/reference/gml-new-game-20261022/full-suite-final/` and `full-review-final-210/`.
- Metric source and order: `modules/base/systems/world/history_system.py` and `src/client/services/history_indicator_catalog.py`.

## Legacy saved panel positions (2026-10-24)

The reproducible cause was stale persistent ImGui settings: when the client
loads the repository's old `imgui.ini` entries, `WindowManager` reapplies the
current GML sizes but the old window ID keeps its saved position. For
example, the saved Politics entry is at (22, 134) and 240×520, while the Python
default is (10, 100) and the current GML size is 244×408. This left a
GML-sized panel at a stale screen position and could make the panels look
displaced or crowded.

Layout-backed windows now save under a versioned hidden ImGui ID while keeping
their visible titles unchanged. Old bare-title entries remain untouched and
cannot override the new GML placement. The ID remains stable after the first
open, so subsequent user-moved positions still persist. The regression test
loads a copy of the legacy Politics entry and verifies the first GML placement.

The 11-step main-pillars journey passed with zero layout findings at both
1517×836 (the reported game viewport) and 1280×720. Reviewed screenshots show
the Politics, Military, Demographics, Economy, and central bar controls aligned
within their source frames. Evidence is under
`artifacts/ui/reference/gml-new-game-20261022/pillars-layout-after-ini-migration-1517x836/`
and `.../pillars-layout-after-ini-migration-1280x720/`.

The currently running `OpenPower Engine` process started before the latest
`WindowManager` GML-window identity update, so it still has the old ImGui window
IDs loaded in memory. It cannot pick up this Python change without a restart.
The source now uses viewport-scoped `openpower.gml.v2` IDs; legacy bare-title
entries such as `POLITICS`, `MILITARY`, and `ECONOMY` in `imgui.ini` no longer
override first-open GML placements. `test_legacy_imgui_positions_do_not_override_gml_window_defaults`
covers this migration. The screenshots from the existing process therefore
need a post-restart visual check before they can confirm the current source.

## Dirty-close callback coverage (2026-10-24)

A source scan of all 54 `GBaseWindow` subclasses found `Dirty(true)` in only
eight windows. Seven use the shared base close prompt and are wired to
Apply/Discard in Python: Budget, Resources, Advisor Settings, Internal Laws,
Economic Health, Constitutional Form, and Unit Research. Increase Production
handles its own close button by hiding directly and resets its temporary choices
on creation, matching the Python behavior. No other base-window close caller
needs the shared prompt. The audit now records the modal as implemented and
maps its Remember, Apply, and Discard controls to their actual caller-level
effects. Existing journeys cover Apply and Discard in all seven panels and
remembered choices shared between Budget and Resources.

## Previous continuation: History indicators and source ordering (2026-10-22)

The History selector now presents the twelve measures that have an OpenPower
counterpart in the order of reference's `EHistoryValues` enum, with source-style
English labels. OpenPower-only measures follow deterministically. The match is
by metric concept; it does not claim identical formulas or units where the two
games calculate them differently.

`HistorySystem` now records the existing `gvt_corruption` field as
`politics.gvt_corruption`. It also derives `country.budget_balance` as annual
revenue minus annual expense, matching the source's net-budget expression.
History fingerprints include both budget inputs, so a budget change adds a new
sample even between scheduled daily samples. Overall Relations uses reference's mean
of all other countries' directed relation values and is available only when
OpenPower's full directed matrix is present. The supplied OpenPower seed has
199 countries and all 39,402 directed pairs, with no missing pairs. Five reference measures remain
unmapped because their authoritative equivalents are absent or use different
formulas: Conventional Forces, Strategic Forces, Upkeep, Research, and
Resource Balance. The source localization bundle was not supplied, so the
selector uses source-style English concepts rather than claiming localized
string parity.

Evidence: the 25-step History journey passes at 800×600, 1024×768, 1280×720,
and 1920×1080. Screenshot review covers all 16 captures with zero geometry
errors. History and panel tests pass 27/27. The refreshed full navigation suite
passes 196/196 journeys; the screenshot review covers 355 captures with zero
geometry errors. Current artifacts:

- Four-viewport History runs and screenshots: `artifacts/ui/reference/history-parity-20261022/`.
- Full navigation suite and review: `artifacts/ui/reference/gml-new-game-20261022/full-suite/` and `full-review/`.
- Source order/label crosswalk: `src/client/services/history_indicator_catalog.py`.

## Previous continuation: GML-sized campaign and country setup (2026-10-22)

The new-game route now uses the source `Scenarios_Window` at 560×354 followed
by `Start_Single_Player` at 346×341. The scenario page reads available
campaigns, country allowlists, descriptions, objectives, duration, sandbox
continuation, and enabled rules from OpenPower. Its list, scenario details,
tabs, and Start/Cancel controls use the exported GML positions. The next page
uses the source country combo, profile and party controls, objective rows, and
Start button. Relative-rectangle assertions match the source GML slots for the
scenario list, country combo, party button, and campaign Start button.

reference's sphere difficulty presets, human/computer assignments, and editable goal
choices have no equivalent OpenPower rules. They are presented as unavailable
or scenario-defined values, while the actual country and party selections feed
the existing server-validated `ActionStartCampaign` path. The party picker
continues to use OpenPower political-party rows and stores the selected party
on the campaign without changing the country's ruling party.

Evidence: country validation passes 22/22 steps, country profile 15/15, and
party selection 19/19. All three routes also pass at 800×600. Campaign system,
new-game task, and persistence tests pass 35/35. The full navigation suite
passes 196/196 journeys with 181 action assertions. Screenshot review covers
355 captures with zero geometry errors; the scenario, country, country-profile,
and party-modal frames were inspected.
Current artifacts:

- Full journey suite: `artifacts/ui/reference/gml-new-game-20261022/full-suite/`.
- Screenshot review: `artifacts/ui/reference/gml-new-game-20261022/full-review/`.
- GML runtime layouts: `src/client/ui/layouts/gml_layouts.json` (62 source windows).

## Previous continuation: System Bar and in-game menu (2026-10-22)

The Python `SystemBar` now follows the 577×38 `System_Bar_Window` GML frame and
right/top anchor. Its source toggle, F1/F3/F4/F5/F10 button rectangles, and
labels use the exported GML slots. The F10 route now overlays the shared menu
inside the running game and supports Return to Game, Settings, and Credits;
Restart and Stop remain disabled until OpenPower has authoritative actions.
The F2 chat slot is visible but disabled because OpenPower has no multiplayer
lobby workflow. F6 History and F9 Console remain keyboard shortcuts.

Evidence: `reference-system-bar-layout.json` passes its 51-step journey at 1280×720;
the four-viewport matrix passes at 800×600, 1024×768, 1280×720, and 1920×1080.
The 800×600 Main Menu, Settings, and Credits screenshots were inspected and
their text and windows stay within the viewport. The latest full suite rerun has 196/196 passing journeys with 181 action assertions. Automated screenshot geometry review covers 355 captures with zero geometry errors. Current artifacts:

- Journey suite: `artifacts/ui/reference/gml-new-game-20261022/full-suite/suite.json`.
- Screenshot geometry review: `artifacts/ui/reference/gml-new-game-20261022/full-review/`.
- Four-viewport System Bar matrix: `artifacts/ui/reference/system-bar-gml/matrix-full-final/`.

Manual live-client check: launched the OpenPower client, selected Ukraine in
New Game, scrolled to the UKR row, and started the sandbox campaign. After the
world database loaded, I opened Help, Save Game, Load Game, Politics, Economy,
Military, and the F10 menu from the running HUD at 1904×1023. Panel headings,
labels, values, and buttons appeared aligned and inside their frames; the
country and scenario setup also stayed inside the viewport. Save and Load were
dismissed without committing a save or loading another campaign. The ticker
shortens long status text to fit its slot and exposes the full text on hover.
The application remains on the live campaign HUD for further inspection.

The refreshed route audit records 126 tested literal paths, eight tested
equivalent validations, two alternate-feedback paths, one shared-component
contract, and 31 effective blocked or partial paths. The blocked paths still
depend on OpenPower workflows or authoritative data that do not exist, including
reference multiplayer/RGAPI, tutorial callbacks, advisor-event messages, and changing
another country's constitutional status. The audit classifies 19 reachable
window mappings as verified and 19 as partial; no reachable window is wholly
missing from the Python UI. These remain functional/data gaps, not reasons to
invent local substitutes for authoritative game actions.

## Used-unit market quantity control (2026-10-22)

The market quantity editor preserves GML `MiddleRight` alignment while focused and after blur; focus shows plain digits and blur restores three-digit space grouping. The field rejects non-digit characters and Enter/Escape commit the draft before focus leaves the editor, matching `GEditBoxNumeric::OnChar` and `OnHotkey`. `GMLValueRepeat` applies the source arrow press, 1/10/100 hold-step selection, initial hold delay and accelerated cadence; quantity stays clamped to current listing availability. The 18-step hold journey uses a timed hold against a 21-unit listing and verifies the `ActionBuyMarketUnit` payload. Separate formatting and numeric-editor journeys verify focus/blur grouping, rejected punctuation, and Enter/Escape commit. These journeys pass at 800×600, 1024×768, 1280×720 and 1920×1080 with zero geometry findings. Standard purchase and empty-market journeys pass 16/16 and 7/7 at 1280×720.

The inspected focus and blur screenshots are `artifacts/ui/reference/navigation-gap-closure-20261022-continued/full/reference-military-market-number-format/checkpoints/009.png` and `.../014.png`; the full 341-capture review reports zero geometry errors. `Unit_Buy_Used_Window` remains partial because source type localization, rebate formula, source meter scale, combined speed meter and 3D preview do not have authoritative OpenPower equivalents. The source IDs/order now map to canonical OpenPower roles.

The source quantity-step gap is now closed: `GMLValueRepeat` uses the same initial press, 1/10/100 hold thresholds, initial 0.5-second delay, and accelerated repeat cadence as `GUpdatableValue` and `GDataDisplayLayer::IterateUpdateCursor`. The focused 18-step hold journey passes at 1280×720 and 800×600; each run verifies the final quantity 21 in `ActionBuyMarketUnit` for a listing of 21. The four threshold tests pass, and review of six intermediate screenshots found zero geometry errors. Evidence is under `artifacts/ui/reference/used-unit-quantity-step-20261024/`. The market window remains partial for source localization, rebate, meter-scale and 3D-preview differences.

## Unit production quantity hold control (2026-10-24)

Production quantity arrows now share `GMLValueRepeat`: a press changes the value by one, holding waits 0.5 seconds, then repeats with the source 1/10/100 thresholds and accelerated cadence. The numeric editor resets repeat state when its value changes. A 650 ms hold journey crosses the initial delay, observes 50 → 51 on click and 51 → 53 on hold, then confirms quantity 53 in `ActionQueueUnitProduction`; the existing production-actions journey still passes its direct editing and action checks. The focused unit/repeat tests pass 6/6.

The source uses recruitable manpower for the infantry maximum, but OpenPower does not expose an equivalent. The UI therefore keeps its existing 0..1,000,000 bound and does not substitute working-age population as recruitable manpower. Four reviewed screenshots from the 24-step production workflow and the quantity-hold journey have zero geometry errors. Evidence is under `artifacts/ui/reference/unit-production-quantity-hold-20261024/`.

## Server-reference trace for remaining actions (2026-10-27)

The locally supplied mirror contains only the client. The public reference-HDM repository also contains server sources; the trace below is pinned to commit `533f0ca03c7df4aef2421bbbb32e4ae489be9325` and describes that mod's behavior, not an independently verified vanilla server.

For a foreign constitutional form change, the [server event handler]([external-link-redacted]) calls `LiberateRegions` before changing a different government form and sets both directional relation values to 100 when the form changes. The [release implementation]([external-link-redacted]) requires a gained proportion of at least 0.75 and a non-hostile diplomatic status, returns military control of qualifying political regions, and creates military access. Foreign capital, martial-law and override controls are disabled by the source constitutional window. OpenPower enables only qualified non-hostile form changes, using the share of target-owned political regions under the actor's military control as a documented native proxy because the published repository declares but does not include the source proportion formula. Its validated transaction releases active occupations for the target's regions, grants a military-access treaty and transit-right effects, and sets both relation directions to 100. The exact reference proportion formula and numeric government-type mapping remain open.

For resource investment, the [server implementation]([external-link-redacted]) multiplies production for the selected resource in each politically controlled region, deducts the estimated cost, synchronizes country totals and records a history marker. `IncreaseProductionApproxCost` is declared in the published common interface but its implementation is absent from the checked repository. The OpenPower estimator and authoritative investment transaction therefore remain open; the UI has not been marked complete by this trace.

## History empty-state layout (2026-10-27)

The empty graph message previously extended beyond the right edge of the source graph frame. It now wraps within the frame, and the journey asserts that the full message is visible and spans multiple lines. At 800×600, 1280×720 and 1518×836, the message rectangle is 350×24 inside the 405×166 graph rectangle. All three 3-step runs and the 52-step populated-history journey pass with no geometry findings or render errors; 12 screenshots were visually reviewed. Reports and screenshots are under `artifacts/ui/reference/history-empty-wrap-20261027/`. The refreshed History case also passes in the current 222-journey suite.

## Unit Design create caption and reopen path (2026-10-27)

The create action text exceeded the fixed 84×18 source slot, so the button now
uses `CREATE` while retaining the same GML position and callback. The 16-step
journey verifies the button against its `Unit_Design_New` rectangle, submits the
request, returns to the parent, reopens the editor, and checks that its
capability input is interactive.

The updated journey passes at 1280×720 in the full navigation suite and at
1518×836 in `artifacts/ui/reference/unit-design-reopen-check-20261027/1518x836/`.
Both reports show zero geometry findings and no render errors; checkpoint 015
was visually reviewed with the editor open. The design-create rejection
journey passes 19/19 at 1518×836. Source localization strings, research-based
ceilings, design cost and native model assets remain separate functional gaps;
the source type IDs/order now map to canonical OpenPower roles.

## Load and new-game failure feedback (2026-10-21)

The reference result callbacks display a localized Generic Message modal when loading
or campaign creation fails. OpenPower keeps the recoverable `LoadingView` open,
shows the captured exception, and offers a return-to-start action. This is
equivalent alternate feedback rather than a literal reproduction of the reference
modal. The shared `LoadingStatusPanel` renders the production and test surfaces.

Evidence: the load and new-game failure journeys each pass all four steps at
800x600, 1280x720, and 1920x1080. All six reports have zero geometry findings
and no render errors. Screenshot review confirms the centered error panel sizes
to its message, has no stale progress bar, and keeps both the full details and
return button visible. The combined index was 164/164 at the time of that run;
the latest full 1280x720 index is recorded below. The viewport index is
`artifacts/ui/reference/loading-failure-feedback/suite.json`.

## New-game country selection validation (2026-10-21)

reference displays a generic warning when Start is pressed without a selected country.
OpenPower disables Start Campaign until both a country and scenario are
selected. The journey checks the disabled state before selection, selects
Ukraine, and verifies that the button becomes enabled. This prevents the
invalid submission as an equivalent validation; it does not reproduce the
source warning modal.

Evidence: all four steps pass at 1280x720 with zero geometry findings and no
render errors. The checkpoint screenshot shows the prompt and disabled button;
the final screenshot shows the selected country and enabled button:
`artifacts/ui/reference/new-game-country-validation/1280x720/`.

## New-game country profile (2026-10-21)

The single-player profile route now opens a dedicated 271×359 `Country Profile`
window using the exported GML controls and anchors. Its three desired-rank
filters use OpenPower GDP, government approval, and military personnel data.
Selecting a suggestion commits the country back to New Game; Cancel leaves the
parent selection unchanged. The separate Game Lobby caller still needs its
multiplayer country-list workflow.

Evidence: `reference-new-game-country-profile.json` passes 14/14 steps at 1280×720,
with zero layout findings and no render errors. Screenshot review covers the
opened profile and selected-candidate state in
`artifacts/ui/reference/country-profile/1280x720/checkpoints/002.png` and
`artifacts/ui/reference/country-profile/1280x720/checkpoints/005.png`.

## War List layout and interaction parity (2026-10-22)

`WarListPanel` now follows the `War_List_Window` 543×296 frame. Its top list,
details area, leader slots, coalition lists, and join/peace/war controls use the
source GML rectangles. Rows bind to `countries_wars`; leader and member names
resolve through the OpenPower country table, and member exhaustion uses the
matching `war_exhaustion_states` row. Missing exhaustion displays as unknown.

Joining a side dispatches `ActionJoinWar`. `TreatyDiplomacySystem` verifies the
war is active, the player controls the requested country, the side is valid,
the country is not already a participant, and the opposing side exists before
changing membership, relations, mail, or news. PEACE/WAR intent dispatches
`ActionOfferPeace`; the server checks the same country authority and requires a
leader for the selected side. The structured peace-package editor is an
OpenPower supplemental page in the source-reserved title `btnApply` slot.

The 18-step join/leader-intent/page/close journey passes at 1280×720 and
800×600 with zero geometry findings and no render errors. The action tests pass
17/17 across diplomacy, advanced diplomacy, and the War List panel. Screenshots
were reviewed at
`artifacts/ui/reference/war-list-gml-reconstruction/interactions-1280x720-final/checkpoints/003.png`,
`.../interactions-800x600-final/checkpoints/003.png`, and
`.../interactions-1280x720-final/checkpoints/014.png`. Remaining source parity
is limited to localized label tokens and reference status-icon artwork.

## Unit design overview and creation form (2026-10-22)

The small `UnitDesignPanel` uses the 324×414 `Unit_Design_New` GML overview;
the separate `UnitDesignEditor` uses the 666×618 `Unit_New_Design` builder. The
overview selectors, description, cost row, bottom 101×16 Unit View/Statistics
tabs, title lock, and create route use their source slots. Statistics use the
GML `frmList` viewport and `scrList` track; the 16-step journey checks the
initial and scrolled row positions, confirms Sensors becomes visible at the
bottom, and returns to Unit View. It passes at 800×600, 1024×768, 1280×720,
and 1920×1080 with zero geometry findings, and its overview and scrolled-state screenshots were visually
reviewed at
`artifacts/ui/reference/unit-design-tabs-matrix-20261027/1280x720/reference-unit-design-tabs/checkpoints/002.png`
and
`artifacts/ui/reference/unit-design-tabs-matrix-20261027/1280x720/reference-unit-design-tabs/checkpoints/013.png`.
Its Unit List and Unit Production entry routes resolve the selected design ID
and canonicalize saved role aliases before displaying the detail.

The builder places its OpenPower role selector in the source unit-type slot
(`cboUnitType` at 80,5, 193×16) and keeps the source model-piece selector in
its own `cboType` slot. Model-piece, variation, part, and color controls remain
disabled with explanations because OpenPower has no matching model catalog or
visual assets. Name, cost, upkeep, and twelve capability values use source
bounds. The capability sliders use OpenPower's numeric bounds and their values
are included in `ActionCreateUnitDesign`. Source meter clicks recalculate cost;
OpenPower currently accepts cost separately, so that cost formula remains
partial. The builder stays editable after a rejected result and closes after
the authoritative state contains the created design. The create/acceptance,
rejected-create, unit-list detail, and production detail journeys pass 12/12,
19/19, 10/10, and 7/7 steps at 1280×720 with zero geometry findings and no
render errors. The refreshed create and rejection scenarios also pass after
this selector-slot correction.

The refreshed overview screenshot and builder/rejection screenshots reviewed
include
`artifacts/ui/reference/navigation-unit-design-recheck-20261022/reference-military-design/checkpoints/003.png`,
`artifacts/ui/reference/navigation-unit-design-recheck-20261022/reference-military-create-design/checkpoints/001.png`,
`artifacts/ui/reference/navigation-unit-design-recheck-20261022/reference-design-create-failure-feedback/checkpoints/011.png`,
`artifacts/ui/reference/navigation-final/reference-unit-list-design-details/checkpoints/005.png`,
and
`artifacts/ui/reference/navigation-final/reference-unit-production-design-details/checkpoints/005.png`.
reference research-based meter ceilings and model/part/texture assets remain
unavailable in OpenPower.

## Unit Research source layout and funding flow (2026-10-22)

`UnitResearchPanel` uses the 607×455 `Unit_Research_Window` template. The four
category controls, branch funding meters, title controls, and three tabs follow
their GML slots; the detail view keeps the twelve source characteristic rows.
OpenPower's `research_tracks` supplies branch-level progress and funding. Its
strategic program, weapons, and defense tracks are shown separately. When an
OpenPower row or preview asset does not exist, the panel says `N/A`, `NEW`, or
that the 3D preview is unavailable rather than inventing a value.

Funding meters now edit a local draft. The GML-sized Apply button enables when a
value differs from its baseline and submits only changed branches through
`ActionUpdateResearchFunding`. Closing a dirty panel opens the shared
Apply/Discard confirmation; Discard sends no actions. The 38-step journey checks
multiple branch edits, no dispatch before Apply, submitted-value persistence
while snapshots lag, accepted-snapshot reconciliation, rejection feedback, and
retention of the retryable draft. The two 9-step close journeys check Apply and
Discard. All three pass at 800×600, 1024×768, 1280×720, and 1920×1080 (12/12
runs) with zero geometry findings. The 800×600 confirmation and the rejected
funding snapshot were visually inspected. The refreshed screenshots and
reports are under
`artifacts/ui/reference/unit-research-apply-close-20261022-reconciled/matrix/`.

reference redistributes one linked budget among categories and characteristics;
OpenPower stores independent branch ratios, so that redistribution remains a
partial semantic difference. Per-characteristic research data and 3D model
assets remain unavailable. The 16 focused research-program and military-panel
tests pass.

## Current route coverage (2026-10-28)

The route crosswalk records 175 source transitions: 134 tested literal routes,
8 equivalent validations, 2 alternate-feedback routes, and 1 shared-component
contract. Remaining workflow gaps include 25 routes without a supported
workflow and 1 unreachable source branch; 3 routes require lifecycle
initialization and 1 is inactive source code. All 31 seed transitions pass.
Nineteen reachable windows remain partial across 59 inbound evidence rows.

Before adding peace-package routes, the complete navigation report had 233/233
passing journeys and 208 exact action assertions at 1517×835. The refreshed
strategic planner route in that report checks payload selection and also
passes at 800×600, 1280×720, and 1920×1080. The surface matrix passes 172/172
runs across 43 surfaces and four viewport sizes.
The earlier 398-capture screenshot review remains historical evidence for the
prior 214-journey suite. The refreshed Unit
Research journeys verify deferred Apply, snapshot reconciliation, rejection
feedback, and dirty-close behavior; the suite also includes the current Unit
List upkeep and disband journeys.

Advisor Settings now reads and writes the economy, politics, and military modes
through `ActionUpdateAdvisorSettings`; the server validates player-country
authority and stores accepted values. Four Apply/Discard/close journeys pass at
1280×720 and 800×600. Screenshot review is under
`artifacts/ui/reference/advisor-authoritative-20261027/`. A bounded OpenPower policy
adapter now observes those modes on new-day AI evaluations: automatic mode
emits the supported country action into the normal simulation step, while
confirmations mode records a stored action in the existing advisor
recommendations table. War declarations, strategic strikes, covert operations,
movement, and battle policies remain outside this player-controlled subset.
The recommendation resolver checks the answering player's country and verifies
that the stored action targets that same country before accepting it.

The new 22-step UI journey opens the recommendations through the F5 Objectives
route, accepts one action, declines another, reads a non-action message, and
checks both one-shot dialog paths. It passes at 800×600, 1280×720, and 1518×836
with zero layout findings and no render errors. The 12 reviewed captures are
listed in `artifacts/ui/reference/advisor-recommendation-review-suite/inventory.json`;
question, decline, and message states are shown in
`artifacts/ui/reference/advisor-recommendation-review/checkpoints/004.png`,
`artifacts/ui/reference/advisor-recommendation-review/checkpoints/011.png`, and
`artifacts/ui/reference/advisor-recommendation-review/checkpoints/017.png`. The
OpenPower adapter is not the reference EHE plan scheduler or its queued advisor-event
workflow; those source semantics remain open.

## Shared dirty-close confirmation (2026-10-21)

The GML base-window close handler presents the shared Apply/Discard dialog when
an edited panel is closed. OpenPower connects `DirtyCloseConfirmation` to seven
panels that track unsaved local edits: Budget, Resources, Advisor Settings,
Internal Laws, Economic Health, Constitutional Form, and Unit Research. Fixture
journeys cover Apply and Discard for all seven panels plus remembered choices
for Budget. They pass with zero geometry findings and no render errors;
screenshot review confirms the confirmation
remains legible over edited panels. The Economic Health policy view also keeps
its labels and controls inside the 264×333 GML frame. The report index is
`artifacts/ui/reference/shared-dirty-close/suite.json`.

## Incoming news projection (2026-10-21)

`GDataAccessLayerClient::InsertPendingNews` adds an item to the reference Event Log but
does not show that window; the HUD toggle performs the separate `Show()` call.
OpenPower receives news through authoritative `news_items` snapshots, and
`EventFeedPresenter` renders new rows on the next frame. The rolling-update
journey opens the feed, delivers a news snapshot, and verifies the new item
without forcing a panel pop-up.

Evidence: the journey passes 4/4 steps at 1280x720. Its report has six
unrelated existing HUD layout findings and no Event_Log geometry finding.
This is an equivalent data-delivery path; reference's pending-news priority queue and
advisor callbacks remain separate workflows. At the time of this incoming-news
run the combined index was 164/164; the latest full-index status and remaining
failed journeys are listed under Current route coverage. The eight-country
treaty grid checks remain separately indexed. Route coverage is 126 tested
literal routes, six equivalent validations, two alternate-feedback routes, one
tested shared-component contract, and 33 remaining paths.

## Event Log layout and interaction parity (2026-10-21)

The Python `NewsPanel` now follows the reference GML `Event_Log` frame and control
slots: 488×199 for the centered panel, 446×185 for the list, four 27×21
category filters, and a 27×21 Goto control. `EventFeedPresenter` reads
OpenPower `news_items` and random-event snapshots. Selecting a typed active
event enables its supported response action; Goto requests local viewport
focus only when the selected item has a region. Random-event policy settings
remain in a supplemental popup outside the source control slots.

The 28-step journey passes at 1280×720 and 800×600. At 1280×720 the panel is
at x=396, y=260; the list is at x=402, y=267, matching the source-local
offsets. The rolling snapshot journey passes 4/4 at 1280×720. The 1280×720
report contains five unrelated HUD layout findings and no Event_Log geometry
finding. Screenshots: `artifacts/ui/reference/news-gml/1280x720/checkpoints/002.png`
shows the empty feed and filter slots; `.../checkpoints/009.png` shows a
snapshot-projected random event and political news row; `.../rolling-update/1280x720/checkpoints/001.png`
shows the updated item after snapshot delivery.

Remaining differences are explicit: General-category items remain visible
because GML has no General filter, and the source pending-news priority queue
and advisor callbacks have no equivalent in the snapshot-to-feed path. The
HUD toggle separately opens and closes the Event_Log panel.

## Main Bar GML control binding and Mail_Window parity (2026-10-21)

The central HUD rendered Advisor, History, Mail, News and Country as ordinary
ImGui buttons even though their source slots are GML toggles or a listbox-style
country selector. The layout mapper correctly refused those mismatched control
types, leaving ImGui's flow cursor to place the buttons below or outside the
GML slots. The central HUD now uses source-sized GML toggle controls and binds
the custom country popup to its `cboListboxLess` slot. The Mail click therefore
lands at its source 27×27 rectangle (x=713, y=648 at 1280×720), and the Event
Log click lands at its 25×19 source slot (x=856, y=684). The separate
SystemBar news icon remains an OpenPower-only route.

The Python `LiveMailPanel` now uses the GML 489×219 window, 475×180 list,
133×18 Delete All control and dynamic 460×18 row template. At 1280×720 it is
placed at x=573, y=311; at 800×600 it is clamped to x=311, y=191 without
resizing the source frame. Each row maps current-country OpenPower messages,
contextual dispatches and response-required treaty proposals. VIEW opens the
matching message/dispatch/proposal destination and consumes that row; DELETE
and Delete All dismiss rows locally, and Escape closes the inbox. Incoming mail
events update the inbox data without automatically showing the window. This
matches the source AddMail callbacks, which add rows but do not call Show.

Verification and screenshot review:

- `reference-mail-layout` passes 10/10 at 1280×720 and 800×600, including exact list
  offsets, Escape, per-row Delete and Delete All close, with zero geometry
  findings and no render errors.
- `reference-mail-context` passes 19/19 at 1280×720 for treaty, trade and battle
  context routes and consume-on-view behavior.
- `reference-treaty-refusal-mail` passes 11/11; `reference-live-combat-mail` passes 19/19;
  `reference-mail-arrival` passes 8/8, including delivery while Mail is closed and
  opening the inbox afterward.
- `reference-news` passes 28/28 at 1280×720 through the actual GML Main Bar News
  toggle, with zero geometry findings. `Main_Bar/togMail` and
  `Main_Bar/togNews` are mapped to `hud.mail` and `hud.news` respectively.

Screenshots: `artifacts/ui/reference/mail-layout/1280x720/checkpoints/001.png` and
`artifacts/ui/reference/mail-layout/800x600/checkpoints/001.png` show the GML inbox
at both sizes; `artifacts/ui/reference/mail-arrival/1280x720/checkpoints/003.png`
shows a newly delivered refusal after the inbox is opened;
`artifacts/ui/reference/news-gml/1280x720/checkpoints/001.png` shows the feed opened
from the corrected Main Bar slot. OpenPower has no equivalent to reference's
first-mail incoming sound; that remaining difference is recorded in the audit.

## Country Information map rendering (2026-10-21)

The Country Information fixture previously had no `session.map_data`, and its
hand-authored region IDs could not match the technical map. The fixture now uses
the base region table and population data, plus the same packed IDs as the real
map. Its test-only map buffer is downsampled to 2048x1024; the game keeps its
normal full-resolution map. A UI-runner OpenGL texture uploader renders the same
country silhouette when no Arcade window is registered.

Evidence: all 27 Ukraine region IDs appear in the map buffer. The `game-hud` UI
journey passes 10/10 steps at 800x600, 1024x768, 1280x720, and 1920x1080; each
run records the country map image as visible and reports zero geometry findings.
Visual review confirms the Ukraine silhouette and regional borders render in the
GML `frmMap` slot at all four sizes.

Artifacts: `artifacts/ui/reference/country-info-real-map/suite.json` and its linked
screenshots/reports.

## Non-navigation Spawn records (2026-10-21)

The source scanner had treated four `LoadGameData`/`IterateGame` Spawn call sites
as user navigation. Source review confirms three are hidden initialization
(Generic Message and System Bar pass `visible=false`; Console is created hidden
and immediately hidden again) and the fourth is commented out. The audit marks
these as `lifecycle_initialization` or `inactive_source_code` and excludes the
two Generic Message records from incomplete-window inbound-route counts.

The scanner still records 173 source transition sites for traceability, but 168
are effective navigation paths: 126 tested routes, six equivalent validations,
two alternate-feedback routes, one tested shared-component contract, and 33
unresolved paths. The current audit finds 14 reachable windows with remaining
contracts across 50 effective inbound-transition evidence rows.

## Source-unreachable repeat occupation question (2026-10-21)

The `OnSubjectChange` branch at `reference_data_control_layer.cpp:1196` asks another
war-declaration question when pending countries remain after an acknowledgement.
`OccupyTerritory` clears the pending set at entry and only inserts the target
country in active code. The loop that would add controllers of occupied regions
is commented out. The acknowledgement removes the single target, leaving no
second pending country, so the repeated question branch is unreachable in the
supplied source version and does not require a Python route.

## Internal Laws last-recognized-group safeguard (2026-10-21)

reference restores the selected status and displays a generic warning if a change
would leave every language or religion illegal. `IdentityPolicyDraft` applies
the same recognized-group guard, and `GenericMessageDialog` presents the
reason without dispatching `ActionSetCountryIdentityPolicy`. The
`identity-last-recognized` journey exercises this for both languages and
religions and verifies that no policy action is sent.

Evidence: a fresh 1280x720 run passed all 8 steps with zero geometry findings.
The screenshot captures the warning over the Internal Laws panel:
`artifacts/ui/reference/identity-last-recognized/retest-20261021/actual.png`.

## Saved-game load route (2026-10-21)

reference's single-player submenu opens `Load_Saved_Game`. OpenPower does not reproduce
that submenu, so its in-game Load control is the equivalent entry point to the
same source-sized saved-game list. The journey clicks that control and checks
the destination's exact 774x290 GML frame and Load control.

Evidence: all 3 journey steps pass at 800x600, 1024x768, 1280x720, and
1920x1080 with zero geometry findings. Screenshot review confirms the list
stays within its GML frame at each size; the selectable slot hitboxes are inset
into the list clip rectangle. This verifies the load selection route and
destination, not successful deserialization of a selected save.
Screenshot: `artifacts/ui/reference/load-saved-game-route/index/reference-load-saved-game-route/checkpoints/001.png`.

The main-menu load screen now uses the same Python `SaveGameDialog` component,
so both entry points share the 774x290 GML frame, fixed metadata columns, and
truncated long names with a full-name tooltip. This replaces the separate
500x600 list that let long save names run into their dates. A live 1904x1023
playtest confirmed the aligned columns and that the GML close control returns
to the main menu. No save was selected or loaded. A component test verifies the
close callback runs once; the focused UI, route-coverage, and GML-binding tests
pass 25/25. The four-size capture set is under
`artifacts/ui/reference/load-dialog-boundaries/`.

## Treaty participant eligibility (2026-10-21)

The treaty detail screen now renders eligible countries and the source GML
“Remove Not Eligible” control. That control stages invalid-member removal in the
participant editor and requires Apply before dispatch. `DiplomacySystem` uses the
same saved eligibility rules for participant updates as it does for treaty entry
and suspension; rejected updates return the invalid country tags. The HUD shows
the rejection through `GenericMessageDialog` and keeps the participant draft open
and marked so it can be corrected after acknowledgement.

Evidence: the removal and rejection journeys pass 18/18 and 16/16 steps at
1280x720, with additional passes at 800x600 and 1024x768. A separate eight-country
grid journey verifies the source five-flags-per-row layout and exclusion rules at
1280x720 and 800x600 (14/14 at each size). Screenshots were reviewed; the GML
details and participant dialogs have no geometry errors. The suite reports one
warning-only `Proposals` tab bounds finding: the tab is visibly rendered, while
the telemetry tab-bar rectangle is offset from its item rectangle. The focused
row-layout, treaty, lifecycle, and command-feedback tests pass (21 total). The
combined report index is 164/164: it includes the remove and rejection
journeys, the news snapshot, saved-game load, identity-policy rejection, and
Economic Health dirty-close journeys, and reuses prior reports for unaffected journeys; the grid journey is
stored separately. The latest route audit shows 125 tested literal routes, five
equivalent validations, two alternate-feedback routes, one tested
shared-component contract, and 34 routes still awaiting full coverage.
Screenshots: `artifacts/ui/reference/treaty-eligibility/`.

## Unit design save failure feedback (2026-10-21)

When `ActionCreateUnitDesign` is rejected, the game HUD's `CommandFeedback`
delivers the authoritative reason to `GenericMessageDialog`. The creation form
stays available behind the notice, so the player can acknowledge the result and
continue editing. The reference save-failure callback is now connected to this result
route.

Evidence: the native game-HUD journey passed all 14 steps at 1280x720, including
opening Military and Unit Design, submitting the action, asserting the rejection
message, and acknowledging it. The captured dialog was visually reviewed; text
fits the 265x131 source window, with zero geometry errors. The server-system,
command-feedback, and movement-feedback focused tests passed (20 total). The
combined report index contained 151/151 passing entries at that point and
reused older reports for unaffected journeys. The route audit then showed
125/173 tested, one equivalent validation, and 47 routes still without full
coverage.
Screenshot: `artifacts/ui/reference/design-feedback/1280x720/reference-design-create-failure-feedback/checkpoints/010.png`.

## Movement refusal feedback (2026-10-21)

The game HUD now consumes newly received `unit_order_feedback` rows and shows a
shared generic-message warning for rejected local movement and naval-invasion
orders. It groups each incoming batch by refusal reason across move and naval-invasion
orders and displays the count;
accepted orders, deployment records, other countries' results, and loaded history
do not open this notice.

Evidence: 10 component tests passed with the existing command-feedback tests. The
native game-HUD journey passed all 5 steps at 1280x720, verified a two-unit count,
excluded a foreign-country refusal, and acknowledged the dialog. Its captured
dialog was visually reviewed; text fits the source-sized message window and the
journey reports zero geometry errors. Screenshot:
`artifacts/ui/reference/movement-refusal/1280x720/reference-movement-refusal-feedback/checkpoints/001.png`.
The combined report index includes this new journey but reuses older evidence for
unaffected routes; it is not a fresh rerun of the whole suite.

## Covert action forms use modal GML windows (2026-10-28)

The source registers cell creation, training and mission configuration as modal
windows. OpenPower now composes them through the shared GML modal helper, keeping
each source window size, title bar, close control and field geometry while dimming
and blocking the parent panel. Prepare, Train, Create and Cancel close only the
active form; the title-bar close control is also covered by the mission journey.

Evidence: the refreshed master suite passes 222/222 at 1280x720 with 201 exact
GameAction assertions. Focused covert journeys pass for cell creation (12/12),
training (13/13), mission configuration (19/19) and foreign-country visibility
(13/13). The shared Generic Message route also passed after the popup helper change.
The mission screenshot with the selected Civilian/Sabotage/Cereals/High terms is
`artifacts/ui/reference/navigation-full-221-20261027/reference-military-covert-mission/checkpoints/012.png`.
The report retains one 2px overlap between country and status combo bounds because
those rectangles overlap in the supplied GML row template.

## Covert mission configuration fields (2026-10-21)

The New Covert Mission form now follows the source GML controls for mission type,
target sector, complexity, resource/unit target, and framed country. Its assigned
target country remains inherited from the selected cell; the source target-country
combo is not repurposed as a cell selector. The client lists target-country resource
rows from OpenPower's resource data, and the server validates cell ownership/stage,
target/profile compatibility, complexity, resource or unit category, and framed
country before charging preparation. The mission saves these terms and the owned
roster/outcome views show them. The interaction/data audit now includes these five
source combo controls and their saved/displayed mission fields.

Evidence: 48 focused covert tests passed. The mission-option journey passed at
800x600, 1024x768, 1280x720 and 1920x1080 (12/12 steps at each size); all four
screenshots were visually reviewed, with no journey geometry errors. The framed
country result dispatch still passes at 1280x720 (5/5). The 151/151 combined report
index reuses prior reports; it is not a fresh rerun of every journey. The latest audit confirms
43/1300 data bindings and 17/909 interaction bindings as verified OpenPower rows.
Artifacts: artifacts/ui/reference/covert-mission-options and
artifacts/ui/reference/covert-framing.

Remaining in Covert Actions: protection percentage is unavailable, and saved
complexity plus resource/unit targets do not yet affect mission success, detection,
or operation effects. The audit still records 48 navigation routes without full
coverage; the new form controls do not close unrelated workflows.

## Covert mission framing and discovered attribution (2026-10-21)

The New Covert Mission dialog now includes the source-supported owner country in
the framing choices and submits it in ActionStartCovertMission. The server rejects
unknown countries and the mission's target before charging preparation. It stores
the selected framed country on the mission. When detection identifies the operation,
the simulation attributes it to that country, applies the diplomatic relation penalty
to the accused country, and retains `attributed_to_owner` only for true owner attribution.
The target receives the identified attribution. A framed third country receives a
separate generic notice and an audience-scoped incident without the cell, actor,
intelligence output, or confidence. The mail dispatch opens the framed-country result
view, which hides the actual owner and operation outcome, following the source callback.

Evidence: 47 focused covert tests passed, including saved framing, invalid/target
country rejection without spending, deterministic detected attribution, relations,
notifications, audience privacy and dispatch visibility. The native mission dialog
journey passed at 800x600, 1024x768, 1280x720 and 1920x1080 (4/4); the framed-country
mail dispatch passed at 1280x720 (5/5). All thirteen captured screens were visually
reviewed with zero geometry errors. The one runtime layout warning is the existing
2px boundary overlap between country and status combos in the source 681x16 roster
row. The 147/147 combined suite is a report index: it reuses earlier journeys and
contains fresh evidence for the mission dialog and mail dispatch, not a fresh run of
all 147 journeys.
Artifacts: artifacts/ui/reference/covert-framing. These checks use native ImGui fixtures
and server simulation tests, not an Arcade live-world playtest.

At the time of this framing-only batch, mission complexity and resource/unit targeting
were still missing. They are now selected, validated, saved, and displayed as described
above; their effects on mission resolution remain open. Protection percentage is also
unavailable. The UI-wide audit still records 50 navigation routes without full coverage.

## Covert roster country and activity editing (2026-10-20)

The dynamic lstCovertActionsItem/cboCountry and cboStatus controls now use the
source GML rectangles and dispatch ActionRetargetCovertCell and
ActionSetCovertCellActivity. Server checks include issuer ownership, expected
country/status, current mission stage, communications and valid destination.
Reassignment uses the existing route planner, third-country transit rights and
arrival pipeline. The last arrived region is preserved as the actual origin when
a capital changes. Validation completes before any route or cell mutation.
Active/Dormant changes do not charge creation or preparation again; waking legacy
dormant assignments also clears their obsolete activity flag.

The client waits for an authoritative snapshot or matching command result before
unlocking the row. Unrelated actor results cannot unlock it. Busy cells and foreign
rosters remain protected. Selecting a row combo updates the mission section to the
same cell immediately without modifying the published gameplay state.

Fresh evidence: 89 Python tests passed, 14 subtests passed and one optional benchmark
was skipped. Six native fixture journeys passed at four sizes (24/24), and twelve
existing readiness/form journeys passed again at 1280x720 (12/12). All 50 captures
were visually reviewed; geometry analysis reported zero errors. Evidence is under
artifacts/ui/reference/covert-roster, including per-size review/inventory.json files.
These are native ImGui fixtures and separate server-system tests, not an Arcade
live-world playtest. The combined-suite.json is an index of 146 reports reusing older
unaffected journeys; it is not a fresh run of all 146 scenarios. The main manifest
now contains 161 journeys.

Source callback references: .codex/Client/Source/reference_covert_actions_window.cpp,
OnCustomEvent, country/status combos (lines 383-454). Python implementations:
src/client/ui/panels/military/covert_roster_controls.py and
modules/base/systems/military/covert_cell_control.py, plus _retarget_cell in
covert_operations_system.py. Behavioral evidence: tests/test_covert_cell_control.py
and tests/ui/covert-roster-suite.json. Dynamic row controls are separate from the
909 static interaction-contract rows; completing these controls does not change
that denominator or the 50 remaining window-navigation routes. As of this 2026-10-20
snapshot, protection, complexity and resource/unit targets remained incomplete;
framing semantics were implemented in the 2026-10-21 section above.

## Covert readiness callback, source roster and mission commands (2026-10-20)

CovertOpsPanel now composes the 746x344 Covert_Actions_Window frames and exported
681x16 lstCovertActionsItem rows. Name offsets, grade slot, assigned country, status,
progress, configured daily upkeep, action positions and selected-mission fields use
the source rectangles. A 2026-10-22 screenshot review found that `lblProgress` is
exported as transparent text inside a meter slot; the ordinary text mapper placed
its heading at the window origin over the first row. It now uses `GMLWidgets.text_at`
to honor the slot. The nine-step ready/cancel journey asserts the heading's GML-relative
rectangle and no overlap with the first cell row; it passes at 800×600, 1024×768,
1280×720, and 1920×1080. All 14 `covert-*` journeys were refreshed after the fix.
The updated full contact-sheet review covers 355 captures with zero geometry errors.
Screenshots are under `artifacts/ui/reference/gml-new-game-20261022/full-suite/` and
`artifacts/ui/reference/covert-progress-heading-20261022/`.

The roster is private to the controlled country. Switching
to a foreign country hides private cells and closes action forms before any foreign
roster is read. Supplementary OpenPower findings remain available in a separate
Intelligence window, also restricted to the controlled country.

UI-created missions set requires_execution_confirmation=True on
ActionStartCovertMission. Preparation reaches a persistent ready stage and emits
EventCovertMissionReady once. A current owner-only ready notice in Mail opens the
Covert Actions panel and selects the exact cell/mission, scrolling its source row
into view even at the end of a long roster. Stale requests report unavailable context
and never select a different cell. Notices disappear after execution, cancellation,
retirement or loss of the referenced cell. Existing automatic mission callers retain
the default False mode, preserving their prior behavior and old saved missions.

ActionExecuteCovertMission validates issuer, mission/cell ownership and ready stage,
communications, assignment location and target availability. It starts the existing
execution/resolution pipeline without charging preparation a second time. Duplicate
execution is rejected. ActionCancelCovertMission cancels preparation or readiness,
restoring the cell to active without a fabricated refund. Retirement cancels unresolved
missions. Native rejection feedback uses the normal CommandFeedback/Generic Message
queue. The client never changes authoritative cell or mission records.

Fresh evidence: 131 Python tests passed, 19 subtests passed and one opt-in performance
benchmark was skipped. Twelve native fixture journeys passed at 800x600, 1024x768,
1280x720 and 1920x1080 (48/48). All 72 captures in the four review directories were
visually inspected; geometry checks reported zero errors. These cover ready-mail
selection of the second cell, execute/cancel, stale snapshot, long roster scroll,
foreign-country privacy/form closure, supplementary intelligence, retirement,
server rejection and the existing create/train/prepare forms. These are native
ImGui fixtures plus separate authoritative system tests, not an Arcade/server live
world playtest. See artifacts/ui/reference/covert-ready and tests/ui/covert-ready-suite.json.

Current audit: 173 source edges, 122 tested literal routes, one alternative validation
and 50 remaining routes. Four further display contracts (39 total) and three action
contracts (10 total) have explicit verified OpenPower bindings. The runtime asset
contains 57 source window templates and three source row templates. Covert Actions
is partial: protection percentage, complexity, resource/unit targeting and framing
semantics were still pending at the time of this 2026-10-20 snapshot. Framing
semantics were implemented in the 2026-10-21 section above. Unknown values are not
substituted with estimates. Configured roster upkeep is explicitly not claimed to
equal actual state-dependent charges.

The main manifest now contains 157 journeys. The combined-suite.json index contains
142 passing reports and reuses older reports for unchanged routes; it is not a fresh
142-case run. Current reachable mapping is 18 verified, seven partial and 13 unknown;
the seven partial windows have 40 inbound evidence rows. Broader data and interaction
gaps remain in their respective CSV registries.

## Selected-group training confirmation (2026-10-20)

The source TrainUnits question is now connected from Unit_List_Window/btnTrain.
The selected owned group opens the same 267x130 source Generic Question canvas.
Yes dispatches one guarded ActionTrainUnit; No dispatches none. A changed unit,
owner, level, location, price, duration or unavailable quote invalidates acceptance.
MilitaryCapabilitySystem publishes unit_training_quotes for the next training level,
using the same nonmutating preflight as training acceptance. The client reads those
terms instead of calculating costs. Unavailable offers contain a reason and null
cost/duration; their Train control is disabled. Training commands optionally carry
expected cost, duration and starting level; changed terms are rejected before any
charge. Existing non-UI callers retain their reference command defaults.
Quote generation indexes designs, sites, battle participants and active orders once
rather than scanning the complete catalog for every unit. Server authority,
facilities, instructors, capacity, funds, battle and movement rules remain active.
This selected-group route covers one OpenPower unit at a time; source multi-unit
selection and other callers remain separate parity work.

Fresh verification: 183 Python tests passed, one opt-in performance test skipped,
and five parameterized subtests passed. After the final guard/tooltip adjustments,
38 focused regression tests passed. Four training journeys passed at each requested
viewport (16/16): Yes, No, changed estimate and unavailable facility. Eight existing
unit reorganization journeys passed again at 1280x720. All 20 training captures and
13 reorganization captures were visually reviewed; zero geometry errors occurred.
Together with the preceding party confirmation runs, this turn reviewed 57 captures
from 40 native fixture runs. None of these are a live Arcade/server world playtest.

Current graph: 173 source edges, 121 tested literal routes, one alternative validation
and 51 remaining routes. Generic Question still has five unconnected source callers.
The main manifest contains 148 journeys. artifacts/ui/reference/unit-training/combined-suite.json
indexes 133 passing reports, including refreshed reorganization evidence; other
reports are reused, not a fresh full-suite run. The broader data and interaction
contract gaps remain open as recorded in audit_summary.json and the CSV registries.

## Confirmed party constitutional transitions and Generic Question (2026-10-20)

Internal Laws now uses the source Generic_Question_Window (267x130) when a staged
party count requires a configured constitutional transition. Yes approves the
unchanged draft; Apply sends one ActionSetPartyEligibility containing both the
party changes and confirmed target form. No restores the previous party draft.
A changed government or party invalidates the request before dispatch. The server
validates the declared transition and final target limits, applies party eligibility
and government changes atomically, updates the election schedule, cancels dependent
scheduled elections/laws according to their existing rules, and records history.
Existing regime-change actions share the same transition mutation helper.

At that checkpoint, 154 Python tests passed. Four native fixture journeys passed at
800x600, 1024x768, 1280x720 and 1920x1080 (16/16): Yes, No, reverse transition and
changed-government rejection. All 24 captures were visually reviewed in the four
review/sheet-01.png files; geometry analysis found zero errors. These are native
ImGui fixture runs, not an Arcade/server live-world playtest. Evidence lives in
artifacts/ui/reference/party-constitution. The combined-suite.json index contains 129
passing reports, reusing 125 earlier reports; it is not a fresh 129-case run.
The current main navigation suite contains 189 journeys; its latest full result is
189/189 passed, with screenshot review recorded in `verification.md`. The extra
constitutional-capital close journeys verify both Apply dispatch and Discard with
no authoritative capital action.

The source scanner includes the verified GenericQuestion factory, which uses
CREATE_GUI_OBJECT rather than WindowSpawn. Eight previously omitted calls raised
the extracted graph from 165 to 173 edges. The current 189-journey run passes in
full. Its latest route audit reports 126 tested routes, 8 equivalent validations,
29 missing-workflow routes, and the remaining partial, callback, lifecycle, and
inactive-source rows shown in the live coverage counts below. The raw 153
WindowSpawn sites remain fully accounted for. There are 38 reachable windows;
Generic Question remains partial because some callers still lack an OpenPower
workflow. Runtime layout assets include 57 source window templates plus two row
types.

## Generic question caller contract (2026-10-28)

The source-sized dialog's `lblMessage` is now bound to the active
`GenericQuestionDialog._question.message`. Yes and No are explicitly mapped to
the caller-supplied accept and cancel callbacks; the shared dialog itself does
not dispatch a `GameAction`. The No path matches the source response behavior.
Yes remains partial because reference plays `ConfirmOrder` and OpenPower has no
equivalent sound event. The audit test keeps these shared contracts separate
from each caller's action, authority checks, and draft-retention behavior.

## Authoritative party eligibility batches (2026-10-20)

Internal Laws now stages non-ruling party eligibility in the source row combo and
includes it in Apply, Discard and close confirmation. ActionSetPartyEligibility
carries the inspected government form and one country-scoped change dictionary.
PoliticalLifecycleSystem validates the complete batch before updating any party:
actor/country authority, current form, configured editing permission, listed parties,
strict boolean values, ruling-party protection, crisis and minimum/maximum eligible
party counts. Accepted changes emit EventPoliticalPartyEligibilityChanged and a
command result; no-op requests do not duplicate change events. The batch runs before
an election due in the same lifecycle update. Other policy command types still have
independent server acceptance.

Published government_form_rules now contain party_policy_editable and eligible-party
count limits (maximum zero means unbounded). Built-in defaults allow editing, with
minimum two for multi-party democracy. Null permission distinguishes legacy saves:
known built-in forms receive default metadata, explicit scenario/mod denial stays
false, and unknown forms remain unavailable without configured authority. Client
preflight catches removed/changed parties and government forms before dispatch.
All three draft models are preflighted before any mixed Apply is sent. HUD warnings
use PanelRenderContext.on_notice so local validation and server errors share one
Generic Message queue; standalone panels retain their own fallback dialog.

Evidence: 137 political/draft/layout/determinism/snapshot Python regressions pass,
plus eight navigation-audit tests. Actual lifecycle tests prove atomic party swaps,
rejection without party mutation, same-update election ordering, no-op event behavior
and legacy metadata migration. Four native party journeys at the required viewport
sizes pass, plus stale-party and composed-HUD notice regressions (6/6). All 12 latest
captures were visually reviewed; warning text and row controls fit, zero geometry
errors. Native fixture runs do not constitute a live-world playtest. Artifacts:
artifacts/ui/reference/party-policy/suite.json and review/.

Constitutional transitions remain open: a batch crossing the configured count limit
is refused with an explanation; the source one-party/multi-party question and actual
regime-change intent are not yet implemented. No complete-window/source-callback
classification was advanced. Fifteen accumulated new journeys were added to the
main navigation manifest, bringing it to 140 entries; this is not a fresh full
140-journey run. Earlier audit totals retain their previous evidence scope.

## Internal Laws generated row geometry (2026-10-20)

The demographic and party lists now use their actual Item_Type,
lstInternalLawsGroups; civil laws use lstInternalLawsLawsItem. Two resolved row
assets are exported separately from windows (runtime window total stays 56).
Rows retain 328x16 bounds, source field rectangles/anchors, name and percentage
TextOffset, and middle vertical alignment. The shared placement session composes
each row at its child-list cursor with scrolling accounted for once. Status inputs
use 16-pixel height. Names fit their source slot with the full value on hover;
clicking the name opens existing OpenPower source provenance. No extra Source
column or table header consumes source row space. Tab width uses source 101 pixels.

The source percentage field ends two pixels inside the status rectangle; its -3
TextOffset is required to avoid actual glyph overlap. This was discovered through
screenshot inspection and is covered by a placement test. Python GML components
now support text offsets and middle alignment; window exports without this metadata
retain their previous behavior. Source skins, exact popup/button artwork and all
window-label metadata are not claimed as pixel-baseline parity.

Evidence: 76 focused Python tests pass, including exported-row/catalog equality,
all child rectangles/anchors and scrolled text placement. The panel journey passes
at four sizes; three additional 800x600 journeys cover twenty long-name groups with
scroll/edit/provenance, combined law/identity close-Apply and recognition warnings.
All seven native runs pass. All 14 latest checkpoint captures were visually
reviewed with zero geometry errors. Native fixture evidence only, not a live-world
playtest. Artifacts: artifacts/ui/reference/law-rows/suite.json and review/.

Remaining: authoritative party eligibility editing and constitutional questions,
migration status semantics, source popup/skin fidelity and broader window/data
coverage. No full-window or route classification was advanced.

## Deferred navigation close requests (2026-10-20)

PanelManager.toggle/set_visible(False) now call an optional request_close port on
visible panels instead of hiding them before their confirmation UI can render.
The panel remains visible until its render result completes closing; panels without
this port retain immediate visibility behavior. PanelCloseIntent composes the signal
into Budget, Resources, Advisor Settings and Internal Laws, reusing each panel's
existing Apply/Discard workflow. Repeated signals coalesce. Internal Laws keeps its
draft country while resolving the request and preserves stale drafts on refusal.

Evidence: 74 focused Python tests pass. They cover manager deferral/fallback/reopen,
actual Internal Laws navigation-close decisions with rendering ports mocked, and
signal composition in the other three panels. Existing Budget unit tests were
updated from a removed popup renderer to the current destination callbacks and
current source-sized slider ID; policy/action assertions remain covered.
Two native HUD Advisor journeys click the actual toggle again to request close,
then Apply/Discard; the stale Internal Laws title-close regression also runs.
All three scenarios pass at all four viewports (12/12). All 20 checkpoint captures
were visually reviewed with zero geometry errors. Native navigation proof covers
Advisor toggle; direct Budget/Resources manager hiding is not claimed as a native
input journey in this batch. No live-world playtest or full source-route completion
is implied. Artifacts: artifacts/ui/reference/navigation-close/all-sizes-suite.json.

Remaining: party editing/constitutional questions, exact generated rows, migration
status behavior and other dirty-capable windows still need their own complete
contracts. Navigation route totals remain unchanged.

## Shared civil-law and identity drafts (2026-10-20)

Internal Laws now stages language/religion statuses until Apply. Per-country drafts
survive tab/country selection; Discard and title-close confirmation cover both law
and identity changes. Aggregate Other groups remain read-only. The displayed combo
reflects the local draft without altering snapshot tables. Immediate dispatch remains
available only for standalone IdentityPolicyView consumers without a draft port.

The identity preflight checks current records, unchanged source statuses, authority
and a positive-share recognized alternative using the complete proposed final state.
Recognition expansions are ordered before restrictions so swapping the last recognized
group does not create an invalid intermediate server state. Both law and identity
preflight must pass before any action is sent. Server actions still accept/reject
independently; no atomic backend batch or source political-party semantics is claimed.
LawPolicyDraft exposes preparation separately from dispatch for this composition.

Evidence: 48 Python tests pass, including an actual IdentityPolicySystem acceptance
of the ordered recognition swap and stale identity blocking civil-law dispatch.
Four native scenarios pass at four viewports (16/16); a combined law/identity Apply
scenario also passes at 800x600. All 30 latest captures were visually reviewed with
zero geometry errors. These native fixtures prove UI/dispatch, not a live-world
playtest. Artifacts: artifacts/ui/reference/identity-draft/all-sizes-suite.json and review/.
Earlier identity journeys now explicitly assert zero dispatch before Apply.

Still open: party eligibility editing/constitutional confirmation, migration status
semantics, exact generated row geometry and panel-manager hide/dirty-close handling.
No complete-window classification or source-route total was advanced.

## Internal Laws title-close confirmation (2026-10-20)

Closing the title X with civil-law drafts now uses the existing source-sized
Save_Confirmation_Window. Apply preflights and dispatches the law drafts; Discard
clears them without commands. A clean close finishes directly. If Apply finds a
stale snapshot, the close is cancelled, the draft remains and Generic Message
explains the refusal. The shared confirmation preferences and Remember behavior
are reused. The pending draft's country is retained during the modal interaction.
This covers title-close; panel-manager hiding, source party/identity dirty drafts
and the full inherited source close contract still require further work.

Evidence: 44 focused Python tests pass, including close decisions and stale-draft
retention. Three complete HUD journeys (Apply, Discard, stale Apply followed by
recovery) pass at all four sizes: 12/12. All 20 checkpoint screenshots were visually
reviewed; confirmation text/buttons, warning and reopened panel fit, zero measured
geometry errors. Native HUD fixture proof only, not a live-world playtest. Initial
standalone attempts correctly closed their only panel but failed the harness's
final-visible-region invariant; the final journeys use the real composed HUD.
Artifacts: artifacts/ui/reference/law-close/all-sizes-suite.json and review/.
Navigation route counts remain unchanged because the complete inherited source
contract and other branches are not yet verified.

## Civil-law drafts and authoritative Apply (2026-10-20)

Civil-law rows now expose only the choices published in country_laws.allowed_values_json.
Unknown/malformed choices remain read-only. Selection creates a client-local per-country
draft; returning to its country restores it. Apply occupies frmTitle/btnApply and sends
existing ActionChangePoliticalLaw intents once, after validating the complete local batch
against current country, values, choices and pending transitions. A stale batch opens
Generic Message and sends nothing; Discard clears it. Client state tables are never changed.
The existing PoliticalLifecycleSystem retains authority over permissions, crisis, cost,
cooldown, scheduling and final effects. Each action is independent on the server; the
client's batch preflight is not a promise of atomic server acceptance.

Evidence: 41 focused Python tests pass, covering drafts, stale/foreign/no-choice cases,
no early partial dispatch and the existing authoritative law-transition tests. Four native
Apply journeys pass at all four viewports; the stale-snapshot journey passes at 800x600.
All nine checkpoint captures were visually reviewed with zero geometry errors. Native
fixtures prove dispatch/UI; they do not run the live world. Artifacts:
artifacts/ui/reference/law-policy/suite.json and review/.

Remaining: source dynamic row geometry, party eligibility editing/constitutional questions,
dirty-close confirmation and complete source Apply semantics (identity policies currently
send immediately). No complete-window or route classification was advanced.

## Internal Laws source section geometry (2026-10-20)

InternalLawsPanel now composes the 399x455 source canvas through named GML slots,
including the demographic list at (35,61,342,76), civil-law list at
(34,183,342,76), party list at (34,292,342,76) and migration fields at their source
positions. Lists scroll independently instead of pushing other sections down.
Source catalog anchors are applied by GMLLayoutSession. Religion/language tabs use
the tab-page strip; the language tab remains the initial OpenPower selection.
Identity source provenance opens in a separate OpenPower details frame, preserving
access without expanding the 76-pixel list. Source dynamic row templates and tab
button skin/precise generated geometry are not yet fully ported.

Migration rates display existing OpenPower entry_rate/exit_rate. The two status
slots navigate to the real migration editor rather than pretending its richer
policy is two source boolean statuses; that behavioral difference remains open.
Civil laws and political parties remain read-only summaries in this panel; their
source editing, constitutional confirmation and Apply/dirty semantics remain gaps.
No route count or complete-window classification was advanced for these changes.

Evidence: 22 Python tests pass. The existing identity scenario with two added panel
captures passes at all four viewports (4/4); warning regression passes at 800x600.
All eight full-panel checkpoint captures were visually reviewed: no overlapping
sections, clipped migration buttons or geometry errors observed. Test fixture scope
only; no Arcade/live-server world playtest in this batch. Artifacts:
artifacts/ui/reference/internal-laws-layout/all-sizes-suite.json and review/.

## Internal-laws identity warning (2026-10-20, partial source callback)

The language/religion branch of Internal_Laws_Window::OnCustomEvent now opens
Generic Message before dispatch when the proposed restriction would leave no other
positive-share legally recognized group. The combo remains snapshot-backed and
therefore retains its old value on refusal. This mirrors the existing OpenPower
server invariant, which also covers Restricted, while the supplied C++ warning
checks Illegal. No client state mutation or substitute authoritative policy added.
The political-party branch, source constitution questions and complete GML panel
composition remain open; the source callback is not marked fully verified and the
navigation total remains 118 tested, one alternative validation, 46 remaining.

Evidence: 14 identity/trade Python tests pass, including both client refusal and
independent authoritative rejection without changing group data. The new native
journey passes at 800x600, 1024x768, 1280x720 and 1920x1080; the existing identity
policy journey still passes. All eight new dialog captures were visually reviewed:
warning text and OK fit, zero geometry errors. These are native fixtures, not a live
world playtest. Artifacts: artifacts/ui/reference/identity-last-recognized/.

## Neutral-territory movement confirmation (previous batch)

Current navigation counts: **118 tested, one alternative validation, 46 remaining**
(29 missing workflows, 12 unwired callbacks, four different workflows and one shared
contract). No route is now classified as missing UI; this does not complete the
window inventory: 35 candidate mappings remain missing and 17 remain partial.

Unit_Attack_Confirm_Window uses the source 225x144 canvas, positions and anchors.
Movement requests accumulate per destination military controller. No discards only
that country's queue; Yes consumes each intent once and rechecks the latest units,
controller and access. Newly granted access uses ordinary movement. Stale selections
show Generic Message without dispatch. ActionInvadeTerritory performs authoritative
ownership, controller, access, domain and route checks before declaring war and
passing authorized movement to the existing military pipeline in the same tick.
The existing diplomacy war behavior is reused. This does not close the explicit
attack/context-menu workflow gaps. The separate ShowMovementRefused callback was
connected and scenario-verified in the movement-refusal section above.

Evidence: 140 Python tests and three subtests passed; three tests skipped. A real
Engine.step test verifies diplomacy/military phase ordering and snapshot replay with
no-op ports for other dependencies. Four native journeys passed at four viewports
(16/16), plus six regression journeys (6/6). All 36 invasion and 14 regression
captures were visually reviewed; measured geometry errors are zero. The fixture
uses production selection/coordinator/UI through deterministic request buttons,
not physical Arcade drag or a live-server world playtest. The combined index has
125 passing journeys and reuses earlier unchanged evidence, not 125 fresh runs.

Runtime templates: 56. Display contracts: 35 verified OpenPower, 277 C++-only,
988 unknown. Interaction contracts: seven verified OpenPower, 184 C++-only,
718 unknown. Artifacts: artifacts/ui/reference/unit-invasion/combined-suite.json,
review-all/, review-regressions/ and visual-review.json. Reproduce with
 tests/ui/reference-unit-invasion-suite.json.

## Map-attached unit and region information (previous batch)

Implemented the actual map callers of two initialized source frames, rather than
substituting the existing unit-details or country panels. Current navigation counts:
**117 tested, one alternative validation, 47 remaining** (29 workflows, 12 callbacks,
four different workflows, one shared contract, one missing-UI route). The remaining
missing-UI route is Unit_Attack_Confirm_Window; implementing its neutral-border
caller requires an authoritative invasion/war intent, because ActionMoveUnit alone
does not declare war. This was inspected, not implemented in this batch.

- Small_Unit_Info_Window retains its 86x51 source positions and follows the sole
  selected projected group, eight pixels to its right. Dragging, multiple selection,
  lost visibility and removed/dead records suppress it. Own infantry quantities are
  personnel; other categories show equipment_quantity, not a fabricated strength
  substitute. Category proportions reflect one OpenPower logical group. Foreign or
  unknown-role quantities remain question marks; source noisy intelligence for an
  individual foreign group remains a partial data contract.
- Sphere_Control_Window retains its 145x56 minimum, source country/flag rows and
  dynamic width adjustment for the longest name. Holding Tab above a valid map hit
  shows political owner and military controller separately. It tracks the cursor
  with the source (+16,-16) offset, clamps to the viewport and hides on release,
  ocean, UI coverage or text input. Missing controller uses the same owner fallback
  as the current OpenPower political map. Existing OpenPower flag assets are used.
- GameView renders both composed frames. WindowManager now supports explicit
  source dynamic sizes and continuously tracked positions; instance-only component
  resize leaves the shared source catalog immutable. The control frame uses the
  tooltip display layer without input/focus. Screenshot review caught its initial
  occlusion behind the fixture's map surface despite passing telemetry assertions;
  the corrected layer was rerun and visually reviewed at all four sizes.
- Removed a client import of modules.base from battle category presentation. Passive
  role aliases/domains live in shared metadata; gameplay profiles remain in the module.
  A parity test covers every known role and alias. Selected-row lookup filters the
  snapshot instead of copying the complete army each rendered frame.
- Added seven explicit display contracts, bringing verified OpenPower data bindings
  to 31/1300 (278 C++-only and 991 unknown remain). Source foreign per-group intelligence
  is retained as a gap. Supported runtime templates: 55.

Evidence: 69 focused Python tests and two subtests pass. Two native map journeys pass
at all four required viewport sizes (8/8), plus four battle regressions (4/4).
Reviewed all 20 latest map captures and nine battle captures; measured geometry errors
are zero. The 121-journey combined index reuses earlier unchanged route evidence; it
is not a fresh 121-case run. map-information uses deterministic projected hit targets
and the production selection controller/UI, plus real held-Tab input. GameView's
projected-selection, UI-capture guard and map-coordinate routing are separately unit
tested. This batch does not claim an Arcade/live-server world playtest.

Artifacts: artifacts/ui/reference/map-information/combined-suite.json,
all-sizes-suite.json, review-all/, review-battle/ and visual-review.json.
Reproduce with tests/ui/reference-map-information-suite.json.

## Battle inspection and published observer totals (previous batch)

Three more source routes are implemented and verified: DisplayCombatInfo (participant),
DisplayCombatInfoSmall (observer), and HandleCombatOver for the inspected battle.
Current navigation counts: **115 tested, one alternative validation, 49 remaining**
(29 workflows, 12 callbacks, four different workflows, one shared contract, three
missing-UI routes). These are navigation counts, not a count of all data/layout gaps.

- Map battle-label selection retains exact battle identity, including displaced labels
  at shared anchors. Participants open Battle_Window (1024x768); observers open
  Battle_Info_Window (225x203). A shared entry is used by GameView and the native
  fixture surface. Country flags use existing OpenPower assets.
- Full inspection exposes recorded force groups, finite geographic coordinates,
  owner-only type orders, global strategy and retreat through ActionSetBattleStrategy.
  The server revalidates commands. The reference dynamic unit-detail scene and all its
  information contracts remain partial; the native cards are not complete source parity.
- Matching results wait for the final snapshot, preserve presentation after battle-row
  removal, and open an inspector-owned summary. Historic/other-battle results are ignored.
  CombatSystem now derives event participants from each concluded battle rather than
  the final iteration's local_units. Summary category losses remain unavailable.
- CombatSystem publishes battle_public_counts with category group totals only, without
  unit identities. All eight observer fields bind these values. Missing, stale,
  incomplete, duplicated or invalid totals show a dash. I/G/A/N count logical OpenPower
  groups; they do not imply source equipment-quantity equivalence. The observer never
  reconstructs private foreign rosters. Dynamic source country-list styling remains
  a separate review item.
- Corrected Begin-only window-padding stack scope. Source-sized canvases pan on both
  axes below source dimensions; offscreen content in 800x600 captures is deliberate.
  The native test host's borderless close overlay is disabled because it intercepted
  the source close button at exactly 1024x768. This is a harness-only correction.
- Screenshot review found a clipped schema diagnostic in resource market availability.
  Its player-facing fallback is now a concise wrapped availability message.

Evidence: 87 focused Python tests plus two subtests pass. A fresh full main regression
passed 118/118 journeys at 1280x720. Four battle journeys were subsequently refreshed
at all four viewport sizes (16/16); the additional published-count journey makes the
current combined index 119 passing journeys. Resource availability is checked separately
at all four sizes. Reviewed 183 full-regression captures and 36 latest battle captures;
plus eight resource-availability captures; none has measured geometry errors. See
visual-review.json for retained findings. This does not establish pixel or semantic parity:
source unit-design/production/research/covert layout contracts and unavailable values
remain explicit gaps. The supported runtime catalog contains 53 source templates.

Evidence lives under artifacts/ui/reference/battle-inspection/: combined-suite.json,
full-regression/, flags-*/suite.json, review-full/, review-flags-main/ and
review-flags-boundaries/. Reproduce battle scenarios with
 tests/ui/reference-battle-inspection-suite.json. The actual native renderer and UI run with
deterministic snapshots and a recording client; this is not an Arcade live-world/server
playtest. Server policy and snapshot transport have separate Python tests.

## Treaty lifecycle and refusal reports (previous batch)

Four additional source sites now have passing context-specific scenarios: stale
selection in Update, accepted/removed notification in OnSubjectChange, incoming
refusal mail and that mail's detailed report callback. Current counts: **112 tested,
one alternative validation, 52 remaining** (29 workflows, 13 callbacks, four
different workflows, one shared contract, five missing-UI routes).

- TreatyDetailLifecycle observes the inspected record once and ignores historic
  activations. Generic Message acknowledgement closes only the inspection that
  raised it; a later selection is protected. Removed/inactive records lose editing
  controls, and an open participant draft is discarded without dispatch.
- EventTreatyLifecycleChanged now carries optional proposal_id, because accepted
  proposals become agreements with different IDs. The server fills it; snapshot
  round trips preserve it. The UI never infers acceptance from matching names.
- EventTreatyRefused retains sponsor, title, prior acceptances and recorded reason
  after proposal deletion. Sponsor-only mail opens TextNotificationDialog using
  Region_Control_Change_Window's 358x248 GML frame, clipped body and OK slot. Missing
  historic audience data is not guessed; absent reasons remain explicitly unknown.
  Other region/advisor callers of that shared frame remain separate gaps.
- server_snapshot fixture delivery replaces named tables and appends journal
  records in one scenario step. The navigation audit matches its exact fixture,
  and geometry evidence now prefers the visible destination checkpoint over a
  final frame where the scenario has already closed that destination.

Fresh evidence: 69 focused Python tests; four journeys at four viewport sizes and
four regression journeys at 1280x720 (20 UI runs). Reviewed 32 scenario and eight
regression destination captures; no measured geometry errors. The runtime catalog
supports 51 source templates. The 115-journey combined index retains older evidence
for unchanged routes; it is not 115 fresh runs. Native fixtures and server policy/
snapshot tests are distinct from a live-world server playtest.

Artifacts: artifacts/ui/reference/treaty-lifecycle/, including combined-suite.json,
all-sizes-suite.json, review/ and review-regressions/. Reproduce with
 tests/ui/reference-treaty-lifecycle-suite.json and reference-treaty-validation-regressions.json.

## Treaty proposal validation (previous batch)

The anarchy sponsorship guard and duplicate-name warning now reproduce two more
caller-specific Generic Message paths. Current navigation counts: **108 tested,
one alternative validation, 56 remaining** (30 workflows, 16 callbacks, four
different workflows, one shared contract, five missing-UI routes).

The reusable base proposal policy checks actual government data and reserves names
against active and pending treaties. Both the Python UI and DiplomacySystem use it;
the server rechecks between actions in one tick and records a rejection for direct
or stale clients. Missing government data does not imply anarchy. Acknowledgement
retains the list or draft; changing the duplicate name allows one new proposal.
The panel context now supplies an optional notice callback from GameLayout.

Fresh validation evidence: two new journeys at four viewport sizes plus four
regression journeys at 1280x720 (12 runs). All 20 destination captures were reviewed
on four contact sheets; zero measured geometry errors. The combined focused Python
run for this and the preceding result/dispatch batch passes 57 tests. Together
these two batches add six verified source routes and 24 fresh UI runs. The
111-journey combined index retains older reports for unchanged routes.

Artifacts: artifacts/ui/reference/treaty-validation/, with combined-suite.json, review/,
review-regressions/ and all-sizes-suite.json. Reproduce with
 tests/ui/reference-treaty-validation-suite.json and reference-treaty-validation-regressions.json.

## Covert outcomes and incoming dispatches (previous batch)

Four further source sites are verified: own and discovered incoming mission
results, authoritative trade mail delivery, and authoritative combat-result mail
delivery. Current source navigation counts: **106 tested, one alternative
validation, 58 remaining** (30 workflows, 18 callbacks, four different workflows,
one shared contract, five missing-UI routes).

- Covert_Actions_Mission_Outcome (451x252) and its attacked variant (401x105)
  use source GML slots and anchors. Exact mission IDs flow from mail to the view.
  Target discovery and attribution rules mask covert identities; incident summaries
  are joined only for the viewer's audience. Source complexity, framed-country and
  resource/unit details lack matching state fields and remain explicitly unavailable.
- Incoming combat and trade domain events add contextual mail without reopening
  the mailbox or forcing a combat summary over gameplay. Clicking the delivered
  combat mail opens that result. A fresh selected-combat overview must still attach
  and reveal its own summary after its final update; that source branch stays open.
- The test runner supports explicit server_event delivery into a recording-client
  fixture. Scenarios assert the exact new dispatch and exclude foreign combat and
  undiscovered covert operations. This is simulated event delivery, not live server
  execution or proof of unread badges and persisted acknowledgement.

Fresh evidence: 39 Python tests; six journeys at 1280x720 and the two new journeys
at 800x600, 1024x768 and 1920x1080 (12 runs). All 23 captured destinations were
visually reviewed; zero measured geometry errors. A root scrollbar covering the
attacked window's close button was removed; only bounded result slots scroll.
The runtime catalog now supports 50 source templates. The combined 109-journey
index retains prior evidence for unchanged routes and is not 109 fresh runs.
Artifacts: artifacts/ui/reference/event-results/, including review-main/,
review-boundaries/ and combined-suite.json. Reproduce with
 tests/ui/reference-event-results-suite.json and reference-event-results-boundaries.json.

## Unit split/merge implementation (previous batch)

Five additional source paths now pass: military context to Split_Group_Window,
both group transfer directions to Unit_Split_Window, legacy unit-list split to
quantity, and legacy unit-list close. Current navigation counts: **102 tested,
one alternative validation, 62 remaining** (30 workflows, 20 callbacks, four
different workflows, one shared contract, seven missing-UI routes).

- New shared commands ActionSplitUnit and ActionMergeUnits are handled by the
  authoritative MilitarySystem through the composed UnitReorganization policy.
  It validates ownership, availability, combat/contact, pending orders, training,
  market listings, compatible traits and exact colocation before changing units.
- Splitting conserves personnel, integer equipment, purchase cost and unit
  provenance. Child IDs use persisted DeterministicRuntime allocation and are
  not reused after merging. Merging preserves totals and weights combat factors
  and cohesion by personnel. Rejected operations do not mutate unit records.
- GML-sized Split_Group_Window (631x347), Unit_Split_Window (289x66), and the
  legacy Unit_List_Window (343x492) are connected to actual selected unit IDs.
  Group edits stay local until apply; cancel dispatches nothing. The legacy
  quantity window accepts its transfer on close, matching its caller callback.
- Unit-list and unit-context Split/Merge now work. The legacy group view also
  dispatches existing training and used-market list/withdraw commands. Foreign
  exact force data is not exposed through that view without an authorized
  observation; its data mapping remains partial.
- Two reusable renderer fixes are covered by regression tests: unclosable
  windows pass p_open=None rather than False to ImGui, and explicit dynamic
  enabled state can override GML initial state without changing the catalog.

Fresh checks: 80 Python tests plus three subtests; 28 UI runs (eight at 1280x720,
eight at 800x600, six each at 1024x768 and 1920x1080). Reviewed 12 main and 30
boundary captures; zero geometry errors. Server tests execute MilitarySystem's
update and check snapshot round trips, conservation, deterministic IDs and
rejections. UI recordings verify exact command payloads; these fixtures remain
separate from an actual live-world playtest.

Artifacts: `artifacts/ui/reference/unit-reorganization/`, with `combined-suite.json`
retaining earlier evidence for unchanged routes. The current full manifest has
107 journeys; this batch reruns eight of them rather than claiming 107 fresh runs.
Reproduce using `tests/ui/reference-unit-reorganization-suite.json` and
`tests/ui/reference-unit-reorganization-boundaries.json`.

## Active goal: close every remaining gap

The user explicitly set this goal on 2026-10-19. It remains active.
The latest audit covers 176 source navigation edges: 71 exact GML widget paths
and 105 handler-only C++ paths. Its journey coverage records 135 tested routes,
8 equivalent validations, 7 equivalent guided-tutorial routes, 2 alternate
feedback routes, 1 shared-component contract, 3 lifecycle initializations, 1
inactive source branch, and 1 unreachable branch. Eighteen routes remain
blocked by missing workflows, chiefly RGAPI multiplayer/server discovery and
the source advisor-event queue. Twenty reachable-window action contracts remain
partial where OpenPower lacks authoritative data, source assets/localization,
exact formulas, or a multiplayer backend. A destination opening alone does not
close any of these routes.

Five new Python windows use their source GML dimensions, slots and anchors.
Native title bars are suppressed for the three source frames without chrome;
otherwise the title bar overlapped the small map-target prompt. Source data is
adapted to OpenPower weapon systems and per-system launch orders. Inventory,
research, target ownership, range, authorization, selected payload and aggregate
launch funding are rechecked from the latest snapshot before dispatch. Preparing
or aborting sends no action. Existing direct-strike buttons now prepare a plan.

The source per-missile representation and casualty/damage estimates are not
invented: the Python surfaces show actual OpenPower systems and explicitly
unavailable estimates. These window data mappings remain partial, although their
listed navigation routes are tested. The active goal also retains these limits.

Evidence: `tests/ui/journeys/reference-strategic-planner.json` (39 steps after the
additional missile-cancel assertion), four viewport runs, 40 reviewed destination
captures, and 42 focused strategic/persistence/navigation/layout tests.
Artifacts: `artifacts/ui/reference/strategic-planner/`. The combined 101-journey index
retains prior reports for routes not rerun in this batch.

## Gap fixes verified on 2026-10-19

Six previously unbound source routes now have passing source-context scenarios:
F3 to Save_Game_Window, F4 to Load_Saved_Game, manual save result to
Generic_Message_Window, and mail callbacks to the selected treaty, trade deal,
and Battle_Summary_Window. The current source-route count is 85 tested, one
alternative validation, and 79 remaining gaps (35 missing workflows, 19 missing
UI, 20 unwired callbacks, four different workflows, one shared-base contract).

- Save/load selectors use their GML dimensions and anchors. Save submits the
  chosen slot through ActionSaveGame; loading delegates to the existing
  NavigationService/LoadGameTask. Read-only slot discovery includes date,
  country and game time. Long names are clipped with full-name tooltips.
- CommandFeedback consumes new local authoritative refusals/failures and final
  save outcomes. It skips initial journal history and other players' results.
  Ordinary executed transport records are not misreported as domain success.
- Generic messages queue separate acknowledgement callbacks. A callback can
  open another notice without overwriting the next queued result. Long bodies
  scroll inside the source text slot, preserving the fixed OK button.
- Mail derives actionable entries from persisted treaty, trade and combat
  events. Selecting one transfers its actual record ID. Battle summaries use
  the server's SIDE_A/SIDE_B values, aggregate losses and region; absent
  per-category losses and country breakdowns are explicitly unavailable.
- Visual review also found and fixed the unit-design cost label overlapping
  the first digits of its input.

Fresh evidence: 19/19 regression journeys at 1280x720; 9/9 additional new-route
runs across 800x600, 1024x768 and 1920x1080; 64 focused Python tests. Reviewed
25 regression captures and 21 boundary captures. These are deterministic UI
runs, not a live-world server playtest. The combined 100/100 journey index keeps
81 earlier reports and 19 reports rerun for these changes; it is not 100 fresh
runs on this revision.

Artifacts: `artifacts/ui/reference/gap-fixes/1280x720/suite.json`,
`artifacts/ui/reference/gap-fixes/boundary-suite.json`,
`artifacts/ui/reference/gap-fixes/combined-suite.json`, and the `review/` and
`boundary-review/` folders. Reproduce with `tests/ui/reference-gap-fixes-suite.json`
and `tests/ui/reference-gap-fixes-boundaries.json` using `utils.run_ui_journeys`.

## Scope and evidence

All 173 extracted reference navigation call sites have either a scenario binding or a
specific remaining gap. The reviewed additions live in
`navigation_route_bindings.json`: source file, line, excerpt, effective destination,
Python control, scenario, and explanation. This does not establish equivalence of
every display field, dynamically created widget, or server outcome.

The source graph records spawn calls. In 19 map diplomacy branches,
`TreatiesWindowSpawn` initializes the surfaces, then `QuickTreatyWindow` shows the
details/proposal window. These entries retain their extracted spawn target and
also record `effective_target_window=Treaty_Details_Window`; their Python destination
is `NEW_TREATY`, not the treaty list. Source sites sharing one handler are matched
by file, line, and destination rather than one handler-wide guess.

## Previous verification baseline (2026-10-17)

- 97/97 main journeys at 1280x720; 27/27 additional boundary runs at 800x600,
  1024x768, and 1920x1080; 46 focused Python tests pass.
- 79 of 165 extracted routes are tested literally, one has tested alternative
  validation, and 85 remain explicit gaps: 35 missing workflows, 20 missing UI
  routes, 23 unwired callbacks, six different workflows, and one shared-base
  save contract. Scenario success does not mean all 165 routes are implemented.
- 136 main-suite captures and 36 boundary captures were visually reviewed through
  contact sheets. No geometry errors were found in these selected snapshots.
- The desktop initially reduced 1920x1080 windows to 1920x1020. The harness now
  records the actual drawable size, fails a size mismatch, and reapplies the client
  size after borderless creation. The corrected 1920x1080 suite was rerun; all 124
  final screenshots match their declared viewport sizes.

Artifacts: `artifacts/ui/reference/navigation-final/suite.json`,
`artifacts/ui/reference/navigation-boundaries/`, `artifacts/ui/reference/navigation-final-review/`,
and `artifacts/ui/reference/navigation-boundary-review/`.

## Connected routes

- L/D/U/C/W/B/R/T open and close their corresponding Python panels. Closing uses
  the title-bar close path so Budget and Resources can ask about unsaved changes.
  Text entry, modifiers, and open popups suppress these letter shortcuts.
- Map context → Diplomacy prepares all 19 source treaty variants, including the
  two inverted requests. Scenarios verify counterpart, treaty type, and both sides
  of `ActionCreateTreaty`. Draft participant sides match the dispatched sides.
- F5 and F9 toggle Objectives and Console. The latter is OpenPower's diagnostic
  console; reference console commands are not implemented by this route.
- Advisor Settings closes through its shared Apply/Discard confirmation.
- The consolidated strategic panel has a tested close control. This does not
  supply reference's separate strategic target/prepare/abort dialog chain.
- Empty covert-cell names disable submission and dispatch no action. This is
  reported as alternative validation, not a literal Generic Message transition.

## Screenshot findings and fixes

| Finding | Fix |
|---|---|
| Apply/Discard buttons were below a 221×95 confirmation popup. | Explicit source slots for text, Remember, Apply, and Discard; compact GML style. |
| Text from underlying windows showed through front panels and dialogs. | Opaque window and popup backgrounds with the existing colors. |
| Country and war-list title bars exposed native `##` ID suffixes. | Custom title rendering hides native ID suffixes. |
| A fixed participant button moved the proposal editor's flow cursor over existing rows. | Editable proposal content stays in the source inner frame with scrolling. |
| Training, mission, and participant-button labels were cut off. | Short labels fitting their source buttons. |
| Full country names plus relation-unit text exceeded the small relation title slot. | Compact country tags and value; full explanation in a tooltip. |
| Unit actions looked actionable without callbacks. | Split/Merge now dispatch authoritative actions; movement destination selection remains a separate gap. |
| Keyboard-count combo selection chose the wrong option or missed clipped options. | Native option selection with explicit scrolling for long lists. |
| Context-menu smoke tests lost their popup when the test engine started. | The fixture opens its popup after test startup; real UI code is shared. |

## Reproduction

```powershell
.\.venv\Scripts\python.exe utils/run_ui_journeys.py tests/ui/reference-navigation-suite.json --output artifacts/ui/reference/navigation-final
.\.venv\Scripts\python.exe -m utils.review_ui_screenshots artifacts/ui/reference/navigation-final/suite.json --output artifacts/ui/reference/navigation-final-review
.\.venv\Scripts\python.exe utils/reference_ui_audit.py --journey-suite artifacts/ui/reference/navigation-final/suite.json
```

Repeat `reference-navigation-boundaries.json` at 800×600, 1024×768, and 1920×1080 with
`--width` and `--height`. Each visible region assertion saves its screenshot and
telemetry before later steps can close the destination. Intermediate geometry
errors fail the run. Contact sheets are an aid to visual review, not an automated
proof that every glyph, label, or untested game state is correct.

## Remaining work

Gap statuses distinguish missing UI, missing workflows, unwired callbacks,
different save/setup flows, and the generic base-window dirty-close contract.
Networking/RGAPI, scripted tutorials, remaining combat-detail contracts, remaining source-only
strategic/covert data fields, and remaining caller-specific feedback are explicit gaps. The mail combat summary and manual-save result routes are now connected. A successful manual opening of an existing destination is never
counted as verification of an absent automatic callback.

These scenarios use deterministic Python fixtures and a recording client. They
verify rendering, navigation, input guards, and dispatched intent; authoritative
server outcomes and a live-world playtest are separate evidence.

## Map occupation confirmation (2026-10-21)

The map context menu exposes Occupy Territory for a selected own unit group targeting a foreign region. It continues through UnitMoveOrders and the existing Unit Attack Confirmation, then dispatches server-validated ActionInvadeTerritory. This keeps OpenPower military entry and combat rules authoritative; it does not directly change regional control like reference GOneClickInvade. The 7-step route passes at 1280x720 with zero geometry findings and no render errors. Reviewed screenshots show the context menu and the declaration-of-war confirmation.

## History_Window GML reconstruction (earlier 2026-10-22 geometry pass)

The previous `HistoryPanel` inherited only the source 530×311 size while keeping
its 740×650 analytical flow layout. That put controls and graph content outside
the GML slots. It now uses the source frame and places the 256×16 indicator
combo, four 7×7 range toggles and their labels, 405×166 chart, vertical min/max
labels, and six horizontal time ticks at their exported `History_Window`
rectangles. Source C++ hides the title lock, Apply control, and all range
controls and labels during initialization. Python keeps the title draggable,
omits the lock, and retains the four GML range slots as an OpenPower-specific
time filter. The analytics popup also remains an OpenPower addition in the
source-sized Apply slot. The window opens at its prior upper-right default
position (x=750,y=90 at 1280×720; x=270,y=90 at 800×600).

The chart reads `history_indicator_definitions` and `history_snapshots` through
`HistoryQueryService`. Missing snapshots remain gaps in the line; an empty range
shows an explicit message. The four OpenPower ranges match the GML slots: 1
month, 6 months, 1 year, and 2 years. OpenPower-specific subject comparison, ranking,
event timelines, granularity, step trends, and CSV actions are available from a
supplemental analytics popup. The initial Population choice maps to
`country.population` when the definition is available and otherwise falls back
to the first enabled indicator. At this earlier geometry pass, the source
indicator crosswalk was still open; the later data and label work is recorded
in the Current continuation at the top of this document.

Evidence: the updated `reference-main-bar-history` journey passes 23/23 steps at
800×600, 1024×768, 1280×720, and 1920×1080. It checks the source Population
default and 40m–43m axis, selects GDP and verifies 80–151 plus the visible
missing-sample gap, changes the OpenPower range, opens analytics, and confirms
the source-hidden lock stays absent. The 16 reviewed captures have zero
geometry errors. The six focused History panel tests pass. Screenshots and
contact sheets are under `artifacts/ui/reference/history-final-20261022/`.

## History event marker tooltip (2026-11-01)

The chart now places 7x7 markers for persisted OpenPower `history_events` on
the selected range's time axis. Nearby events merge within the source 8 px
threshold. Hover opens the `History_Tooltip_Window` GML template (250x100 base)
with the event title, game minute, and optional causal source. The runtime frame
fits measured text plus 8 px; its `txtText` field keeps the source 4 px inset
and all-side anchors. The tooltip uses the source 16 px marker offset, flips
above a marker near the parent's lower edge, and clamps to the right edge of
the History window. Chart samples now use their game-minute positions on the
same range axis.

The populated history journey passes 57/57 steps at 800x600 and 1280x720 with
zero layout findings and no render errors. Both reviewed tooltip screenshots
show the marker and text inside the History panel; the lower-edge case flips
above the marker and clamps at the parent's right edge. Reports and captures
are under `artifacts/ui/reference/history-event-tooltip-gml-800x600-20261101/` and
`artifacts/ui/reference/history-event-tooltip-gml-1280x720-20261101/`. reference-specific
marker type/value labels and localization remain unavailable; OpenPower event
records remain the tooltip's only data source.

## Trade_Detailed_Window GML reconstruction (2026-10-21)

The previous Python trade form kept a 760×640 flow design inside the
648×423 source frame. Most editors and summaries therefore landed below or
outside their corresponding source slots. The panel now opens centered at the
source size and binds the title lock/page/close controls, both country columns,
cash spinners, region and research selectors, asset lists, balance indicators,
expiry editor, and proposal/clear actions to their exported GML rectangles.
The shared GML binding layer now recognizes the catalog's `input` kind for
numeric edit controls; without that mapping, numeric fields silently reverted
to normal flow layout.

OpenPower remains authoritative for trade content. Cash, owned regions and
transferable research levels stay in a local draft until submit; the trade
system revalidates terms server-side. The Units page retains the source field
slots as disabled controls because OpenPower has no military-unit trade action.
The balance meter shows only the cash contribution ratio and explicitly leaves
territory/research unpriced. The title action switches to OpenPower's
multi-deal offers/history view.

Evidence: `bilateral-trade.json` passes all 29 steps at 1280×720 and 800×600,
with zero geometry findings and no render errors. The initial-layout journey
passes at both sizes, the economy-to-trade route passes 4/4 at 1280×720, and the Units-page journey passes 2/2 with unsupported source controls disabled.
Focused GML-binding and bilateral-trade tests pass 24/24. Screenshots reviewed:
`artifacts/ui/reference/trade-gml-reconstruction/proposal-review-1280x720/actual.png`,
`artifacts/ui/reference/trade-gml-reconstruction/workflow-revised-1280x720/actual.png`, and
`artifacts/ui/reference/trade-gml-reconstruction/workflow-revised-800x600/actual.png`, and
`artifacts/ui/reference/trade-gml-reconstruction/units-unavailable-1280x720/actual.png`.

The Units-page screenshot confirms the unavailable controls stay within their source slots. Remaining gaps are the reference unit-transfer page's authoritative action/data contract and the source trade-evaluation/price semantics, which OpenPower does not expose.

## Unit List disband action (2026-10-22)

The GML-positioned `DISBAND` button now sends one `ActionDisbandUnits` with the
selected own unit IDs. The military system rejects stale or duplicate IDs,
foreign ownership, zero-strength units, combat/readiness/training/movement
activity, and active deployment, order, or market references. Successful
requests remove the selected unit rows and release their strength from each
owner's `military_count`; completed deployment history remains delivered.
reference dispatches the request immediately, so the Python panel also clears the
local selection after sending it.

The 47-step `reference-unit-list-operations` journey verifies the button becomes
enabled after selection, captures the selected-row state, checks the exact
action payload, confirms selection clearing disables the button again, and
checks that declining TRAIN keeps the selection available for another attempt.
It also checks the own-unit annual OpenPower upkeep estimate and ascending and
descending upkeep sorting. The estimate allocates the existing country
military-budget formula; reference government, training, and sale modifiers are not
claimed as reproduced. The journey passes at 800×600, 1024×768, 1280×720, and
1920×1080. Together with the budget and panel tests, the focused test set
passes 47/47.
The authoritative unit reorganization tests pass 38/38, including multi-unit
batches, foreign/stale requests, busy units, active deployment, and preserved
completed deployment history. The refreshed full navigation suite passes
196/196 journeys with 181 action assertions. Screenshot review covers 350
captures with zero geometry errors; the selected-button capture is
`artifacts/ui/reference/navigation-gap-closure-20261022-continued/full/reference-unit-list-operations/checkpoints/026.png`.

The Unit List window remains partial because the exact reference upkeep modifiers
and training/sale marker assets are still unavailable.

## Unit List TRAIN confirmation lifecycle (2026-10-24)

TRAIN now keeps the selected unit IDs while its Yes/No question is open. If the
player chooses No, the question closes without dispatching an action and the
same selection remains available. Choosing Yes revalidates every published
quote and unit signature before dispatching the per-unit authoritative actions;
TRAIN and SELL stay disabled for that selection until a row click recalculates
eligibility, matching the source's post-confirmation button lock.

The reusable `reference-unit-training-confirmation-suite` covers the Unit List route
and the Yes, No, and stale-quote confirmation cases. All four journeys pass at
800×600, 1024×768, 1280×720, and 1920×1080: 16/16 runs and zero layout errors.
Each viewport still reports three warning-level overlaps: the Type and Name
sort hitboxes overlap their arrow hitboxes, and adjacent source rows overlap by
one pixel. No control is clipped after the narrow-viewport fit.
The Unit List frame scales horizontally only when the viewport is narrower
than its 835 px source width; this keeps the scrollbar inside an 800×600
viewport while preserving the reference GML dimensions on wider screens. The
focused confirmation and reorganization tests pass 48/48, and the GML layout
binding tests bring the targeted total to 59/59. Screenshots were reviewed at
800×600 and 1280×720 after Yes; both show the selection retained with TRAIN and
SELL disabled. The 800×600 capture also confirms the scrollbar stays inside
the frame. Evidence is under
`artifacts/ui/reference/unit-training-confirmation-20261024-r6/`.

The interaction remains partial because OpenPower sends one authoritative
action per unit while reference uses its client-side `TrainUnits` batch event.

## Increase Production action and estimate (2026-10-27)

The five GML toggles remain independently selectable, start clear, and reset
when the dialog opens. Apply now chooses the highest selected percentage,
submits `ActionIncreaseResourceProduction`, and closes after dispatch. The
authoritative `InternalEconomySystem` validates the connected-country scope,
resource and percentage, treasury, and production rows; it debits the treasury,
updates national production and eligible controlled-region rows, rebuilds the
resource ledger, and emits `EventResourceProductionIncreased` for history.

The dialog recalculates its estimate from current OpenPower production data on
each render. It prefers explicit regional rows only when the selected country
currently controls an eligible region, otherwise it uses the national row when
no explicit regional allocation exists. The displayed OpenPower rule prices
one year of incremental output value; the tooltip retains cents while the GML
label follows whole-dollar formatting. The supplied reference mirror contains calls
to `IncreaseProductionApproxCost` and a declaration, but not its method body,
so exact source formula and localization parity remain open and are identified
as such in `data_contracts.csv`.

Server tests pass 8/8, the focused production dialog tests pass 2/2, and the
production journey passes at 800×600, 1280×720, and 1518×836 with no layout or
render errors. At that checkpoint the 220-journey suite passed 220/220 with
198 action assertions; the current master suite passes 222/222 with 201
assertions. Reviewed screenshots show the 340×164 dialog and all five estimates
inside the GML slots at those three sizes. Evidence is under
`artifacts/ui/reference-resource-production-20261027/` and
`artifacts/ui/reference/navigation-full-220-20261024/reference-resource-production-dialog/`.

## Campaign-start party selection (2026-10-22)

`NewGameView` now opens the reference `Party_Selection_Window` at 339×197. The picker
reads the country's parties from OpenPower `political_parties`, defaults to its
ruling party, preserves the previous choice on Cancel, and selects the new
country's default party after a country switch. Its GML title, close button,
list, Confirm, and Cancel controls follow the exported source rectangles.

The chosen party ID travels with `ActionStartCampaign` and is saved to
`campaigns.player_party_id` only after the campaign system verifies that the
party belongs to the selected country. This records the player's campaign
choice without changing the country's ruling party. The 18-step journey passes
at 1280×720, including confirm, cancel, country switch, close, and a visual
check of the open modal. The refreshed navigation suite passes 196/196 journeys
with 181 action assertions; screenshot review covers 352 captures with zero
geometry errors. Campaign-system, new-game-task, and persistence tests pass 35/35.

Screenshots and reports are under
`artifacts/ui/reference/gml-new-game-20261022/full-suite/`, with the
contact sheets under `artifacts/ui/reference/gml-new-game-20261022/full-review/`.

## Covert protection display and framed-country rendering (2026-10-27)

The Covert Actions protection slot now shows the OpenPower domestic-security
coverage computed by the same policy used in covert mission detection. The
tooltip identifies it as an OpenPower estimate and explains that it is not
numerically equivalent to reference's `NationalSecurity()` formula. When the panel has
no authoritative regional population, it keeps an explicit `Unknown` value.

The selected mission detail renderer now receives the current state snapshot so
it can resolve a saved framed-country tag to its country name. The regression
journey uses one domestic-security cell and a mission framed to Poland; it asserts
`10.8%` and `Poland`. This also covers the former render error where the detail
renderer referenced a state value outside its scope.

Evidence: the refreshed `reference-military-covert` route passes 8/8 journey steps at
1280×720 with zero geometry findings and no runtime render errors. It verifies
the titlebar close and hidden panel state. The open-panel checkpoint was visually
reviewed and shows the protection value and framed country inside their source
slots. The earlier 220-case suite passed at that checkpoint; the current
current 222-case master also passes 222/222. The covert route passes in the current
master artifact. See
`artifacts/ui/reference/navigation-full-221-20261027/reference-military-covert/checkpoints/003.png`
and `report.json`.

The 14 visible GML caption slots in Covert Actions now map to the captions
rendered in their corresponding OpenPower panel surfaces. They remain partial
because the source localization tables are absent from the supplied mirror.
The Covert Actions window remains partial because saved complexity and
resource/unit targets do not yet change mission-resolution effects, and the
OpenPower coverage formula intentionally differs from reference's source formula.

## Live UKR playtest: demographic meter and safe game exit (2026-10-28)

An isolated Windows client profile under
`.temp/reference-ui-playtest-20261028-a/` started an Open Sandbox campaign as UKR.
The live Demographics panel exposed a scaling mismatch: country HDI is stored
on a 0..1 scale, while the shared meter renders a 0..100 value. The panel now
shows the numeric score and scales the fill to percent; missing data is labeled
`N/A` instead of looking like a real zero. The live run displayed `HDI Score:
0.70` with the expected 70% fill. Its screenshot regression is
`artifacts/ui/reference/navigation-full-221-20261027/reference-main-pillars-no-overlap/checkpoints/012.png`.

The live exit path also reproduced an OpenGL error: the in-game menu closed the
window during `GameView.on_draw`, before ImGui finished rendering the frame.
`GameLayout` now schedules window close for the next frame. The third live run
exited with an empty stderr log at
`.temp/reference-ui-playtest-20261028-a/client-run3.stderr.log`; the prior failing
run logs are retained in the same isolated profile for comparison.

Focused regression tests pass **5/5** for HDI display/data handling and deferred
window close. The refreshed main-pillars route includes the HDI assertion; the
master navigation suite passes **222/222** journeys with **201** exact action
assertions.

The Treaty Details route was also rerun at **1518×836**, the viewport of the
reported live screenshot. It passes **16/16** steps with zero geometry findings
and no render errors. The reviewed capture keeps the details dialog within the
treaty window's source-positioned fields. Evidence:
`artifacts/ui/reference/treaty-details-1518x836-20261028/reference-politics-treaty-details/checkpoints/004.png`
and `report.json`.

The wide main-panels route was refreshed at the same viewport with Politics,
Treaties, Military, Demographics, and Economy open together. It passes **13/13**
steps, including pairwise non-overlap checks and the `HDI Score: 0.70` assertion,
with zero geometry findings and no render errors. The screenshot was reviewed:
`artifacts/ui/reference/wide-main-panels-1518x836-20261028/reference-wide-main-panels-no-overlap/checkpoints/011.png`.

The conditional `Mini_Map` now renders in `GameLayout` at its 228×155 GML size,
anchored to the bottom-right viewport edge. Its source map rectangle displays a
downsampled OpenPower region map with the active map-mode palette and a camera
center marker. Map click/drag recenters the current projection, Home returns to
the controlled country, the magnifier toggles global unit display, and the
vertical source track controls normalized camera zoom. The 13-step route passes
at 800×600, 1280×720, and 1518×836 with zero geometry findings and render
errors; screenshots were visually reviewed. Source realistic/strategic frame
art remains unavailable. Evidence:
`tests/ui/journeys/reference-mini-map.json`,
`artifacts/ui/reference/mini-map-gml-800x600-20261028/checkpoints/000.png`,
`artifacts/ui/reference/mini-map-gml-1280x720-20261028/checkpoints/000.png`, and
`artifacts/ui/reference/mini-map-gml-1518x836-20261028/checkpoints/000.png`.

## Trade offers in the source GML window (2026-10-28)

OpenPower's bilateral trade workflow now switches its offers index into the
source `Trade_Window` at 630×245. Its proposer, recipient, status, offer list,
and View action use the exported GML slots. View opens the existing
`Trade_Detailed_Window` at 648×423, where offered/requested assets and the
available accept, reject, counter, and withdraw actions stay bound to the
authoritative OpenPower trade system. The source `TradeWindowSpawn` has no
caller in the supplied mirror, so this flow remains attached to OpenPower's
TRADE panel entry.

The 40-step bilateral journey passes at 800×600, 1280×720, and 1518×836 with
zero geometry findings and no render errors. The list and detail screenshots
were reviewed at all three viewports after removing the overlapping bottom Back
control; the titlebar action returns to the offers list. Evidence:
`tests/ui/journeys/bilateral-trade.json`,
`artifacts/ui/reference/trade-offer-gml-20261028/checkpoints/017.png`,
`artifacts/ui/reference/trade-offer-gml-20261028/checkpoints/020.png`,
`artifacts/ui/reference/trade-offer-gml-20261028/checkpoints/023.png`,
`artifacts/ui/reference/trade-offer-gml-800x600-20261028/checkpoints/017.png`,
`artifacts/ui/reference/trade-offer-gml-800x600-20261028/checkpoints/020.png`,
`artifacts/ui/reference/trade-offer-gml-1518x836-20261028/checkpoints/017.png`, and
`artifacts/ui/reference/trade-offer-gml-1518x836-20261028/checkpoints/020.png`.

The GML exporter now includes all 92 extracted templates from the window
registry and component tree, including layout-only/unreachable templates. This
catalog expansion supplies geometry references but does not claim gameplay
parity for those windows.

## Singleplayer country profile route (2026-10-28)

The `Country_Profile_Window` mapping now reflects the existing Python dialog in
`NewGameView`: its 271×359 frame and controls bind to the extracted GML slots,
including the three 17×16 rank icons and the 228×4 divider. The 21-step route
checks desired-meter dragging, filter updates, all three visible rank icons,
candidate selection, Confirm, and Cancel; it passes at 800×600, 1280×720, and
1518×836 with zero geometry findings or render errors. All three selected-rank
captures were visually reviewed. Ranking uses OpenPower GDP, government
approval, and military personnel because the source economic/political/military
rank vectors are not present in the reference mirror.

This does not implement the separate reference multiplayer-lobby profile callback;
that route depends on RGAPI lobby data and remains blocked until OpenPower has
an equivalent multiplayer workflow. Evidence:
`tests/ui/journeys/reference-new-game-country-profile.json`,
`artifacts/ui/reference/country-profile-800x600-20261028/reference-new-game-country-profile/checkpoints/009.png`,
`artifacts/ui/reference/tutorial-guide-full-20261028/reference-new-game-country-profile/checkpoints/009.png`, and
`artifacts/ui/reference/country-profile-1518x836-20261028/reference-new-game-country-profile/checkpoints/009.png`.

The central HUD bar now uses the complete **689×96** `Main_Bar` frame and its
reference GML slot coordinates. The political, military, and demographics
shortcuts remain in the separate lower-left ToggleBar; removing them no longer
shrinks or shifts the country, quick-action, clock, and ticker fields. The
refreshed 1280×720 and 1518×836 captures show the full-size bar centered at the
bottom. Focused HUD and demographic regressions pass **23/23** tests.

The isolated live client was restarted with the full-width change, opened an
Open Sandbox campaign as UKR, and showed Politics, Military, Economy, Demographics,
and Treaties. The left shortcuts stayed separate, the 0.70 HDI meter filled to
70%, and the country, quick actions, clock, and ticker remained aligned in the
central bar. Exit to Desktop closed the live window. The clean 1518×836 journey
capture is retained at
`artifacts/ui/reference/wide-main-panels-1518x836-20261028/reference-wide-main-panels-no-overlap/checkpoints/011.png`.

Strategic Warfare now uses the exact 274×362 `Strategic_Warfare` GML root.
Its 6-step route checks frame size, viewport containment, and separation from
Military and the central bar at 800×600, 1280×720, and 1518×836. At compact
height the window shifts upward; on wide screens it moves beside the Military
panel. Reviewed captures are in `artifacts/ui/reference/strategic-warfare-gml-800x600-20261028/checkpoints/005.png`,
`artifacts/ui/reference/strategic-warfare-gml-1280x720-20261028/checkpoints/005.png`,
and `artifacts/ui/reference/strategic-warfare-gml-1518x836-20261028/checkpoints/005.png`.

Objectives now uses the exact 354×336 `Objectives_Window` GML root. Its
recommendation review route passes 22/22 steps at the same three viewport sizes,
including the accept, decline, and read/acknowledge actions. Reviewed compact
and wide captures are `artifacts/ui/reference/objectives-gml-800x600-20261028/checkpoints/001.png`
and `artifacts/ui/reference/objectives-gml-1518x836-20261028/checkpoints/001.png`.

The 2026-10-29 campaign journey also verifies the GML Description/Objectives/Tips
tabs, remaining time, and read-only goal rows with a disabled completion-status
indicator (34/34 steps at 1280×720). The Goals and Tips captures are
`artifacts/ui/reference/objectives-tabs-final-20261029-retry2/checkpoints/006.png`
and `artifacts/ui/reference/objectives-tabs-final-20261029-retry2/checkpoints/011.png`.
All nine visible Objectives GML content slots now have explicit OpenPower data
bindings for the active scenario, country, description, goals, time limit, and
advice page. These remain partial where source translations, authored tips, or
source-specific deadline and outcome semantics are unavailable.

The production dialog was rechecked at 1280×720: 22/22 steps, zero layout
findings, and no render errors. The reviewed GML-sized dialog and all five
estimates are visible in
`artifacts/ui/reference/resource-production-gap-audit-20261029/checkpoints/005.png`.
Its Apply route is verified OpenPower behavior; exact reference cost-formula and
localization parity remain partial in the five value rows.
All 17 previously unresolved Unit Production display slots now bind to their
OpenPower GML render surfaces, including the three queue pages, producer,
capacity, and initial ETA. These rows remain partial where exact source text or
source production calculations are unavailable.
The refreshed seven-route Unit Production playtest passed all 98 steps at
1280×720, with no render errors. The 13-step compact-layout route also passed
at 800×600 with zero layout findings. The queue-limit capture has one warning:
the last queue row meets the bottom of its scroll viewport; visual review shows
the list scrollbar and no overlap with the separate capacity area. Evidence is
under `artifacts/ui/reference/unit-production-gap-review-20261029/`.

## Combined live panel placement (2026-10-28)

The live UKR sandbox exposed a collision that isolated panel routes could not
catch: Objectives opened on top of Strategic Warfare. The shared window
placement service now tracks the GML windows drawn in the current frame and
chooses the nearest free position for Objectives and Strategic Warfare while
preserving a 112-pixel clear strip above the bottom HUD. At the 1518-pixel
client width, Politics, Objectives, Military, Strategic Warfare, and Economy
now occupy separate columns; the central `Main_Bar` remains centered and its
ticker stays inside its slot.

The seven-step combined route passes at 1280×720 and 1518×836, asserting
visibility, exact Objectives dimensions, viewport containment, and no overlap
between Objectives, Military, Strategic Warfare, or the bottom bar. Reviewed
route captures:
`artifacts/ui/reference/floating-panels-no-overlap-1280x720-20261028/reference-floating-panels-no-overlap/checkpoints/007.png`
and
`artifacts/ui/reference/floating-panels-no-overlap-1518x836-20261028/reference-floating-panels-no-overlap/checkpoints/007.png`.

## Political metrics and control audit (2026-10-28)

Tracing `GPoliticWindow::OnCreate/Update` and the shared `GCursorMeter` exposed
that the pressure track had been omitted from the Python panel. It now renders
the source GML track at its catalog rectangle with no fill and an adjacent
`N/A`; OpenPower has no authoritative political-pressure field. The UI does not
substitute a zero value. The selected-country government form also now follows
the source precedence rule: show `Martial law` whenever the martial-law flag is
set, otherwise show the stored form label.

The source meter initializes its first fill cursor as draggable and emits a
local `c_OnMeterChangeEvent`, but `GPoliticWindow` has no `OnCustomEvent`
receiver and sends no political GameEvent for that change. Its next data update
sets the displayed meter again from the selected-country record. Python keeps
approval, stability, corruption, and ideology as read-only values bound to
current OpenPower state; source-only visual dragging is classified
`verified_unavailable`, rather than presented as a game action. Locked track
fragments and hidden Apply controls are also explicitly accounted for. The
static caption bindings remain partial because the reference translation tables are
not in the supplied source mirror.

The `reference-politics-close` route passes, and the latest master suite reports
233/233 journeys with 208 action assertions. I reviewed the 1280×720 capture after opening Politics; the
N/A text and empty pressure rail occupy the correct GML row and remain clear of
the approval and stability controls:
`artifacts/ui/reference/politics-pressure-review-20261028/reference-politics-close/checkpoints/001.png`.

## Treaty details conditions and responses (2026-10-28)

The `Treaty_Details_Window` uses its 634×448 GML frame and now fills all six
condition slots from the selected treaty's saved `conditions_json`. Values are
read-only in details and appear at the source coordinates. The geographic label
uses its source rectangle explicitly because its GML type is a transparent graph
rather than a normal label. A smaller label font keeps the full caption within
its 130 px source slot. On compact screens, the dialog moves above the 96 px
bottom HUD area; the treaty list is hidden while details are open so no text is
left partially visible behind the modal.

Pending proposal Accept and Reject controls use the source `btnModify` and
`btnRefuse` positions and dispatch `ActionRespondTreaty` with the selected
proposal and controlled country. reference's separate pressure-country total and
pressure-side sponsorship action do not exist in OpenPower, so the source meter
shows an empty rail with `N/A`, the pressure list states why it has no data, and
SPONSOR stays disabled. Source relation, region, rank, and research categories
remain different from OpenPower's native thresholds and ratios; the UI and audit
keep those mappings partial rather than claiming enum parity.

The 26-step detail route passes at 800×600, 1280×720, and 1518×836 with zero
geometry findings and no render errors. The 9-step Accept and 8-step Reject
routes pass in the 233/233 master suite; both send the expected action. The
focused audit, treaty lifecycle, treaty specification, and GML layout tests pass
42/42. Reviewed screenshots:

- `artifacts/ui/reference/treaty-details-conditions-800x600-20261028/reference-politics-treaty-details/checkpoints/004.png`
- `artifacts/ui/reference/tutorial-guide-full-20261028/reference-politics-treaty-details/checkpoints/004.png`
- `artifacts/ui/reference/treaty-details-conditions-1518x836-20261028/reference-politics-treaty-details/checkpoints/004.png`
- `artifacts/ui/reference/tutorial-guide-full-20261028/reference-treaty-response-accept/checkpoints/004.png`

The master audit now contains no `assumption/unknown` interaction or data
contracts for Treaty Details. Remaining differences are explicit: OpenPower
condition proxies, unavailable localization, and unsupported pressure data.

## Credits typography and source slots (2026-10-28)

The live credits panel had inherited the general 14 px ImGui font and rendered
all source rows as a flow table. That made long values overflow the fixed GML
columns and caused multi-person roles to move later labels away from their
source positions. The layout exporter now retains the Credits template's
`FontSize`, `TextAlign`, and `TextOffset`; the renderer uses the catalogued
label rectangles and the 9 px/13 px source fonts, clips each value to its GML
slot, and applies the source `GCreditsWindow::OnCreate` +140 px shift to the
DreamCatcher labels.

The public Steam Edition roster reports 54 people with 57 credits. Its 57
role/person assignments fit the mapped source slots; the extra GML labels remain
blank rather than shifting the roster or inventing credits. Exact localized
source-string parity remains unverified because the localized credit resources
are absent from the mirror.
The 21-step route passes at 800×600, 1280×720, and 1517×835 with zero layout
findings and no render errors. I reviewed the opening credits frame at all
three viewports and the scrolled OpenPower attribution frame at 1280×720:

- `artifacts/ui/reference/credits-gml-alignment-800x600-20261028/checkpoints/002.png`
- `artifacts/ui/reference/credits-gml-alignment-1280x720-20261028/checkpoints/002.png`
- `artifacts/ui/reference/credits-gml-alignment-1517x835-20261028/checkpoints/002.png`
- `artifacts/ui/reference/credits-gml-alignment-1280x720-20261028/actual.png`

## Credits roster text verification (2026-10-29)

The Steam Edition roster now uses the published spelling `Vasso T. Kontoulis`.
Each credit-name widget exposes a stable journey ID, and the main-menu journey
asserts that exact label while scrolling the GML-sized credits child. The
57-entry/54-unique-string fixture check passes, and the refreshed 23-step
journey passes at 1518×836 with zero layout findings or render errors. I
reviewed `artifacts/ui/reference/credits-roster-correction-20261029/1518x836/actual.png`;
the tester name and OpenPower attribution render in their intended scroll slots.
The source-localized strings remain unavailable, so translation parity is still
open.

## GML text metrics across layouts and repeated rows (2026-10-28)

The shared GML export now retains `FontSize`, `TextAlign`, and `TextOffset` for text components. The bound layout session applies source alignment and offsets, while shared text primitives inherit the component's source font size unless the panel explicitly overrides it. Dynamic repeated row templates now parse and apply all three properties too, so list labels use their GML font metrics rather than silently falling back to the general UI font.

Verification passes: **21/21** focused GML row and binding tests, **233/233** master navigation journeys, **54/54** UI surfaces, and **7/7** dedicated dynamic-row journeys at 1517×835. No render-error checks failed. I reviewed final captures for Internal Laws, covert cells, treaties, mail, unit production/reserves, and the map legend. The master journey reports contain **37 occurrences across 18 journeys** of the same 1 px overlap between the assigned-country and status combo slots in the covert-cell source row. The separate surface and dynamic-row reports have zero layout findings.

Reports and reviewed captures are under:

- `artifacts/ui/reference/gml-rows-font-navigation-1517x835-20261028/`
- `artifacts/ui/reference/gml-rows-font-all-surfaces-1517x835-20261028/`
- `artifacts/ui/reference/gml-row-font-recheck-1517x835-20261028/results-correct-surface/`
- `artifacts/ui/reference/gml-rows-font-all-surfaces-1517x835-20261028/internal-laws/1517x835/actual.png`
- `artifacts/ui/reference/gml-rows-font-all-surfaces-1517x835-20261028/covert-ops/1517x835/actual.png`
- `artifacts/ui/reference/gml-rows-font-all-surfaces-1517x835-20261028/treaties/1517x835/actual.png`
- `artifacts/ui/reference/gml-rows-font-all-surfaces-1517x835-20261028/mail/1517x835/actual.png`
- `artifacts/ui/reference/gml-rows-font-all-surfaces-1517x835-20261028/unit-production/1517x835/actual.png`
- `artifacts/ui/reference/gml-rows-font-all-surfaces-1517x835-20261028/unit-reserves/1517x835/actual.png`
- `artifacts/ui/reference/gml-rows-font-all-surfaces-1517x835-20261028/map-legend/1517x835/actual.png`

## Peace package submission feedback (2026-10-28)

The War List peace editor now waits for the authoritative `ActionSubmitPeaceDeal`
result before clearing a draft. Rejections retain the offered/requested clauses
and display the server reason; accepted submissions clear the draft and show
the success feedback. `AdvancedDiplomacySystem` records a correlated result
for each submit/response outcome, including validation failures, so the client
does not mistake the transport-level `executed` result for an applied deal.

The focused UI journey opens the reference-sized War List, selects War reparations,
sets the payer direction, amount, and duration, adds the clause, and asserts the
exact dispatched action payload. It passes **14/14** steps at 1280×720 and
800×600, with zero layout findings and no render errors at either size. Separate
pending-deal fixtures verify that the opposing player sees the terms and can
send both Accept and Reject; each route passes **8/8** steps at 1280×720. The
test harness now permits a fixture to choose its controlled country and
selected region, which lets these routes exercise a real opposing-side context.
Result-delivery journeys separately cover an applied submission (**15/15**)
and a rejected submission (**17/17**): success clears the package, while
rejection appears once in the shared Generic Message dialog and preserves the
draft after acknowledgement. The underlying submission button is available
again after either result. These routes have zero layout findings and no render
errors. The updated master navigation run now reports **238/238** passing
journeys and **213** exact action assertions at 1280×720; its previous 233
passing results were reused and the five new peace-package routes were run.
Evidence: `artifacts/ui/reference/navigation-final-continuation-20261028/suite.json`.
The domain tests verify authoritative applied/rejected result records; editor
unit tests verify draft retention on both domain rejection and transport
failure, and clearing only on success. I reviewed the editor and incoming-deal
screenshots, including the rejection dialog before acknowledgement:

- `tests/ui/journeys/reference-war-list-peace-package.json`
- `tests/ui/journeys/reference-war-list-peace-response-accept.json`
- `tests/ui/journeys/reference-war-list-peace-response-reject.json`
- `tests/ui/journeys/reference-war-list-peace-submit-applied.json`
- `tests/ui/journeys/reference-war-list-peace-submit-rejected.json`
- `artifacts/ui/reference/peace-package/checkpoints/004.png`
- `artifacts/ui/reference/peace-package/actual.png`
- `artifacts/ui/reference/peace-package-800x600/checkpoints/004.png`
- `artifacts/ui/reference/war-list-peace-response-accept/checkpoints/003.png`
- `artifacts/ui/reference/war-list-peace-response-reject/checkpoints/003.png`
- `artifacts/ui/reference/war-list-peace-submit-applied/actual.png`
- `artifacts/ui/reference/war-list-peace-submit-rejected/checkpoints/012.png`

## Single-player start action crosswalk (2026-10-28)

The source Start button sends `GSetGameObjectives` with the editable `m_vGameObjectives` list and applies three advisor CPU-toggle modes. OpenPower's valid start path is `NewGameView._start_game` → `NewGameTask` → `ActionStartCampaign`; `CampaignSystem` validates the selected scenario, country, party, and setup, then creates objective records from the scenario's fixed `objectives_json`. This is a partial mapping: arbitrary reference goal editing and those CPU-toggle values are not inputs to `ActionStartCampaign`.

The existing country-validation journey covers the disabled Start guard, while `tests/test_new_game_task.py::test_new_game_start_action_includes_selected_party` checks the action payload. Campaign setup validation and objective initialization are covered in `tests/test_campaign_system.py`. New-game failure details remain visible in the recoverable LoadingView instead of the source Generic Message modal.

## Multiplayer event and strategic research crosswalk (2026-10-28)

The five server events found in `Game_Lobby` now have explicit unavailable mappings: `GSetPlayerInfo` (ready/name), `GSystemGameEvent` (kick/ban), and `GStartGameRequest`. The source requires a multiplayer lobby, while OpenPower has no multiplayer session, chat, or player-management workflow, so these rows do not claim a GameAction equivalent.

The Military panel's AMDS `btnResearch` is only a partial match: OpenPower opens `UnitResearchPanel`, where a separate funding action exists, but that does not start reference's costed, timed AMDS program. `btnNuclearProgram` stays unavailable because the OpenPower strategic-production and missile-defense models do not define a nuclear research-start action. Preserve both distinctions until matching authoritative program state and rules exist.

The source events are visible in `.codex/Client/Source/reference_game_lobby_window.cpp`, `.codex/Client/Source/reference_military_window.cpp`, and `.codex/Client/Source/reference_client_advisor.cpp`. The synchronized action rows are guarded by `test_unavailable_multiplayer_events_and_strategic_research_buttons_are_not_mapped_to_unrelated_actions` in `tests/test_reference_navigation_coverage.py`.

## Single-player setup control dispositions (2026-10-28)

The full `Start_Single_Player` interaction list now distinguishes the local country/profile/party routes from source-only setup inputs. Country selection filters to the current scenario, defaults its party, and later becomes `ActionStartCampaign`; profile and party windows use the tested OpenPower routes. Closing the setup returns to scenario selection without starting a campaign.

The five source objective toggles and deadline combos edit `m_vGameObjectives`; OpenPower instead displays fixed scenario objective titles and deadlines. The six source Human/Computer controls choose per-sphere advisor ownership; OpenPower shows the player as controller and configures advisor modes separately after startup. These 16 source controls remain explicitly unavailable until the campaign setup action can carry equivalent authoritative fields. Title Apply is hidden by the source, and the source lock toggle stays omitted.

The country/profile/party flows retain their existing geometry journeys. `test_single_player_start_maps_fixed_scenario_setup_and_keeps_source_goal_gap_explicit` now checks every setup interaction row and gap-table disposition against the explicit audit bindings.

The Military panel now has explicit audit bindings for all 19 interactive source controls: its title close and hidden Apply slot, all ten routes into existing Python panels, the unavailable nuclear-program action, and the partial AMDS-research route. Each navigation binding points to its existing UI journey. Four source progress-meter children remain partial because OpenPower shows strategic-unit readiness and operational missile-defense coverage rather than nuclear or AMDS research progress. `test_military_panel_routes_and_progress_meters_have_explicit_openpower_dispositions` checks route artifacts and synchronizes the bindings with both CSV crosswalks.


The Military display crosswalk now accounts for its GML captions, force-summary values, and strategic-meter values. It records that the source's category quantity and cross-country rank calculations differ from OpenPower's unit-strength and local unit-group counts, and that its nuclear/AMDS meters differ from OpenPower's strategic readiness and operational missile-defense coverage. The UI keeps the GML-centered alignment for the unit-count column and missile-defense value. These bindings remain partial where exact source localization or metric semantics are unavailable.

Fresh Military UI evidence: `reference-military-guided-tour.json` passes 33/33 steps at 1280×720 with zero geometry findings or render errors; `reference-military-close.json` passes its 4-step close route at the same viewport. I reviewed `artifacts/ui/reference/military-center-alignment-review-20261028/reference-military-close/checkpoints/001.png`: the `UNITS` heading, group counts, and missile-defense percentage are centered in their GML slots. The latest combined focused Python batch passes 136 tests. These are scenario-harness results, not a new live-world playtest.

`Player_Options_Window` (23 controls) and `Political_Parties_Window` (6 controls) are marked unused in the source window registry and have no active C++ class or runtime spawn route in the supplied mirror. Their controls now remain explicitly unavailable; the GML names alone do not authorize mapping them to the similar Start Single Player or Politics controls. Their interaction rows and duplicate gap entries are checked against `UNUSED_SOURCE_TEMPLATE_INTERACTION_BINDINGS`.

## Multiplayer host and lobby controls (2026-10-28)

The host setup's 23 non-lock controls and the lobby's remaining 10 source controls now have explicit `verified_unavailable` bindings. This covers server configuration, host objective/deadline selectors, startup/cancel, player/country selection, and lobby chat. The source C++ behavior is recorded, but none of these routes is redirected to single-player actions because OpenPower has no authoritative multiplayer server/session workflow. The five server-event controls already documented above remain unavailable as well.

`test_host_and_lobby_controls_are_explicitly_unavailable_without_multiplayer_workflows` verifies complete non-lock control coverage, source-side-effect notes, interaction rows, and duplicate gap rows. The updated interaction and gap status counts are summarized in `README.md` and `verification.md`.

## Scenario selection crosswalk (2026-10-28)

`Scenarios_Window` now has explicit dispositions for all 15 non-lock controls. Its nine sphere-difficulty toggles map to disabled N/A placeholders because OpenPower does not define reference's independent Politics/Economy/Military presets. Selecting a campaign scenario updates the local scenario draft and eligible-country list; the source custom list's fixed nine-scenario offset is not reused. The objective preview is read-only and omits reference's initial completion-state toggles.

The source Start button selects a scenario and country and starts its connection flow. OpenPower CONTINUE advances to a separate country/party stage, with `ActionStartCampaign` dispatched only after setup. Exit/Cancel return to the main menu; because this flow starts no multiplayer connection, those routes do not claim to call `CancelConnect`. The source-hidden Apply slot remains hidden. `test_scenario_selection_controls_distinguish_openpower_setup_from_reference_presets` checks each control's disposition and its gap-table rows.

## Battle inspection controls (2026-10-28)

The nine previously unknown Battle window controls now have explicit partial mappings. Participant flags change the country shown in local inspection; the source-only hit-reset animation is absent. Strategy and Retreat use OpenPower's authoritative `ActionSetBattleStrategy` route with active-battle, country-authority, participating-force, and safe-route validation, while the source uses theme-specific tactical presets and `GBattleOverviewUnitActionUpdate`. The meter now draws its green fill, red remainder, and separator in their GML slots. Its value remains OpenPower battle balance rather than the source actor-value progress formula.

The existing own-battle journey verifies country selection, per-force and all-force orders, retreat, and close behavior. `test_battle_inspection_controls_document_partial_openpower_strategy_and_display_matches` synchronizes the nine source controls with the contract and gap tables.

The battle inspection suite passes 5/5 journeys at 1280×720 with zero geometry findings or render errors. I reviewed `artifacts/ui/reference/battle-inspection-crosswalk-20261028/reference-battle-inspection-own/checkpoints/001.png`; the green fill, red remainder, and white separator align within the GML meter slots.

## Strategic target selection crosswalk (2026-10-28)

The nine target-country window controls now have explicit dispositions. OpenPower's `ActionLaunchStrategicStrike` is region- and weapon-specific. reference's country-wide target types, ground/submarine/all missile-category selector, missile-count arrows, and draggable count meter do not share that action shape. Target country and military/civilian mode map partially to an OpenPower plan; selecting an individual weapon maps to its inventory record. The count arrows and meter remain unavailable instead of pretending to choose a weapon quantity. The source Suggest button computes missile assignment and casualty estimates; OpenPower's region suggestion is documented as a different local convenience.

`reference-strategic-planner.json` verifies the OpenPower prepare/confirm workflow and `ActionLaunchStrategicStrike` payload. `test_strategic_target_controls_preserve_openpower_region_and_weapon_semantics` checks all nine interaction dispositions and duplicate gap rows.

The source missile-count arrows and draggable percentage meter remain explicitly unavailable because OpenPower's launch action identifies a specific weapon and has no quantity field; the server also permits only one pending launch per weapon record. The GML meter slot currently hosts the OpenPower authorization-context selector, which is not presented as a count control.

`reference-strategic-planner.json` passes at 1280×720. I reviewed `artifacts/ui/reference/strategic-target-crosswalk-20261028/reference-strategic-planner/checkpoints/005.png`; the selected country is POL and its default target region is Warsaw, matching the fixture ownership data.

## Unit reserves layout and control crosswalk (2026-10-28)

`UnitReservesPanel` now keeps the source window frame, count slots, four category-specific GML pages, and `lstUnitDeployItem` row template. The source `g_def_tabbd` metrics are exported and applied to four runtime-created category buttons: 71×16 px, −1 px button spacing, 0 px left offset, and a 17 px child-page offset from `FrameOffsetTop=-1`. This places the first list row at panel-relative `(36, 94)` without changing static GML geometry. The `txtQty*` slots display counts of the visible OpenPower reserve-group buckets, while their source row-count shape is retained.

The list controls use Shift range selection and Ctrl toggling. Capital deployment dispatches `ActionDispatchUnitDeployment` for selected eligible groups; training presents one quote-backed confirmation and dispatches per-unit `ActionTrainUnit` requests. The four dynamic tab buttons clear the current selection. Source `NuclearAllowed` has no OpenPower equivalent, so the strategic tab remains available while capital deployment stays disabled on that tab. The source category names and icon art also remain unavailable; OpenPower keeps its native unit taxonomy and status semantics.

The layout journey passes 22/22 at 800×600, 1280×720, and 1920×1080 with zero geometry findings or render errors. The action journey passes 27/27 at 1280×720 and 1517×835; it asserts selection reset on category change, both selected-group deployment payloads, and training payloads. Screenshots were reviewed at all three layout sizes and for the training question: `artifacts/ui/reference/unit-reserves-gml-tabs-20261028-r2/actual.png`, `artifacts/ui/reference/unit-reserves-gml-tabs-20261028-800x600/actual.png`, `artifacts/ui/reference/unit-reserves-gml-tabs-20261028-1920x1080/actual.png`, `artifacts/ui/reference/unit-reserves-actions-20261028-r2/checkpoints/023.png`, and `artifacts/ui/reference/navigation-final-continuation-20261028/reference-unit-reserves-actions/checkpoints/023.png`.

`UNIT_RESERVES_INTERACTION_BINDINGS` and `DISPLAY_BINDINGS_BY_WINDOW` now feed these source paths into the audit generator. The generated crosswalk includes the runtime-created `tabGroups/@tabButtons` control set, which has no static component-tree node. `test_unit_reserves_display_and_interaction_contracts_match_verified_python_routes` checks the generated interaction/data/gap rows against those bindings. The separate GameView drop regression verifies dispatch for valid regions and rejects drops over UI or outside the map; the remaining partial status comes from source taxonomy, localization/artwork, and `NuclearAllowed` differences.

## Main bar country and time controls (2026-10-28)

`Main_Bar` keeps the 689×96 GML frame and child slots. The country field is 197×16 at `(238, 30)` and the read-only status slot is 65×13 at `(237, 47)`. The clock button remains 27×27 at `(549, 32)`; its 92×22 speed frame is at `(579, 35)`. The five source speed toggles occupy 16×18 slots at x=2, 20, 38, 56, and 74. Date and time remain in the right-hand 90 px label slots.

The country popup now has a fixture-backed route in `main-bar-layout.json`: opening the flag-backed picker, selecting POL, and checking the map focus request and neutral status. Python resolves PLAYER, active-war HOSTILE, active ALLIANCE, active military transit access, and NEUTRAL from OpenPower state; the displayed status colors match the reference RGB values. The 65 px button uses `ALLIED` for the source Allied status and `ACCESS` for Military Access, with the full access name in the hover tooltip. Separate fixture journeys exercise alliance, hostility, and military transit. Exact reference localization, the source ZoomToCountry sound, and the source player display name are not present in the supplied assets/state contract.

The source has Pause plus four non-paused speed toggles. Those five controls retain their exact 16×18 source slots at x=2, 20, 38, 56, and 74 inside the 92×22 frame. OpenPower adds speed level 5 in the unused root-edge gutter at x=94 relative to `frmTimeSelection`, ending at the 689 px Main_Bar root edge; the audit identifies it as an OpenPower extension. The source disables these toggles for non-admin players; the current OpenPower client is single-player and always identifies as `local_admin`. Exact speed rates are also different. The source `btnTime` behavior is preserved: it swaps the date/time labels with the speed controls without sending an action.

`frmMeterPolitic`, `frmMeterMilitary`, and `frmMeterEconomic` now render as nine-segment bars in their exact GML slots. Their tooltips name OpenPower-native metrics: government approval, the selected country's ready-or-fortified unit share, and economic health. This closes the missing-display gap while keeping formula parity partial because the supplied C++ mirror does not include the source sphere-meter implementation.

The 45-step main-bar journey checks the three 50×13 meter hitboxes, the exact 47×28 flag focus hitbox, the 461×19 `btnLocate` hitbox and its region-focus request, country selection, status, clock, date/time, ticker, and speed controls. It passes at 800×600, 1024×768, 1280×720, 1517×835, and 1920×1080 with zero geometry findings or render errors. A separate location-less bulletin fixture verifies that the `btnLocate` slot remains source-sized but disabled, shows a concise reason on hover, and sends no viewport request; the six-step route passes at the same five sizes. Reviewed tooltip checkpoints at 800×600 and 1920×1080 are under `artifacts/ui/reference/main-bar-locate-disabled-tooltip-final-20261028/`. Clicking the flag focuses and selects the active country's representative region through OpenPower's viewport controller. The ticker child is mouse-transparent so the parent-level locate target remains clickable across its full source rectangle, including the one-pixel GML bleed around the ticker frame. Populated-state screenshots were reviewed at 800×600 and 1517×835 under `artifacts/ui/reference/main-bar-sphere-meters-populated-20261028/`; locate and flag journeys are under `artifacts/ui/reference/main-bar-country-flag-20261028/` and `artifacts/ui/reference/main-bar-locate-fixed2-20261028/`. Three additional 7-step fixtures verify ALLIED, HOSTILE, and ACCESS statuses. The full suite remains 245/245 with 214 action assertions; the neutral country-selection checkpoint is `artifacts/ui/reference/navigation-final-continuation-20261028/main-bar-layout/checkpoints/013.png`, and status screenshots are under `artifacts/ui/reference/navigation-final-continuation-20261028/reference-main-bar-alliance/`, `reference-main-bar-hostile/`, and `reference-main-bar-military-access/`. Focused unit tests cover sphere metric sources, range bounds, segment geometry, alliance, war precedence, transit-right expiry/suspension, normalized country tags, and compact status labels.

## Unit split quantity meter anchoring (2026-10-28)

`frmSplitMeter` now hosts the integer slider in its source GML rectangle, `(102, 43, 87, 16)` relative to the 289×66 popup. Before this binding, the slider followed ImGui flow layout below the quantity fields, overflowing the fixed frame; interaction then scrolled the popup contents and displaced its close button. The source-slot binding keeps the fields, meter and close action anchored together and prevents that scroll.

The 33-step `reference-unit-split.json` journey checks both slider bounds, a real slider drag, increment/decrement limits, direct quantity entry, popup close/commit, reverse transfer and the exact final `ActionSplitUnit` payload. It passes at 800×600, 1024×768, 1280×720, 1517×835 and 1920×1080 with zero geometry findings. The quantity-popup screenshots at the slider checkpoint were visually reviewed at all five sizes; reports and checkpoints are under `artifacts/ui/reference/unit-split-meter-contract-final-20261028/`. The source fill and remainder button children still map to the one combined OpenPower slider; that renderer composition difference remains documented as partial.

## Budget and Resources inherited title controls (2026-10-28)

The previously unknown `Budget_Window` and `Resources_Window` title actions now have explicit contracts. Source `GBaseWindow::OnMouseClick` routes Exit through `ExitWindow` and Apply through `Apply()` to each derived `Save()` implementation. The Python panels use their shared dirty-close confirmation and existing Apply actions. Budget Apply submits `ActionUpdateBudget`, matching the source server update; Resources Apply submits the supported per-resource `ActionUpdateResourcePolicy` drafts, while source global tax remains disabled because OpenPower has no matching authoritative field/action.

The audit classifies both Exit routes and Budget Apply as verified OpenPower behavior. Resources Apply stays partial because its source Save also sends the unavailable global-tax modifier. Existing budget and resource Apply/Discard journeys cover the exact outcomes; `test_budget_and_resource_title_actions_are_traced_to_python_routes` checks the generated interaction/gap rows against source callbacks and Python routes. The full 245-journey suite remains passing; the refreshed contract audit is in `docs/ui/reference-title/interaction_contracts.csv` and `gap_table.csv`.

## Thematic map legend country selection (2026-10-28)

`Thematic_Map_Legend/lstCountries` now has a resolved interaction contract. The source `OnListItemSelected` callback reads the selected row's country ID and calls `SelectedCountrySetLookAt`; the OpenPower row uses its country tag to request the same map focus. The generated contract is verified OpenPower behavior, not an assumption about a list click or a game action.

Both `reference-map-thematic-legend.json` and `reference-map-empire-legend.json` select POL and assert the country viewport request. `test_thematic_map_country_list_selection_matches_source_look_at_handler` ties the source callback, those journeys, and the generated interaction/gap rows together. The 245-journey suite and zero-failure audit are unchanged.

## Battle overview small-unit list selection boundary (2026-10-28)

`Battle_Overview_Small_Unit_Info/lstUnits` is now explicitly partial. The source handles `OnListItemSelected`, but the only call that would notify the owning battle window is commented out, so the row selection currently has no active state-changing effect. OpenPower's battle overview selects an entire battle record and opens its inspection workflow; that does not implement the source's country-unit row interaction and is not treated as equivalent.

`test_battle_overview_country_rows_remain_distinct_from_openpower_battle_selection` verifies the source callback, the partial interaction contract, and the corresponding gap rows. The refreshed audit still reports 245/245 navigation journeys; current totals are 188 partial and 101 assumption/unknown interaction contracts. The exact generated tables are `interaction_contracts.csv` and `gap_table.csv` in this directory.

## Economic summary meter interaction boundary (2026-10-28)

The economic-model meter uses `GIdeologyMeter`, whose source fill cursor is non-draggable and whose background is locked. OpenPower renders it with a read-only cursor meter. The health and resource summary meters use the generic `GCursorMeter`, which permits a local drag of the fill cursor; that generic gesture only changes a transient meter value and sends a custom event that `GEconomicWindow` does not handle. OpenPower keeps both summaries read-only and directs actual resource policy edits to the Resources panel.

The six meter-child interactions now have explicit contracts: the two model controls and two locked backgrounds are verified as non-interactive; the two source-draggable fill controls remain partial. `test_economic_summary_meter_controls_keep_source_drag_boundary_explicit` checks the source meter configuration, absent economic-window event handler, Python read-only rendering, and generated contract/gap rows. The refreshed audit remains 245/245 navigation journeys and has no failures.

## Internal Laws interaction contract closure (2026-10-28)

The eight previously unknown controls in `Internal_Laws` now map to their source and OpenPower roles. The title Apply and close paths are linked to the inherited `GBaseWindow` callbacks, OpenPower's multi-action draft submission, and dirty-close confirmation. The four law/party/religion/language lists are identified as dynamic row hosts; the actual edits happen in their child controls. The two source migration dropdowns store binary border flags, while OpenPower routes to its separate migration-policy editor and does not invent an equivalent border toggle.

`test_internal_laws_controls_map_to_supported_drafts_and_separate_migration_editor` checks the C++ callbacks and Save payload, Python action types, existing law/identity/party/close journeys, and all eight generated contract/gap rows. All eight remain partial for documented schema or workflow differences. The full audit still has 245/245 navigation journeys; the focused navigation/layout/domain test set passes 80 tests.

## Compact HUD panel navigation (2026-10-29)

At 800×600, the four 50×50 panel launchers previously moved to the strip directly above `Main_Bar`. The Politics panel then covered the Military, Economy, and Demographics launchers, so players could not reach those panels. Compact view now places the launchers in a 230×50 strip immediately below the 38 px `System_Bar_Window`, preserving each GML-sized button and its 10 px spacing. Wider viewports keep the launchers beside the centered `Main_Bar`.

`reference-compact-panel-navigation.json` verifies each main panel opens and closes while the launcher strip remains inside the viewport and does not overlap it. It asserts launcher containment instead of a fixed child offset because roomy layouts retain standard ImGui window padding. The journey passed 14/14 steps with zero layout findings at 800×600, 1024×768, 1280×720, 1518×836, and 1920×1080; reports and screenshots are under `artifacts/ui/reference/live-game-probe-20261029/compact-panel-navigation-matrix/`. `main-bar-layout.json` passed 45/45 at 800×600, and the all-main-panels layout journey passed 13/13 at 1024×768 and 1518×836. The 800×600 all-panels-at-once layout is not a valid no-overlap target: the fixed-size Treaty, Military, Economy, Demographics, and Politics windows exceed the available packing area. The focused compact journey tests each launcher in turn instead. Live gameplay screenshots also confirmed the four main panels and treaty list at 1518×836.

## Live game text alignment check (2026-10-29)

Captured the running OpenPower Engine window and compared its client area (about 1520×837, excluding the native title bar) with the 1518×836 wide-panel harness capture. The running process loaded the current `FontLoader.configure_ui` path; a separate Arcade window measured `pixel_ratio=1.0` and a 1:1 framebuffer. The 3 font-context tests pass. No frame-wide text offset or DPI mismatch was reproduced. The current live capture centers `Main_Bar` as the harness does; text hidden by foreground panels is occluded by those windows. Long live values and table entries remain candidates for targeted content-width checks.

## Economic window caption bindings (2026-10-29)

The seven visible `Economic_Window` caption slots now map to the literals already rendered by `EconomyPanel` in their GML slots. They remain partial because the source localization tables are absent; no missing economic values or behaviors were reclassified as implemented. `test_economic_window_gml_captions_have_explicit_openpower_bindings` checks the seven GML token IDs against Python and the generated data/gap rows. The focused navigation suite passes 60/60. Data rows now report 761 partial and 269 assumption/unknown; gap rows report 1,023 partial and 553 assumption/unknown.

## Treaty list caption bindings (2026-10-29)

The ten visible `Treaties_Window` title, filter, section, and table-header slots now have explicit bindings to the captions rendered by `LiveTreatiesPanel`. They remain partial because the source localization is unavailable and OpenPower's table columns retain their documented layout differences. `test_treaties_window_gml_captions_have_explicit_openpower_bindings` checks each GML token ID, Python caption, and generated data/gap row. The focused navigation suite passes 61/61. Data rows now report 771 partial and 259 assumption/unknown; gap rows report 1,033 partial and 543 assumption/unknown.

## Internal laws display binding and migration precision (2026-10-29)

The ten `Internal_Laws` display slots now point to their Python caption, identity-profile host, or migration-rate value. OpenPower migration rates use one decimal place to match the source formatter; unavailable rates retain the em dash. The demographic profile and migration policy remain partial because their data sources and editing flows differ from reference.

`internal-laws-layout.json` passed 20/20 steps with zero geometry findings at 1518×836 and 800×600. Screenshots are under `artifacts/ui/reference/internal-laws-review-20261029-{1518x836,800x600}/actual.png`. The focused navigation, migration, and resource tests pass 80/80.

## Resources window display and data contracts (2026-10-29)

All 21 `Resources_Window` display rows now have explicit Python bindings. The panel uses OpenPower's active-country resource catalog and `resource_ledger`; it does not import the reference resource list. Resource production share, GDP share, recorded trade, and net balance each document their OpenPower field and fallback. reference stock availability has no OpenPower equivalent: `balance_usd` is a net flow and is not reported as available stock. The per-resource trade-target and global-tax controls remain visibly unavailable because OpenPower has no matching authoritative actions or fields.

`reference-resource-policy-multiple-drafts.json` passed 23/23 steps with zero geometry findings at 1518×836 and 800×600. The reviewed captures show aligned resource-table headings and the selected-resource controls in both viewports: `artifacts/ui/reference/resource-policy-review-20261029-1518x836/actual.png` and `artifacts/ui/reference/resource-policy-review-20261029-800x600/actual.png`. Current contract totals are 808 partial / 237 assumption-or-unknown data rows and 1,069 partial / 506 assumption-or-unknown gap rows.

## System bar shortcut captions and route check (2026-10-29)

The six `System_Bar_Window` F-key captions now bind to the labels rendered by `SystemBar`; the chat caption stays partial because its multiplayer route is unavailable. The full system-bar journey was corrected to open the `OPENPOWER` settings tab before checking the Reduce motion control, which lives on that tab.

`reference-system-bar-layout.json` passed 73/73 steps with zero geometry findings at 1518×836 and 800×600. The reviewed `OPENPOWER` tab checkpoints show the F1–F10 captions aligned in the top-right bar: `artifacts/ui/reference/system-bar-review-20261029-1518x836-rerun/checkpoints/045.png` and `artifacts/ui/reference/system-bar-review-20261029-800x600-rerun/checkpoints/045.png`.

## Relations display check (2026-10-31)

The four `Relations_Window` display slots are traced to the Python title, country selectors, and directed relation value. Their contracts remain partial because the source localization and numerical equivalence are unverified. `reference-relations-data.json` passed 5/5 steps with zero geometry findings at 1518×836 and 800×600; both screenshots were reviewed. These checks document existing behavior and do not close the remaining implementation gaps.

## Resource balance label (2026-10-31)

The selected resource's `balance_usd` value is now labeled `NET BALANCE` in the source availability slot, and a missing row shows `Unavailable` instead of zero. The resource-policy journey passed 23/23 steps at 1518×836 with no geometry findings; `artifacts/ui/reference/net-balance-20261031/actual.png` was reviewed. The source stock-availability metric remains unsupported.

## Tutorial close and open sequence (2026-10-31)

The in-game interface guide now treats closing Relations and opening Country Information as separate goals, following reference states 42 and 43. The close step points at the native Relations close button; the next step points at More Info. The in-game journey passed 36/36 steps at 1518×836 and, after adding explicit arrow checks, 38/38 at 800×600, with zero geometry findings. Both close-step screenshots and the compact More Info arrow were inspected. The main-menu preview passed 65/65 steps at 1280×720. This covers those transitions only; the source tutorial state machine remains incomplete.

## Tutorial relation-window explanations (2026-10-31)

The interface guide includes separate, manually advanced steps for inspecting and moving the Relations window, corresponding to reference states 40 and 41. Both require Relations to remain open; unlike panel-transition goals they do not advance merely because the window is visible. The journey now drags Relations by 60×50 pixels, verifies its new position and continues to the close step: 54/54 steps passed at 1518×836 and 800×600 with zero geometry findings. Both post-drag screenshots were reviewed under `artifacts/ui/reference/tutorial-drag-20261101-{wide,compact}/checkpoints/033.png`. The main-menu preview passed 69/69 steps at 1280×720. The full source tutorial remains incomplete.

## Tutorial main-bar explanations (2026-11-01)

The interface guide now includes the advisor, history, mail, ticker, event feed, date, and time-control explanations corresponding to reference states 45–53. Read-only ticker and date labels can provide arrow anchors. When the speed controls hide the date, the date step points to the clock button and explains how to restore it. The in-game journey checks both states and passed 86/86 steps at 1518×836 and 800×600; the menu preview passed 88/88 at 1280×720, with zero geometry findings. The clock-fallback and menu-preview screenshots were inspected. These steps do not complete the reference scripted tutorial state machine.

## Tutorial mini-map actions (2026-11-01)

The mini-map navigation and zoom explanations use the live controls as arrow targets. A map gesture or zoom gesture advances its matching active guide step; unrelated and earlier gestures do not. Manual Next remains available, consistent with the source tutorial's allowance for clicking through these specific goals. `reference-tutorial-mini-map.json` exercises the real guide and mini-map together, including viewport requests and automatic transitions; it passed 15/15 at 800×600. The full guide passed 93/93 at 1518×836, and the independent mini-map journey passed 13/13 at 1280×720. Captured arrow geometry was reviewed. The remaining scripted tutorial sequence is still incomplete.

## Window dragging and live telemetry (2026-11-01)

Scenario telemetry normally pins window positions for deterministic geometry. An explicit `drag_window` operation now allows the selected window to move while checking its resulting coordinates. Live telemetry instead preserves ordinary user positioning. The hidden Arcade live-smoke test sent mouse events over multiple frames and observed a window move from (20, 20) to (80, 70); its screenshot is `artifacts/ui/reference/live-drag-smoke-20261101-rerun/actual.png`. The earlier Computer Use drag in the main game did not move Relations and remains inconclusive; it is not claimed as a successful live-game drag.

## Options autosave settings and save route (2026-11-01)

The source Profile tab now exposes the reference autosave toggle, incremental mode,
minute interval, and save name in their GML slots. `GameSettingsService`
persists these settings and the four-digit counter; changing the save name resets
the counter. `AutosaveScheduler` sends `ActionSaveGame` through the normal
client/server path after the configured elapsed interval, waits for that command
result before sending another save, and skips terminal non-sandbox campaigns.
Automatic save results stay quiet as in reference `DisplaySaveResult`; manual outcomes
continue to use `GenericMessageDialog`.

The settings journey passed 20/20 steps at 800×600 with zero layout findings and
no render errors. Its final screenshot was reviewed at
`artifacts/ui/reference/options-autosave-gameover-20261101/actual.png`. The focused
settings, campaign-presenter, command-feedback, and scheduler tests passed 29/29;
the scheduler integration test writes an actual `Autosave0000` slot through
`GameSession` and confirms the region table is present. Invalid slot names remain
rejected by OpenPower's save-path validation.
## Autosave filename validation (2026-11-01)

The enabled autosave filename is checked with the same `validate_save_name`
rule as the save writer. An invalid name stays in the staged draft, shows a red
inline warning in the source frame, and prevents Confirm from closing or saving
the settings. Back and title close still discard the draft. The scenario verifies
that correcting the name allows Confirm and persistence.

`reference-options-autosave-invalid-name.json` passed 11/11 at 800×600; its inline
warning and blocked-Confirm screenshot were reviewed at
`artifacts/ui/reference/options-autosave-invalid-rerun-20261101/checkpoints/005.png`.
The normal autosave settings journey passed 20/20 at 1280×720 with zero layout
findings; its final screen was reviewed at
`artifacts/ui/reference/options-autosave-valid-final-20261101/actual.png`. The focused
test set now passes 30/30.

## Unit research linked funding groups (2026-11-01)

The source `GCursorMeter::UpdateCursors` distributes a changed cursor's delta proportionally among unlocked linked cursors. The Python UI and authoritative `ResearchProgramSystem` now share that policy for the four main category ratios and the three strategic subtrack ratios. Applying a staged change sends only the changed OpenPower branch ratios.

Evidence:

- `tests/test_unit_research_funding.py` verifies both groups, zero-value peers, and locked peers.
- `tests/test_research_program_system.py::test_research_funding_actions_redistribute_authoritative_linked_groups` verifies the server-side single-action behavior.
- `tests/ui/journeys/reference-unit-research-linked-allocation.json` passed 28/28 steps at 1280x720 and 800x600 with zero layout findings and no render errors.
- Screenshots: `artifacts/ui/reference/unit-research-linked-1280x720/actual.png` and `artifacts/ui/reference/unit-research-linked-800x600/actual.png`. Both were reviewed.

The window remains partial: the source `NuclearReady()` gate has no exact OpenPower field, and per-characteristic research values and 3D assets are unavailable.

## Country profile uses OpenPower metric defaults (2026-11-01)

The country profile now resolves absent GDP, government-approval, and military-count snapshot values with OpenPower's native defaults before ranking candidates. reference-provided rank vectors are still unavailable, so the source ranking parity gap remains explicit.

Evidence:

- `tests/test_country_profile.py` verifies the defaults affect candidate ranks as expected.
- `tests/ui/journeys/reference-new-game-profile-defaults.json` passed 13/13 steps at 1280x720 and 800x600, with zero layout findings and no render errors.
- The selected-country rank bars and GML-sized profile were reviewed in `artifacts/ui/reference/new-game-profile-defaults-1280x720/checkpoints/008.png` and `artifacts/ui/reference/new-game-profile-defaults-800x600/checkpoints/008.png`.

## Movement refusal route and dormant denial object (2026-11-01)

The supplied source mirror registers `GUnitMovementDenialWindow` and defines a spawn factory, but has no external call to `UnitMovementDenialWindowSpawn`. Its `lstDenialList` is bound without a row-population path. The active reference refusal callback is `GDataControlLayer::ShowMovementRefused`, which opens `Generic_Message_Window`; OpenPower's `UnitOrderFeedback` follows that active route through `GenericMessageDialog`.

`reference-movement-refusal-feedback.json` passed 5/5 steps at 1280x720 and 800x600 with zero layout findings and no render errors. Both screenshots were reviewed: `artifacts/ui/reference/movement-refusal-active-route-1280x720/checkpoints/001.png` and `artifacts/ui/reference/movement-refusal-active-route-800x600/checkpoints/001.png`. The denial-list GML object is recorded as dormant; the tested generic-message route remains the implemented window path.

## Handler-only C++ navigation paths (2026-11-01)

The navigation audit now distinguishes exact GML widget paths from source event/call paths. A route with an extracted C++ handler or call site and no catalog-resolved GML widget is `verified_cpp`; its destination geometry remains unresolved until the geometry crosswalk measures it. This removes false `assumption/unknown` labels without claiming a GML widget or layout match.

The global D, U, C, W, B, R, and T shortcuts each have a source-reviewed C++ route and a passing journey in the 247/247 navigation suite. The D journey opens and closes Unit Reserves; the B journey opens Budget. Their reviewed captures show the Underployed Troops and Budget panels above the bottom HUD:

- `artifacts/ui/reference/navigation-final-continuation-20261028/reference-shortcut-d/checkpoints/001.png`
- `artifacts/ui/reference/navigation-final-continuation-20261028/reference-shortcut-b/checkpoints/001.png`

The D and B captures were visually reviewed; text and panel bounds are legible at the 1517x835 run size.

## Thematic map legend labels and routes (2026-11-01)

The focused map-legend suite covers opening the legend from the map-mode menu,
the GDP ranking and country-focus route, and the Empire key and country-focus
route. At 800x600 and 1280x720, all three journeys passed at each size. The
GDP journey now checks the RANK, COUNTRY, and REL headers plus HIGH/LOW gradient
labels and visible country tags.

The right-anchored GML legend frame and its country rows stayed within the
viewport. All six final screenshots were reviewed; no layout findings or render
errors were reported. Evidence is under
`artifacts/ui/reference/map-legend-crosswalk-800x600-20261101/` and
`artifacts/ui/reference/map-legend-crosswalk-1280x720-20261101/`.

The source localization bundle is absent, so the exact translated reference wording
remains unavailable. These checks verify the current OpenPower English labels
and map-mode data.

## Four-viewport UI regression and live playtest (2026-11-01)

The 11 layout-sensitive journeys for production, research, the unit list,
floating panels, main pillars, menu navigation, and the military guided tour
passed at 800x600, 1024x768, 1280x720, and 1920x1080 (44/44 total). Each run
reviewed 52 captures; the screenshot geometry reviewer reported no geometry
errors. `tests/test_ui_testability.py` passed 15/15 tests.

The full 253-journey suite at 800x600 was resumed after correcting the compact
geometry expectations and now passes 253/253. Its final review scanned 545
captures with no geometry errors. The same 11 focused journeys also passed at
1518x836; the reviewer scanned 52 captures with no geometry errors.

Source-relative control coordinates remain strict from 1280 pixels wide.
Compact-width runs still assert visibility and viewport containment because
the production and list panes compress their content at those sizes. The
source-size no-overlap checks for simultaneous floating panels also run from
1280 pixels wide; at 1024x768, the clamped Objectives window can overlap
Military when both are open. That overlap is retained with the current GML
anchors and is not covered by the compact-width no-overlap assertion.

A live Open Sandbox session as Ukraine was started at 1920x1080. Politics,
Military, Economy, Demographics, Treaties, and Unit Research were inspected on
the rendered map. Text and controls were readable in their GML-anchored
panels; the treaty proposal draft was closed without sending an action.

Artifacts: `artifacts/ui/reference/recheck-800x600b-20261101/`,
`artifacts/ui/reference/recheck-1024x768-20261101/`,
`artifacts/ui/reference/recheck-1280x720-20261101/`,
`artifacts/ui/reference/recheck-1518x836-20261101/`,
`artifacts/ui/reference/recheck-1920x1080-20261101/`, and
`artifacts/ui/reference/full-matrix-800x600-20261101/`.
