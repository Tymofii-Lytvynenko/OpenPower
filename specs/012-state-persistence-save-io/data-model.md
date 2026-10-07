# Data Model: Save State and Static World Ingestion

## Persistent state

`GameState` dataclass metadata is the source of truth for durable fields.

- Persistent `pl.DataFrame` fields are stored as `<field>.parquet`.
- The keyed `tables` mapping is stored as `tables/<table-name>.parquet`.
- Dataclasses such as `TimeData`, `DeterminismState`, and `JournalState`, plus JSON-compatible scalar/mapping fields, are stored in `meta.json`.
- Fields marked transient, including per-tick events/actions and schema/revision internals, are not part of the save contract.
- `meta.json` includes the save-format version, timestamp, persistent field names, schema versions, and system checkpoint keys.

## Save slot lifecycle

```text
unmodified slot -> sibling staging directory -> hidden backup rename -> staged slot rename -> backup cleanup
                                                   |
                                                   +-- failed install: restore backup to slot
```

Staging and target directories share the save filesystem. An interrupted replacement may leave `.slot.backup`; save discovery and loading expose that intact generation when the normal slot is absent or lacks metadata.

## Static world tables

- Definition TOMLs load before other tables and are named `def_<filename-stem>`.
- Region records normalize `hex` to uppercase `#RRGGBB`, deduplicate by hex using active-mod priority, and derive the runtime integer ID as `B + (G << 8) + (R << 16)` in `Int32`.
- Country master records merge by `id`; each `countries_*.tsv` adds/overrides columns by that same key.
- World TOML list/entity/matrix records become Polars tables. Matrix rows retain `source` and `target`; scalar payloads use `value`, while mapping payloads become columns.
- DataLoader's live initialization also preserves region adjacency, domestic production, regional production, geographic columns, and schema normalization used by the existing game.

## Versioning

`SAVE_FORMAT_VERSION` advances through one-step `SaveMigration` entries. Version-1 saves receive deterministic state, journal, and schema-version defaults when migrated to version 2. Future versions without a supported migration path fail explicitly.
