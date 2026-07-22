"""Derive region-border relationships from the authoritative colour map."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl
from PIL import Image


REGION_ADJACENCY_SCHEMA = {
    "region_id": pl.Int32,
    "neighbor_region_id": pl.Int32,
}


class RegionAdjacencyBuilder:
    """Builds a compact undirected adjacency table without retaining the map in state."""

    def from_image(self, image_path: Path, valid_region_ids: set[int]) -> pl.DataFrame:
        if not image_path.exists() or not valid_region_ids:
            return pl.DataFrame(schema=REGION_ADJACENCY_SCHEMA)
        Image.MAX_IMAGE_PIXELS = None
        pairs: set[tuple[int, int]] = set()
        with Image.open(image_path) as image:
            width, height = image.size
            for top in range(0, height, 512):
                bottom = min(height, top + 512)
                crop_top = max(0, top - 1)
                pixels = np.asarray(image.crop((0, crop_top, width, bottom)).convert("RGB"), dtype=np.uint32)
                packed = (pixels[:, :, 0] << 16) | (pixels[:, :, 1] << 8) | pixels[:, :, 2]
                self._collect_pairs(pairs, packed[:, :-1], packed[:, 1:], valid_region_ids)
                self._collect_pairs(pairs, packed[:-1, :], packed[1:, :], valid_region_ids)
        rows = [
            {"region_id": first, "neighbor_region_id": second}
            for first, second in sorted(pairs)
        ]
        return pl.DataFrame(rows, schema=REGION_ADJACENCY_SCHEMA, strict=False) if rows else pl.DataFrame(schema=REGION_ADJACENCY_SCHEMA)

    def _collect_pairs(
        self,
        pairs: set[tuple[int, int]],
        first: np.ndarray,
        second: np.ndarray,
        valid_region_ids: set[int],
    ) -> None:
        difference = first != second
        if not bool(difference.any()):
            return
        candidates = np.column_stack((first[difference], second[difference]))
        candidates.sort(axis=1)
        for left, right in np.unique(candidates, axis=0):
            first_id, second_id = int(left), int(right)
            if first_id in valid_region_ids and second_id in valid_region_ids:
                pairs.add((first_id, second_id))
