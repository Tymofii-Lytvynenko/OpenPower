import hashlib
from typing import Dict, Tuple

def generate_political_colors(owner_tags: list[str]) -> Dict[str, Tuple[int, int, int]]:
    """
    Generates deterministic colors for a list of country tags.
    Returns: {'USA': (R, G, B), ...}
    """
    color_map = {}
    for tag in owner_tags:
        if not tag or tag == "None":
            color_map[tag] = (0, 0, 0)
            continue
        
        # Hash the tag to get consistent RGB
        hash_bytes = hashlib.md5(str(tag).encode('utf-8')).digest()
        color_map[tag] = (hash_bytes[0], hash_bytes[1], hash_bytes[2])
        
    return color_map