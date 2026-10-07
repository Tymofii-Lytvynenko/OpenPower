# Political Lifecycle Contracts

## Authoritative action boundary

Political actions are data-only `GameAction` values in `src/shared/actions.py`. The base political system validates actor-to-country authority, government permission, crisis state, value/range, cost, cooldown, and deadline before applying a change. Rejected actions leave political gameplay tables unchanged and return a reason through the existing journal/message path.

Initial actions cover law change, election override, and explicit crisis/regime decision. Human and AI actions enter the same validators and deterministic resolvers. An election override is accepted only when its type has exactly one enabled record in the current form's `election_overrides_json`, the actor controls the country, no political crisis is active, its duration/date/cost/cooldown are valid, and the country can fund it. The accepted action updates the canonical next election date, records the applied override, and publishes one-time approval/stability consequences for the politics owner to consume.

Each override rule is a JSON object with `type` (`postpone`, `accelerate`, `suspend`, or `succession`), optional `enabled` and `legal_authority` (currently `government`), inclusive `minimum_duration_days` and `maximum_duration_days`, `minimum_notice_days` for acceleration, `cost`, `cooldown_days`, `approval_delta`, and `stability_delta`. Duration is the number of days to move/hold the date; acceleration cannot move an election earlier than its configured notice floor. Succession applies the country's configured successor party and starts its next-election clock after the requested duration. Consequence deltas are percentage points, bounded to [-100, 100], then applied once with the country indicator clamped to [0, 100].

Government `crisis_rules_json` contains deterministic threshold records for protest, strike, paralysis, or government crisis, each tied to one approval/stability/corruption metric and an inverse recovery threshold. A multi-threshold update evaluates records by priority, type, and stable rule ID. Active records are indexed by country/rule ID to prevent duplicates; recovery records their cause and recomputes the aggregate government crisis status. Bounded approval/stability/corruption deltas are published as pending political effects and consumed once by the politics owner.

Government `regime_change_paths_json` contains path records with a stable `id`, one or more `crisis_types`, `minimum_support` in [0, 1], and minimum approval/stability in percentage points. Optional `outcome` values select an existing target `government_form_id`, an eligible country `ruling_party_id`, allowed `law_values`, bounded indicator deltas, and declared `relation_effects` (`target_country_id`, bounded `delta`, optional `reciprocal`). Optional `failure_effects` declares percentage-point approval/stability/corruption deltas for a failed attempt. `ActionResolvePoliticalCrisis.decision` names the path ID. Before mutation, the authoritative handler validates actor control, crisis status/deadline/type, target forms/parties/laws/relations, support, and indicator thresholds. A valid but under-threshold attempt resolves as `failed`, applies only configured failure deltas, and leaves regime, party authority, laws, relations, and territory unchanged. Success commits government/party/election schedule, declared laws and their dependent effects, bounded indicators, declared relations, crisis record, and history at one action boundary. Pending law transitions follow their configured regime-change carry-over rule; the replaced election schedule is cancelled and recreated from the target form.

AI politics is composed from independent law, election-override, and crisis policies. Candidate generation excludes the local player and countries mapped to human players, evaluates only configured legal options, and uses the same pure validators and regime assessment used by the authoritative action handler. Accepted AI choices are ordinary political actions scheduled into the engine's ordered action batch; their concise rationale is carried on the action and saved with the command result. The AI does not directly mutate political tables and does not select a regime path whose support, indicator, target-state, or relation preconditions currently fail.

## Published outcome boundary

Lifecycle outcomes are data-only events in `src/shared/events.py` and durable table records. Each outcome identifies country, source/action, game minute, status, and reason. Dependent systems consume only typed `political_effects` relevant to their own domain; no client or political system writes another subsystem's derived values.

## Determinism and persistence

- Input ordering is preserved for actions; table evaluation uses stable keys and deterministic tie-break rules.
- Deadlines use simulation game minutes.
- Elections snapshot eligible parties and support at the declared boundary.
- Snapshot and save/load contracts include every lifecycle table and pending deadline.
- Unknown effect/cause source is explicit; the contract forbids inferred attribution.

## Client projection

The political overview is read-only and derives government, ruling party, active laws, next election, separate bounded values, current crisis, and recent attributable history from the latest client snapshot. Buttons dispatch semantic actions and render authoritative acceptance/rejection results.
