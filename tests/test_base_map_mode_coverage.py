from src.client.visualization.map_modes.base_map_mode import BaseMapMode


def test_abstract_map_mode_hooks_have_no_base_fallback():
    assert BaseMapMode.name.fget(None) is None
    assert BaseMapMode.calculate_colors(None, None) is None
