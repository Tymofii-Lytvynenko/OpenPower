from pathlib import Path

import cv2
import numpy as np

class RegionMapData:
    """
    PURE DATA. Safe for Server and Client.
    Responsible for: Loading the image and providing ID lookups.
    """
    def __init__(self, image_path: str):
        # Map coordinates refer to stored pixels, as they do in the adjacency reader.
        self.raw_img = cv2.imread(image_path, cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION)
        if self.raw_img is None:
            raise FileNotFoundError(f"Missing map: {image_path}")
        source = Path(image_path).resolve()
        stat = source.stat()
        self.source_path = source
        self.source_revision = (source, stat.st_mtime_ns, stat.st_size)
        
        self.height, self.width, _ = self.raw_img.shape
        
        # Convert BGR image to a 2D array of Region IDs
        # (This is pure math/logic, perfectly fine for Core)
        b, g, r = cv2.split(self.raw_img)
        self.packed_map = b.astype(np.int32) | (g.astype(np.int32) << 8) | (r.astype(np.int32) << 16)

        # Free memory of the raw image, we only need the ID array now
        del b, g, r
        del self.raw_img

    def get_region_id(self, x: int, y: int) -> int:
        """
        Used by Server (Move Validation) and Client (Mouse Hover).
        """
        if 0 <= x < self.width and 0 <= y < self.height:
            return int(self.packed_map[y, x])
        return 0
