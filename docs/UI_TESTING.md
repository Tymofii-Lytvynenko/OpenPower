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

Operations are `click`, `input`, `drag` (fraction 0..1 for custom invisible-button sliders), `open`, `check`, `select` (option label or index in `value`), `scroll`, `key`, `wait`, `assert`, `assert_absent`, and `assert_action`. Keys use ImGui names such as `escape`. Assertions can check `visible`, `enabled`, `value`, `type`, `label`, `min_width`, `min_height`, `inside` a region ID, and `no_overlap` with another selector. Action assertions check type, count, and dotted fields such as `allocations.personal_income_tax_rate`, with optional numeric `tolerance`.

The deterministic sample world uses a recording client and in-memory settings. These scenarios verify UI behavior and command dispatch, without claiming to verify server simulation. `--fixture file.json` replaces tables and overrides globals or time:

```json
{"tables": {"units": [{"id": "unit-1", "owner": "UKR", "region_id": 1, "strength": 1000}]}, "globals": {"tick": 0}}
```

Registered schemas normalize supplied rows; empty lists retain typed empty tables. Supply representative data for loaded, empty, disabled, error, foreign-country, and long-list states. A smoke fixture does not cover every game state.

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

Live operations are `click`, `input`, `drag`, `scroll` (optional wheel `amount`), and `key`. Targets must be visible, enabled interactive controls. Vector input accepts a list. Native IO events are delivered over multiple frames, with acknowledgements in `report.json.commands`. Unique IDs are deduplicated across view changes through `receipts.json`. A `dispatched` acknowledgement confirms input delivery; verify the resulting widget value or game state separately. A context replacement before acknowledgement is reported as interrupted.

The real client also exports `game`: current view, authoritative simulation tick/date, pause and speed, selected country budget fields, table sizes, recent command results, and system errors. Use this to confirm a command reached the simulation. `frame_timing_ms` summarizes the last 240 rendered frame intervals; these include inspection overhead and are practical diagnostics, not benchmark gates. Screenshots, overlays, and JSON serialization run on an artifact worker, with one export in flight to prevent a backlog.

These interactions operate the real game and can trigger its usual actions, saves, and navigation. The bridge is opt-in and local. `ui-test live-smoke` verifies the protocol in a hidden real Arcade window by changing a checkbox and text field and capturing the framebuffer.

## Original Budget scenario

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
