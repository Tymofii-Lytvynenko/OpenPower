# Feature Specification: Demographics & Dynamic Time Engine Systems

## User Scenarios & Testing

### Primary User Story
As a strategy player, I want simulation time to advance from `GAME_EPOCH` (Jan 1, 2001 00:00) across 5 speed levels with deterministic population birth (TFR), aging, and life expectancy mortality dynamics, so that long-term demographic trends shape national power over game decades.

### Acceptance Scenarios
1. **Time Dilation & Playback Controls**: **Given** player controls for game speed (Levels 1 to 5), **When** speed level changes, **Then** `minutes_per_sec` adjusts deterministically (Level 1: 30 min/s; Level 2: 60 min/s; Level 3: 120 min/s; Level 4: 600 min/s; Level 5: 2,400 min/s).
2. **Deterministic Epoch Datetime**: **Given** `total_minutes` elapsed since `GAME_EPOCH` (`datetime(2001, 1, 1, 0, 0)`), **When** minute accumulators advance, **Then** integer fields (`year`, `month`, `day`, `hour`, `minute`) and formatted UI string `date_str` (`"%Y-%m-%d %H:%M"`) are calculated via `timedelta`.
3. **Event Signaling**: **Given** hour or day rollovers, **When** minute steps advance, **Then** `EventNewHour`, `EventNewDay`, and 1Hz `EventRealSecond` events are pushed to `state.events`.
4. **Demographic Birth & Aging Equations**: **Given** regional demographic tables (`pop_14`, `pop_15_64`, `pop_65`), **When** `PopulationSystem` updates, **Then** births are generated from fertile women (\(\text{FEMALE\_RATIO} = 0.25\), \(\text{CHILDBEARING\_YEARS} = 35\)), kids age into workforce (\(\frac{1}{15 \cdot 365.25}\)), workforce ages into retirement (\(\frac{1}{50 \cdot 365.25}\)), and mortality applies per life expectancy.

### Edge Cases
- Paused simulation (`t.is_paused = True`): `EventRealSecond` continues to pulse with `is_paused = True` for UI heartbeats, but simulation date does not advance.
- Regional population column fallbacks: Missing `pop_14`, `pop_15_64`, `pop_65` default to 0; missing `fertility_rate` defaults to 2.7; missing `life_expectancy` defaults to 67.0 years.

## Exact Mathematical Formulas & Time Constants

### 1. Game Speed Multiplier Table (`TimeSystem.minutes_per_sec`)

| Speed Level | Speed Name | Real Seconds per Game Day | Game Minutes per Real Second |
| :--- | :--- | :--- | :--- |
| **Level 1** | Very Slow | `48.0s` / day | `30.0` min/sec |
| **Level 2** | Slow | `24.0s` / day | `60.0` min/sec |
| **Level 3** | Normal (Default) | `12.0s` / day | `120.0` min/sec |
| **Level 4** | Fast | `2.4s` / day | `600.0` min/sec |
| **Level 5** | Very Fast | `0.6s` / day | `2400.0` min/sec |

### 2. Demographic Progression Equations (`PopulationSystem`)
- **Daily Birth Step per Fertile Person**:
  \[ \text{BirthStep} = \frac{\text{TFR} \cdot 0.25}{35 \cdot 365.25} \cdot \text{DaysPassed} \]
- **Daily Death Step**:
  \[ \text{DeathStep} = \frac{1.0}{\text{LifeExpectancy} \cdot 365.25} \cdot \text{DaysPassed} \]
- **Aging Progression**:
  - Kids to Workforce Age Rate: \( \text{Aging}_{\text{kids}} = \frac{1}{15 \cdot 365.25} \cdot \text{DaysPassed} \)
  - Workforce to Retirement Age Rate: \( \text{Aging}_{\text{work}} = \frac{1}{50 \cdot 365.25} \cdot \text{DaysPassed} \)
- **Demographic Bracket Transitions**:
  \[ \text{pop\_14}_{\text{new}} = \text{pop\_14} + (\text{pop\_15\_64} \cdot \text{BirthStep}) - (\text{pop\_14} \cdot \text{Aging}_{\text{kids}}) \]
  \[ \text{pop\_15\_64}_{\text{new}} = \text{pop\_15\_64} + (\text{pop\_14} \cdot \text{Aging}_{\text{kids}}) - (\text{pop\_15\_64} \cdot \text{Aging}_{\text{work}}) \]
  \[ \text{pop\_65}_{\text{new}} = \text{pop\_65} + (\text{pop\_15\_64} \cdot \text{Aging}_{\text{work}}) - (\text{pop\_65} \cdot \text{DeathStep}) \]

## Success Criteria

- **SC-001**: Date Accuracy: 100% of minute accumulators evaluate to exact `datetime` dates from `GAME_EPOCH` (2001-01-01 00:00).
- **SC-002**: Demographic Realism: Population demographic brackets balance cleanly without negative population bugs.
- **SC-003**: Performance: Demographic updates across 10,000+ regions execute in under 2ms per tick.

## Assumptions & Dependencies

- **Assumption**: `GAME_EPOCH = datetime(2001, 1, 1, 0, 0)` in `src/server/state.py`.
- **Dependency**: `population_system.py` and `time_system.py` run within the simulation ECS graph.
