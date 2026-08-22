import unittest

import numpy as np

from src.client.renderers.texture_manager import TextureManager


class MapVisualEncodingTest(unittest.TestCase):
    def test_region_ids_and_borders_share_one_rgba_texture(self) -> None:
        dense_map = np.array([
            [0, 1, 1],
            [0, 1, 2],
        ], dtype=np.uint32)

        encoded = TextureManager.encode_map_visual(dense_map, 3, 2)
        restored = np.flipud(encoded)

        decoded_ids = (
            restored[:, :, 0].astype(np.uint32) << 16
            | restored[:, :, 1].astype(np.uint32) << 8
            | restored[:, :, 2].astype(np.uint32)
        )
        self.assertTrue(np.array_equal(decoded_ids, dense_map))
        self.assertEqual(restored[0, 0, 3], 0)
        self.assertEqual(restored[0, 1, 3], 0)
        self.assertEqual(restored[0, 2, 3], 255)
        self.assertEqual(restored[1, 1, 3], 255)

    def test_terrain_texture_is_reduced_without_changing_aspect_ratio(self) -> None:
        size = TextureManager.fit_texture_size(16000, 8000, 8192, 4096)

        self.assertEqual(size, (8192, 4096))

    def test_small_terrain_texture_is_not_upscaled(self) -> None:
        size = TextureManager.fit_texture_size(2048, 1024, 8192, 4096)

        self.assertEqual(size, (2048, 1024))

    def test_lookup_texture_uses_smallest_power_of_two_capacity(self) -> None:
        self.assertEqual(TextureManager.required_lut_dimension(4561), 128)
        self.assertEqual(TextureManager.required_lut_dimension(70000), 512)

    def test_dense_map_downsampling_keeps_discrete_region_ids(self) -> None:
        dense_map = np.array([
            [1, 1, 2, 2],
            [1, 1, 2, 2],
            [3, 3, 4, 4],
            [3, 3, 4, 4],
        ], dtype=np.uint32)

        reduced = TextureManager.resample_dense_map(dense_map, 4, 4, 2, 2)

        self.assertTrue(np.array_equal(reduced, np.array([[1, 2], [3, 4]])))

    def test_native_region_map_resolution_is_preserved(self) -> None:
        size = TextureManager.fit_texture_size(
            16000,
            8000,
            *TextureManager.MAX_MAP_TEXTURE_SIZE,
        )

        self.assertEqual(size, (16000, 8000))


if __name__ == "__main__":
    unittest.main()
