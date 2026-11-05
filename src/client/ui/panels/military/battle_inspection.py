"""Selection and command policy for one battle, independent of its windows."""
from __future__ import annotations

from src.client.services.journal_cursor import JournalCursor
from src.client.ui.panels.military.presenter import MilitaryPresenter
from src.client.ui.panels.shared.panel_data import normalize_side
from src.shared.actions import ActionSetBattleStrategy
from src.client.ui.panels.shared.unit_categories import unit_category


class BattleInspection:
    STRATEGIES = ("hold", "attack", "defend", "back_off", "reorganize", "attack_preset", "defend_preset", "retreat")

    def __init__(self, country: str, send_action, player_id: str):
        self.country = country.upper()
        self._send = send_action
        self._player_id = player_id
        self.presenter = MilitaryPresenter()
        self.battle_id = ""
        self.full = False
        self._cursor = JournalCursor()
        self._result = None
        self._last_row = None
        self.ended = False
        self._final_result = None

    @staticmethod
    def row(state, battle_id):
        table = state.tables.get("battles")
        return next((row for row in table.to_dicts() if str(row.get("id")) == battle_id), None) if table is not None else None

    def open(self, state, battle_id: str) -> bool:
        row = self.row(state, battle_id)
        if row is None:
            return False
        self.battle_id = battle_id
        self.full = self.is_participant(row)
        self._cursor = JournalCursor(getattr(getattr(state, "journal", None), "domain_events", []))
        self._result = None
        self._last_row = dict(row)
        self.ended = False
        self._final_result = None
        return True

    def display_row(self, state):
        row = self.row(state, self.battle_id)
        if row is not None:
            self._last_row = dict(row)
        elif self.ended and self._last_row is not None:
            row = {**self._last_row, **self._final_result, "status": "concluded"}
            winner = str(row.get("victor_side") or "").upper()
            if winner in {"SIDE_A", "SIDE_B"}:
                row["balance"] = 1.0 if winner == "SIDE_A" else 0.0
        return row

    def is_participant(self, row) -> bool:
        return self.country in set(normalize_side(row.get("attacker_side"))) | set(normalize_side(row.get("defender_side")))

    def groups(self, state):
        return self.presenter.battle_force_summary(state, self.battle_id, self.country) if self.full else []

    def recorded_losses(self, state):
        if not self.full:
            return []
        return self.presenter.battle_loss_summary(state, self.battle_id, self.country)

    def own_postures(self, state):
        if not self.full:
            return []
        return self.presenter.battle_postures_for_country(state, self.battle_id, self.country)

    def command(self, state, strategy, unit_type="all") -> bool:
        row = self.row(state, self.battle_id)
        # Revalidate against the latest snapshot rather than the window's
        # original participant/active state. The server remains authoritative.
        if (row is None or not self.full or not self.is_participant(row)
                or row.get("status") != "active" or strategy not in self.STRATEGIES):
            return False
        own_groups = [group for group in self.groups(state) if group["country_id"] == self.country]
        if not own_groups or (unit_type != "all" and not any(group["unit_type"] == unit_type for group in own_groups)):
            return False
        self._send(ActionSetBattleStrategy(self._player_id, self.battle_id, strategy, self.country, unit_type))
        return True

    def poll_result(self, state):
        events = getattr(getattr(state, "journal", None), "domain_events", [])
        for event in self._cursor.consume(events):
            payload = event.get("payload") or {}
            if (self.full and event.get("event_type") == "EventBattleEnded"
                    and str(payload.get("battle_id")) == self.battle_id
                    and self.country in payload.get("participant_countries", [])):
                self._result = dict(payload)
        row = self.row(state, self.battle_id)
        # Source summaries are attached only after the inspected combat's final
        # update, not on every combat result received by the local player.
        if self._result is not None and (row is None or row.get("status") == "concluded"):
            result, self._result = self._result, None
            self.ended = True
            self._final_result = result
            return result
        return None

    def close(self):
        self.battle_id = ""
        self._result = None
        self._last_row = None
        self.ended = False
        self._final_result = None


def category_counts(groups, side):
    counts = dict.fromkeys("IGAN", 0)
    for group in groups:
        if group["side"].removeprefix("SIDE_") != side:
            continue
        # Role domains distinguish ground air-defense from aircraft; a word
        # search for "air" silently misclassified its observed unit count.
        category = unit_category(group["unit_type"])
        if category:
            counts[category] += group["unit_count"]
    return counts
