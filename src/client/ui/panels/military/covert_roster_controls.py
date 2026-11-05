"""Source row controls with country-scoped pending authoritative requests."""
from src.client.ui.core.instrumented_imgui import imgui
from src.client.services.journal_cursor import JournalCursor
from src.client.ui.components.hud.country_selector import country_options_from_state
from src.shared.actions import ActionRetargetCovertCell, ActionSetCovertCellActivity


def _signature(row):
    return row.get("country_id"), row.get("target_country_id"), row.get("status")


class CovertRosterControls:
    def __init__(self):
        self.pending = {}
        self._cursor = None
        self._country = ""

    def update(self, state, context):
        country = str(context.target_tag or "").upper()
        if country != self._country:
            self._country = country
            self.pending.clear()
        records = getattr(getattr(state, "journal", None), "command_results", [])
        if self._cursor is None:
            self._cursor = JournalCursor(records)
        else:
            for record in self._cursor.consume(records):
                actor = str(record.get("actor_id") or record.get("player_id") or "")
                client = context.net_client
                if (client is not None and actor == str(client.player_id)
                        and record.get("status") in {"applied", "rejected", "failed"}
                        and record.get("action_type") in {"ActionRetargetCovertCell", "ActionSetCovertCellActivity"}):
                    self.pending.pop(str(record.get("cell_id") or ""), None)
        table = state.tables.get("covert_cells")
        rows = {} if table is None else {str(r.get("id")): r for r in table.iter_rows(named=True)}
        for key, signature in list(self.pending.items()):
            if key not in rows or _signature(rows[key]) != signature:
                self.pending.pop(key, None)

    def submit(self, row, action, context):
        key = str(row.get("id"))
        if (not context.is_own_country or context.net_client is None or key in self.pending
                or str(row.get("country_id") or "").upper() != str(context.target_tag or "").upper()):
            return False
        self.pending[key] = _signature(row)
        context.net_client.send_action(action)
        return True

    def render(self, ui, row, mission, state, context, on_select):
        key = str(row.get("id"))
        status = str(row.get("status") or "unknown")
        target = str(row.get("target_country_id") or "")
        available = (context.is_own_country and context.net_client is not None
                     and status in {"active", "idle", "dormant"} and bool(row.get("communications_ready"))
                     and not (mission and mission.get("status") in {"preparation", "ready", "executing", "cleanup"})
                     and key not in self.pending)
        options = country_options_from_state(state)
        tags, labels = [option.tag for option in options], [option.name for option in options]
        if target not in tags:
            tags.insert(0, target)
            labels.insert(0, target or "Unknown")
        imgui.begin_disabled(not available)
        changed, index = imgui.combo("##assigned_country", tags.index(target), labels,
            test_id=f"covert_ops.cell.{key}.country", gml_id=ui.path("cboCountry"))
        imgui.end_disabled()
        if changed and available:
            on_select(key)
            self.submit(row, ActionRetargetCovertCell(context.net_client.player_id, key,
                tags[index], target, status), context)
        states = ["Active", "Dormant"]
        current = "Active" if status == "idle" else status.replace("_", " ").title()
        if current not in states:
            states.insert(0, current)
        imgui.begin_disabled(not available or key in self.pending)
        changed, index = imgui.combo("##cell_activity", states.index(current), states,
            test_id=f"covert_ops.cell.{key}.status", gml_id=ui.path("cboStatus"))
        imgui.end_disabled()
        if changed and available and key not in self.pending:
            on_select(key)
            self.submit(row, ActionSetCovertCellActivity(context.net_client.player_id, key,
                states[index] == "Active", target, status), context)
        if imgui.is_item_hovered(imgui.HoveredFlags_.allow_when_disabled) and not available:
            imgui.set_tooltip("Awaiting server reply." if key in self.pending else
                              "Finish or cancel the current operation and restore communications before editing.")
