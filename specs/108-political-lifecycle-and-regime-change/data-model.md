# Data Model: Political Lifecycle and Regime Change

The existing `countries` runtime row remains authoritative for aggregate approval, stability, and corruption values consumed by other systems. New normalized tables hold lifecycle detail. Tables are owned by the base module and pass through the existing schema registry, snapshots, save writer, and migrations.

## Government form catalog

Seed/scenario data identifies a form and its rules: electoral eligibility, election interval, executive succession, party eligibility, law permissions, override permissions/costs, crisis thresholds, regime-change paths, and pending-law carry-over policy. Values are validated and have bounded defaults; no per-country duplicate catalog is created.

`election_overrides_json` is a list of enabled rule records. Each record declares `type`, inclusive `minimum_duration_days`/`maximum_duration_days`, optional `minimum_notice_days`, finite non-negative `cost`, non-negative `cooldown_days`, and bounded `approval_delta`/`stability_delta` consequences in percentage points. Supported types are `postpone`, `accelerate`, `suspend`, and `succession`; the latter uses the country's configured successor party. Invalid or duplicate rules are unavailable rather than permissive. The accepted action records its source and prior/new election date in `political_history`; one-time indicator consequences are stored as pending `political_effects` and marked applied by the politics owner.

`crisis_rules_json` accepts a list (or an object containing a `rules`/`thresholds` list) of threshold records. Each record declares a unique `id`, `type` (`protest`, `strike`, `paralysis`, or `government_crisis`), `metric` (`approval`, `stability`, or `corruption`), `threshold` in percentage points, `direction`, hysteresis `recovery_threshold`, deterministic `priority`, and optional bounded one-time indicator deltas. Thresholds fire only when crossed; an active rule ID cannot open twice. Recovery uses the opposite direction and a strictly separated threshold, closes the record once, and restores the government's aggregate crisis status from any remaining active records. Causes, evidence, notifications, and typed one-time consequences are attributed to the individual crisis record.

`regime_change_paths_json` accepts a list (or an object with a `paths` list). Each path has an `id`, `crisis_types`, `minimum_support` (0–1), and minimum approval/stability (0–100). Its optional `outcome` declares `government_form_id`, `ruling_party_id`, `law_values`, bounded indicator deltas, and `relation_effects` (country target, delta, optional reciprocal application). Optional `failure_effects` declares the only indicator changes permitted on an under-threshold attempt. Missing/ambiguous target rows, disallowed law values, or unsupported relation targets invalidate the path before mutation. An accepted decision uses `ActionResolvePoliticalCrisis.decision` as the path ID; success updates government, law, party, relation, indicator, and election-schedule state together, while failure preserves the prior regime/laws/relations/territory and records configured failure consequences.

## `country_governments`

Key: `country_id`.

Fields: `country_id`, `government_form_id`, `ruling_party_id`, `election_eligible`, `next_election_at_minute`, `succession_party_id`, `crisis_status`, `initialized`, `last_election_id`, and `updated_at_minute`.

Legacy initialization uses existing country government/form columns and seeded laws, never changes region ownership, and does not schedule an election for a non-electoral form.

## `political_parties`

Key: (`country_id`, `party_id`). Fields: country, party identity/label, support share, organization, ideology/policy JSON, electoral eligibility, and ruling status. Shares are clamped and normalized deterministically among eligible parties; an empty opposition uses the configured incumbent fallback.

## `country_laws` and `law_transitions`

`country_laws` is keyed by (`country_id`, `law_id`) and stores current allowed value, source seed ID, and last effective time. A transition records ID, actor, previous/target value, created/effective/cooldown game minutes, status, carry-over policy, explicit effects JSON, and rejection/resolution reason. Current law changes only at the effective boundary.

## `political_elections`

Key: `id`. Stores country/form, scheduled/opened/resolved minutes, electorate/eligible-party snapshots, turnout, per-party vote totals/results, winner, coalition members, override type, status, and deterministic tie-break/result evidence. Roster snapshots prevent later membership changes from changing an open election.

## `political_crises`

Key: `id`. Stores country, crisis type, trigger and evidence, created/deadline/resolved minutes, support/organization, prior and proposed regime/ruling authority/law state, status, outcome, and consequences. Successful regime changes are applied together at one boundary; failed attempts leave prior regime authority intact.

## `political_effects` and `political_history`

Effects are bounded, typed, attributable outputs for existing dependents (tax, labor, migration, rights, economic behavior, domestic stability, military readiness). History rows record action/system source, previous/new values, cause, time, and result. Cause is `unknown` when no authoritative source record exists.

## State bounds and ordering

- Approval, stability, corruption, support, organization, turnout, and confidence are clamped to declared ranges; missing/non-finite input is normalized at the schema/system boundary.
- Stable order: validate ordered actions; initialize missing legacy state; resolve due law transitions; resolve scheduled elections/overrides; evaluate crisis thresholds in configured order; publish outputs and history; update cached next-deadline/revision state.
- State tables use integer game minutes, stable IDs, and deterministic tie-breaks; no wall clock enters outcome calculation.
