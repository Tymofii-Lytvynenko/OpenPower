# Covert Actions and Visibility Contract

## Commands

The client and AI submit semantic actions through the existing action boundary:

- `ActionCreateCovertCell`: request a cell for an authorized owner and target.
- `ActionTrainCovertCell`: request a funded eligible skill increase.
- `ActionSetCovertCellAssignment`: request a lifecycle/assignment change.
- `ActionStartCovertMission`: request one supported mission for an available cell.
- `ActionRetireCovertCell`: retire an owned eligible cell.

The authoritative system revalidates ownership, capacity, target, mission/skill compatibility, readiness, communications, route access, war/diplomacy rules, deadlines, duplicate activity, and funds. A rejection publishes a reason and leaves the cell, budget, and target unchanged. The UI must not write tables directly.

## Resolution and side effects

Mission resolution is deterministic from authoritative game state and uses configured mission profiles. It emits bounded findings/incidents, messages and diplomatic/political effects through existing contracts. Sabotage may disrupt a target value but cannot delete authoritative entities. Detection and attribution are separate outcomes.

## Audience rules

- Owners may inspect their cells, missions, and findings.
- A target may inspect operation type/result only after discovery.
- Detection may reveal details without revealing the owner; unattributed operations must not leak owner IDs, cell IDs, or the private output payload.
- Other countries receive only findings shared by an eligible treaty effect. Shared military findings preserve source confidence/freshness limits.
- The presenter may downgrade known information into confirmed, estimated, outdated, or unknown states; it may not increase authority or confidence.

## State and compatibility

Covert tables travel through the existing GameState snapshot and save boundaries. Missing records in legacy state mean empty tables. New fields require the normal schema/migration path; no covert-specific client persistence is allowed.
