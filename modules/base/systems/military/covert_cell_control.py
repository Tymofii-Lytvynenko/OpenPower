"""Validate roster editing and apply activity changes without client policy."""
from modules.base.systems.military.authority_policy import player_controls_country


def editable_cell(state, cells, missions, action):
    cell = next((r for r in cells if str(r.get("id")) == str(action.cell_id)), None)
    if cell is None or not player_controls_country(state, action.player_id, str(cell.get("country_id") or "").upper()):
        return None, "The issuer cannot edit this covert cell."
    if (str(cell.get("target_country_id") or "").upper() != str(action.expected_target_country_tag or "").upper()
            or cell.get("status") != action.expected_status):
        return None, "The cell changed while editing. Review its current assignment and status."
    if cell.get("status") not in {"active", "idle", "dormant"}:
        return None, "The cell must be available or dormant before editing its country or activity."
    if any(str(r.get("cell_id")) == str(cell["id"]) and r.get("status") in
           {"preparation", "ready", "executing", "cleanup"} for r in missions):
        return None, "Cancel or finish the cell's current mission before editing its assignment."
    return cell, ""


def set_cell_activity(state, cells, missions, action):
    cell, reason = editable_cell(state, cells, missions, action)
    if reason:
        return reason
    if type(action.is_active) is not bool:
        return "Choose an active or dormant state."
    if action.is_active and (not cell.get("communications_ready")
            or str(cell.get("location_country_id") or "").upper() != str(cell.get("target_country_id") or "").upper()):
        return "The cell must reach its assignment and restore communications before activation."
    cell["status"] = "active" if action.is_active else "dormant"
    # Older dormant assignments used the assignment field as an activity flag.
    # Waking such a cell must remove that flag so mission validation can proceed.
    if action.is_active and cell.get("assignment") == "dormant":
        cell["assignment"] = "unassigned"
    cell["last_known_status"] = cell["status"]
    return ""
