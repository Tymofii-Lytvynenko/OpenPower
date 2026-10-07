from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from typing import Any

import polars as pl


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
    status: str = "active"
    effects_summary: str = ""
    response_summary: str = ""
    recovery_summary: str = ""
    response_options: tuple[tuple[str, float], ...] = ()

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
        typed_items = self._typed_event_items(state)
        if typed_items:
            return typed_items

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

    def _typed_event_items(self, state) -> list[EventFeedItem]:
        tables = getattr(state, "tables", {})
        instances = tables.get("random_event_instances") if isinstance(tables, dict) else None
        if instances is None or instances.is_empty():
            return []

        region_index = self._region_index(state)
        effects = tables.get("random_event_effects")
        effects_by_event: dict[str, list[dict[str, Any]]] = {}
        if effects is not None and not effects.is_empty():
            for row in effects.sort(["event_id", "category", "id"]).iter_rows(named=True):
                effects_by_event.setdefault(str(row.get("event_id") or ""), []).append(row)

        responses = tables.get("random_event_responses")
        response_by_event: dict[str, dict[str, Any]] = {}
        if responses is not None and not responses.is_empty():
            for row in responses.sort(["applied_at_minute", "id"], descending=[True, True]).iter_rows(named=True):
                response_by_event.setdefault(str(row.get("event_id") or ""), row)

        now = max(0, int(getattr(getattr(state, "time", None), "total_minutes", 0) or 0))
        items: list[EventFeedItem] = []
        visible_statuses = {"active", "resolved", "cancelled", "skipped"}
        start_column = "starts_at_minute" if "starts_at_minute" in instances.columns else "triggered_at_minute"
        event_rows = (
            instances.filter(pl.col("status").is_in(visible_statuses))
            .sort([start_column, "id"], descending=[True, True])
            .head(50)
        )
        for row in event_rows.iter_rows(named=True):
            event_id = str(row.get("id") or "")
            region_id = self._integer(row.get("region_id"))
            region = region_index.get(region_id, {})
            region_name = self._text(region.get("name"), f"Region {region_id}")
            country = self._text(row.get("country_id") or region.get("controller") or region.get("owner"))
            severity = self._ratio(row.get("severity"))
            status = self._text(row.get("status"), "active")
            expiry = max(0, self._integer(row.get("expires_at_minute")))
            remaining = max(0, expiry - now)
            event_effects = effects_by_event.get(event_id, [])
            effects_summary = ", ".join(
                self._format_effect(effect)
                for effect in event_effects
                if self._text(effect.get("status")) in {"pending", "active", "resolved"}
            )
            response = response_by_event.get(event_id)
            response_summary = (
                f"{self._text(response.get('response_id'))} · {self._number(response.get('cost')):,.0f}"
                if response is not None
                else self._text(row.get("response_id"))
            )
            options = self._response_options(row.get("response_options_json"))
            recovery_summary = self._recovery_summary(row.get("recovery_state_json"), status)
            duration = f"{remaining / 1_440:.1f} days remaining" if status == "active" else status
            details = [region_name, f"severity {severity:.0%}", duration]
            if effects_summary:
                details.append(f"effects: {effects_summary}")
            if response_summary:
                details.append(f"response: {response_summary}")
            if recovery_summary:
                details.append(f"recovery: {recovery_summary}")
            items.append(
                EventFeedItem(
                    id=f"instance:{event_id}",
                    category=self.category_for(row.get("category") or row.get("event_type")),
                    country_tag=country,
                    headline=self._text(row.get("label"), self._text(row.get("event_type"), "World event")),
                    body=" · ".join(details),
                    created_at=f"Minute {self._integer(row.get('triggered_at_minute'))}",
                    severity=self._severity_label(severity),
                    region_id=region_id or None,
                    status=status,
                    effects_summary=effects_summary,
                    response_summary=response_summary,
                    recovery_summary=recovery_summary,
                    response_options=options if status == "active" else (),
                )
            )
        items.extend(self._journal_event_items(state, region_index, items))
        return items

    def _journal_event_items(
        self,
        state,
        region_index: dict[int, dict[str, Any]],
        existing: list[EventFeedItem],
    ) -> list[EventFeedItem]:
        journal = getattr(state, "journal", None)
        records = getattr(journal, "domain_events", [])
        if not isinstance(records, list):
            return []
        represented_events = {
            item.id.removeprefix("instance:")
            for item in existing
            if item.id.startswith("instance:")
        }
        items: list[EventFeedItem] = []
        for index, record in enumerate(records[-100:]):
            if not isinstance(record, dict) or record.get("event_type") != "EventRandomEventLifecycleChanged":
                continue
            payload = record.get("payload")
            if not isinstance(payload, dict):
                continue
            event_id = str(payload.get("event_id") or "")
            status = str(payload.get("status") or "")
            if not event_id or status in {"controls_changed", "response_applied"}:
                continue
            if status not in {"response_rejected", "cancelled", "skipped", "resolved"}:
                continue
            if status in {"cancelled", "skipped", "resolved"} and event_id in represented_events:
                continue
            matching = next(
                (item for item in existing if item.id == f"instance:{event_id}"),
                None,
            )
            region_id = matching.region_id if matching is not None else None
            country = matching.country_tag if matching is not None else ""
            region_name = region_index.get(region_id or 0, {}).get("name") if region_id else ""
            reason = str(payload.get("reason") or "")
            details = [str(region_name or f"Region {region_id}") if region_id else "World", status]
            if reason:
                details.append(reason)
            items.append(
                EventFeedItem(
                    id=f"lifecycle:{event_id}:{status}:{record.get('tick', index)}",
                    category=self.category_for(payload.get("event_type")),
                    country_tag=country,
                    headline=f"{str(payload.get('event_type') or 'World event').replace('_', ' ').title()} · {status.replace('_', ' ')}",
                    body=" · ".join(details),
                    created_at=f"Minute {self._integer(payload.get('at_minute'))}",
                    severity="warning" if status == "response_rejected" else "info",
                    region_id=region_id,
                    status=status,
                )
            )
        return items

    @staticmethod
    def _response_options(value: Any) -> tuple[tuple[str, float], ...]:
        try:
            rows = json.loads(str(value or "[]"))
        except (TypeError, ValueError, json.JSONDecodeError):
            return ()
        if not isinstance(rows, list):
            return ()
        return tuple(
            (str(row.get("response_id") or ""), EventFeedPresenter._number(row.get("cost")))
            for row in rows
            if isinstance(row, dict) and str(row.get("response_id") or "").strip()
        )

    @staticmethod
    def _recovery_summary(value: Any, status: str) -> str:
        try:
            recovery = json.loads(str(value or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
            recovery = {}
        if isinstance(recovery, dict):
            progress = recovery.get("progress")
            state = str(recovery.get("state") or "").strip()
            if progress is not None:
                return f"{max(0.0, min(1.0, EventFeedPresenter._number(progress))):.0%} {state}".strip()
            if state:
                return state
        return "recovery pending" if status == "resolved" else ""

    @staticmethod
    def _format_effect(effect: dict[str, Any]) -> str:
        category = str(effect.get("category") or "effect").replace("_", " ")
        magnitude = EventFeedPresenter._number(effect.get("magnitude"))
        unit = str(effect.get("unit") or "")
        if unit in {"ratio", "index"}:
            return f"{category} {magnitude * 100:+.1f}%"
        return f"{category} {magnitude:+.2f} {unit}".strip()

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

    @staticmethod
    def _number(value: Any, default: float = 0.0) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            return default
        return number if number == number and abs(number) != float("inf") else default
