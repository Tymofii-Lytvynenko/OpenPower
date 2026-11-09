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


def test_revisioned_feed_summary_is_cached_and_uses_the_idle_ticker():
    state = SimpleNamespace(
        tables={
            "messages": pl.DataFrame(),
            "news_items": pl.DataFrame(),
            "objectives": pl.DataFrame(),
        },
        table_revisions={},
    )
    presenter = FeedPresenter()

    summary = presenter.build_summary(state, "UKR")

    assert summary.ticker_text == "Operations feed idle."
    assert summary.ticker_region_id is None
    assert presenter.build_summary(state, "UKR") is summary


def test_ticker_location_checks_explicit_region_then_country_capital():
    regions = pl.DataFrame({"id": [7]})
    no_regions = SimpleNamespace(tables={})
    assert FeedPresenter._ticker_region_id(no_regions, {"region_id": 7}) is None

    state = SimpleNamespace(tables={"regions": regions})
    assert FeedPresenter._ticker_region_id(state, {"region_id": 7}) == 7
    assert FeedPresenter._ticker_region_id(
        state, {"related_country_id": "UKR"}
    ) is None

    state.tables["country_governments"] = pl.DataFrame(
        {"country_id": ["CAN"], "capital_region_id": [7]}
    )
    assert FeedPresenter._ticker_region_id(
        state, {"related_country_id": "UKR"}
    ) is None

    state.tables["country_governments"] = pl.DataFrame(
        {"country_id": ["UKR"], "capital_region_id": [7]}
    )
    assert FeedPresenter._ticker_region_id(
        state, {"region_id": 99, "related_country_id": "UKR"}
    ) == 7

    state.tables["country_governments"] = pl.DataFrame(
        {"country_id": ["UKR"], "capital_region_id": [999]}
    )
    assert FeedPresenter._ticker_region_id(
        state, {"related_country_id": "UKR"}
    ) is None


def test_message_queries_cover_global_rows_and_mailbox_dismissals():
    global_state = SimpleNamespace(
        tables={
            "messages": pl.DataFrame(
                {"id": ["old", "new"], "created_at": ["1", "2"]}
            )
        }
    )
    assert [
        row["id"] for row in FeedPresenter().messages_for_country(global_state, "UKR")
    ] == ["new", "old"]

    dismissed = SimpleNamespace(
        is_dismissed=lambda kind, message_id: kind == "message" and message_id == "hidden"
    )
    targeted_state = SimpleNamespace(
        tables={
            "messages": pl.DataFrame(
                {
                    "id": ["hidden", "global", "other"],
                    "country_id": ["UKR", "", "CAN"],
                    "created_at": ["3", "2", "1"],
                    "is_read": [False, True, False],
                }
            )
        }
    )
    visible = FeedPresenter(dismissed).messages_for_country(targeted_state, "UKR")

    assert [row["id"] for row in visible] == ["global"]


def test_news_and_objective_queries_handle_global_and_country_specific_tables():
    presenter = FeedPresenter()
    state = SimpleNamespace(
        tables={
            "news_items": pl.DataFrame(
                {"id": ["old", "new"], "created_at": ["1", "2"]}
            ),
            "objectives": pl.DataFrame(
                {
                    "id": ["slow", "fast", "done", "other"],
                    "country_id": ["UKR", "UKR", "UKR", "CAN"],
                    "status": ["active", "active", "completed", "active"],
                    "progress": [0.2, 0.8, 1.0, 0.9],
                }
            ),
        }
    )

    assert [row["id"] for row in presenter.news_for_country(state, "UKR")] == [
        "new",
        "old",
    ]
    assert [row["id"] for row in presenter.objectives_for_country(state, "UKR")] == [
        "fast",
        "slow",
        "done",
    ]

    missing_country_column = SimpleNamespace(
        tables={
            "news_items": pl.DataFrame({"id": ["news"], "created_at": ["1"]}),
            "objectives": pl.DataFrame({"id": ["objective"], "status": ["active"]}),
        }
    )
    assert len(presenter.news_for_country(missing_country_column, "UKR")) == 1
    assert len(presenter.objectives_for_country(missing_country_column, "UKR")) == 1
    assert presenter.news_for_country(SimpleNamespace(tables={}), "UKR") == []
    assert presenter.objectives_for_country(SimpleNamespace(tables={}), "UKR") == []
