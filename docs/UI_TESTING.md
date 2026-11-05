# Agent UI testing

The shared ImGui facade exposes panels, HUD, menus, editor UI, text, containers, images, plots, and custom drawing while recording is enabled. Native behavior is preserved outside telemetry frames.

## Commands

```powershell
openpower ui-test list
openpower ui-test run settings
openpower ui-test run game-hud --journey tests/ui/journeys/hud-budget.json
openpower ui-test run budget --journey tests/ui/journeys/budget.json
openpower ui-test run settings --journey tests/ui/journeys/settings.json
openpower ui-test run economic-health --journey tests/ui/journeys/debt-input.json
openpower ui-test all --matrix --output artifacts/ui/matrix
openpower ui-test all --rerun-failed --output artifacts/ui/matrix
openpower ui-test live-smoke
```

Use `.\.venv\Scripts\python.exe main.py` instead of `openpower` if the entry point is not installed. `list` reads the production panel registry plus game HUD, editor HUD, map context, unit context, and unit details. New registered panels automatically join the catalog.

`run` writes to `artifacts/ui/<surface>` unless `--output` is supplied. `all` isolates each run in a subprocess and writes `suite.json`; failures do not stop other surfaces. The matrix covers 800×600, 1024×768, 1280×720, and 1920×1080. Use `--width` and `--height` for other sizes. `--rerun-failed` repeats the failing surface/size pairs from the existing suite report.

Exit code 0 means the scenario, geometry checks, screenshots, and any visual comparison passed; 1 means a failed run; 2 means invalid arguments or setup failure.

## Agent artifacts and repair workflow

- `actual.png`: final rendered framebuffer.
- `overlay.png`: numbered bounding boxes for visible interactive controls.
- `report.json`: checks, interaction steps, engine log, layout findings, submitted actions, fixture details, and telemetry. `overlay.legend` maps screenshot numbers to IDs and source locations.
- `diff.png`: visual differences when a baseline is supplied.

Widgets include semantic and native IDs, type, label, value, enabled/visible/present state, rectangle, parent region, and `source.path/line/function`. Vector inputs expose component IDs and rectangles; combo and list-box controls expose their options. Absent widgets become invisible rather than retaining stale visible state; historical `ever_visible` and `ever_enabled` observations remain available.

Rectangles use logical ImGui coordinates from the viewport's top left. `overlay.framebuffer_scale` converts them to screenshot pixels. Draw commands and plots describe visual geometry and are not assumed to be clickable controls.

The agent reads the report, locates the rendering code, changes its layout or styling, reruns the same fixture/journey, and inspects the new screenshot and diagnostics. Generated reports are ignored by Git; versioned baselines can live in `tests/ui/golden/`.

Diagnostics detect invalid or negative dimensions, zero-size controls, off-screen windows, duplicate native IDs, partially clipped controls, and overlapping sibling controls. Geometry and identity errors fail the run. Clipping and overlap are warnings because scrolling and deliberate overlays are valid patterns. Use explicit journey assertions for critical controls. Geometry checks do not prove glyph readability; inspect screenshots for typography and appearance.

## JSON journeys and fixtures

```json
{"steps": [
  {"op": "check", "target": {"label": "Reduce motion", "type": "checkbox"}, "value": true},
  {"op": "assert", "target": {"label": "Reduce motion", "type": "checkbox"}, "value": true},
  {"op": "input", "target": {"label": "Windowed resolution", "type": "input_int2"}, "value": [1600, 900]}
]}
```

`target` is an exact ID or a selector with `id`, `label`, `type`, `source` (path substring), and/or `region` (ancestor ID or label). Ambiguous selectors fail with matching IDs instead of choosing an arbitrary control.

`relative_to` and `relative_rect` compare source-relative geometry. Add `relative_rect_min_viewport_width` or `relative_rect_min_viewport_height` when responsive compact layouts intentionally move or compress controls; visibility and viewport checks still run at every size.

`drag_window` targets an exact semantic window ID with `dx` and `dy` in logical pixels. It drags from the native title bar over several frames and checks the resulting position within three pixels. It temporarily permits that window to move in the otherwise pinned scenario telemetry. Use a reachable destination inside the viewport.

