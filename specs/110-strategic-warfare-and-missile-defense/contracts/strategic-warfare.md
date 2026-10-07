# Strategic Warfare Contracts

## Player/AI intent

`ActionLaunchStrategicStrike` is the only launch request. It carries `player_id`, `country_tag`, registered `weapon_id`, optional `origin_region_id` (must match the design origin when one is configured), `target_region_id`, `weapon_type`, optional `target_country_tag`, `target_object_id`, `payload_level`, `target_mode` (`military` or `civilian`), and `authorization_context`. The server resolves and persists the authoritative origin region before validating range.

`ActionProduceStrategicWeapon` requests a quantity against a country-owned scenario design by `weapon_id`. It is accepted only when the actor controls the country, the strategic-program and weapon research gates pass, the design's payload is researched, a scenario production cost and duration are configured, and the treasury can pay. Optional `strategic_production_authorized_countries` restricts policy authority; absent that list, control plus research are the authority. Invalid requests do not create an order or debit funds.

The action is intent, not authority. `StrategicWarfareSystem` revalidates country control, target ownership, weapon ownership and operational/readiness state, research, duplicate pending orders, target-object eligibility, payload cap, origin, range, political authorization, and treasury cost before committing any inventory or balance mutation. A rejected request adds a journal command result with a reason and creates no order.

## Weapon production lifecycle

1. Validate `ActionProduceStrategicWeapon` against an owned design, research, optional production-policy allowlist, positive configured cost/duration, bounded quantity, and treasury balance.
2. Debit the configured total cost and persist a `pending` row in `strategic_production_orders`; do not increase inventory early.
3. At `completes_at_minute`, revalidate the design and research gates. If valid, increase `quantity`; after the design's `readiness_minutes`, increase `ready` and mark the order completed. A zero readiness delay completes both stages together.
4. If the design/research is no longer valid, cancel the order and refund its cost when the owning country still exists.
5. Keep production cost and duration in scenario data. A row with absent/non-positive values is an inventory-only row and cannot be queued for production.

## Accepted launch lifecycle

1. Create a durable `pending` order containing target/mode/payload/authorization and timing data.
2. Decrement ready/total weapon inventory and debit the launch cost atomically with order creation.
3. Resolve time from positive weapon `flight_minutes`, otherwise `strategic_flight_minutes`, with a minimum one-minute delay.
4. Publish a transition event and authorized launch notifications. If detected, target/observers receive an early-warning message without unconfirmed impact details; attribution may remain unknown.
5. At resolution, cancel on a missing target or changed target ownership; otherwise evaluate eligible defenses in configured order.
6. Stop on interception. If no defense intercepts, apply bounded target and collateral effects, update supported authoritative fields, and record each impact.
7. Publish final transition/notifications and apply diplomatic relation deltas through the existing relations table. Do not rewrite ownership or treaty membership.

## Defense contract

- Only researched, operational layers with positive readiness and matching coverage/range may attempt.
- Default order is long-range then short-range; scenario `missile_defense_layer_order` may override it.
- Default probabilities are long-range `0.60` then `0.50` after first-attempt failure (combined `0.80` at full readiness), and short-range `0.50` once. Configured probabilities are clamped to `[0, 1]` and scaled by layer readiness.
- Each attempt is seeded by simulation seed, stable order ID, and layer/attempt salt. The attempt record is serialized on the order.
- No blast damage is applied after interception. Defense readiness and configured daily maintenance are consumed through existing layer state.

## Impact contract

- Military and civilian modes produce distinct impact categories.
- Unit damage applies only to eligible units in the target region; if `target_object_id` is supplied, only that object is affected.
- Civilian impact updates only supported regional fields and country fields. Public approval uses `countries.gvt_approval`; legacy/custom schemas may use `approval_rating` only when `gvt_approval` is absent.
- Effect magnitudes are clamped and aggregate. They are not a spatial blast simulation. Collateral rows identify a separate affected region/category and are bounded independently.
- Every lifecycle transition emits `EventStrategicStrikeTransition`. Messages are limited to the attacker, detected target, configured observers, and final target/attacker recipients. Relations change through `countries_relations` only.

## Persistence and client projection

All lifecycle state resides in schema-registered `strategic_weapons`, `strategic_production_orders`, `strategic_launch_orders`, `missile_defense_layers`, and `strategic_impacts` tables plus existing country/region/unit/research/relations/messages state. Existing snapshot, IPC, save/load, and ordered-action replay mechanisms are authoritative; no feature-specific persistence path is introduced.

The client reads presenter projections and sends `ActionLaunchStrategicStrike`. It does not mutate `GameState`. The panel reports readiness, range, payload profile, pending target/order, authorization/target validation status, defense coverage and configured interception estimate, and recent outcomes. Any probability shown before resolution is an estimate, not the seeded result.
