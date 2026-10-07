# Persistence Validation Notes

## Open Full-World Round-Trip Throughput Observation

The full regression run reached `tests/test_headless_simulation.py::TestSaveLifecycleForSimulation::test_real_session_save_roundtrip_preserves_all_persistent_state`. That scenario advances the full world for six simulation ticks before writing and loading two save formats. It was still CPU-bound after more than five minutes and was interrupted; no pass/fail result was obtained for this run.

At the time, a pre-existing detached Python child process was also resident with approximately 16.5 GB working set and high cumulative CPU time. Its ownership and relationship to an unsaved user session could not be established, so it was left running. The observed wall time is therefore a throughput warning, not a clean benchmark or proof of a product regression.

No optimization was attempted. Re-run in a verified clean environment and separately measure simulation ticks, serialization, and both load paths before selecting a target. Any later algorithm optimization remains limited to three iterations; record each attempt and result, then leave the issue open if the gate still fails.

## Implementation findings and decisions

- `GameState` already marks durable and transient dataclass fields through persistence metadata helpers. `SaveWriter` and `DataLoader.load_save` use those helpers, Parquet payloads, JSON metadata, and the versioned migration registry.
- `SaveWriter` already stages saves under the save root and retains/restores a hidden backup during replacement. `core.saves` recognizes backups when the normal slot is unavailable; existing tests inject serialization and rename failures.
- `SaveStateLoader` is a thin facade over `DataLoader`, so the latter remains the single save-restoration implementation.
- There are two initial-state paths: `StaticAssetLoader.compile_initial_state` loads definition TOMLs, while the production session uses `DataLoader.load_initial_state`, which adds adjacency, schema, and domestic/regional production but currently does not load definition TOMLs. Reuse the definition parsing capability in the production path rather than replacing its additional game data.
- `DataLoader` already merges mod layers for regions, countries, and world relations and derives region IDs with the specified BGR-compatible packing. Tests cover those layered behaviors. Extend them to assert the live path's definitions-first ordering and keep all existing enrichment tables.
- Broad parse exceptions currently print and return empty DataFrames in some static ingestion helpers. That preserves a log line but can still let an invalid required asset masquerade as an empty world; fail with a path-specific exception for required malformed assets, while allowing genuinely absent optional directories to stay empty.
- The prior long lifecycle run is not a reliable SC-001/SC-002 measurement because it included six simulation ticks and a separate unidentified process. Establish isolated save/load timings before choosing whether any optimization is warranted.

No external API behavior is needed beyond the installed Polars/Parquet, orjson, and rtoml interfaces already used in the codebase; implementation will follow the repository's existing serialization calls and test them empirically.
