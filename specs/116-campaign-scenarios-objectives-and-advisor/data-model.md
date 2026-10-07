# Data Model: Campaign Scenarios, Objectives, and Advisor

## Authoritative scenario definition — `campaign_scenarios`

Scenario configuration identifies title/description, selectable country IDs, political/sphere scope, bounded starting setup, enabled rules, objective definitions, win/loss conditions, maximum duration, sandbox continuation, and enabled state. Starting setup is validated against a per-table field allowlist and applied once by `CampaignSetupSystem` before the first actionable update.

## Runtime campaign — `campaigns`

One record per scenario actor and game start, keyed by deterministic `id`; stores `scenario_id`, `player_id`, actor country/scope, start minute, setup-applied flag and provenance, effective rules, outcome/reason/time, and whether post-outcome sandbox continuation is allowed. Outcomes include ongoing, victory, defeat, draw, and sandbox continuation.

## Campaign objective — `objectives`

One progress record per campaign definition with actor/country, type, target IDs/resource/branch/control field, target/current/remaining values, comparison, required flag, relative or absolute deadline, hold duration/start/elapsed time, reset-or-decay rule, last evaluation/change times, status/reason, missing-data reason, and append-preserving evidence JSON.

Supported measurements include region control/conquest, treaty membership, resource quantity/share, GDP per capita, research level, strategic weapon construction, and strategic weapon use. Measurement output records whether the authoritative source is available, its value and unit, and source table. Missing sources block visibly instead of inventing zero data.

Objective states: `pending`, `active`, `completed`, `failed`, `expired`, `cancelled`, or `blocked`. Optional `failure_conditions` are authoritative metric predicates; any satisfied predicate records a failed transition. On a terminal non-sandbox campaign outcome, unresolved goals fail on defeat or are cancelled on victory/draw. Hold conditions accrue only while continuously satisfied; a lost condition resets or decays according to the definition. A legacy objective without a campaign record remains presentable and begins evaluating from current authoritative state.

Measurements include population totals and the current human-development index from the country record, in addition to control/conquest, treaty membership, resource quantity/share, GDP per capita, research level, and strategic weapon construction/use. Resource quantity may fall back from the domestic production ledger to the regional production ledger; missing authoritative inputs remain blocked.

## Sphere/party delegation — `sphere_delegations`

Stores campaign and owner country, delegate, scope type/ID, explicit authority domains, priorities, start minute, return condition, current controller, active flag, and reason. Supported scopes are country, ruling party, and active treaty sphere. Return conditions are `manual` and `campaign_end`; campaign-end delegation returns to human control when the non-sandbox campaign concludes. AI context is reconstructed from these rows and is narrowed to the declared authority and current scope; ownership is not transferred.

## Advisor recommendation — `advisor_recommendations`

Stores campaign/actor, title/reason/source signal, affected country/region, confidence, urgency, expiry, optional action JSON, active/stale/resolved status, creation time, and stale reason. Recommendations are informational: they never dispatch their optional action automatically. Signals that cease to apply become stale; expired/resolved items are not presented as current guidance.

## Relationships and evaluation order

```text
campaign_scenarios ──start──> campaigns ──owns──> objectives
                                     ├──────────> sphere_delegations
                                     └──────────> advisor_recommendations

CampaignSystem boundary:
authoritative source tables → objective progress → outcome rules → advisor signals → active scenario rules
```

This order makes simultaneous objective/deadline results deterministic and ensures advisor projections observe the just-updated objective state. State persists through existing registered-table snapshots, IPC, and saves.
