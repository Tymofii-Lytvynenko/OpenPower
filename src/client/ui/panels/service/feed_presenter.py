from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import polars as pl

from src.client.ui.panels.service.mail_inbox_state import MailInboxState


@dataclass(frozen=True, slots=True)
class HudFeedSummary:
    ticker_text: str
    ticker_region_id: int | None
    unread_messages: int
    unread_news: int
    active_objectives: int


class FeedPresenter:
    """Builds lightweight HUD and service panel models from the shared state."""

    def __init__(self, mail_inbox_state: MailInboxState | None = None) -> None:
        self._mail_inbox_state = mail_inbox_state
        self._summary_cache_key: tuple | None = None
        self._summary_cache: HudFeedSummary | None = None

    def build_summary(self, state, country_tag: str) -> HudFeedSummary:
        cache_key = self._summary_key(state, country_tag)
        if cache_key == self._summary_cache_key and self._summary_cache is not None:
            return self._summary_cache

        messages = self.messages_for_country(state, country_tag)
        news_items = self.news_for_country(state, country_tag)
        objectives = self.objectives_for_country(state, country_tag)
        ticker_region_id = self._ticker_region_id(state, news_items[0] if news_items else None)

        ticker_text = "Operations feed idle."
        if news_items:
            headline = str(news_items[0].get("headline") or "").strip()
            body = str(news_items[0].get("body") or "").strip()
            ticker_text = headline if not body else f"{headline} | {body}"

        unread_messages = len([row for row in messages if not bool(row.get("is_read", False))])
        unread_news = max(0, len(news_items) - 1)
        active_objectives = len([row for row in objectives if str(row.get("status", "active")).lower() != "completed"])
        summary = HudFeedSummary(
            ticker_text=ticker_text,
            ticker_region_id=ticker_region_id,
            unread_messages=unread_messages,
            unread_news=unread_news,
            active_objectives=active_objectives,
        )
        self._summary_cache_key = cache_key
        self._summary_cache = summary
        return summary

    def _summary_key(self, state, country_tag: str) -> tuple:
        """Use table revisions so unchanged HUD feeds are not re-sorted per frame."""
        revisions = getattr(state, "table_revisions", None)
        if revisions is None:
            # Lightweight test doubles may not expose revisions; their object
            # identity is still safe because each replacement is a new state.
            return (id(state), country_tag)
        return (
            country_tag,
            self._mail_inbox_state.revision if self._mail_inbox_state is not None else 0,
            tuple(
                (name, int(revisions.get(name, 0)))
                for name in ("messages", "news_items", "objectives", "country_governments", "regions")
            ),
        )

    @staticmethod
    def _ticker_region_id(state, news_item: dict | None) -> int | None:
        if not news_item:
            return None

        tables = getattr(state, "tables", {})
        regions = tables.get("regions") if isinstance(tables, Mapping) else None
        if regions is None or "id" not in regions.columns:
            return None

        explicit_region_id = FeedPresenter._positive_int(news_item.get("region_id"))
        if explicit_region_id is not None and FeedPresenter._region_exists(regions, explicit_region_id):
            return explicit_region_id

        country_tag = str(news_item.get("related_country_id") or "").strip()
        governments = tables.get("country_governments") if isinstance(tables, Mapping) else None
        if not country_tag or governments is None or not {
            "country_id", "capital_region_id"
        }.issubset(governments.columns):
            return None

        government = governments.filter(
            pl.col("country_id").cast(pl.Utf8) == country_tag
        )
        if government.is_empty():
            return None
        capital_region_id = FeedPresenter._positive_int(
            government["capital_region_id"][0]
        )
        if capital_region_id is None or not FeedPresenter._region_exists(regions, capital_region_id):
            return None
        return capital_region_id

    @staticmethod
    def _region_exists(regions: pl.DataFrame, region_id: int) -> bool:
        return not regions.filter(
            pl.col("id").cast(pl.Int64, strict=False) == region_id
        ).is_empty()

    @staticmethod
    def _positive_int(value: object) -> int | None:
        try:
            number = int(value)
        except (TypeError, ValueError, OverflowError):
            return None
        return number if number > 0 else None

    def messages_for_country(self, state, country_tag: str) -> list[dict]:
        messages = state.tables.get("messages")
        if messages is None or messages.is_empty():
            return []

        if "country_id" not in messages.columns:
            rows = messages.sort("created_at", descending=True).to_dicts()
            return self._visible_messages(rows)

        filtered = messages.filter(
            (pl.col("country_id") == country_tag) | (pl.col("country_id") == "")
        )
        return self._visible_messages(filtered.sort("created_at", descending=True).to_dicts())

    def _visible_messages(self, rows: list[dict]) -> list[dict]:
        if self._mail_inbox_state is None:
            return rows
        return [
            row for row in rows
            if not self._mail_inbox_state.is_dismissed("message", row.get("id"))
        ]

    def news_for_country(self, state, country_tag: str) -> list[dict]:
        news_items = state.tables.get("news_items")
        if news_items is None or news_items.is_empty():
            return []

        if "related_country_id" not in news_items.columns:
            return news_items.sort("created_at", descending=True).to_dicts()

        targeted = news_items.filter(pl.col("related_country_id") == country_tag)
        if not targeted.is_empty():
            return targeted.sort("created_at", descending=True).to_dicts()

        return news_items.sort("created_at", descending=True).to_dicts()

    def objectives_for_country(self, state, country_tag: str) -> list[dict]:
        objectives = state.tables.get("objectives")
        if objectives is None or objectives.is_empty():
            return []

        if "country_id" not in objectives.columns:
            return objectives.to_dicts()

        return (
            objectives.filter(pl.col("country_id") == country_tag)
            .sort(["status", "progress"], descending=[False, True])
            .to_dicts()
        )