Operations are `click`, `close_window`, `input`, `replace` (text replacement in an already focused input), `drag` (fraction 0..1 for custom invisible-button sliders), `hold`, `open`, `check`, `select` (option label or index in `value`), `scroll`, `key`, `wait`, `assert`, `assert_region`, `assert_absent`, and `assert_action`. A hold uses `frames` (1–600) or `duration_ms` (1–10000) to keep a control pressed; use elapsed time when verifying time-based repeat behavior across different render rates. `close_window` targets an exact semantic window ID and clicks its title-bar close control. Keys use ImGui names such as `escape`. Widget assertions can check `visible`, `enabled`, `value`, `type`, `label`, `min_width`, `min_height`, `inside` a region ID, and `no_overlap` with another selector. `assert_region` checks a `WindowManager.window` or other semantic region by its exact ID and can verify `visible`, `kind`, `label`, `min_width`, and `min_height`. Action assertions check type, count, and dotted fields such as `allocations.personal_income_tax_rate`, with optional numeric `tolerance`.

The deterministic sample world uses a recording client and in-memory settings. These scenarios verify UI behavior and command dispatch, without claiming to verify server simulation. `--fixture file.json` replaces tables and overrides globals or time:

```json
{"tables": {"units": [{"id": "unit-1", "owner": "UKR", "region_id": 1, "strength": 1000}]}, "globals": {"tick": 0}}
```

Journeys can declare a project-relative `fixture` path in their JSON; an explicit `--fixture` argument takes precedence. Registered schemas normalize supplied rows; empty lists retain typed empty tables. Supply representative data for loaded, empty, disabled, error, foreign-country, and long-list states. A smoke fixture does not cover every game state.

For gameplay-surface fixtures, `test_support.player_country` sets the recording
client's controlled country and `test_support.selected_region_id` selects the
region used to resolve the initial country context. These fields let journeys
exercise actions from an opposing player's view without changing game data.

## Instrumenting new widgets

```python
from src.client.ui.core.instrumented_imgui import imgui

changed, value = imgui.checkbox("Reduce motion", value, test_id="settings.reduce_motion")
```

Explicit interactive IDs create native `###` identities independent of visible labels. Repeated rows should use domain keys, for example `test_id=f"unit.{unit_id}.select"`. Native functions and enums remain available through the facade.

Existing calls get automatic semantic IDs from source function, API call order, container, pushed ID scope, and hidden label suffix. Changing numeric values or translating visible labels does not change these IDs. Inserting another call of the same API earlier in the function or reordering unkeyed rows can change automatic IDs; use explicit IDs for durable journeys.

HUD toggles use `hud.panel.<lowercase-registry-id>`; system controls use `hud.system.<action-id>`. Other navigation anchors include `hud.country`, `hud.clock`, `hud.pause`, `hud.speed.<level>`, and `economy.budget_btn`. `UIRunTelemetry.frame()` can record any renderer, and `UITestDriver` resolves the current native IDs. ImPlot calls use `core.instrumented_implot.implot`.

## Visual comparison

```powershell
openpower ui-test run settings --journey tests/ui/journeys/settings.json --baseline tests/ui/golden/settings.png --tolerance 0.03
```

Comparison smooths minor rasterization noise and measures the fraction of unmasked pixels with a substantial color difference. Tolerance ranges from 0 to 1. Image-size differences fail explicitly. A journey may provide `visual_masks`: `{x, y, width, height}` rectangles in screenshot pixels for clocks or animated areas. The report contains the ratio, threshold, baseline path, and diff image. Baselines are never updated automatically.

## Inspect and control the actual game

Catalog surfaces load the same `fonts/main_font.ttf` asset and logical base size as
the Arcade client through `FontLoader.configure_ui`. The selected font is recorded
in `runtime.font`; screenshots made with the default ImGui font are not evidence
for the game's text metrics.

Source layout widgets require an explicit `gml_id`. Never infer a binding from a
visible label, a live value, or the previous widget: extra country data must not
consume another field's coordinates. Use `gml_child_frame` for flowing lists and
`GMLWidgets` for fixed source fields. Source windows use compact font and padding
metrics through `gml_style` so controls fit their source rectangles.

Geometry validation also rejects overlapping text and text covering buttons,
including disabled actions. This is separate from the visibility and navigation
checks; passing those checks alone does not establish readable layout.

