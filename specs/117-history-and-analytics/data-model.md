# Data Model: History and Analytics

History is an observational layer over authoritative `GameState`. It never feeds values back into gameplay systems.

## HistoryIndicatorDefinition (`history_indicator_definitions`)

One configured measurable series. The stable `id` names the indicator; `subject_type`, source table/field, subject key, optional related key/filter, unit, aggregation, and optional derivation describe measurement. Sampling policy includes `sample_interval_minutes`, `retention_window_minutes`, `max_samples_per_series`, `missing_data_policy`, and `enabled`. `schema_version` supports future migration.

Defaults are daily sampling, a five-year retention window, at most 3,650 samples per series, and `mark_gap` for missing observations. Scenario or module configuration can override them.

## HistorySeriesState (`history_series_state`)

One row per `(subject_type, subject_id, indicator_id)`, with deterministic `id`. It is the incremental index: latest value/snapshot/boundary, unit, confidence, value kind, completeness, last sample time/tick, next due time, sample count, compaction time, and source revision. It preserves identities when source entities disappear.

## HistorySnapshot (`history_snapshots`)

An immutable observation keyed by deterministic `id`, containing subject and indicator identity, nullable numeric value, unit, game minute, tick, source boundary (`initial`, `change`, `interval`, or `entity_removed`), confidence, completeness, value kind, and schema version. Missing observations remain explicit rows with a null value unless the indicator selects `omit`.

## HistoryEvent (`history_events`)

An immutable source-evidence row keyed by journal or cause identity. It contains event type/title, primary and related subject IDs, region, serialized details, source and cause references, game time/tick, confidence, completeness, and schema version. Journal IDs and economic cause IDs are namespaced to make ingestion idempotent.

## Invariants

- Subject/indicator series IDs and event IDs are stable and deterministic.
- History reads do not mutate source tables; recording writes only the four history tables and history cursor/revision globals.
- Values are never compared across different units as raw magnitudes. Relative indexing is explicit and unavailable across an unconverted unit transition.
- Missing and stale data are not presented as zero; rankings report excluded subjects and freshness.
- Retention and downsampling are deterministic per series and do not alter current state or later simulation outcomes.
