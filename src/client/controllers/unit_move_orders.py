"""Queue neutral-border confirmations without changing the observed world."""
import json
import math
from dataclasses import dataclass
from uuid import uuid4

from src.client.utils.diplomacy_utils import get_military_enemies
from src.shared.actions import ActionMoveUnit, ActionInvadeTerritory


@dataclass(frozen=True)
class MoveIntent:
    unit_ids: tuple[str, ...]
    region_id: int
    latitude: float
    longitude: float
    controller: str


def _rows(state, name):
    table = state.tables.get(name)
    return table.to_dicts() if table is not None else []


def movement_controller(state, region_id):
    target = next((row for row in _rows(state, "regions") if row.get("id") == region_id), None)
    return str(target.get("controller") or target.get("owner") or "").strip().upper() if target else ""


def entry_has_access(state, owner, controller):
    if not controller or controller == owner or controller in get_military_enemies(state, owner):
        return True
    for row in _rows(state, "treaty_effects"):
        if row.get("country_id") != owner or row.get("effect") != "stationing_rights":
            continue
        try:
            tags = json.loads(str(row.get("detail") or "[]"))
        except (ValueError, TypeError):
            continue
        if isinstance(tags, list) and controller in tags:
            return True
    return False


class UnitMoveOrders:
    def __init__(self, client, country, notice, identity_factory=None):
        self.client = client
        self.country = country.upper()
        self.notice = notice
        self._identity = identity_factory or (lambda: str(uuid4()))
        self.pending: dict[str, list[MoveIntent]] = {}

    def request(self, unit_ids, region_id, latitude, longitude):
        state = self.client.get_state()
        if (not isinstance(region_id, int) or region_id <= 0
                or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in (latitude, longitude))
                or not -90 <= latitude <= 90 or not -180 <= longitude <= 180):
            return False
        controller = movement_controller(state, region_id)
        if not controller:
            return False
        requested = set(unit_ids)
        owned = tuple(sorted(str(row["id"]) for row in _rows(state, "units")
                             if row.get("id") in requested and row.get("owner") == self.country
                             and int(row.get("strength") or 0) > 0))
        if not owned:
            return False
        intent = MoveIntent(owned, region_id, float(latitude), float(longitude), controller)
        if entry_has_access(state, self.country, controller):
            self._send_normal(intent)
        else:
            self.pending.setdefault(controller, []).append(intent)
        return True

    def cancel(self, country):
        self.pending.pop(country, None)

    def confirm(self, country):
        # Consume first: a repeated button activation cannot dispatch twice.
        intents = self.pending.pop(country, [])
        state = self.client.get_state()
        units = {str(row.get("id")): row for row in _rows(state, "units")}
        for intent in intents:
            if (movement_controller(state, intent.region_id) != intent.controller
                    or any(identity not in units or units[identity].get("owner") != self.country
                           or int(units[identity].get("strength") or 0) <= 0 for identity in intent.unit_ids)):
                self.notice("Movement order", "The selected units or destination changed. Choose the destination again.")
                continue
            if entry_has_access(state, self.country, intent.controller):
                self._send_normal(intent)
            else:
                self.client.send_action(ActionInvadeTerritory(
                    self.client.player_id, self._identity(), list(intent.unit_ids), intent.region_id,
                    intent.controller, intent.latitude, intent.longitude,
                ))

    def _send_normal(self, intent):
        for identity in intent.unit_ids:
            self.client.send_action(ActionMoveUnit(self.client.player_id, identity, intent.region_id,
                                                  intent.latitude, intent.longitude))
