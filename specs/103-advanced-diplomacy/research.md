# Research: Advanced Diplomacy & Coalition Systems

## Decisions

### Reuse the existing action/event and treaty lifecycle

- **Decision**: Represent player intent with existing shared actions, store pending proposals in `peace_deals`, and emit immutable domain events for proposal, resolution, ownership, coalition, expansion, and exhaustion changes.
- **Rationale**: This preserves passive-client architecture and lets treaty diplomacy close wars using the existing action path rather than directly coupling peace packages to war internals.
- **Evidence**: `AdvancedDiplomacySystem` already routes accepted packages into `ActionOfferPeace`; territory transfer now publishes `EventTerritoryOwnershipChanged` after state commit. `DiplomaticBalanceSystem` consumes ownership/occupation/war/battle/day events and updates projection tables.

### Validate the complete package before applying any clause

- **Decision**: Normalize clauses, enforce bounded types/counts, verify all participants/regions/treaties, then apply all changes only after every invited participant accepts and the war remains active.
- **Rationale**: Prevents partial mutation from invalid clauses or unauthorized responses and supports multi-party wars.
- **Evidence**: `PeaceDealPolicy.validate_clauses` validates against the two war sides; system tests exercise invalid clauses, unauthorized responders, expiry, and multi-party acceptance.

### Keep balance state in explicit projection tables

- **Decision**: Persist rolling expansion events/scores, coalition pacts, and per-war exhaustion rows in the schema-managed tables; mirror current values to country/unit projections for UI and simulation consumers.
- **Rationale**: Explicit records are serializable and auditable; country/unit projections are inexpensive for map overlays and combat/politics consumers.
- **Evidence**: `modules/base/schema.py` defines all four tables and country/unit fields. Domain events notify the client-facing state stream.

### Make AI peace temperament explicit and backwards-compatible

- **Decision**: Read an optional `diplomatic_ai_archetype` country field with `conciliatory`, `pragmatic`, and `hawkish` profiles; default missing/unknown values to neutral `pragmatic`. Apply a small bounded utility offset to acceptance scoring.
- **Rationale**: The spec requires different leader archetypes to evaluate identical terms differently, but the repository had no leader personality contract. A neutral-default country runtime field lets scenarios/mods opt in without changing existing content or save behavior.
- **Weights**: conciliatory `+0.12`, pragmatic `0.0`, hawkish `-0.12`; utility is clamped to `[0, 1]` after clause and alliance adjustments.
- **Verification**: An identical-war/identical-terms test asserts a 0.24 score spread between opposing archetypes.

## Identified gap and change

The occupation-to-expansion scoring path previously recognized offensive capture only when the attacker belonged to `side_a`. This omitted equivalent captures by `side_b`. The condition has been made symmetric, with a regression test proving side-B threat score and event attribution. Existing score weights and coalition threshold are unchanged.

## Open coverage

- Run the full regression suite after the new active/suspended/expired alliance, mixed AI response, and both-orientation annexation cases.
- Verify save/load and IPC preserve the optional archetype field and neutral default; scenario-specific content may choose profiles without hardcoding them in the engine.
