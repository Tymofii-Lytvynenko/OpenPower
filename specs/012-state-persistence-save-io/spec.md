# Feature Specification: State Persistence, Parquet Save/Load & Static Data Ingestion

## User Scenarios & Testing

### Primary User Story
As a player saving and loading grand strategy campaigns, I want fast, atomic, corruption-proof save file creation (compressed Parquet format) and 3-phase static world data ingestion (TSVs and TOML blueprints), so that game progress is preserved safely and starting new games or restoring saves is near-instant.

### Acceptance Scenarios
1. **Atomic Save File Writes (`SaveWriter`)**: **Given** an active campaign, **When** `save_game(save_name)` executes, **Then** all Polars DataFrames are serialized to Parquet and metadata is written to `meta.json` in a unique staging directory on the save filesystem. A completed staging directory replaces the slot by rename; an existing slot is first retained as a hidden backup and restored if installation fails. Orphaned backups remain discoverable and loadable after process interruption.
2. **Reflection-Driven Save Restoration (`SaveStateLoader`)**: **Given** a save directory, **When** `load(save_name)` executes, **Then** reflection matches `GameState` dataclass fields to `.parquet` files and `meta.json` primitives, reconstructing `GameState` with 100% fidelity.
3. **3-Phase Static World Ingestion (`StaticAssetLoader`)**: **Given** static game assets, **When** starting a new campaign (`compile_initial_state`), **Then** datasets load in strict order:
   - **Phase 1: Definitions**: `modules/{mod}/data/definitions/*.toml` loaded into `def_*` Polars tables.
   - **Phase 2: Entities**: `regions.tsv` (deduplicated by hex color with 24-bit integer ID generation) and `countries.tsv` (horizontally joined with `countries_*.tsv`).
   - **Phase 3: World Relations**: `modules/{mod}/data/world/*.toml` parsed using List, Entity Dict, or Adjacency Matrix strategies into relational tables.
4. **Hex to 24-Bit ID Generation**: **Given** a region hex string (e.g. `#FF8000`), **When** parsing regions, **Then** red, green, and blue components are converted to uint32 and packed into Int32 runtime ID: \(\text{ID} = B + (G \cdot 256) + (R \cdot 65536)\).

### Edge Cases
- Save directory deletion (`delete_save`): `shutil.rmtree` permanently removes save folder cleanly.
- TOML matrix flattening: Adjacency matrix dictionary structures (`source -> target -> {attributes}`) automatically unroll into flat tabular DataFrames (`source`, `target`, `attributes`).
- Hex string normalization: Handles hex strings with or without leading `#` prefix, normalizing to uppercase `#RRGGBB`.

## Technical Architecture & File Serialization Strategies

```
Static File Ingestion (StaticAssetLoader)
├── Phase 1: data/definitions/*.toml  ──> state.tables["def_<key>"]
├── Phase 2: data/regions/regions.tsv ──> Hex -> 24-bit ID -> state.tables["regions"]
│            data/countries/*.tsv     ──> Horizontal Join -> state.tables["countries"]
└── Phase 3: data/world/*.toml        ──> Matrix / List Flatten -> state.tables["<key>"]

Save Persistence Pipeline (SaveWriter / SaveStateLoader)
├── user_data/saves/<save_name>/meta.json          ──> Primitives, globals, TimeData
├── user_data/saves/<save_name>/*.parquet           ──> Persistent DataFrame fields
└── user_data/saves/<save_name>/tables/*.parquet    ──> Keyed GameState tables
    Hidden staging and backup directories are used only during replacement; a backup remains readable if commit is interrupted.
```

## Functional Requirements

- **FR-001**: A save operation MUST serialize persistent game state and metadata into a staging location before installing the completed save slot.
- **FR-002**: Replacing an existing save MUST retain a recoverable copy until the new save is installed successfully; failed installation MUST restore the prior save when possible.
- **FR-003**: Loading MUST reconstruct persistent state from the save's table files and metadata while excluding transient runtime state.
- **FR-004**: Save versions MUST be migrated in sequence; unsupported future versions and malformed required save data MUST fail with a diagnostic rather than load partial substitute state.
- **FR-005**: New-game data ingestion MUST load definitions, entities, and world relations in the documented order and report the source of malformed required inputs.
- **FR-006**: Region identifiers and relation data MUST be normalized consistently when reading supported TSV and TOML source forms.

## Success Criteria

- **SC-001**: Ultra-Fast Save Operations: Saving full campaign state to compressed Parquet files completes in under 300ms.
- **SC-002**: Ultra-Fast Load Operations: Restoring full campaign state completes in under 500ms.
- **SC-003**: 100% Atomic Protection: Interrupted disk writes leave previous save archives 100% intact without data corruption.

## Assumptions & Dependencies

- **Assumption**: Apache Parquet (`write_parquet` / `read_parquet`) handles DataFrame compression.
- **Dependency**: `orjson` parses JSON metadata with high performance.
