"""Snapshot-backed law drafts; all gameplay decisions remain on the server."""
from __future__ import annotations

import json
from dataclasses import dataclass

from src.shared.actions import ActionChangePoliticalLaw


def law_choices(row):
    try:
        values = json.loads(str(row.get("allowed_values_json") or "[]"))
    except (ValueError, TypeError):
        return ()
    return tuple(dict.fromkeys(value for value in values if isinstance(value, str) and value.strip())) if isinstance(values, list) else ()


@dataclass(frozen=True)
class LawDraft:
    original_value: str
    target_value: str


class LawPolicyDraft:
    def __init__(self):
        self.country = ""
        self.pending: dict[str, LawDraft] = {}
        self._countries: dict[str, dict[str, LawDraft]] = {}

    def select_country(self, country):
        country = str(country or "").strip().upper()
        if country != self.country:
            self._countries[self.country] = self.pending
            self.pending = self._countries.setdefault(country, {})
            self.country = country

    def choose(self, row, value):
        law_id = str(row.get("law_id") or "")
        if not law_id or value not in law_choices(row):
            return False
        original = str(row.get("value") or "")
        if value == original:
            self.pending.pop(law_id, None)
        else:
            self.pending[law_id] = LawDraft(original, value)
        return True

    def prepare(self, state, context):
        if not self.pending:
            return [], ""
        if not context.is_own_country or context.net_client is None or str(context.target_tag).upper() != self.country:
            return [], "This country's law policy is outside your control."
        table = state.tables.get("country_laws")
        rows = {} if table is None else {
            str(row.get("law_id") or ""): row for row in table.iter_rows(named=True)
            if str(row.get("country_id") or "").upper() == self.country}
        transitions = state.tables.get("law_transitions")
        scheduled = set() if transitions is None else {
            str(row.get("law_id") or "") for row in transitions.iter_rows(named=True)
            if str(row.get("country_id") or "").upper() == self.country and row.get("status") == "scheduled"}
        # Validate the entire local batch before dispatch; a changed snapshot must
        # not silently apply only the first draft. Server validation still follows.
        for law_id, draft in self.pending.items():
            row = rows.get(law_id)
            if row is None or str(row.get("value") or "") != draft.original_value or draft.target_value not in law_choices(row) or law_id in scheduled:
                return [], "The laws changed while you were editing. Discard the draft and choose again."
        actions = [ActionChangePoliticalLaw(context.net_client.player_id, self.country, law_id, draft.target_value)
                   for law_id, draft in self.pending.items()]
        return actions, ""

    def apply(self, state, context):
        actions, reason = self.prepare(state, context)
        if reason:
            return reason
        self.pending.clear()
        for action in actions:
            context.net_client.send_action(action)
        return ""
