# Feature Specification: History and Analytics

## User Scenarios & Testing

### Primary User Story

As a player, I want to inspect how countries, regions, wars, economies, populations, and relations changed over time, so that I can understand causes, compare performance, and make decisions from trends rather than isolated current values.

### Acceptance Scenarios

1. **Open a history graph**: **Given** a country or region has recorded snapshots, **When** the player opens history, **Then** the player can select an indicator, time range, granularity, and comparison target and see the trend with units and missing-data treatment.
2. **Compare countries**: **Given** several countries are selected, **When** the comparison view opens, **Then** it shows comparable GDP, GDP per capita, population, development, stability, reserves, military strength, resource coverage, and other supported indicators for the same period.
3. **Review relations**: **Given** two countries have changed relations, treaties, wars, or recognition status, **When** their relationship history opens, **Then** the player sees the timeline of values and attributable diplomatic events.
4. **Review a war timeline**: **Given** a war or battle has occurred, **When** the player opens its history, **Then** it sees start, escalations, battles, occupation changes, peace, losses, and relevant political or economic events in chronological order.
5. **Inspect event causes**: **Given** a current indicator changed after a policy or event, **When** the player opens the cause trail, **Then** the history view links the change to recorded policies, events, damage, migration, or system transitions where evidence exists.
6. **Use a ranking table**: **Given** countries have a shared indicator and period, **When** the player requests a ranking, **Then** countries are ordered by the same snapshot and tie or missing-data rules are visible.
7. **Persist historical data**: **Given** history exists across multiple save points, **When** the game is saved and loaded, **Then** the configured history range, timestamps, and values remain available without changing current state.

### Edge Cases

- An indicator has no historical samples; the interface shows unavailable rather than drawing a false zero line.
- A country or region is created, renamed, merged, or removed; its history preserves identity links and labels according to the configured rule.
- A time range contains missing snapshots; the graph marks gaps and does not interpolate without an explicit display option.
- Two countries use different units or scales; comparison normalizes units and shows the conversion basis.
- A ranking has tied values or stale data; tie ordering and freshness are shown and deterministic.
- A war contains several fronts or battles; the timeline keeps separate event identity while preserving chronological order.
- A legacy save contains no history snapshots; the system starts recording from the first supported boundary without changing current values.
- History retention limits are reached; old data is downsampled or removed according to a visible policy, never silently mixed with current state.

## Functional Requirements

- **FR-001**: The system MUST record time-series snapshots for configured country, region, military, demographic, economic, political, diplomatic, and strategic indicators.
- **FR-002**: Each snapshot MUST include subject identity, indicator, value, unit, game time, source boundary, confidence or completeness state, and schema version.
- **FR-003**: History MUST support configurable sampling intervals, retention windows, aggregation levels, and deterministic downsampling without changing the authoritative current state.
- **FR-004**: The history view MUST support line or step trends, selected time range, sample granularity, unit labels, missing-data markers, and current-value comparison.
- **FR-005**: Country and region comparisons MUST use the same time boundary, indicator definition, unit, and missing-data policy for every selected subject.
- **FR-006**: Ranking tables MUST specify indicator, period, direction, tie rule, data freshness, and excluded or unavailable subjects.
- **FR-007**: Relationship history MUST record relation values, treaty or war transitions, recognition status, sanctions or embargo signals, and attributable diplomatic events where available.
- **FR-008**: War and battle timelines MUST record lifecycle transitions, participants, battle events, occupation changes, losses or readiness changes when authoritative, peace outcome, and related escalation events.
- **FR-009**: Event and cause trails MUST link a changed indicator to the originating policy, action, event, damage record, migration flow, political transition, or other recorded source without inventing causes.
- **FR-010**: The system MUST distinguish authoritative historical values from estimates, stale observations, derived aggregates, and missing data.
- **FR-011**: AI and human actions MUST produce the same historical records for the same authoritative state changes.
- **FR-012**: History MUST survive save/load, snapshot synchronization, replay, and configured retention or downsampling without altering future simulation outcomes.
- **FR-013**: The player MUST be able to export or inspect the selected series, comparison, relation timeline, or event timeline in a readable form supported by the existing client.
- **FR-014**: Identical state, time, sampling policy, and ordered actions MUST produce identical snapshot values, ranking order, timeline order, and downsampling results.
- **FR-015**: History processing MUST record changed or due indicators incrementally and MUST avoid full-world snapshots when no configured value changed.

## Key Entities & Data Model

- **History Snapshot**: A timestamped value for one subject and indicator with unit, source, completeness, and version.
- **Indicator Definition**: The name, unit, source, aggregation, retention, and comparison policy for a measurable series.
- **Comparison Query**: A selected set of subjects, indicator, period, unit, and missing-data policy.
- **Ranking Result**: A deterministic ordered set with values, ties, freshness, and excluded subjects.
- **Relationship Timeline**: Time-ordered relation, treaty, war, recognition, and diplomatic event history for a pair of countries.
- **Event Timeline**: Time-ordered campaign, war, battle, political, economic, disaster, and strategic events with source links.

## Scope Boundaries

This feature adds historical storage, graphs, comparison tables, rankings, relationship timelines, war timelines, and cause trails. It does not add or replace thematic map rendering, map colours, map legends, current-state simulation, economy, diplomacy, combat, or event generation.

## Success Criteria

- **SC-001**: 100% of configured indicator changes create a correctly timestamped history sample at the declared sampling boundary.
- **SC-002**: History views show units, time range, current value, gaps, freshness, and source state for 100% of selected series with available data.
- **SC-003**: Comparisons and rankings use identical period and unit rules for all included subjects and expose ties and unavailable data.
- **SC-004**: Relationship and war timelines preserve chronological ordering and show all authoritative lifecycle transitions in controlled scenarios.
- **SC-005**: Save/load and replay preserve configured history without changing current simulation state or next outcome.
- **SC-006**: A player can answer “what changed, when, and which recorded event caused it?” for a supported indicator within 60 seconds when source evidence exists.
- **SC-007**: Recording and querying 10 million snapshots remains within the configured retention budget and returns a selected series or ranking in under 500 milliseconds in a controlled benchmark.

## Assumptions & Dependencies

- **Assumption**: Current state remains authoritative; history is an append-oriented observation and evidence layer.
- **Assumption**: Retention and sampling are scenario-configurable, with a default that preserves daily samples and important event boundaries.
- **Assumption**: Cause links exist only where a source system publishes attributable evidence; the interface must show unknown causes instead of guessing.
- **Dependency**: Existing economy, demographics, politics, diplomacy, military, strategic, random-event, notification, snapshot, and persistence systems publish the values and event transitions to record.