Every visible `assert_region` in a journey now captures `checkpoints/<step>.png`
and the corresponding telemetry JSON. Geometry errors in any checkpoint fail
`journey.checkpoint_geometry`, even if that dialog closes before `actual.png`.

Run the maintained navigation suite and build contact sheets for visual review:

```powershell
.\.venv\Scripts\python.exe utils/run_ui_journeys.py tests/ui/reference-navigation-suite.json --output artifacts/ui/reference/navigation-final
.\.venv\Scripts\python.exe utils/run_ui_journeys.py tests/ui/reference-unit-order-targeting-suite.json --output artifacts/ui/reference/unit-order-targeting
.\.venv\Scripts\python.exe -m utils.review_ui_screenshots artifacts/ui/reference/navigation-final/suite.json --output artifacts/ui/reference/navigation-final-review
```

`--rerun-failed` resumes failed runs in the selected output directory. Use a fresh
directory when implementation changes require new evidence for previously passing
scenarios. `tests/ui/reference-navigation-boundaries.json` contains the focused scenarios
for repeating at 800×600, 1024×768, and 1920×1080.

The compact tutorial suite checks that the guide yields to full-width military
panels at 800×600 and resumes on the same step when each panel closes:

```powershell
.\.venv\Scripts\python.exe utils/run_ui_journeys.py tests/ui/reference-tutorial-compact-viewport-suite.json --output artifacts/ui/reference/tutorial-compact-viewport --width 800 --height 600
```

The report records both the requested and actual drawable viewport. A mismatch
fails `runtime.viewport`: desktop work-area clamping previously reduced 1920×1080
to 1920×1020 while reports retained the requested dimensions. Borderless fixtures
reapply their client size after creation. Historical matrix results without this
check are not proof of exact viewport dimensions.

`navigation_route_bindings.json` records reviewed source call sites separately:
callbacks sharing a C++ handler are distinguished by file, line, and destination.
Unsupported callbacks stay explicit gaps; opening their destination manually does
not verify their trigger or context. Alternative input validation is reported
separately from a literal source navigation route.

`tests/ui/journeys/main-bar-layout.json` checks Main_Bar's source offsets with
`relative_to` and `relative_rect` assertions, including the separate primary panel
toggles, clock, news button, and the expanded speed controls. Central content
retains source offsets relative to the cropped source area at x=176. Run this journey at
800×600, 1024×768, 1280×720, and 1920×1080 after changing the bottom HUD.

```powershell
$env:OPENPOWER_UI_ARTIFACTS = "C:\ProgramData\DEV\OpenPower\artifacts\ui\live"
.\.venv\Scripts\python.exe main.py
```

The existing Arcade `ImGuiService` records UI frames and exports JSON, screenshot, and overlay about twice per second. This includes main menu, loading, and new-game screens outside the standalone catalog. Remove the environment variable to disable the bridge.

Write `commands.json` in that directory, preferably by atomic replacement:

```json
{"commands": [
  {"id": "unique-request-001", "op": "click", "target": "hud.panel.eco"},
  {"id": "unique-request-002", "op": "input", "target": "budget.income_tax_rate", "value": 35}
]}
```

Live operations are `click`, `input`, `drag`, `pointer_drag`, `scroll` (optional wheel `amount`), and `key`. `click`, `input`, `drag`, and `scroll` target visible, enabled interactive controls. Vector input accepts a list. `pointer_drag` dispatches a real window mouse gesture and does not require a widget target; provide `start` and `end` points in logical window coordinates with a top-left origin. The optional `button` is `left` (default), `right`, or `middle`; `steps` controls interpolation frames and defaults to 8 (valid range 1–120). For example:

```json
{"commands": [{
  "id": "move-unit-on-map",
  "op": "pointer_drag",
  "start": {"x": 820, "y": 410},
  "end": {"x": 1040, "y": 520},
  "button": "left",
  "steps": 10
}]}
```

Native IO events are delivered over multiple frames, with acknowledgements in `report.json.commands`. Unique IDs are deduplicated across view changes through `receipts.json`. A `dispatched` acknowledgement confirms input delivery; verify the resulting widget value or game state separately. A context replacement before acknowledgement is reported as interrupted.

