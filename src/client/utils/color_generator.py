import hashlib
import colorsys
from typing import Dict, Tuple

def generate_political_colors(owner_tags: list[str]) -> Dict[str, Tuple[int, int, int]]:
    color_map = {}
    
    for tag in owner_tags:
        if not tag or tag == "None":
            color_map[tag] = (0, 0, 0)
            continue
        
        # Use hash to get a value between 0.0 and 1.0 for the Hue
        hash_int = int(hashlib.md5(str(tag).encode('utf-8')).hexdigest(), 16)
        hue = (hash_int % 360) / 360.0
        
        # FIXED VALUES to prevent dark/muddy colors:
        # Saturation: 0.7 - 0.9 (Vibrant, avoids gray)
        # Lightness: 0.5 - 0.6 (Bright, avoids black/brown)
        saturation = 0.8 
        lightness = 0.5
        
        # Convert HSL back to RGB (returns 0.0 to 1.0)
        r, g, b = colorsys.hls_to_rgb(hue, lightness, saturation)
        
        # Scale to 0-255
        color_map[tag] = (int(r * 255), int(g * 255), int(b * 255))
        
    return color_map