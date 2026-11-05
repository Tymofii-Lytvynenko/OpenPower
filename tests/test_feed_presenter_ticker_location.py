from types import SimpleNamespace

import polars as pl

from src.client.ui.panels.service.feed_presenter import FeedPresenter


def test_ticker_location_uses_the_latest_bulletins_country_capital():
    state = SimpleNamespace(
        tables={
            "news_items": pl.DataFrame(
                {
                    "id": ["latest", "older"],
                    "headline": ["Latest bulletin", "Older bulletin"],
                    "body": ["Current news", "Earlier news"],
                    "category": ["political", "military"],
                    "severity": ["info", "warning"],
                    "related_country_id": ["UKR", "POL"],
                    "created_at": ["2001-01-02", "2001-01-01"],
                }
            ),
            "country_governments": pl.DataFrame(
                {"country_id": ["UKR", "POL"], "capital_region_id": [7, 9]}
            ),
            "regions": pl.DataFrame({"id": [7, 9], "name": ["Kyiv", "Warsaw"]}),
            "messages": pl.DataFrame(),
            "objectives": pl.DataFrame(),
        },
    )

    summary = FeedPresenter().build_summary(state, "UKR")

    assert summary.ticker_text == "Latest bulletin | Current news"
    assert summary.ticker_region_id == 7


def test_ticker_location_is_unavailable_when_the_latest_bulletin_has_no_mapped_capital():
    state = SimpleNamespace(
        tables={
            "news_items": pl.DataFrame(
                {
                    "id": ["global"],
                    "headline": ["Global bulletin"],
                    "body": [""],
                    "related_country_id": [""],
                    "created_at": ["2001-01-02"],
                }
            ),
            "country_governments": pl.DataFrame(
                {"country_id": ["UKR"], "capital_region_id": [0]}
            ),
            "regions": pl.DataFrame({"id": [7]}),
            "messages": pl.DataFrame(),
            "objectives": pl.DataFrame(),
        },
    )

    summary = FeedPresenter().build_summary(state, "UKR")

    assert summary.ticker_region_id is None
