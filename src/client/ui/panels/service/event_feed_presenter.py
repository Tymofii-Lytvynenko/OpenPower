from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class EventCategory(str, Enum):
    GENERAL = "general"
    MILITARY = "military"
    POLITICAL = "political"
    ECONOMIC = "economic"


@dataclass(frozen=True, slots=True)
class EventFeedItem:
    id: str
    category: EventCategory
    country_tag: str
    headline: str
    body: str
    created_at: str
    severity: str = "info"
    region_id: int | None = None

    @property
    def summary(self) -> str:
        headline = self.headline.strip()
        body = self.body.strip()
        if not body:
            return headline
        if not headline:
            return body
        return f"{headline}. {body}"


class EventFeedPresenter:
    """Builds the world event feed without coupling feed data to ImGui."""

    _CATEGORY_ALIASES: dict[EventCategory, frozenset[str]] = {
        EventCategory.MILITARY: frozenset(
            {"military", "war", "conflict", "combat", "defense", "defence", "security", "army"}
        ),
        EventCategory.POLITICAL: frozenset(
            {"political", "politics", "diplomacy", "diplomatic", "treaty", "election", "government"}
        ),
        EventCategory.ECONOMIC: frozenset(
            {
                "economic",
                "economy",
                "trade",
                "market",
                "finance",
                "financial",
                "budget",
                "energy",
                "industry",
                "industrial",
                "resource",
                "strike",
            }
        ),
    }

    def items(self, state, category: EventCategory | None = None) -> list[EventFeedItem]:
        items = [*self._active_event_items(state), *self._news_items(state)]
        if category is None:
            return items
        return [item for item in items if item.category is category]

    def counts(self, state) -> dict[EventCategory, int]:
        counts = {category: 0 for category in EventCategory}
        for item in self.items(state):
            counts[item.category] += 1
        return counts

    def category_for(self, raw_category: Any) -> EventCategory:
        normalized = str(raw_category or "").strip().lower().replace("-", "_").replace(" ", "_")
        terms = {term for term in normalized.split("_") if term}
        if normalized:
            terms.add(normalized)

        for category, aliases in self._CATEGORY_ALIASES.items():
            if terms & aliases:
                return category
        return EventCategory.GENERAL

    def _news_items(self, state) -> list[EventFeedItem]:
        news = getattr(state, "tables", {}).get("news_items")
        if news is None or news.is_empty():
            return []

        if "created_at" in news.columns:
            news = news.sort("created_at", descending=True)

        return [
            EventFeedItem(
                id=f"news:{row.get('id') or index}",
                category=self.category_for(row.get("category")),
                country_tag=self._text(row.get("related_country_id")),
                headline=self._text(row.get("headline"), "Untitled bulletin"),
                body=self._text(row.get("body")),
                created_at=self._text(row.get("created_at")),
                severity=self._text(row.get("severity"), "info"),
            )
            for index, row in enumerate(news.iter_rows(named=True))
        ]

    def _active_event_items(self, state) -> list[EventFeedItem]:
        state_globals = getattr(state, "globals", {})
        raw_events = state_globals.get("active_events", []) if isinstance(state_globals, dict) else []
        if not isinstance(raw_events, list):
            return []

        region_index = self._region_index(state)
        events = sorted(
            (row for row in raw_events if isinstance(row, dict)),
            key=lambda row: self._integer(row.get("start_minute")),
            reverse=True,
        )
        items: list[EventFeedItem] = []
        for index, row in enumerate(events):
            region_id = self._integer(row.get("region_id"))
            region = region_index.get(region_id, {})
            region_name = self._text(region.get("name"), f"Region {region_id}")
            severity = self._ratio(row.get("severity"))
            event_type = self._text(row.get("event_type"))
            items.append(
                EventFeedItem(
                    id=f"active:{row.get('id') or index}",
                    category=self.category_for(event_type),
                    country_tag=self._text(region.get("controller") or region.get("owner")),
                    headline=self._text(row.get("label"), "World event"),
                    body=f"{region_name} · severity {severity:.0%}",
                    created_at=f"Minute {self._integer(row.get('start_minute'))}",
                    severity=self._severity_label(severity),
                    region_id=region_id or None,
                )
            )
        return items

    @staticmethod
    def _region_index(state) -> dict[int, dict[str, Any]]:
        regions = getattr(state, "tables", {}).get("regions")
        if regions is None or regions.is_empty() or "id" not in regions.columns:
            return {}
        return {int(row["id"]): row for row in regions.iter_rows(named=True)}

    @staticmethod
    def _text(value: Any, default: str = "") -> str:
        if value is None:
            return default
        text = str(value).strip()
        return text or default

    @staticmethod
    def _integer(value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _ratio(value: Any) -> float:
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _severity_label(severity: float) -> str:
        if severity >= 0.75:
            return "critical"
        if severity >= 0.45:
            return "warning"
        return "info"