The real client also exports `game`: current view, authoritative simulation tick/date, pause and speed, selected country budget fields, table sizes, recent command results, and system errors. Use this to confirm a command reached the simulation. `frame_timing_ms` summarizes the last 240 rendered frame intervals; these include inspection overhead and are practical diagnostics, not benchmark gates. Screenshots, overlays, and JSON serialization run on an artifact worker, with one export in flight to prevent a backlog.

These interactions operate the real game and can trigger its usual actions, saves, and navigation. The bridge is opt-in and local. Live telemetry preserves normal window positioning. `ui-test live-smoke` verifies the protocol in a hidden real Arcade window by changing a checkbox and text field, dragging the window through Arcade mouse events, and capturing the framebuffer.

## reference Budget scenario

Run the Budget panel interaction scenario from the project root:

```powershell
openpower ui-test budget
```

The command opens a 1280×1000 Hello ImGui window, runs the scenario through Dear ImGui Test Engine, then exits. It writes `report.json` and `actual.png` under `artifacts/ui/budget`. Use `--width`, `--height`, and `--output` to change the viewport or artifact directory.

The report contains the Test Engine status, scenario checks, the submitted `ActionUpdateBudget`, and semantic layout telemetry. Each widget record includes its stable `id`, visible label, type, enabled and visible state, last rectangle, parent region, and whether the widget was ever visible or enabled during the run. Rectangles use ImGui screen coordinates in logical units, with the origin at the top left.

## Adding testable widgets

Use `test_id` on `UIPrimitives.button`, `UIPrimitives.slider_float`, or `UIPrimitives.invisible_button`. The wrapper gives the widget an ImGui `###` identifier, so changing its visible label does not change its underlying ID. Optional telemetry is collected only while a `UIRunTelemetry.frame()` is active.

Pass `test_id` to `WindowManager.window` to expose a semantic region and its rectangle. Interactive tests can use `UITestDriver` to address controls by stable ID. It clicks the recorded rectangle and resolves the live native ImGui ID for value input, including controls nested inside menus or child windows. Tests do not need to hard-code localized labels. Widget telemetry also includes this native `imgui_id`.

The Budget scenario enters a 35 percent income tax rate, drags infrastructure allocation to 70 percent, and clicks Apply. It checks the dispatched command using a recording client; simulation and server snapshot updates are outside this scenario. Exit code 0 means all interaction and layout checks passed and the screenshot was saved; failures return 1.

The Python Test Engine is initialized through Hello ImGui because its runner manages the threading needed by the Python bindings. The harness uses the APIs available in the project's installed `imgui-bundle`; it does not depend on the newer `immapp.testing` convenience module.

## Identity policy and bilateral trade journeys

The synthetic fixture `tests/ui/fixtures/identity-trade.json` supplies two countries, identity groups, regions, research and pending deals. Its values are UI test data, not demographic statistics.

```powershell
.\.venv\Scripts\python.exe main.py ui-test run internal-laws --fixture tests/ui/fixtures/identity-trade.json --journey tests/ui/journeys/identity-policy.json --output artifacts/ui/identity-policy --width 1280 --height 720
.\.venv\Scripts\python.exe main.py ui-test run trade --fixture tests/ui/fixtures/identity-trade.json --journey tests/ui/journeys/bilateral-trade.json --output artifacts/ui/bilateral-trade --width 1280 --height 720
```

Repeat with `--width 800 --height 600` for the smaller viewport. Identity controls use `identity.*` IDs, navigation uses `laws.*`, and trade controls use `trade.*`. These journeys check visibility, disabled aggregate controls, source details and exact dispatched actions. The recording client does not settle deals; simulation behavior is covered by `tests/test_identity_bilateral_workflows.py`.

## Incoming events and snapshots

Journeys can explicitly simulate delivery from a server through the recording
client. `server_event` appends one domain event using `target` (event type),
`event_id`, and `payload`. `server_snapshot` loads `fixture` (a UTF-8 JSON path)
and replaces its named tables, then appends its journal records in the same step.
These operations change test fixtures only; production panels still consume
snapshots and dispatch actions through their ordinary ports.

`tests/ui/reference-treaty-lifecycle-suite.json` exercises a stale mail selection,
removal during participant editing, and activation of the exact inspected
proposal. Its snapshots carry `EventTreatyLifecycleChanged.proposal_id`, matching
the server's proposal-to-agreement link. Assertions check the notice, disabled
editing, one-shot delivery and close-on-acknowledgement behavior.

## Selected battle inspection

