# Research: Demographics and Time Simulation

## Codebase findings

1. `TimeSystem` already owns five fixed speed levels, the `GAME_EPOCH`-based date calculation, pause state, and new-hour/new-day/real-second events.
2. `PopulationSystem` is registered after time and consumes `EventRealSecond`; it updates only regional cohort columns and does not consume pending migration flows.
3. Polars remains the authoritative state format. For the standard numeric schema, cohort formulas can run over aligned NumPy vectors and be written back as Polars columns; legacy or nonstandard schemas retain the Polars expression fallback. Missing demographic input columns are supplied for older worlds.
4. `GameState.update_table` preserves the table schema and other regional columns, so the system can remain a local transformation of the canonical regions table.
5. The spec's 2 ms/10,000-region criterion is empirical: the optimized vector path still requires repeated default-pool measurements, and source inspection cannot establish that gate.

## Decisions

- Preserve the five speed multipliers and `timedelta` calendar arithmetic exactly.
- Treat paused real-second events as UI heartbeats only; do not advance simulation demographics while paused.
- Clamp invalid negative elapsed time to zero, cap each one-tick cohort transfer at 100%, and prevent negative stored population after long delayed updates. Ordinary formula-sized updates remain unchanged.
- Keep demographic default values compatible with legacy data. Bound fertility below by zero and life expectancy below by one year to keep rates valid.
- Keep births based on working-age population, aging transitions based on the source cohort, and mortality based on the retirement cohort, matching the documented formulas.
- Cache the region-aligned country demographic inputs until country data changes or the immutable regional table is replaced. Reuse the cache directly after this system's population-only table update; compare ordered region IDs and owners when another writer replaces the table so ownership changes still invalidate the join.
- Use a NumPy vectorized cohort calculation for supported numeric columns to avoid Polars lazy-plan startup on each real-second tick; return to the Polars expression implementation for unsupported dtypes or unsafe numeric ranges so legacy behavior remains available.
- Measure SC-003 on the supported local runtime and record a miss as open work rather than weakening the target.
