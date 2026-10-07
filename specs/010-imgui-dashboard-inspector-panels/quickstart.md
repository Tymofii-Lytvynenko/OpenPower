# Quickstart and Verification

## Focused tests

Run these from the repository root:

```powershell
.venv\Scripts\python.exe -m pytest -q tests/test_budget_panel.py tests/test_data_inspector_panel.py tests/test_politics_stability_drift.py tests/test_resources_panel.py
```

The budget and resource tests are headless contract tests. The data inspector tests verify filtering, ordering, and visible-row clipping. Politics tests exercise weekly eligibility, fallback behavior, exact baseline drift, and preservation of modifiers.

## Desktop verification

1. Start a local game and open Budget for the player's country. Change personal income tax and at least one sector ratio; apply and verify the dispatched action contains the updated, bounded ratios and that the next authoritative snapshot reflects them.
2. Open Resources with active market flows. Verify imports, exports, net values, and the bar chart are visible. Also inspect an empty/malformed fixture in tests to confirm missing schema fields are called out.
3. Open Data Inspector on a 10,000+ row Polars frame, scroll, sort, and search. Check that only visible rows are drawn.
4. Inspect actual rendered FPS while dragging controls and record the machine/build details and median/p95 in `performance-log.md`.

## Performance limits

- Target: 10,000-row Data Inspector frame <4 ms/frame; interactive dashboards 60+ FPS.
- Measure before changing an algorithm. Each algorithm has a maximum of three measured optimization iterations. Log every implementation change and its before/after result; if the target still fails after iteration three, stop tuning it, record the outstanding issue, and continue with other requirements.
- Headless unit tests do not establish rendered OpenGL frame time. Do not mark either GUI performance gate verified from test-only evidence.
