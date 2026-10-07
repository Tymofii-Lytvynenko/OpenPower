# Data Model: Demographics and Time Simulation

## Clock state

`GameTime` holds integer `total_minutes`, calendar fields, `date_str`, pause state, speed level, and internal elapsed-second accumulators. `total_minutes` is the source of truth for displayed calendar values and is interpreted relative to `GAME_EPOCH`.

## Regional cohorts

The `regions` table remains the sole authoritative demographic ledger:

| Column | Type/invariant | Legacy default |
| --- | --- | --- |
| `pop_14` | non-negative integer population under 15 | 0 |
| `pop_15_64` | non-negative integer working-age population | 0 |
| `pop_65` | non-negative integer population 65+ | 0 |

The `countries` table supplies `fertility_rate` (default 2.7) and `life_expectancy` in years (default 67.0). Optional health capacity and economic health modifiers affect only regional life-expectancy scaling. Natural changes do not mutate migration state or count pending flows as residents.

## Derived rates

Rates are calculated per update from elapsed simulated days. Negative durations become zero. Cohort aging and deaths are bounded to at most the source cohort for one update; resulting cohort values remain non-negative integers.
