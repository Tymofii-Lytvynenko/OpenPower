# Contract: Battle Status View

`BattleStatusView` is a read-only projection built from the latest authoritative snapshot. It is usable by the map overlay, the battle overview panel, and a selected-battle details view without exposing mutable server objects.

## Shape

```text
BattleStatusView {
  battle_id: str
  region_id: int
  region_name: str
  status: active | stalemate | concluded
  mode: positional | assault
  round: int
  side_a: {
    countries: list[str]
    participants: list[ParticipantView]
    weighted_strength: float
    losses: int
  }
  side_b: {
    countries: list[str]
    participants: list[ParticipantView]
    weighted_strength: float
    losses: int
  }
  balance: float
  readiness_distribution: {
    parked: int
    ready: int
    fortified: int
  }
  victor_side: str
  occupation: {
    status: str
    controller_country_id: str
    garrison_strength: int
    resistance: float
    contested: bool
  }
  started_at_minute: int
  updated_at_minute: int
  concluded_at_minute: int
}

ParticipantView {
  country_id: str
  role: principal | ally
  unit_count: int
  weighted_strength: float
}
```

The view uses stable country ordering and preserves `SIDE_A`/`SIDE_B` labels even if the attacker/defender display text changes. It contains no terrain, supply, regional fortification, or logistics fields.

## Unit readiness projection

The unit details/overlay projection contains:

```text
unit_id, owner, readiness_status, transition_target,
readiness_progress, readiness_eta_minute, pending_order_type
```

The progress bar is determinate only when a transition exists. It is hidden (or rendered as zero) for a stable unit. A transition status label must identify both current and target statuses so `ready -> fortified` is not mistaken for an already fortified unit.

## Refresh contract

The client computes a snapshot signature from:

```text
battles, battle_participants, battle_units, occupations,
selected_unit_readiness, selected_unit_pending_order
```

When the signature changes, the presenter rebuilds views and the renderer refreshes markers/overlays. A snapshot with unchanged signature is safe to skip. The client does not infer combat results, advance progress, or write a table.

Snapshot decoding and view projection are bounded, headless-safe operations. They must not wait for graphics initialization, network I/O, or simulation locks; the performance fixture records the update bound for a representative battle snapshot.

## Panel behavior

- The battle overview lists active and stalemate battles and keeps a concluded battle visible until the next snapshot retires it.
- Each row shows region, mode, status, both side country lists, relative balance, and current weighted strengths.
- Selecting a row focuses the corresponding region and makes the side/participant detail available without issuing a gameplay action.
- An empty or unavailable table produces the existing empty-state message instead of a client exception.

## Map behavior

The tactical map keeps the current engagement markers. A battle marker adds a status color and a compact balance indicator; a concluded battle marker is removed after the authoritative snapshot no longer contains it. Unit status icons and progress bars remain screen-space overlays and follow the existing projection/selection rules.

## Compatibility and failure handling

If an older snapshot lacks new columns, the presenter applies the same defaults as the data-model migration (`ready`, no transition, `active`/`inactive` legacy status) and still renders the existing battle row. Malformed participant rows are ignored for display and surfaced through the existing diagnostic path; they must never mutate simulation state.
