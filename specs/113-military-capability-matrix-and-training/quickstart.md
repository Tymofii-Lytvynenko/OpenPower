# Quickstart: Military Capability Matrix and Training

## Prerequisites

- Use the repository environment: `.venv\Scripts\python.exe`.
- Run the focused checks from the repository root.
- The interactive acceptance scenarios require a running desktop client and a save with owned and foreign military forces; headless tests do not substitute for the 30-second inspection and authorized-information checks.

## Automated validation

Current catalog, research/design, and training coverage:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_capability_catalog.py tests/test_military_capability_system.py tests/test_research_program_system.py
```

Combat projection and military presentation coverage:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_combat_system.py tests/test_military_presenter.py
```

Run the opt-in SC-007 controlled fixture in an otherwise idle process and record Python/Polars versions, thread count, warm-up policy, changed-record ratio, total duration, and stage breakdown. Keep fixture construction outside the timed interval; do not run it concurrently with a full-world simulation or another large benchmark.

```powershell
$env:RUN_MILITARY_CAPABILITY_PERFORMANCE_CHECKS='1'; .venv\Scripts\python.exe -m pytest -s -q tests/test_military_capability_performance.py
```

## Interactive acceptance

1. Open a design and verify its role, domain, fixed baseline, adjustable capabilities, target interactions, strongest counter, research prerequisites, cost, maintenance, and production eligibility are visible before queueing production.
2. Issue training for an eligible owned unit. Verify the selected facility and instructor are recorded, the unit leaves map/battle eligibility, progress advances only while active, and pause/resume/cancel preserve paid/completed progress and restore the correct deployment location.
3. Attempt training with no eligible facility, no available instructor, insufficient funds, a moving unit, a battle participant, and an invalid/retired design; verify each rejection/block reason is visible and no unauthorized state mutation occurs.
4. Inspect an enemy with no observation and verify its force is shown as unknown, not as a zero-strength authoritative force.
5. Resolve military espionage with low/high observer telecom and different active intelligence coverage. Verify role/strength ranges, source, confidence, and freshness change deterministically without revealing enemy unit IDs or exact designs.
6. Raise an opposing unit's readiness while a foreign espionage cell is active in its country. Verify a bounded mobilization signal appears only to the eligible observer, identifies the force domain and readiness transition but not the unit or cell, and is shared only through authorized military-intelligence treaties.
7. Repeat with treaty-authorized allied findings; verify the best eligible estimate is selected, the receiving country's authority/telecom caps apply, and stale observations are visibly outdated.
8. Save/load during active training and with current/stale intelligence. Verify records, progress, estimates, and subsequent deterministic outcomes are preserved.
9. Repeat a controlled mixed-role engagement and verify an attacker outside the configured target interaction matrix contributes no damage; compare battle ID, sides, readiness timing, occupation, and ownership before and after.

Record automated output separately from live-client observations. SC-007 remains open until the controlled 50,000-unit/10,000-design, 5%-changed benchmark is measured under an isolated runtime; allow no more than three measured algorithm-optimization iterations.
