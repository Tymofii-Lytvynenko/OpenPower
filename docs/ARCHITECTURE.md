# OpenPower runtime architecture

OpenPower uses a server-authoritative, data-oriented simulation. Gameplay modules
contribute systems, table schemas, and save migrations through one versioned mod
API. The client submits commands and renders acknowledged state snapshots; it
never mutates the authoritative world.

## Runtime flow

1. `ModManager` resolves manifests; the author-facing `mod()` declaration is
   normalized into a `ModContribution` with systems, schemas, and migrations.
2. `WorldSchemaRegistry` merges module schemas and validates loaded world data.
3. `Engine` validates the system graph and builds a stable phase-aware order.
4. `GameSession` validates command envelopes and executes one atomic tick.
5. Successful domain signals are appended to the persistent journal.
6. `StateSnapshotEncoder` sends only changes since the latest client acknowledgement.
7. Headless tooling fingerprints complete persistent state for deterministic
   run comparison and writes machine-readable artifacts.

## Adding a gameplay feature

- Put gameplay policy under its module, not in `src/server` or the UI.
- Add or extend `TableSchema` contributions in the module schema file.
- Implement a small system with explicit dependencies and `SystemAccess`.
  Declare every consumed action in `SystemAccess.handles`; unhandled commands
  are rejected before the tick instead of being reported as executed.
- Mutate tables only through `GameState.update_table` so schema normalization,
  rollback checkpoints, and delta revisions remain correct.
- Use `stable_sum` for floating-point gameplay reductions that enter persisted state.
- Represent external intent as a `GameAction`; command metadata belongs to
  `CommandEnvelope` and must not be duplicated in the action.
- Emit a `DomainGameEvent` for durable gameplay facts. Use `GameEvent` only for
  intra-tick signals such as time pulses.
- Add a sequential save migration when persisted data changes.
- Prove deterministic behavior by comparing complete state for the same seed and
  command sequence, including a save/resume run.

## Failure and debugging contracts

- Missing dependencies, duplicate system IDs, cycles, schema conflicts, and
  unsupported mod API versions fail during startup.
- A system exception rolls the complete `GameState` and declared mutable system
  state back to the start of the tick.
- Command rejections, command failures, system errors, RNG state, and domain
  events are available in simulation artifacts and the in-game console.
- `openpower mod validate` exercises manifest resolution, contribution import,
  layered data, schemas, system ordering, action routes, and one startup tick.
- `openpower sim run` and `openpower sim compare` expose the same runtime path
  for scripted regression scenarios and full-state determinism checks.
- The simulation process advances with a fixed wall-clock step. Headless tools
  may use a different explicit fixed step, but must never feed measured execution
  duration into gameplay logic.
