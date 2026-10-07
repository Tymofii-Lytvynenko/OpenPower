# Tasks: Treaty and Diplomatic Map Overlay

## Phase 1: Data and relationship correctness

- [X] T001 Add a loader regression for base treaty and war files and correct the war collection key in `modules/base/data/world/countries_wars.toml`.
- [X] T002 Color only active, non-expired treaty members and active war belligerents; exclude suspended members while preserving active legacy rows without status in `src/client/utils/diplomacy_utils.py`.
- [X] T003 Cover selected, allied, overlapping-alliance, enemy, neutral, suspended, expired, ended-war, occupied, annexation-pending, and changed-controller map states in `tests/test_empire_map_mode.py`.

## Phase 2: GPU palette transition and focus performance

- [X] T004 Add prior/target lookup textures, bounded eased transition progress, continuity during retargeting, and target-palette selection alpha in `src/client/renderers/texture_manager.py`, `src/client/renderers/map_renderer.py`, and `src/client/renderers/shaders/globe.frag`.
- [X] T005 Reuse region groups while ordered ID/owner/controller values remain stable and verify focus/color recalculation on the 4,559-region fixture; latest alternating-focus median 0.792 ms on the 12-thread pool.
- [X] T006 Add shader/LUT headless contracts and fake-texture interpolation/retarget tests in `tests/test_map_rendering_pipeline.py`.

## Phase 3: Integrated acceptance

- [X] T007 Run the complete repository suite after current changes; latest result: 684 passed, 16 skipped, 116 warnings, 190 subtests passed in 162.89 seconds.
- [ ] T008 Validate focus selection and globe rendering in the running desktop client. The opt-in GPU check now compiles the production globe shader pair and renders the production fragment shader to verify transition blending, border darkening, and selection highlighting; actual globe geometry, interactive picking, and on-screen focus behavior remain unverified.

## Exit criteria

Data loading, deterministic diplomacy classification, LUT interpolation contracts, and SC-002 timing are covered. The feature remains open until full-suite and interactive GPU acceptance are recorded.
