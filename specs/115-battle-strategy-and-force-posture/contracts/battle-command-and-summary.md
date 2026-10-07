# Battle Command and Summary Contract

## Commands

- `ActionSetBattleStrategy(player_id, battle_id, strategy, country_tag, unit_type)` requests a posture or a named preset. The authoritative system checks active battle, country authority, participant ownership, and force-type eligibility before writing state.
- Matching `battle_strategy_constraints` scenario rules can restrict allowed strategies or require one. A rule violation rejects the entire command before posture, movement, funds, or command-order tables change.
- Commands received at one simulation boundary are sorted deterministically: occupation requests first, then battle/country posture requests; broad force scope precedes specific force types. Issuer and strategy provide stable same-scope tie-breakers.
- `ActionOccupyRegion(player_id, region_id, new_controller_tag)` requests military control after conflict and hostile-force gates pass. It must not change political owner.
- Rejected commands create an action-journal rejection with a readable reason and do not change unit posture, route, currency, controller, or command history.
- Rejection journaling is the only mutation for a rejected command; unrelated nullable projection values are not normalized as a side effect.

## Events and state

- Applied posture orders are persisted in `battle_command_orders`; current per-force projection is persisted in `battle_force_postures` and `units`.
- `EventBattleCommandApplied` identifies order, battle, country, resulting strategy, affected units, and game minute.
- Retreat and return use the shared `unit_movement_routes` contract and emit route/lifecycle status without changing the resolver's two-side model.
- Occupation emits `EventOccupationChanged` for each changed controller and records that sovereignty is unchanged.

## Viewer projection

- `MilitaryPresenter` methods that return force identity, positions, countries, posture history, or losses accept a viewer country.
- A participant or explicitly authorized intelligence source may receive detailed projections; nonparticipants receive no unit IDs or country-by-country force/loss details.
- Missing intelligence remains unknown; it is never represented as zero forces or a fabricated loss total.
- The overview labels its aggregate balance as an estimate and leaves authoritative outcome to `CombatSystem`.
- Authorized command history exposes all seven resolver projections, not only attack, defense, and casualty modifiers.