The `battle-map` surface composes the actual BattleEffectRenderer, camera and
GameLayout. Its test input overlay sends a clicked label through the renderer's
hit test and the same GameLayout selection entry point used by GameView.
`tests/ui/reference-battle-inspection-suite.json` covers participant commands, a foreign
observer and the inspected combat's final-update summary. Events and snapshots
are fixture delivery; this surface does not run an Arcade world or live server.

Battle_Window retains its 1024x768 coordinate canvas. Smaller viewports expose
scrollbars; the `scroll` operation brings a source control into view on both
axes before input. Hello ImGui's own borderless close/drag/resize overlays are
disabled so they cannot intercept game controls at the fixture viewport edge.

## Map-attached information

`map-information` uses deterministic projected hit targets with the production
UnitInteractionController and MapInformationWindows. It exercises single/multiple
selection, snapshot removal, foreign unknown values and held Tab over region/ocean
hits. `hover`, `key_down` and `key_up` journey operations preserve real pointer/key
state across assertions. Use tests/ui/reference-map-information-suite.json at all four
viewports. The input fixture does not replace an Arcade live-map playtest.

Check the pixels as well as region telemetry: an unfocused window can have valid
geometry while another window covers it. Review intermediate screenshots before
classifying the route complete. The region-control overlay uses the native tooltip
display layer and no inputs; the unit composition frame stays below normal panels.

## Neutral-territory movement

`unit-movement` feeds production UnitInteractionController movement requests into
UnitMoveOrders and the source-sized confirmation dialog. The invasion suite covers
cancel, accumulating requests, independent country queues, stale controller and
server refusal. Deterministic request buttons are not an Arcade drag playtest.
The territory-entry Python tests separately run actual diplomacy/military systems
inside Engine.step and verify snapshot replay; other system dependencies are no-op
ports. Use tests/ui/reference-unit-invasion-suite.json at all four required viewports.

## Party constitutional confirmation verification (2026-10-20)

Run the four focused journeys serially with:

```powershell
.venv\Scripts\python.exe utils/run_ui_journeys.py tests/ui/party-constitution-suite.json --output artifacts/ui/reference/party-constitution/1280x720 --width 1280 --height 720
```

Fresh results: 16/16 native fixture runs across the four requested sizes and 24
reviewed captures, without geometry errors. The cases cover Yes followed by Apply,
No restoring the previous draft, the reverse transition, and a government change
while the question is open. The 154-test Python regression set covers authoritative
validation, atomic rejection, transition side effects and existing political flows.
The 129-report combined index reuses earlier results and is not a fresh suite run.

## Selected-group training confirmation (2026-10-20)

`tests/ui/unit-training-suite.json` contains Yes, No, changed-estimate and unavailable
training journeys. Fresh runs passed at all four requested sizes (16/16); eight
unit reorganization journeys passed again at 1280x720. Review directories under
artifacts/ui/reference/unit-training contain all 33 reviewed captures and zero geometry
errors. The 183-test regression run passed with one opt-in benchmark skipped;
38 focused tests passed after the last guard/tooltip edits. New unit_training_quotes
fixture rows represent published server data. Fixtures do not calculate those terms
or apply dispatched training commands; server tests separately verify charges,
rejection and snapshot persistence.

## Covert mission readiness and exact cell selection (2026-10-20)

Use tests/ui/covert-ready-suite.json with utils/run_ui_journeys.py. The twelve cases
passed serially at all four requested viewports (48/48); all 72 captures were
reviewed with zero geometry errors. Evidence is below artifacts/ui/reference/covert-ready.
The 131-test regression set passed with 19 subtests and one skipped opt-in benchmark.
The cases cover ready mail, exact selection and scroll, execute/cancel, stale data,
retirement, server rejection, foreign privacy and existing create/train/prepare forms.
Authoritative tests separately cover readiness, single execution, authority/access
refusal, cancellation, retirement and snapshot persistence. UI fixtures record
commands and deliver explicit snapshots; they do not simulate those commands.
The combined 142-report index reuses older results and is not a fresh full-suite run.

## Conditional Game Over result

`tests/ui/reference-game-over-suite.json` covers defeat, victory, title-close return,
and sandbox continuation. The terminal dialog uses OpenPower campaign outcome and
objective data in the 503×273 `Game_Over_Window` frame; both title close and Main
Menu use the existing `NavigationService.stop_game` route. Sandbox continuation
keeps the game open and leaves the outcome in Objectives.

