"""Authoritative commands for prepared covert missions awaiting execution."""
from src.shared.actions import ActionExecuteCovertMission
from modules.base.systems.military.authority_policy import player_controls_country


def control_prepared_mission(state, cells, missions, action):
    mission = next((row for row in missions if str(row.get("id")) == str(action.mission_id)), None)
    cell = next((row for row in cells if mission and str(row.get("id")) == str(mission.get("cell_id"))), None)
    if not mission or not cell:
        return "The selected mission or cell is unavailable."
    country = str(mission.get("owner_country_id") or "").strip().upper()
    if country != str(cell.get("country_id") or "").strip().upper() or not player_controls_country(state, action.player_id, country):
        return "The issuer cannot command this mission."
    execute = isinstance(action, ActionExecuteCovertMission)
    if execute:
        if mission.get("status") != "ready" or cell.get("status") != "ready":
            return "The mission is not awaiting execution."
        target = str(mission.get("target_country_id") or "").strip().upper()
        countries, regions = state.tables.get("countries"), state.tables.get("regions")
        if (not cell.get("communications_ready")
                or str(cell.get("location_country_id") or "").strip().upper() != target
                or str(cell.get("target_country_id") or "").strip().upper() != target):
            return "The cell no longer has access or communications at the target."
        if (countries is None or not any(str(r.get("id") or "").strip().upper() == target for r in countries.iter_rows(named=True))
                or regions is None or not any(str(r.get("owner") or "").strip().upper() == target for r in regions.iter_rows(named=True))):
            return "The mission target is no longer available."
    elif mission.get("status") not in {"preparation", "ready"} or cell.get("status") not in {"preparing", "ready"}:
        return "Only a preparing or ready mission can be cancelled."
    now = int(state.time.total_minutes)
    if execute:
        try:
            duration = max(1, int(float(state.globals.get("covert_execution_minutes", 1))))
        except (TypeError, ValueError, OverflowError):
            return "The configured mission execution duration is invalid."
        if now + duration > 9_223_372_036_854_775_807:
            return "The mission execution date exceeds the supported range."
        mission.update(status="executing", resolves_at_minute=now + duration, updated_at_minute=now)
        cell.update(status="preparing", last_known_status="executing mission")
    else:
        mission.update(status="cancelled", updated_at_minute=now, result="cancelled")
        cell.update(status="active", mission_type="", last_known_status="mission cancelled")
    # Preparation was already funded. Neither starting execution nor cancellation
    # charges again or fabricates a refund for work that has already been done.
    state.journal.append_command_result(dict(tick=int(state.globals.get("tick", 0)), player_id=str(action.player_id),
        action_type=type(action).__name__, status="applied", reason="Mission execution started." if execute else "Mission cancelled."))
    return ""
