"""Country-scoped cell selection and exact ready-mission navigation requests."""


class CovertSelection:
    def __init__(self):
        self.country = ""
        self.cell_id = ""
        self.selected_cell_ids = ()
        self.anchor_cell_id = ""
        self._requested = None
        self._unavailable_request = False

    def request(self, cell_id, mission_id=""):
        self._requested = (str(cell_id), str(mission_id))

    def select(self, cell_id):
        self.cell_id = str(cell_id or "")
        self.selected_cell_ids = (self.cell_id,) if self.cell_id else ()
        self.anchor_cell_id = self.cell_id
        self._unavailable_request = False

    def select_extended(self, cell_id, ordered_cell_ids, *, ctrl=False, shift=False):
        cell_id = str(cell_id)
        ordered = list(dict.fromkeys(str(value) for value in ordered_cell_ids))
        if cell_id not in ordered:
            ordered.append(cell_id)

        current = list(self.selected_cell_ids)
        if shift:
            anchor = self.anchor_cell_id if self.anchor_cell_id in ordered else cell_id
            first, last = sorted((ordered.index(anchor), ordered.index(cell_id)))
            selected = ordered[first:last + 1]
            if ctrl:
                selected = list(dict.fromkeys((*current, *selected)))
        elif ctrl:
            if cell_id in current:
                selected = [value for value in current if value != cell_id]
            else:
                selected = [*current, cell_id]
            self.anchor_cell_id = cell_id
        else:
            selected = [cell_id]
            self.anchor_cell_id = cell_id

        self.selected_cell_ids = tuple(value for value in ordered if value in selected)
        self.cell_id = cell_id if cell_id in self.selected_cell_ids else (
            self.selected_cell_ids[-1] if self.selected_cell_ids else ""
        )
        self._unavailable_request = False
        if not self.selected_cell_ids:
            self._unavailable_request = True

    def reconcile(self, country, cells, missions):
        if self.country != country:
            self.country, self.cell_id = country, ""
            self.selected_cell_ids = ()
            self.anchor_cell_id = ""
            self._unavailable_request = False
        index = {str(row.get("id")): row for row in cells}
        warning = ""
        if self._requested is not None:
            cell_id, mission_id = self._requested
            self._requested = None
            cell = index.get(cell_id)
            valid_mission = not mission_id or any(
                str(row.get("id")) == mission_id and str(row.get("cell_id")) == cell_id
                and row.get("status") == "ready" for row in missions)
            if cell is None or not valid_mission or (mission_id and cell.get("status") != "ready"):
                warning = "The requested cell or ready mission is no longer available."
                self.cell_id = ""
                self.selected_cell_ids = ()
                self.anchor_cell_id = ""
                self._unavailable_request = True
            else:
                self.select(cell_id)
        else:
            self.selected_cell_ids = tuple(value for value in self.selected_cell_ids if value in index)
            if self.cell_id not in self.selected_cell_ids:
                self.cell_id = self.selected_cell_ids[-1] if self.selected_cell_ids else ""
            if self.anchor_cell_id not in index:
                self.anchor_cell_id = self.cell_id
            if not self.selected_cell_ids and not self._unavailable_request:
                self.cell_id = next(iter(index), "")
                self.selected_cell_ids = (self.cell_id,) if self.cell_id else ()
                self.anchor_cell_id = self.cell_id
        return index.get(self.cell_id), warning


def selected_mission(missions, cell_id):
    candidates = [row for row in missions if str(row.get("cell_id")) == cell_id]
    active = [row for row in candidates if row.get("status") in {"preparation", "ready", "executing", "cleanup"}]
    return next(iter(active or candidates), None)


def mission_index(missions):
    result = {}
    active = {"preparation", "ready", "executing", "cleanup"}
    for mission in missions:
        key = str(mission.get("cell_id"))
        previous = result.get(key)
        if previous is None or (previous.get("status") not in active and mission.get("status") in active):
            result[key] = mission
    return result
