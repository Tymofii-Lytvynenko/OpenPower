# Quickstart: Tactical Battle Visualization

This guide validates the feature after implementation. It covers the authoritative mode/anchor contract, globe projection, smooth presentation timing, lifecycle behavior, and the 100-battle performance budget.

## Prerequisites

- Python 3.10 or newer.
- Project dependencies installed (`pip install -e .` and the development test dependencies used by the repository).
- A local game session that can create two hostile units in one region and issue an attack order.

## Focused automated validation

From the repository root, run:

```powershell
.venv\Scripts\python.exe -m pytest `
  tests/test_battle_anchor_policy.py `
  tests/test_globe_overlay_projection.py `
  tests/test_battle_effect_renderer.py `
  tests/test_battle_effect_performance.py `
  tests/test_engagement_mvp.py `
  tests/test_battle_status_interface.py `
  tests/test_client_snapshot_performance.py
```

Expected outcomes:

- a proximity contact remains `positional`/Passive and uses a stable contact or region fallback anchor;
- an accepted attack changes the same battle to `assault`/Active without changing its ID or anchor;
- projection hides back-facing anchors, preserves bounded front-facing markers, and culls decorative geometry that cannot fit within the globe edge;
- phase values advance smoothly from presentation time, are deterministic, and freeze under reduced motion;
- concluded/stalemated rows stop combat effects;
- battle markers remain visible when unit billboards are filtered;
- the existing snapshot/presenter budget remains intact, and a warmed-up repeated baseline-versus-feature render benchmark keeps 100 simultaneous battles within the feature’s five-percent median frame-time overhead target.

The render benchmark must warm up both paths, collect the same number of repeated baseline and 100-battle samples, compare their medians, and report both medians plus the calculated percentage overhead. The snapshot/presenter test remains a separate transport regression and is not accepted as evidence of frame-time overhead.

In headless validation, the benchmark's overlay-free baseline is the existing CPU unit-projection pass for 100 ordinary billboards; the feature sample adds 100 battle-anchor projections, label placement, and no-op ImGui draw-command dispatch. This is a comparable CPU-path diagnostic, not a measurement of the complete GPU-backed client frame. A result from this proxy cannot pass SC-007; verify the five-percent frame-time target in the running client with the same scene and record the real frame medians separately.

If the project environment does not provide `.venv`, run the same command with `python -m pytest` after installing the test dependencies.

## Manual map validation

1. Launch the normal client with `python main.py` (or the installed `openpower` entry point).
2. Create or load a scenario with two hostile armies close enough to enter the engagement radius without an attack order. Confirm a restrained marker appears at the meeting point and the battle panel says Passive/Positional.
3. Issue an accepted attack order for one participant. Confirm the same marker stays at the same geographic point while the effect becomes visibly stronger and the panel says Active/Assault.
4. Execute the globe acceptance matrix: yaw at 45-degree intervals; pitch at `-60`, `-30`, `0`, `30`, and `60` degrees; minimum, midpoint, and maximum supported zoom; plus anchors immediately on both sides of the longitude seam. Confirm back-facing effects disappear, every front-facing battle keeps its bounded static marker, decorative motion is omitted before it can cross the silhouette, no geometry crosses the hidden hemisphere or seam, and screen footprints remain bounded.
5. Hide one or both owners in the unit filter. Confirm the battle marker and state label remain available while the authoritative battle row is visible.
6. Wait for stalemate or conclusion. Confirm the combat animation stops immediately after the state update; any conclusion cue disappears within one second.
7. Enable reduced motion in settings. Confirm movement/flashes are suppressed but the marker, side colors, mode label, and focus control remain usable.

## Passive/Active user acceptance protocol

1. Prepare 20 battle displays with labels and raw battle data hidden: 10 authoritative `positional` cases and 10 authoritative `assault` cases. Randomize their order independently for each participant.
2. Recruit at least 10 representative players. Record only an anonymous participant identifier and each Passive/Active classification.
3. Collect exactly one classification for every display from every participant, producing at least 200 judgments.
4. Count correct classifications against the authoritative mode. The criterion passes when at least 190 of the first 200 judgments are correct.
5. Record the scenario set, participant count, correct count, total count, percentage, and pass/fail result in the validation results section without collecting unrelated personal data.

## Validation results

On 2026-10-07, the focused anchor, projection, renderer, performance, combat,
status, and snapshot suite reported `28 passed in 0.97s`. The latest
repository-wide automated suite reported `684 passed, 16 skipped, 116 warnings,
190 subtests passed in 162.89s`; the warnings are the existing Pyglet
`ctypes._pointer_type_cache` deprecation warning.

Three repeated warmed headless CPU-proxy runs measured overlay-free / 100-battle
medians of `1.166 / 7.812 ms` (`570.16%`), `1.184 / 7.911 ms` (`568.35%`), and
`1.175 / 7.660 ms` (`551.77%`). The median run measured `1.175 / 7.812 ms` and
`568.35%` overhead. This proxy intentionally excludes the rest of the
GPU-backed client frame and discards draw commands; it is diagnostic evidence,
not a pass or substitute for in-client SC-007 measurement. Renderer inspection
found revision-cached table normalization, batched anchor projection, and
bounded spatial occupancy; no repeated per-frame Polars conversion or
all-pairs rectangle scan remains. Record the elevated proxy cost as a follow-up
performance issue, but do not treat this CPU-only ratio as the actual frame-time
gate or spend optimization iterations without an in-client profile.

Automated globe projection tests cover the yaw/pitch/zoom/seam matrix. The
interactive globe scenarios, real frame-time gate, and blinded 200-judgment
Passive/Active protocol remain open and require a running client and human
participants; the feature is not fully empirically accepted until those results
are recorded.

Refer to [data-model.md](data-model.md) for anchor and lifecycle semantics and [contracts/battle-visualization.md](contracts/battle-visualization.md) for the renderer input/visibility contract.
