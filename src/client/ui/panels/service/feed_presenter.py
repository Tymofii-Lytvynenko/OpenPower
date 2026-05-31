from __future__ import annotations

from dataclasses import dataclass

import polars as pl


@dataclass(frozen=True, slots=True)
class HudFeedSummary:
    ticker_text: str
    unread_messages: int
    unread_news: int
    active_objectives: int


class FeedPresenter:
    """Builds lightweight HUD and service panel models from the shared state."""

    def build_summary(self, state, country_tag: str) -> HudFeedSummary:
        messages = self.messages_for_country(state, country_tag)
        news_items = self.news_for_country(state, country_tag)
        objectives = self.objectives_for_country(state, country_tag)

        ticker_text = "Operations feed idle."
        if news_items:
            headline = str(news_items[0].get("headline") or "").strip()
            body = str(news_items[0].get("body") or "").strip()
            ticker_text = headline if not body else f"{headline} | {body}"

        unread_messages = len([row for row in messages if not bool(row.get("is_read", False))])
        unread_news = max(0, len(news_items) - 1)
        active_objectives = len([row for row in objectives if str(row.get("status", "active")).lower() != "completed"])
        return HudFeedSummary(
            ticker_text=ticker_text,
            unread_messages=unread_messages,
            unread_news=unread_news,
            active_objectives=active_objectives,
        )

    def messages_for_country(self, state, country_tag: str) -> list[dict]:
        messages = state.tables.get("messages")
        if messages is None or messages.is_empty():
            return []

        if "country_id" not in messages.columns:
            return messages.sort("created_at", descending=True).to_dicts()

        filtered = messages.filter(
            (pl.col("country_id") == country_tag) | (pl.col("country_id") == "")
        )
        return filtered.sort("created_at", descending=True).to_dicts()

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
