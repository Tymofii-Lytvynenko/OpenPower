from __future__ import annotations

import unittest
from types import SimpleNamespace

import polars as pl

from src.client.ui.panels.shared.panel_data import resolve_country_name, resolve_region_name
from src.shared.geo_names import get_geo_name_resolver, normalize_geo_language_code


class TestGeoNameResolution(unittest.TestCase):
    def test_localizes_country_and_region_names(self):
        state = SimpleNamespace(
            globals={"geo_language_code": "uk"},
            tables={
                "countries": pl.DataFrame([
                    {"id": "USA", "name": "United States"},
                ]),
                "regions": pl.DataFrame([
                    {"id": 1, "iso_region": "US-CA", "name": "California"},
                ]),
            },
        )

        expected_country = get_geo_name_resolver("uk").country_name("USA")
        expected_region = get_geo_name_resolver("uk").region_name("US-CA")
        self.assertNotEqual(expected_country, "United States")
        self.assertNotEqual(expected_region, "California")
        self.assertEqual(resolve_country_name(state, "USA"), expected_country)
        self.assertEqual(resolve_region_name(state, 1), expected_region)

    def test_falls_back_to_table_names_for_unknown_codes(self):
        state = SimpleNamespace(
            globals={"geo_language_code": "xx"},
            tables={
                "countries": pl.DataFrame([
                    {"id": "ZZZ", "name": "Mystery Land"},
                ]),
                "regions": pl.DataFrame([
                    {"id": 7, "name": "Fallback Region"},
                ]),
            },
        )

        self.assertEqual(resolve_country_name(state, "ZZZ"), "Mystery Land")
        self.assertEqual(resolve_region_name(state, 7), "Fallback Region")

    def test_normalizes_geo_language_codes(self):
        self.assertEqual(normalize_geo_language_code("UK"), "uk")
        self.assertEqual(normalize_geo_language_code("zz"), "en")


if __name__ == "__main__":
    unittest.main()
