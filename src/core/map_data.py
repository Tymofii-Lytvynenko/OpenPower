import cv2
import numpy as np

class RegionMapData:
    """
    PURE DATA. Safe for Server and Client.
    Responsible for: Loading the image and providing ID lookups.
    """
    def __init__(self, image_path: str):
        # cv2.imread is safe on a headless server
        self.raw_img = cv2.imread(image_path)
        if self.raw_img is None:
            raise FileNotFoundError(f"Missing map: {image_path}")
        
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