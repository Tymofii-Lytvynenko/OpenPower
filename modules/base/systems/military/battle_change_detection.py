"""Detect changes in the public state of an active battle."""

from collections.abc import Iterable, Mapping
from typing import Any


def battle_snapshot_changed(
    previous: Mapping[str, Any],
    *,
    status: str,
    mode: str,
    side_a_tags: Iterable[str],
    side_b_tags: Iterable[str],
    side_a_strength: int,
    side_b_strength: int,
    balance: float,
) -> bool:
    return (
        str(previous.get("status") or "active") != status
        or str(previous.get("mode") or "") != mode
        or str(previous.get("attacker_side") or "") != ",".join(sorted(side_a_tags))
        or str(previous.get("defender_side") or "") != ",".join(sorted(side_b_tags))
        or float(previous.get("side_a_strength") or -1.0) != float(side_a_strength)
        or float(previous.get("side_b_strength") or -1.0) != float(side_b_strength)
        or float(previous.get("balance") or -1.0) != balance
    )
