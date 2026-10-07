# Campaign Actions and Overview Contract

## Commands

- `ActionStartCampaign(player_id, scenario_id, country_tag)` starts an enabled scenario for an existing selectable actor. The server validates scenario and setup JSON completely before applying any setup rows, creates the campaign/objectives once, and journals a readable applied/rejected result.
- Party-scoped starts require a current party record selected as the actor country's ruling party. Sphere-scoped starts require the configured active treaty to contain the selected country after staged setup is applied.
- Setup may update only existing rows in its explicit table/field allowlist. All staged frames must pass their registered Polars types before the first authoritative table is changed; allowed treaty-sphere setup fields are membership, sides, and status.
- `ActionSetSphereDelegation(player_id, country_tag, scope_type, scope_id, delegate_id, authority, priorities, active, return_condition)` adds, updates, or returns one explicit scoped delegation. Only the campaign owner may change it. Unsupported scope, authority, party, or treaty membership is rejected without changing the delegation or political ownership.
- Delegation return conditions are `manual` and `campaign_end`; the latter restores human control at a terminal non-sandbox outcome.
- `optional_action_json` on an advisor row is a proposal only; no recommendation silently dispatches a `GameAction`.

## Authoritative system boundary

- `CampaignSetupSystem` runs in bootstrap before gameplay actions and handles scenario start/delegation commands.
- `CampaignSystem` runs after domain systems and evaluates objectives, then campaign outcomes, advisor recommendations, and scenario rule publication.
- Objective types consume existing country/region/treaty/production/research/strategic records. They must not recalculate source-system mechanics.
- Delegation authority is derived from active rows and intersected with supported domains, matching country/party/treaty scope. It grants no control outside that scope.
- Stable IDs/order and identical state/time/actions produce identical progress, recommendations, and outcomes.

## Viewer projection

- `CampaignPresenter.build_overview(state, country_tag)` returns that actor's latest campaign, its scenario, campaign-owned objectives, active recommendations sorted by urgency/deadline, and that campaign's delegation records.
- Campaign overview shows objective current/target/remaining value, progress, status/reason, deadline, hold time, missing-data reason, outcome, scope/delegation, and active advisor priorities.
- New-game selection shows enabled scenarios and eligible actors before sending `ActionStartCampaign`.
- Client UI reads snapshots and sends semantic actions only; the simulation remains authoritative.

## Persistence/replay

Scenario definitions, campaign provenance/outcomes, objective evidence/deadlines, delegation state, and advisor status live in registered tables. Replaying the same ordered actions and simulation boundary from equivalent state must reproduce the same persisted rows and transitions.
