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
  tests/test_engagement_mvp.py `
  tests/test_battle_status_interface.py `
  tests/test_client_snapshot_performance.py
```

Expected outcomes:

- a proximity contact remains `positional`/Passive and uses a stable contact or region fallback anchor;
- an accepted attack changes the same battle to `assault`/Active without changing its ID or anchor;
- projection hides back-facing anchors and handles the globe edge/seam;
- phase values advance smoothly from presentation time, are deterministic, and freeze under reduced motion;
- concluded/stalemated rows stop combat effects;
- battle markers remain visible when unit billboards are filtered;
- 100 simultaneous battles stay within the existing client performance gate and the feature’s five-percent overhead target.

If the project environment does not provide `.venv`, run the same command with `python -m pytest` after installing the test dependencies.

## Manual map validation

1. Launch the normal client with `python main.py` (or the installed `openpower` entry point).
2. Create or load a scenario with two hostile armies close enough to enter the engagement radius without an attack order. Confirm a restrained marker appears at the meeting point and the battle panel says Passive/Positional.
3. Issue an accepted attack order for one participant. Confirm the same marker stays at the same geographic point while the effect becomes visibly stronger and the panel says Active/Assault.
4. Rotate the globe through the front, edge, and back hemispheres and zoom in/out. Confirm effects follow the surface, disappear behind the globe, do not draw across the seam, and keep a bounded screen footprint.
5. Hide one or both owners in the unit filter. Confirm the battle marker and state label remain available while the authoritative battle row is visible.
6. Wait for stalemate or conclusion. Confirm the combat animation stops immediately after the state update; any conclusion cue disappears within one second.
7. Enable reduced motion in settings. Confirm movement/flashes are suppressed but the marker, side colors, mode label, and focus control remain usable.

Refer to [data-model.md](../data-model.md) for anchor and lifecycle semantics and [contracts/battle-visualization.md](contracts/battle-visualization.md) for the renderer input/visibility contract.
