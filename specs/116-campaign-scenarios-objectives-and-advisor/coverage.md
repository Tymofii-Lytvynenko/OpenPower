# Campaign Feature Coverage Matrix

## Baseline

Focused baseline before feature-specific changes on 2026-10-07:

```text
50 passed, 1 skipped, 6 subtests passed in 4.27s
```

Command: the focused campaign, AI delegation, IPC, save, and layer-boundary tests. The post-change quickstart result is recorded in `research.md`. The campaign performance gate is documented there; its three measured optimization iterations are exhausted and must not be repeated.

## Functional requirements

| Requirement | Implementation and evidence |
| --- | --- |
| FR-001 selectable actors, scope, setup, deadlines, outcomes, sandbox | Server validates playable actor allowlists plus current party/treaty scope; `campaign_selection.py` filters new-game actors and previews scope/rules/objective deadlines. Tested in `test_scenario_allowlist_rejects_existing_but_unselectable_actor`, scope validation, and `test_campaign_selection.py`. |
| FR-002 one-time country/party/sphere, relations, military/economic setup, rules | Setup allowlist covers countries, regions, governments, relations, research, strategic weapons, and treaty membership. All table frames are type-checked before commit. Tested by one-time setup and invalid/unsupported update cases. |
| FR-003 control, conquest, treaty, resource, GDP/person, population/development, strategic construction/use, resource share | `campaign_objective_policy.measure_objective`; exhaustive canonical measurement matrix asserts source tables, regional-production fallback, and unavailable population/development inputs. |
| FR-004 objective actor, target, threshold, hold, deadline, progress, failure predicates, evidence | `objectives` schema, `_build_objective`, `_evaluate_objectives`; tests cover pending, active, completed, failed, expired, cancelled, and blocked rows with transition evidence. |
| FR-005 authoritative subsystem outputs only | Measurements read territory, active treaty, production, country population/development/GDP, research, and strategic tables. Missing inputs block with a reason; no missing value is substituted with a fabricated successful metric. |
| FR-006 current/target/remaining, held time, deadline, last-change evidence | `CampaignPresenter.latest_evidence` and `ObjectivesPanel`; unit test verifies current/target/remaining, hold time, deadline, source, and last measured value. Equality remaining uses absolute distance. |
| FR-007 pending/active/completed/failed/expired/cancelled/blocked with reasons | Lifecycle tests cover all seven states. Explicit failure conditions fail objectives; terminal non-sandbox victory/draw cancels unresolved goals and defeat fails them. |
| FR-008 required/optional objectives, outcomes, deadlines, draw, sandbox | Outcome tests cover objective/metric victory, simultaneous draw, deadlines, optional cancellation, sandbox advisor continuation, and deadline-boundary completion/expiry. |
| FR-009 delegation owner/delegate/scope/authority/priorities/time/return/controller | Country, current ruling party, and active treaty tests verify scope; duplicate actions are idempotent; `manual` and `campaign_end` return conditions are visible and persist. |
| FR-010 delegation stays in declared scope and does not change ownership | Rejected invalid authority/return-condition actions preserve rows; AI policy tests verify party/treaty target filters and country ownership is unchanged. |
| FR-011 advisor consumes messages/news/objectives/system signals | Advisor tests cover political crises, news, unread messages, blocked objectives/deadlines, debt distress, migration pressure, and infrastructure damage. |
| FR-012 reason/source/affected area/confidence/urgency/expiry/optional action; no implicit command | Recommendation tests verify contextual fields, urgency/confidence, expiry, stale/expired transitions, and empty optional-action proposals. No path dispatches them. |
| FR-013 AI and delegated actors use campaign/authority rules | `AISystem._delegation_context` integration tests ensure live party/treaty scope and explicit domain authority narrow AI context. |
| FR-014 save/load, snapshots, IPC, replay | `test_campaign_persistence.py` compares campaign-owned rows through snapshot, IPC, save/load and deterministic continuation. |
| FR-015 identical state/time/actions produce identical campaign results | Persistence test replays identical starts/delegation/news/time inputs and compares campaign, objective, recommendation, scenario, and delegation rows. |
| FR-016 overview shows objectives/evidence/delegation/advisor priorities | Presenter and panel tests cover country scoping, sort order, progress/deadline/evidence, and delegation priority/return text. Rendered usability acceptance remains manual. |

