"""Confirm published training terms without calculating gameplay on the client."""
import math

from src.client.ui.components.shared.generic_question_dialog import GenericQuestionDialog
from src.shared.actions import ActionTrainUnit


def training_offer(state, unit_id, country):
    units, quotes = state.tables.get("units"), state.tables.get("unit_training_quotes")
    unit = None if units is None else next((row for row in units.iter_rows(named=True)
                                            if str(row.get("id")) == unit_id), None)
    quote = None if quotes is None else next((row for row in quotes.iter_rows(named=True)
                                              if str(row.get("unit_id")) == unit_id), None)
    if not unit or str(unit.get("owner")) != country or not quote or quote.get("country_id") != country:
        return None
    if unit.get("is_moving") or unit.get("engagement_mode") or str(unit.get("training_state") or "") == "training":
        return None
    if not quote.get("available") or quote.get("from_level") != str(unit.get("training_level") or "Recruit"):
        return None
    if not quote.get("target_level") or any(type(quote.get(key)) not in {int, float}
            or not math.isfinite(quote[key]) or quote[key] < 0 for key in ("cost", "required_days")):
        return None
    return quote


def training_unavailable_reason(state, unit_id, country):
    table = state.tables.get("unit_training_quotes")
    quote = None if table is None else next((row for row in table.iter_rows(named=True)
        if str(row.get("unit_id")) == unit_id and row.get("country_id") == country), None)
    return str((quote or {}).get("reason") or "No available training estimate. Wait for updated unit information.")


def _unit_signature(state, unit_id):
    table = state.tables.get("units")
    row = None if table is None else next((r for r in table.iter_rows(named=True)
                                           if str(r.get("id")) == unit_id), None)
    keys = ("owner", "strength", "training_level", "current_region_id", "source_region_id",
            "unit_lifecycle", "is_moving", "engagement_mode", "training_state")
    return tuple(row.get(key) for key in keys) if row else None


class UnitTrainingConfirmation:
    def __init__(self, client, country, notify=None):
        self.client, self.country, self.notify = client, country, notify
        self.question = GenericQuestionDialog("unit.training.question")
        self._state = None

    def request(self, state, unit_id, *, on_accept=None):
        return self.request_many(state, [unit_id], on_accept=on_accept)

    def request_many(self, state, unit_ids, *, on_accept=None):
        selected_ids = tuple(dict.fromkeys(str(unit_id or "").strip() for unit_id in unit_ids))
        selected_ids = tuple(unit_id for unit_id in selected_ids if unit_id)
        if not selected_ids:
            return False

        offers = {
            unit_id: training_offer(state, unit_id, self.country)
            for unit_id in selected_ids
        }
        if any(offer is None for offer in offers.values()):
            return False
        signatures = {
            unit_id: _unit_signature(state, unit_id)
            for unit_id in selected_ids
        }
        self._state = state

        def accept():
            if any(
                training_offer(self._state, unit_id, self.country) != offers[unit_id]
                or _unit_signature(self._state, unit_id) != signatures[unit_id]
                for unit_id in selected_ids
            ):
                if self.notify:
                    self.notify(
                        "Unit training",
                        "A selected unit or training estimate changed. Review the selection again.",
                        severity="warning",
                    )
                return

            for unit_id in selected_ids:
                offer = offers[unit_id]
                self.client.send_action(ActionTrainUnit(
                    self.client.player_id,
                    self.country,
                    unit_id,
                    offer["target_level"],
                    expected_cost=offer["cost"],
                    expected_required_days=offer["required_days"],
                    expected_from_level=offer["from_level"],
                ))
            if on_accept is not None:
                on_accept()

        if len(selected_ids) == 1:
            offer = offers[selected_ids[0]]
            message = (
                f"Train to {offer['target_level']}?\n"
                f"Estimated duration: {offer['required_days']:g} days\n"
                f"Cost: $ {offer['cost']:,.2f}\nStart training?"
            )
        else:
            targets = ", ".join(sorted({offer["target_level"] for offer in offers.values()}))
            durations = [float(offer["required_days"]) for offer in offers.values()]
            duration_text = f"{min(durations):g}–{max(durations):g} days"
            total_cost = sum(float(offer["cost"]) for offer in offers.values())
            message = (
                f"Train {len(selected_ids)} selected units to {targets}?\n"
                f"Estimated duration: {duration_text}\n"
                f"Combined cost: $ {total_cost:,.2f}\nStart training?"
            )
        return self.question.show(message, accept, lambda: None)

    def render(self, state):
        self._state = state
        self.question.render()
