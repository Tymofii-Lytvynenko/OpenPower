from types import SimpleNamespace
import json
import unittest

import polars as pl

from src.client.ui.panels.service.event_feed_presenter import (
    EventCategory,
    EventFeedItem,
    EventFeedPresenter,
)


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
        self.assertEqual(
            presenter.category_for("population_displacement"),
            EventCategory.DEMOGRAPHIC,
        )

    def test_projects_typed_event_history_with_effects_response_expiry_and_recovery(self):
        state = SimpleNamespace(
            tables={
                "regions": pl.DataFrame(
                    {"id": [7], "name": ["Odesa"], "owner": ["UKR"]}
                ),
                "random_event_instances": pl.DataFrame(
                    [
                        {
                            "id": "epidemic-1",
                            "event_type": "epidemic",
                            "category": "health",
                            "label": "Epidemic",
                            "region_id": 7,
                            "country_id": "UKR",
                            "severity": 0.8,
                            "status": "active",
                            "triggered_at_minute": 1_000,
                            "expires_at_minute": 4_320,
                            "response_id": "public_health_response",
                            "response_options_json": json.dumps(
                                [{"response_id": "public_health_response", "cost": 15_000.0}]
                            ),
                            "recovery_state_json": "{}",
                        },
                        {
                            "id": "flood-1",
                            "event_type": "flood",
                            "category": "disaster",
                            "label": "Flood",
                            "region_id": 7,
                            "country_id": "UKR",
                            "severity": 0.4,
                            "status": "resolved",
                            "triggered_at_minute": 500,
                            "expires_at_minute": 900,
                            "response_id": "",
                            "response_options_json": "[]",
                            "recovery_state_json": "{}",
                        },
                    ]
                ),
                "random_event_effects": pl.DataFrame(
                    [
                        {
                            "id": "epidemic-1:health",
                            "event_id": "epidemic-1",
                            "category": "health",
                            "subject_type": "region",
                            "subject_id": "7",
                            "magnitude": -0.08,
                            "unit": "index",
                            "status": "active",
                        }
                    ]
                ),
                "random_event_responses": pl.DataFrame(
                    [
                        {
                            "id": "response-1",
                            "event_id": "epidemic-1",
                            "response_id": "public_health_response",
                            "cost": 15_000.0,
                            "applied_at_minute": 1_100,
                        }
                    ]
                ),
            },
            globals={},
            time=SimpleNamespace(total_minutes=2_880),
            journal=SimpleNamespace(
                domain_events=[
                    {
                        "tick": 7,
                        "event_type": "EventRandomEventLifecycleChanged",
                        "payload": {
                            "event_id": "epidemic-1",
                            "event_type": "epidemic",
                            "status": "response_rejected",
                            "reason": "Insufficient authority.",
                            "at_minute": 2_000,
                        },
                    }
                ]
            ),
        )

        items = EventFeedPresenter().items(state)

        self.assertEqual(
            [item.id for item in items],
            [
                "instance:epidemic-1",
                "instance:flood-1",
                "lifecycle:epidemic-1:response_rejected:7",
            ],
        )
        epidemic = items[0]
        self.assertEqual(epidemic.status, "active")
        self.assertIn("Odesa", epidemic.body)
        self.assertIn("1.0 days remaining", epidemic.body)
        self.assertIn("health -8.0%", epidemic.effects_summary)
        self.assertIn("public_health_response", epidemic.response_summary)
        self.assertEqual(epidemic.response_options, (("public_health_response", 15_000.0),))
        self.assertEqual(items[1].recovery_summary, "recovery pending")
        self.assertIn("Insufficient authority", items[2].body)

    def test_counts_fallback_events_and_item_summary_handle_empty_headlines(self):
        state = SimpleNamespace(
            tables={},
            globals={
                "active_events": [
                    {"id": "war", "event_type": "war", "severity": 0.9, "start_minute": 5},
                    {"id": "market", "event_type": "economic_boom", "severity": 0.5, "start_minute": 1},
                ]
            },
        )
        presenter = EventFeedPresenter()

        counts = presenter.counts(state)
        item = EventFeedItem(
            id="body-only",
            category=EventCategory.GENERAL,
            country_tag="",
            headline="",
            body="A headline was unavailable.",
            created_at="",
        )

        self.assertEqual(counts[EventCategory.MILITARY], 1)
        self.assertEqual(counts[EventCategory.ECONOMIC], 1)
        self.assertEqual(item.summary, "A headline was unavailable.")

    def test_active_event_projection_ignores_non_list_global_payloads(self):
        state = SimpleNamespace(tables={}, globals={"active_events": ("invalid",)})

        self.assertEqual(EventFeedPresenter()._active_event_items(state), [])

    def test_journal_projection_filters_invalid_and_duplicate_lifecycle_records(self):
        records = [
            "not a record",
            {"event_type": "OtherEvent", "payload": {}},
            {"event_type": "EventRandomEventLifecycleChanged", "payload": "invalid"},
            {
                "event_type": "EventRandomEventLifecycleChanged",
                "payload": {"event_id": "", "status": "resolved"},
            },
            {
                "event_type": "EventRandomEventLifecycleChanged",
                "payload": {"event_id": "controls", "status": "controls_changed"},
            },
            {
                "event_type": "EventRandomEventLifecycleChanged",
                "payload": {"event_id": "started", "status": "started"},
            },
            {
                "event_type": "EventRandomEventLifecycleChanged",
                "payload": {"event_id": "represented", "status": "cancelled"},
            },
            {
                "tick": 42,
                "event_type": "EventRandomEventLifecycleChanged",
                "payload": {
                    "event_id": "rejected",
                    "event_type": "war",
                    "status": "response_rejected",
                    "reason": "No authority.",
                    "at_minute": "invalid",
                },
            },
            {
                "event_type": "EventRandomEventLifecycleChanged",
                "payload": {
                    "event_id": "unrepresented",
                    "event_type": "economic",
                    "status": "resolved",
                    "at_minute": 25,
                },
            },
        ]
        state = SimpleNamespace(journal=SimpleNamespace(domain_events=records))
        represented = EventFeedItem(
            id="instance:represented",
            category=EventCategory.GENERAL,
            country_tag="",
            headline="Existing instance",
            body="",
            created_at="",
        )

        items = EventFeedPresenter()._journal_event_items(state, {}, [represented])

        self.assertEqual(
            [item.id for item in items],
            ["lifecycle:rejected:response_rejected:42", "lifecycle:unrepresented:resolved:8"],
        )
        self.assertEqual(items[0].severity, "warning")
        self.assertIn("Minute 0", items[0].created_at)
        self.assertIn("No authority.", items[0].body)
        self.assertEqual(items[1].status, "resolved")

    def test_event_feed_parsers_formatters_and_numeric_fallbacks(self):
        presenter = EventFeedPresenter()

        self.assertEqual(presenter._journal_event_items(
            SimpleNamespace(journal=SimpleNamespace(domain_events=())), {}, []
        ), [])
        self.assertEqual(presenter._response_options("not-json"), ())
        self.assertEqual(presenter._response_options("{}"), ())
        self.assertEqual(presenter._recovery_summary("not-json", "active"), "")
        self.assertEqual(
            presenter._recovery_summary('{"progress": 2, "state": "recovering"}', "active"),
            "100% recovering",
        )
        self.assertEqual(presenter._recovery_summary('{"state": " paused "}', "active"), "paused")
        self.assertEqual(
            presenter._format_effect({"category": "gdp_per_capita", "magnitude": 0.25, "unit": "currency"}),
            "gdp per capita +0.25 currency",
        )
        self.assertEqual(presenter._text(None, "fallback"), "fallback")
        self.assertEqual(presenter._integer("invalid"), 0)
        self.assertEqual(presenter._ratio("invalid"), 0.0)
        self.assertEqual(presenter._severity_label(0.5), "warning")
        self.assertEqual(presenter._number(object(), 7.5), 7.5)


if __name__ == "__main__":
    unittest.main()
