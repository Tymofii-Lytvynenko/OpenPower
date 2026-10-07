# Random Event Contracts

## Commands

Commands are dataclass `GameAction` values in `src/shared/actions.py` and must be handled by the authoritative random-event module system. The client must only dispatch them; it cannot update event tables.

### `ActionSetRandomEventControls`

Fields: `player_id`, `enabled` (optional global state), `category` (optional category key), `category_enabled` (optional boolean), `frequency_multiplier` (optional finite value in the configured range), and `maximum_active_events` (optional positive integer). At least one setting must be provided. The system accepts this only from the configured scenario administrator; rejected updates do not partially change settings. Accepted controls take effect at the next eligibility boundary and are persisted.

### `ActionRespondToRandomEvent`

Fields: `player_id`, `event_id`, `response_id`, and `country_tag`. The instance must be active, response must exist and be available, actor must control the funding country, country must be the target authority under the definition, and funds must cover the full cost. All validation precedes mutation. The accepted result deducts cost once, records mitigation/risk/effects, and cannot be repeated.

## Persistent tables

The table schemas are defined in `modules/base/schema.py` and documented in [data-model.md](../data-model.md):

- `random_event_instances`: one row per triggered/terminal instance.
- `random_event_effects`: one row per instance, effect category, and affected subject.
- `random_event_responses`: one row per accepted response.
- `random_event_controls`: one row per configured category.
- `random_event_cooldowns`: one keyed row per event type and target.

All keyed rows use stable unique IDs. Every numeric field is finite and bounded before storage. Polars table updates are authoritative; the old `globals["active_events"]` list is a compatibility projection only.

## Domain events and history

- `EventRandomEventTriggered` remains the trigger fact consumed by existing infrastructure effects and gains only backward-compatible optional context fields.
- `EventRandomEventLifecycleChanged` records skipped, resolved, cancelled, or disabled transitions with instance ID, type, status, reason, and game minute.
- Existing domain journal and command-result records carry the durable, readable audit trail through save/load and snapshots.

## Ordering and determinism

The registered system runs after `base.time`. It expires/due-processes existing rows, handles validated commands, then evaluates `EventNewDay` eligibility from category controls, conditions, ownership, cooldown, and active cap. Eligible definitions and candidate targets are ordered by stable IDs before deterministic random selection. Existing trigger events continue to be visible to later consumers in the same simulation step.
