"""Project territory ownership changes into the local player's mail inbox."""
from __future__ import annotations

from collections.abc import Mapping


def region_control_dispatches(
    state,
    country_tag: str,
    dismissed_event_ids: frozenset[str] | set[str] = frozenset(),
) -> list[dict]:
    country = str(country_tag or "").strip().upper()
    records = getattr(getattr(state, "journal", None), "domain_events", [])
    if not country:
        return []

    latest_by_region: dict[int, tuple[str, str, int]] = {}
    for sequence, record in enumerate(records):
        if record.get("event_type") != "EventTerritoryOwnershipChanged":
            continue
        payload = record.get("payload") or {}
        region_id = _region_id(payload.get("region_id"))
        if region_id is None:
            continue

        previous_owner = str(payload.get("previous_owner") or "").strip().upper()
        owner = str(payload.get("owner") or "").strip().upper()
        event_id = str(record.get("event_id") or f"journal:{sequence}")
        if owner == country and previous_owner != country:
            change = "gained"
        elif previous_owner == country and owner != country:
            change = "lost"
        else:
            continue

        # The source removes an opposite pending region and clears the whole
        # grouped mail set when it is viewed. Replaying every journal row would
        # otherwise put acknowledged regions back into a later mail item.
        if event_id in dismissed_event_ids:
            latest_by_region.pop(region_id, None)
            continue

        latest_by_region[region_id] = (change, event_id, sequence)

    names = _region_names(state, set(latest_by_region))
    dispatches = []
    for kind, title in (("gained", "TERRITORY GAINED"), ("lost", "TERRITORY LOST")):
        changes = [
            (region_id, event_id, sequence)
            for region_id, (change, event_id, sequence) in latest_by_region.items()
            if change == kind
        ]
        if not changes:
            continue

        region_ids = sorted(region_id for region_id, _, _ in changes)
        event_ids = [event_id for _, event_id, _ in sorted(changes, key=lambda change: change[2])]
        latest_event_id = max(changes, key=lambda change: change[2])[1]
        dispatches.append(
            {
                "id": f"region-{kind}:{latest_event_id}",
                "kind": "region_control",
                "reference": kind,
                "subject": f"{title.title()} ({len(region_ids)})",
                "body": "\n".join(
                    (title, *(names.get(region_id, f"Region {region_id}") for region_id in region_ids))
                ),
                "payload": {"region_ids": region_ids, "event_ids": event_ids},
            }
        )
    return dispatches


def _region_id(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        region_id = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return region_id if region_id > 0 else None


def _region_names(state, region_ids: set[int]) -> dict[int, str]:
    tables = getattr(state, "tables", {})
    regions = tables.get("regions") if isinstance(tables, Mapping) else None
    if regions is None or not {"id", "name"}.issubset(regions.columns):
        return {}
    requested = set(region_ids)
    return {
        int(row["id"]): str(row["name"] or f"Region {row['id']}")
        for row in regions.select("id", "name").iter_rows(named=True)
        if row.get("id") is not None and int(row["id"]) in requested
    }
