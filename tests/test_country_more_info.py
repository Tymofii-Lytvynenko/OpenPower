import unittest
from types import SimpleNamespace

import numpy as np
import polars as pl

from src.client.renderers.country_region_map import CountryRegionMapRasterizer
from src.client.ui.panels.country_more_info import CountryMoreInfoPresenter


class CountryMoreInfoPresenterTest(unittest.TestCase):
    def test_builds_country_summary_from_runtime_tables(self):
        state = SimpleNamespace(
            globals={"geo_language_code": "en"},
            tables={
                "countries": pl.DataFrame(
                    [
                        {
                            "id": "USA",
                            "human_dev": 0.9,
                            "poverty_rate": 0.12,
                            "fertility_rate": 1.8,
                            "life_expectancy": 77.5,
                            "budget_infra_ratio": 0.42,
                            "budget_telecom_ratio": 0.33,
                        },
                        {"id": "CAN", "human_dev": 0.8},
                    ]
                ),
                "regions": pl.DataFrame(
                    [
                        {
                            "id": 11,
                            "owner": "USA",
                            "controller": "USA",
                            "area_km2": 100.0,
                            "pop_14": 10,
                            "pop_15_64": 80,
                            "pop_65": 10,
                            "type": "State",
                            "macro_region": "North America",
                        },
                        {
                            "id": 12,
                            "owner": "USA",
                            "controller": "USA",
                            "area_km2": 300.0,
                            "pop_14": 20,
                            "pop_15_64": 130,
                            "pop_65": 50,
                            "type": "State",
                            "macro_region": "North America",
                        },
                        {
                            "id": 21,
                            "owner": "CAN",
                            "controller": "CAN",
                            "area_km2": 600.0,
                            "pop_14": 1,
                            "pop_15_64": 2,
                            "pop_65": 3,
                            "type": "Province",
                            "macro_region": "North America",
                        },
                    ]
                ),
                "domestic_production": pl.DataFrame(
                    [
                        {"country_id": "USA", "game_resource_id": "financial_services", "domestic_production": 900.0},
                        {"country_id": "USA", "game_resource_id": "cereals", "domestic_production": 100.0},
                        {"country_id": "CAN", "game_resource_id": "wood_and_paper", "domestic_production": 500.0},
                    ]
                ),
            },
        )

        model = CountryMoreInfoPresenter().build(state, "USA")

        self.assertEqual(model.tag, "USA")
        self.assertEqual(model.region_ids, (11, 12))
        self.assertEqual(model.region_count, 2)
        self.assertEqual(model.population_total, 300)
        self.assertAlmostEqual(model.land_area_km2, 400.0)
        self.assertAlmostEqual(model.world_area_share_pct, 40.0)
        self.assertAlmostEqual(model.human_dev_pct, 90.0)
        self.assertAlmostEqual(model.world_human_dev_pct, 85.0)
        self.assertAlmostEqual(model.infrastructure_pct, 42.0)
        self.assertEqual(model.composition_rows[0].label, "State")
        self.assertEqual(model.production_rows[0].label, "Financial Services")


class CountryRegionMapRasterizerTest(unittest.TestCase):
    def test_renders_cropped_country_regions_with_internal_borders(self):
        packed_map = np.array(
            [
                [0, 0, 0, 0, 0],
                [0, 1, 1, 2, 0],
                [0, 1, 2, 2, 0],
                [0, 0, 0, 0, 0],
            ],
            dtype=np.int32,
        )
        map_data = SimpleNamespace(packed_map=packed_map, width=5, height=4)

        raster = CountryRegionMapRasterizer(max_size=(20, 20), padding_px=0).render(map_data, [1, 2])

        self.assertIsNotNone(raster)
        assert raster is not None
        self.assertEqual(raster.source_bbox, (1, 1, 4, 3))
        self.assertGreaterEqual(raster.image.width, 3)
        self.assertGreaterEqual(raster.image.height, 2)

        pixels = np.asarray(raster.image)
        border_color = np.asarray((33, 156, 255, 255), dtype=np.uint8)
        self.assertTrue(np.any(np.all(pixels == border_color, axis=-1)))


if __name__ == "__main__":
    unittest.main()