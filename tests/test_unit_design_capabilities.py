import pytest

from src.client.ui.panels.military.unit_design_widgets import capabilities_for_design, saved_capabilities
from src.client.ui.panels.military.unit_market_panel import UnitMarketPanel


@pytest.mark.parametrize("raw", [None, "not json", "[]", "null"])
def test_market_capabilities_leave_missing_or_invalid_values_unavailable(raw):
    design = {"class_name": "infantry", "capabilities_json": raw}
    assert saved_capabilities(design) == {}
    assert UnitMarketPanel._saved_capabilities(design) == {}
    assert capabilities_for_design(design)


def test_saved_numeric_values_override_role_defaults_and_skip_invalid_values():
    design = {"class_name": "infantry", "capabilities_json": '{"speed": "12.5", "armor": "invalid"}'}
    assert saved_capabilities(design) == {"speed": 12.5}
    assert capabilities_for_design(design)["speed"] == 12.5
    assert UnitMarketPanel._saved_capabilities(design) == {"speed": 12.5}
