"""Build actionable inbox entries from persisted domain facts."""
from __future__ import annotations

from src.client.ui.panels.service.region_control_dispatches import region_control_dispatches


def journal_dispatches(
    state,
    country_tag: str,
    dismissed_region_event_ids: frozenset[str] | set[str] = frozenset(),
) -> list[dict]:
    country = str(country_tag).upper()
    rows = []
    for record in reversed(getattr(getattr(state, "journal", None), "domain_events", [])):
        payload = record.get("payload") or {}
        event_type = record.get("event_type")
        kind, reference, subject, body = "", "", "", ""
        if event_type == "EventBattleEnded" and country in payload.get("participant_countries", []):
            kind, reference = "battle", str(payload.get("battle_id") or "")
            subject = f"Battle concluded: {reference}"
            body = f"Victor: {payload.get('victor_tag') or 'Undecided'}"
        elif event_type == "EventDiplomaticTradeChanged" and country in {
            payload.get("source_country_id"), payload.get("target_country_id"),
        }:
            kind, reference = "trade", str(payload.get("deal_id") or "")
            subject = f"Trade {payload.get('status') or 'updated'}: {reference}"
            body = str(payload.get("reason") or "")
        elif event_type == "EventTreatyProposed" and country in {
            payload.get("source_country_tag"), payload.get("target_country_tag"),
        }:
            kind, reference = "treaty", str(payload.get("treaty_id") or "")
            subject = f"Treaty proposal: {reference}"
        elif event_type == "EventTreatyRefused" and country == payload.get("source_country_tag"):
            kind, reference = "treaty_refusal", str(payload.get("treaty_id") or "")
            subject = f"Treaty refused: {payload.get('title') or reference}"
            body = str(payload.get("reason") or "Reason not recorded")
        if kind and reference:
            rows.append(dict(id=str(record.get("event_id") or ""), kind=kind,
                             reference=reference, subject=subject, body=body, payload=payload))
    rows.extend(region_control_dispatches(state, country, dismissed_region_event_ids))
    from src.client.ui.panels.military.presenter import MilitaryPresenter
    missions = MilitaryPresenter().covert_missions_for_country(state,country) if "covert_missions" in getattr(state,"tables",{}) else []
    cells_table = getattr(state, "tables", {}).get("covert_cells")
    cells = {} if cells_table is None or "country_id" not in cells_table.columns else {
        str(row.get("id")): row for row in cells_table.iter_rows(named=True)
        if str(row.get("country_id") or "").upper() == country}
    for mission in missions:
        cell_id = str(mission.get("cell_id") or "")
        cell = cells.get(cell_id)
        if (mission.get("owner_country_id") == country and mission.get("status") == "ready"
                and cell and cell.get("status") == "ready"):
            key = str(mission.get("id") or "")
            # This is a current readiness notice, not a replay of historical
            # events. Execution/cancellation removes it just as the source does.
            rows.append(dict(id=f"covert-ready:{key}", kind="covert_ready", reference=cell_id,
                subject=f"{cell.get('cell_name') or cell_id}: ready to execute",
                body=str(mission.get("mission_type") or "").replace("_", " "),
                payload=dict(mission_id=key, cell_id=cell_id)))
        if mission.get("result"):
            key = str(mission.get("id") or "")
            rows.append(dict(id=f"covert:{key}",kind="covert",reference=key,
                subject=f"Operation result: {key}",body=str(mission.get("result")),payload={}))
    return rows
