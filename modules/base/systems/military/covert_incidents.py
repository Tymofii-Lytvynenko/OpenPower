"""Build the audience and record for a resolved covert mission."""


def mission_incident(mission, outcome, incident_id: str, now: int) -> dict:
    owner = str(mission.get("owner_country_id") or "").strip().upper()
    target = str(mission.get("target_country_id") or "").strip().upper()
    audience = [owner]
    if outcome.discovered:
        audience.append(target)
        if outcome.attributed_country_id and outcome.attributed_country_id not in {owner, target}:
            audience.append(outcome.attributed_country_id)
    return {
        "id": incident_id,
        "mission_id": mission["id"],
        "audience_country_ids": sorted(set(filter(None, audience))),
        "incident_type": "discovery" if outcome.discovered else "operation_result",
        "summary": (
            outcome.result if outcome.discovered or audience == [owner]
            else "Unattributed security incident"
        ),
        "created_at_minute": now,
    }
