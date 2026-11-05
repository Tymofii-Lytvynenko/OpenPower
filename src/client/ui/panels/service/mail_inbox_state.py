"""Track this client's temporary inbox dismissals without mutating snapshots."""
from __future__ import annotations


class MailInboxState:
    """Hold UI-only hidden mail ids for the lifetime of one game session."""

    def __init__(self) -> None:
        self._dismissed: set[str] = set()
        self._dismissed_region_events: dict[str, set[str]] = {}
        self._revision = 0

    @staticmethod
    def key(kind: str, item_id: object) -> str:
        return f"{kind}:{str(item_id or '')}"

    @property
    def revision(self) -> int:
        return self._revision

    def is_dismissed(self, kind: str, item_id: object) -> bool:
        key = self.key(kind, item_id)
        return bool(item_id) and key in self._dismissed

    def dismiss(self, kind: str, item_id: object) -> None:
        if not item_id:
            return
        key = self.key(kind, item_id)
        if key not in self._dismissed:
            self._dismissed.add(key)
            self._revision += 1

    def dismiss_many(self, items: set[tuple[str, str]]) -> None:
        previous_count = len(self._dismissed)
        self._dismissed.update(self.key(kind, item_id) for kind, item_id in items if item_id)
        if len(self._dismissed) != previous_count:
            self._revision += 1

    def dismissed_region_event_ids(self, country_tag: str) -> frozenset[str]:
        country = str(country_tag or "").strip().upper()
        return frozenset(self._dismissed_region_events.get(country, ()))

    def dismiss_region_events(self, country_tag: str, event_ids) -> None:
        country = str(country_tag or "").strip().upper()
        ids = {str(event_id) for event_id in event_ids if event_id}
        if not country or not ids:
            return
        dismissed = self._dismissed_region_events.setdefault(country, set())
        previous_count = len(dismissed)
        dismissed.update(ids)
        if len(dismissed) != previous_count:
            self._revision += 1
