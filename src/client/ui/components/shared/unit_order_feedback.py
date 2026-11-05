"""Surface newly rejected unit orders through the shared message dialog."""
from __future__ import annotations

from collections import OrderedDict
from collections.abc import Iterable, Mapping

from src.client.ui.components.shared.generic_message_dialog import GenericMessageDialog


class UnitOrderFeedback:
    """Convert authoritative movement refusal rows into one-shot UI notices."""

    _MOVEMENT_ORDER_TYPES = frozenset({"move", "naval_invasion"})

    def __init__(self, dialog: GenericMessageDialog, initial_records: Iterable[Mapping] = ()):
        self._dialog = dialog
        # Snapshot history must not reopen warnings already observed before this UI mounted.
        self._seen_ids = {self._record_id(row) for row in self._rows(initial_records)}
        self._seen_ids.discard("")

    def update(self, records, player_country_tag: str) -> None:
        rows = self._rows(records)
        live_ids = {self._record_id(row) for row in rows}
        live_ids.discard("")
        self._seen_ids.intersection_update(live_ids)

        refused: OrderedDict[str, int] = OrderedDict()
        for row in rows:
            record_id = self._record_id(row)
            if not record_id or record_id in self._seen_ids:
                continue
            self._seen_ids.add(record_id)
            if str(row.get("owner_country_id") or "").strip().upper() != str(player_country_tag or "").strip().upper():
                continue
            if str(row.get("status") or "").strip().lower() != "rejected":
                continue
            order_type = str(row.get("order_type") or "").strip().lower()
            if order_type not in self._MOVEMENT_ORDER_TYPES:
                continue
            reason = str(row.get("reason") or "The movement order could not be completed.").strip()
            refused[reason] = refused.get(reason, 0) + 1

        for reason, count in refused.items():
            noun = "unit" if count == 1 else "units"
            self._dialog.enqueue(
                "Movement refused",
                f"{count} {noun} could not move. {reason}",
                severity="warning",
            )

        # The authoritative table is a rolling window; retaining only live IDs bounds memory.
        self._seen_ids.intersection_update(live_ids)
        self._seen_ids.update(live_ids)

    @staticmethod
    def _record_id(row: Mapping) -> str:
        return str(row.get("id") or "").strip()

    @staticmethod
    def _rows(records) -> list[dict]:
        if records is None:
            return []
        if hasattr(records, "to_dicts"):
            return records.to_dicts()
        return [dict(row) for row in records if isinstance(row, Mapping)]
