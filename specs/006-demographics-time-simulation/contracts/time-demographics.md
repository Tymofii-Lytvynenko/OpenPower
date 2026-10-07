# Time and Demographics Contracts

## TimeSystem

- Valid speed levels 1–5 map to 30, 60, 120, 600, and 2,400 game minutes per real second.
- `total_minutes` advances only while unpaused. Calendar fields and `date_str` are recomputed from `GAME_EPOCH + timedelta(minutes=total_minutes)`.
- Hour/day boundary events describe simulation-time rollovers. `EventRealSecond` is a real-time heartbeat and carries pause state; it may fire while the simulation is paused.

## PopulationSystem

- Consumes only unpaused `EventRealSecond` values with positive elapsed simulation seconds.
- Ensures legacy population/country demographic columns exist with documented defaults.
- For elapsed days `d`, uses `birth = TFR * 0.25 / (35 * 365.25) * d`, `aging_children = d / (15 * 365.25)`, `aging_workers = d / (50 * 365.25)`, and `death = d / (life_expectancy * 365.25)` before per-tick safety bounds.
- Applies births to children, transitions to the next bracket from the originating cohort, and deaths to retirees. Results are integer, non-negative, and deterministic for identical input state and events.
- Does not directly apply migration or any pending movement record.
