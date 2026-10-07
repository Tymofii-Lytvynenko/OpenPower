# Persistence and Static-Loading Contracts

## SaveWriter

- `save_game(state, name) -> bool` accepts a canonical slot name and writes a complete staged save before replacing the slot.
- Invalid names and serialization/install failures return `False`; an existing generation remains recoverable.
- The save root contains versioned `meta.json`, DataFrame Parquet files, and `tables/*.parquet`.
- `delete_save(name)` removes the visible slot and its orphaned hidden backup; invalid names are rejected.

## SaveStateLoader / DataLoader

- `SaveStateLoader.load(name)` delegates to the canonical `DataLoader.load_save(name)` path.
- Loading reconstructs only fields marked persistent, applies ordered save migrations, restores keyed tables from Parquet, and attaches the supplied schema registry when configured.
- A missing normal slot may be recovered from a valid hidden backup. Invalid metadata, unsupported versions, unreadable Parquet, or invalid canonical names produce a visible error.

## Initial static data

- `DataLoader.load_initial_state()` returns a `GameState` whose definition tables are available before entity/world consumers run.
- Static world phase order is definitions, entities (regions and countries), then world relations; the existing adjacency, resource, geography, and schema tables remain available.
- Region hex input accepts an optional `#` and normalizes to uppercase `#RRGGBB`; invalid required data must identify its source path rather than silently become an empty table.
- Mod layering is deterministic: later resolved mods override non-null values for matching entity keys.
