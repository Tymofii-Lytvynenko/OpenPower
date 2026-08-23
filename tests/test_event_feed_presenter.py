from types import SimpleNamespace
import unittest

import polars as pl

from src.client.ui.panels.service.event_feed_presenter import EventCategory, EventFeedPresenter


class TestEventFeedPresenter(unittest.TestCase):
    def test_combines_active_world_events_and_news_into_categories(self):
        state = SimpleNamespace(
            tables={
                "regions": pl.DataFrame(
                    {
                        "id": [7],
                        "name": ["Odesa"],
                        "owner": ["UKR"],
                        "controller": ["UKR"],
                    }
                ),
                "news_items": pl.DataFrame(
                    {
                        "id": ["war-1", "treaty-1", "market-1"],
                        "headline": ["War begins", "Treaty signed", "Markets rally"],
                        "body": ["Forces mobilized", "Delegates agreed", "Growth accelerates"],
                        "category": ["war", "diplomacy", "economic"],
                        "severity": ["warning", "info", "info"],
                        "related_country_id": ["POL", "FRA", "DEU"],
                        "created_at": ["2026-08-23 12:00", "2026-08-23 11:00", "2026-08-23 10:00"],
                    }
                ),
            },
            globals={
                "active_events": [
                    {
                        "id": "flood-1",
                        "event_type": "flood",
                        "label": "Flood",
                        "region_id": 7,
                        "severity": 0.8,
                        "start_minute": 120,
                    }
                ]
            },
        )

        items = EventFeedPresenter().items(state)

        self.assertEqual(
            [item.category for item in items],
            [
                EventCategory.GENERAL,
                EventCategory.MILITARY,
                EventCategory.POLITICAL,
                EventCategory.ECONOMIC,
            ],
        )
        self.assertEqual(items[0].country_tag, "UKR")
        self.assertIn("Odesa", items[0].summary)

    def test_filters_categories_and_treats_unknown_types_as_general(self):
        state = SimpleNamespace(
            tables={
                "news_items": pl.DataFrame(
                    {
                        "id": ["one", "two"],
                        "headline": ["Election", "Meteor shower"],
                        "body": ["", ""],
                        "category": ["government_election", "astronomy"],
                        "severity": ["info", "info"],
                        "related_country_id": ["USA", ""],
                        "created_at": ["2", "1"],
                    }
                )
            },
            globals={},
        )

        presenter = EventFeedPresenter()

        self.assertEqual(len(presenter.items(state, EventCategory.POLITICAL)), 1)
        self.assertEqual(len(presenter.items(state, EventCategory.GENERAL)), 1)
        self.assertEqual(presenter.category_for("economic_boom"), EventCategory.ECONOMIC)


if __name__ == "__main__":
    unittest.main()
