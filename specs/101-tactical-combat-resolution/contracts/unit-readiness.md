# Contract: Unit Readiness

## Domain values

The wire values are lowercase strings:

```text
readiness_status: parked | ready | fortified
transition_stage: direct | parked_to_ready | parked_to_fortified | ready_to_fortified
pending_order_status: queued | released | canceled | rejected
```

## Command

`ActionSetUnitReadiness` is a shared passive action:

```text
unit_id: str
target_status: str  # parked, ready, or fortified
```

The server validates ownership, unit existence, and the target value. The command is idempotent when the target equals the stable status and no transition is active. It is rejected with a domain error when the unit is destroyed, missing, or controlled by another country.

## State contract

Every unit snapshot contains:

```text
readiness_status: str
readiness_transition_id: str
readiness_progress: float  # [0.0, 1.0]
readiness_eta_minute: int
remaining_minutes: int  # derived, never persisted as a second countdown
```

When `readiness_transition_id` is empty, progress is `0.0`, ETA is `0`, and `remaining_minutes` is `0`. During a transition, `readiness_status` remains the last completed status, while the target and timing are read from the transition row. The server clamps progress and persists the absolute ETA; `remaining_minutes=max(0, readiness_eta_minute-current_game_minute)` is derived for presentation. Clients must not extrapolate or submit progress.

## Transition rules

| Current | Requested | Server result |
|---------|-----------|---------------|
| `parked` | `ready` | Schedule 2 game days. |
| `ready` | `parked` | Complete immediately. |
| `ready` | `fortified` | Schedule 2 game days. |
| `fortified` | `ready` | Complete immediately. |
| `parked` | `fortified` | Schedule `parked_to_ready` for 2 days, then `ready_to_fortified` for 2 days. |
| any | current stable status | No-op if no transition; an explicit request cancels an incompatible transition and pending order. |

At each simulation update the readiness system:

1. advances progress from authoritative game minutes;
2. completes due transitions atomically;
3. starts the second stage of `parked -> fortified` or releases the pending order;
4. emits one transition event per completion boundary.

Paused simulation does not advance the clock or progress. Save/load preserves the transition ID, stage, timestamps, progress cache, and pending order.

## Order gating

`ActionMoveUnit` and `ActionAttackUnit` use this contract:

- a `parked` unit receives a pending order and a `parked -> ready` transition;
- a `ready` unit may execute immediately;
- a `fortified` unit cancels fortified posture, performs the immediate `fortified -> ready` release, and then executes or queues the order according to movement/attack validation;
- an order never executes before the required readiness boundary;
- a new explicit readiness command cancels an incompatible pending order and reports the cancellation event.

If hostile contact starts while a readiness transition is active, the server cancels the transition, removes its pending order, and resolves the unit using its last completed stable status. This cancellation is observable through `EventUnitReadinessCanceled` and cannot be reconstructed or overridden by the client.

Movement and attack also end a stable `fortified` posture even when the order later fails spatial or ownership validation. The latest valid movement/attack order replaces the existing pending order. An invalid replacement is rejected and leaves the existing pending order unchanged. A failed order does not mutate a completed transition.

When an order is accepted at the same simulation minute that a readiness transition becomes due, hostile-contact interruption is evaluated before transition completion. If contact is present, the transition is canceled and the unit enters combat with its last completed status; otherwise the transition completes and the pending order is released normally.

## Events

`EventUnitReadinessStarted`:

```text
unit_id, transition_id, from_status, target_status,
stage, started_at_minute, completes_at_minute
```

`EventUnitReadinessCompleted`:

```text
unit_id, transition_id, status, completed_at_minute,
released_order_id
```

`EventUnitReadinessCanceled`:

```text
unit_id, transition_id, status, canceled_at_minute, reason
```

Events are server-generated, ordered by `(simulation_minute, unit_id, transition_id)`, and emitted once per state boundary. Replaying the same action/time sequence produces the same event payloads.

## Client presentation

The unit overlay displays the stable status icon/label. When a transition is active, it additionally displays target status, a determinate progress bar, and the derived remaining time in rounded days and hours. The UI disables or explains commands that will wait for readiness but does not silently change the action payload.
