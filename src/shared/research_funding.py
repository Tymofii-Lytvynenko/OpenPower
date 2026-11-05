from __future__ import annotations

from collections.abc import Iterable, Mapping
import math


RESEARCH_CATEGORY_FUNDING_GROUP = ("ground", "air", "naval", "strategic")
STRATEGIC_PROGRAM_FUNDING_GROUP = (
    "strategic_program",
    "strategic_weapons",
    "strategic_defense",
)


def linked_research_funding_group(branch: str) -> tuple[str, ...]:
    normalized_branch = str(branch or "").strip().lower()
    if normalized_branch in RESEARCH_CATEGORY_FUNDING_GROUP:
        return RESEARCH_CATEGORY_FUNDING_GROUP
    if normalized_branch in STRATEGIC_PROGRAM_FUNDING_GROUP:
        return STRATEGIC_PROGRAM_FUNDING_GROUP
    return (normalized_branch,)


def redistribute_linked_funding(
    funding_by_branch: Mapping[str, float],
    selected_branch: str,
    requested_ratio: float,
    linked_branches: Iterable[str],
    *,
    locked_branches: Iterable[str] = (),
) -> dict[str, float]:
    """Apply the source linked-meter delta to the selected branch and its peers."""
    updated = dict(funding_by_branch)
    group = tuple(dict.fromkeys(linked_branches))
    updated[selected_branch] = _ratio(requested_ratio)
    if selected_branch not in group:
        return updated

    previous_ratio = _ratio(funding_by_branch.get(selected_branch, 0.0))
    delta_to_distribute = previous_ratio - updated[selected_branch]
    locked = set(locked_branches)
    peers = tuple(branch for branch in group if branch != selected_branch and branch not in locked)
    if not peers or abs(delta_to_distribute) <= 1e-12:
        return updated

    peer_total = sum(_ratio(funding_by_branch.get(branch, 0.0)) for branch in peers)
    equal_share = peer_total == 0.0
    for branch in peers:
        previous_peer_ratio = _ratio(funding_by_branch.get(branch, 0.0))
        share = 1.0 / len(peers) if equal_share else previous_peer_ratio / peer_total
        updated[branch] = _ratio(previous_peer_ratio + delta_to_distribute * share)

    return updated


def _ratio(value: object) -> float:
    try:
        ratio = float(value)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    if not math.isfinite(ratio):
        return 0.0
    return min(1.0, max(0.0, ratio))