Run the focused journeys at compact and wide viewports:

```powershell
.\.venv\Scripts\python.exe utils/run_ui_journeys.py tests/ui/reference-game-over-suite.json --output artifacts/ui/reference/game-over-parity-800x600-20261029 --width 800 --height 600
.\.venv\Scripts\python.exe utils/run_ui_journeys.py tests/ui/reference-game-over-suite.json --output artifacts/ui/reference/game-over-parity-1518x836-20261029 --width 1518 --height 836
```

All 8 runs passed with zero geometry findings or render errors. Review the initial
dialog captures under each journey's `checkpoints/`; the final framebuffer after
returning to the menu may be black because the harness records the navigation
request while stopping the game session. Ranking formulas, localized result copy,
and exact source deadline presentation still differ from reference.

## Covert multi-cell selection

The covert roster now uses the GML `MultiExtended` behavior: click replaces the
selection, Ctrl toggles a row, and Shift selects a contiguous range. Group mission,
training, and retirement controls send the existing authoritative action once per
selected cell. Mission payloads retain each cell's own target country.

Run the dedicated journey and the existing covert readiness suite:

```powershell
uv run --frozen python utils/run_ui_journeys.py tests/ui/reference-covert-multi-cell-suite.json --output artifacts/ui/reference/covert-multi-cell-800x600-20261029 --width 800 --height 600
uv run --frozen python utils/run_ui_journeys.py tests/ui/reference-covert-multi-cell-suite.json --output artifacts/ui/reference/covert-multi-cell-1518x836-20261029 --width 1518 --height 836
uv run --frozen python utils/run_ui_journeys.py tests/ui/covert-ready-suite.json --output artifacts/ui/reference/covert-ready-regression-1280x720-20261029 --width 1280 --height 720
uv run --frozen python -m pytest -q tests/test_covert_selection.py
```

The multi-cell journey passed 37/37 steps at both sizes. It asserts two mission
actions with different target countries, two training actions, and two retirement
actions, plus mission cancellation and both training dismissal routes. The
selection unit tests passed 7/7; the 12-journey readiness suite passed 12/12 at
1280×720. The creation and training title-close routes are verified. Narrow
modal roots retain their exact GML dimensions; only the shared title close hitbox
is clamped when the extracted source rectangle falls outside the root. Reviewed
training-dialog captures at 800×600 and 1518×836 show the close control in the
upper-right corner. No geometry or render errors occurred; each multi-cell report
retains two 1 px warnings where assigned-country and status controls meet in roster
rows.

## Covert outcome dismissal

The master `reference-covert-outcomes` journey passed 16/16 steps at 1517×835 with zero
layout findings or render errors. The own-country result closes through its GML
title Exit; the attacked-operation result closes through its explicit `btnExit`.
Reviewed captures are `artifacts/ui/reference/navigation-final-continuation-20261028/reference-covert-outcomes/checkpoints/003.png`
and `artifacts/ui/reference/navigation-final-continuation-20261028/reference-covert-outcomes/checkpoints/010.png`.

## Saved-game selection and dispatch

`tests/ui/load-game-suite.json` uses a test-only save-slot metadata fixture. The
journey enters the single-player menu, opens Load Game, selects the fixture slot,
checks that Load becomes enabled, and asserts the exact `load_saved_game` request
before confirming the dialog closes. It tests UI dispatch through
`RecordingNavigation`; it does not read a save file or execute `LoadGameTask`.

Run at compact and wide viewports:

```powershell
uv run --frozen python utils/run_ui_journeys.py tests/ui/load-game-suite.json --output artifacts/ui/reference/load-game-800x600-20261029 --width 800 --height 600
uv run --frozen python utils/run_ui_journeys.py tests/ui/load-game-suite.json --output artifacts/ui/reference/load-game-1518x836-20261029 --width 1518 --height 836
```

Both reports pass 10/10 steps with zero geometry findings, warnings, or render
errors. Reviewed dialog captures are
`artifacts/ui/reference/load-game-800x600-20261029/load-game-success/checkpoints/003.png`
and
`artifacts/ui/reference/load-game-1518x836-20261029/load-game-success/checkpoints/003.png`.
