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

Record automated benchmark measurements, the globe-matrix result, the user-acceptance totals, and the final pass/fail decision here during implementation. Do not mark the feature complete while required evidence is missing.

Refer to [data-model.md](data-model.md) for anchor and lifecycle semantics and [contracts/battle-visualization.md](contracts/battle-visualization.md) for the renderer input/visibility contract.
