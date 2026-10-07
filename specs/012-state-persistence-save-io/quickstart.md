# Quickstart: Persistence and Static Data

## Focused correctness checks

```powershell
.venv\Scripts\python.exe -m pytest -q tests/test_save_writer_atomicity.py tests/test_save_loader_type_hints.py tests/test_data_loader_mod_layering.py
```

The tests use temporary save roots and synthetic mod fixtures. They cover rollback, orphaned backup discovery/recovery, persistent-field reflection, definitions/entities/world ordering, layer overrides, and 24-bit region IDs without mutating the user's save data.

## Broader save/load regressions

```powershell
.venv\Scripts\python.exe -m pytest -q tests/test_political_persistence.py tests/test_random_event_persistence.py tests/test_recognition_persistence.py tests/test_economic_health_integration.py
```

The full-world simulation save lifecycle in `tests/test_headless_simulation.py` includes simulation ticks; keep that result separate from serialization-only save/load timing.

## Performance gates

For the representative production world, record repeated `SaveWriter.save_game` and `DataLoader.load_save` durations, median/p95, table count/rows, Python/Polars/Arrow versions, CPU, storage, and whether filesystem caches were warm. Compare against the <300 ms save and <500 ms load targets. Establish a baseline before tuning. Allow at most three measured optimization iterations per algorithm; after the third miss, record attempts/results in `performance-log.md` and move to other specifications.

## Manual recovery check

In a temporary save root, inject a rename failure after the current slot is moved to its hidden backup. Confirm the old generation remains listable/loadable, then retry a successful save and confirm the new generation is installed. Do not perform fault injection against a user's real save directory.
