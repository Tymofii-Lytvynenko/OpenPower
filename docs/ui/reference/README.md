# reference implementation UI functional mapping

Generated from the resolved UI catalog and OpenPower's mapping audit. OpenPower mappings are read from the current `PanelSpec` registry plus explicit review aliases in `utils/reference_ui_audit.py`.

The OpenPower implementation is Python under `src/client/ui`. Layout and behavior evidence is read-only; it is not an implementation target.

## Audit result

- GML definitions: 220; object nodes including children: 3803; resolved catalog nodes: 3803.
- Candidate window roots: 92; status counts: `{"reachable": 45, "unknown": 17, "conditional": 26, "unused": 4}`.
- OpenPower window mapping evidence: `{"verified_openpower": 31, "partial": 53, "verified_unavailable": 8}`.
- Component rows: 3014; dynamic C++ creation sites: 144.
- Window-spawn navigation edges: 176 verified call paths; 71 map to an exact GML widget path and 105 are handler-level only.
- Reachable-window mapping evidence: `{"verified_openpower": 21, "partial": 24}`; reachable windows with missing or partial contracts: 20 (60 inbound-transition evidence rows in `unimplemented_windows.csv`).
- Dynamic creation sites with same-class receiver-specific geometry/visibility evidence: 57/144; detailed source locations are in `dynamic_components.csv`, and the rest need creator/update tracing.
- WindowSpawn call-site accounting: 153 total = 135 navigation/callback + 18 lifecycle; unaccounted: 0.
- Data contracts: 1366; interaction contracts: 911.
- Data evidence: `{"partial": 911, "assumption/unknown": 174, "verified_cpp": 78, "verified_openpower": 129, "verified_unavailable": 74}`; interaction evidence: `{"verified_openpower": 328, "partial": 226, "verified_unavailable": 271, "verified_cpp": 86}`.
- Gap rows: 2545 (candidate windows, display data, navigation edges, and interactive controls).
- Gap evidence: `{"verified_openpower": 620, "partial": 1208, "verified_unavailable": 371, "assumption/unknown": 255, "verified_cpp": 91}`.
- Transition journey coverage: 176 extracted C++ edges; statuses: `{"tested": 129, "tested_equivalent_validation": 7, "blocked_missing_workflow": 18, "reachable_route_test_missing": 2, "tested_shared_component_contract": 1, "journey_not_run": 1, "source_operation_missing": 4, "unreachable_source_branch": 1, "lifecycle_initialization": 3, "inactive_source_code": 1, "tested_equivalent_alternate_feedback": 2, "tested_equivalent_guided_tutorial": 7}`.
- Fixed-viewport geometry crosswalk: 64/176 source-widget routes have GML control coordinates plus measured Python destination geometry at 1280×720; see `layout_geometry_crosswalk.csv`.
- Unknown GML type references: 0; inheritance cycles: 0.

## Files

- `window_registry.csv`: candidate window roots, reachability evidence, GML size/sections, and OpenPower PanelSpec or layout-surface mapping.
- `component_tree.csv`: full resolved paths, parent/order, GML geometry, static enable/visibility, source binding and C++ member operations.
- `dynamic_components.csv`: `ObjectSpawn`/`CREATE_GUI_OBJECT` sites omitted from static GML trees, with same-class receiver-specific geometry/visibility calls and source locations where found.
- `navigation_graph.json`: extracted C++ window-spawn edges, exact conditions, mode, and source lines; only `verified_cpp` edges are treated as verified.
- `navigation_journey_coverage.csv`: journey or explicit gap status for every extracted C++ navigation edge.
- `layout_geometry_crosswalk.csv`: source GML widget/window geometry paired with tested Python control and destination rectangles at the fixed 1280×720 viewport, or an explicit unresolved status.
- `data_contracts.csv`: display components with GML tokens, C++ source/member operations, OpenPower binding and Python/schema source files, units, fallback, and update cadence status.
- `interaction_contracts.csv`: all GML interactive controls, C++ source, route, GameAction status, restrictions, and confirmation/error gaps.
- `generic_message_callback_map.csv`: every active Generic_Message_Window display call, its OK callback effects, OpenPower counterpart, and unsupported or partial routes.
- `gap_table.csv`: one row per candidate window, display-data contract, extracted transition, and interactive control, with its current OpenPower target and remaining action.
- `unimplemented_windows.csv`: inbound C++ evidence, current Python implementation, and remaining action for each incomplete reachable-window contract.
- `seed_transition_coverage.csv`: crosswalk for the 31 manually verified source transitions to Python UI journeys, clicks, destination assertions, and suite status. It covers this seed set only, not every extracted C++ edge.
- `audit_summary.json`: counts and parser validation diagnostics.
- `requirements_coverage.md`: implementation status, verification evidence, and requirements that remain open.

## Evidence policy

`verified_gml` means the node and its static geometry/token come from the resolved catalog and were checked against `layout_catalog.gml` counts. `verified_cpp` means a class/event/member path or call site is supported by the stored mapping evidence. In navigation rows, a handler-level `verified_cpp` route has no exact GML widget path; geometry remains unresolved unless the crosswalk measures it. `verified_openpower` means a concrete current panel/model binding is identified. `verified_unavailable` means the source value is known but no authoritative OpenPower field exists, so the implementation shows an explicit unavailable fallback. `assumption/unknown` marks unresolved or candidate equivalence. Numeric GML `Text` values are preserved as tokens and are not interpreted as visible copy.

`unused` means the window candidate has no active matching C++ `TypeName`, GUI registration, spawn method/call, or source reference in this mirror. Commented-out declarations do not count as runtime evidence. It describes only the evidence represented by these mapping tables. `conditional` means active C++ creates/spawns the window but it was not reached from the Main Bar/Main Menu click graph. `reachable` means a click-graph path from one of those roots was found.

The generated CSVs preserve unknown bindings as gaps. They do not invent missing game data, actions, restrictions, or error states. Geometry is GML-local and does not assert pixel-perfect equivalence in OpenPower.

## UI verification

- Historical surface matrix: 172/172 runs across 43 surfaces and four requested viewport sizes. Earlier runs did not validate the actual native viewport; see navigation_verification.md for the correction and current evidence. The merged `suite.json` points to the latest reports for surfaces rerun after layout fixes.
- Current journey suite: 253/253 JSON journeys, including 234 exact GameAction assertions. 20 historical focused functional journeys passed their requested-size matrices (0/0 runs).
- Manually verified seed-transition journey coverage: `{"tested": 31}`.
- Crosswalk click IDs are OpenPower controls reviewed as equivalents for the source paths; they are not GML widget IDs.
- Journey fixtures cover directed Relations values/history, treaty details, and covert-cell workflows; reviewed runs include action dispatch and geometry evidence.
- Raw screenshots, logs, and reports are temporary run artifacts; the generated audit tables preserve the reviewed results.
- See `requirements_coverage.md` for remaining evidence and parity gaps; passing geometry tests do not establish functional equivalence for unresolved contracts.