## Acceptance scenarios and edge cases

| Scenario | Evidence / acceptance check |
| --- | --- |
| AC-1 Start scenario and expose eligible actor/scope/setup before actions | Setup is applied once; actor list filters by scenario; preview exposes scope, rules, objectives, and deadlines. |
| AC-2 Track all objective families | Table-driven measurement test covers every canonical supported type and authoritative source. |
| AC-3 Hold region/conquest control continuously | Region-control hold tests cover reset, decay, and conquest measurement. |
| AC-4 GDP/person, resource share, population/development thresholds | All four metric families and missing population/development sources are covered. |
| AC-5 Treaty/strategic resolution uses authoritative records | Treaty membership/inactive treaty, construction, and strategic-use tables are covered. |
| AC-6 Delegate bounded sphere and return it | Country/party/sphere authority, invalid actions, manual return, campaign-end return, and idempotence are covered. |
| AC-7 Advisor priority/context for crises/opportunities/deadlines | Crisis, opportunity news, message, objective deadline, debt, migration, and infrastructure signals are covered. |
| AC-8 Deterministic victory/defeat/draw/sandbox state | Victory, defeat, draw, deadlines, optional closure, and sandbox continuation tests pass. |
| AC-9 Continue after persistence and load | Campaign-owned save/load/snapshot/IPC/replay continuation test passes. |
| EC-1 Empty objective sandbox stays playable | Empty scenario enters sandbox and accepts bounded delegation without forced outcome. |
| EC-2 Two objectives on one signal evaluate independently | Duplicate production measurement test gives each objective its own target/status/evidence. |
| EC-3 Control lost before hold completes resets/decays | Separate reset and decay hold tests pass; regained control accrues from preserved progress only. |
| EC-4 Missing metric source visibly blocks | Missing resource, population, and development records return unavailable/block reasons. |
| EC-5 Actor/delegation changes do not transfer progress | Changing current player country leaves objective actor/country attached to the original campaign actor. |
| EC-6 Deadline and completion on one boundary are deterministic | Exact-deadline completion wins; unmet objective remains live at the deadline and expires after it. |
| EC-7 Invalid advisor guidance is stale, not actionable | Read-message invalidation stales guidance; expiry transitions to expired; recommendations carry no dispatched action. |
| EC-8 Legacy objective rows remain visible and initialize from current state | Presenter retains legacy rows; evaluator now measures them from authoritative state even without a campaign record. |

## Success criteria

| Criterion | Evidence |
| --- | --- |
| SC-001 setup once and overview ready before first action | Setup/action tests plus campaign presenter projection. |
| SC-002 supported objective types update from authoritative state with evidence | Measurement matrix and transition tests. |
| SC-003 a lost held condition is not falsely completed | Existing hold reset test plus decay case. |
| SC-004 every configured high-priority signal has context and expiry | Signal-family/lifecycle tests. |
| SC-005 seeded/replayed/save-loaded state is identical | Campaign persistence/replay test. |
| SC-006 next action/deadline discoverable in 30 seconds | Panel text is covered headlessly, but the rendered 30-second desktop check is still open because no native app is exposed in this task. |
| SC-007 10,000 objectives + 5,000 signals under 500 ms | 458.45 ms after exactly three optimization iterations; no further tuning permitted. |

## Scope exclusions

Multiplayer (`specs/102`) and game-editor-specific behavior listed in `specs/implementation-scope.md` are excluded. Shared gameplay map rendering and general game navigation remain in scope.
