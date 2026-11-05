from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import polars as pl

from src.client.ui.components.hud.sphere_metrics import main_bar_sphere_metrics
from src.client.ui.core.gml_widgets import GMLWidgets
from src.client.ui.layouts.gml_layout import GMLLayoutSession, get_gml_layout


def test_main_bar_sphere_metrics_use_selected_country_and_native_openpower_state():
    state = SimpleNamespace(
        tables={
            "countries": pl.DataFrame(
                {
                    "id": ["AAA", "BBB"],
                    "gvt_approval": [73.5, 20.0],
                    "economic_health": [0.62, 0.95],
                }
            ),
            "units": pl.DataFrame(
                {
                    "owner": ["AAA", "AAA", "AAA", "BBB"],
                    "readiness_status": ["ready", "parked", "fortified", "parked"],
                }
            ),
        }
    )

    metrics = main_bar_sphere_metrics(state, "AAA")

    assert metrics["frmMeterPolitic"].value == 73.5
    assert metrics["frmMeterMilitary"].value == 200.0 / 3.0
    assert metrics["frmMeterEconomic"].value == 62.0
    assert metrics["frmMeterPolitic"].label == "Government approval"
    assert metrics["frmMeterMilitary"].label == "Ready or fortified military units"
    assert metrics["frmMeterEconomic"].label == "Economic health"


def test_main_bar_sphere_metrics_clamp_country_values_and_report_empty_force():
    state = SimpleNamespace(
        tables={
            "countries": pl.DataFrame(
                {"id": ["AAA"], "gvt_approval": [120.0], "economic_health": [-0.5]}
            ),
            "units": pl.DataFrame(
                {"owner": ["BBB"], "readiness_status": ["ready"]}
            ),
        }
    )

    metrics = main_bar_sphere_metrics(state, "AAA")

    assert metrics["frmMeterPolitic"].value == 100.0
    assert metrics["frmMeterMilitary"].value == 0.0
    assert metrics["frmMeterEconomic"].value == 0.0


def test_segmented_meter_draws_the_nine_source_child_frames_in_order():
    layout = get_gml_layout("Main_Bar")
    session = GMLLayoutSession(layout, (100.0, 200.0), (layout.width, layout.height))
    native = MagicMock()
    native.get_scroll_x.return_value = 0.0
    native.get_scroll_y.return_value = 0.0
    ui = GMLWidgets("Main_Bar")
    ui.hitbox = Mock(return_value=False)

    with patch("src.client.ui.core.gml_widgets.imgui", native), \
         patch("src.client.ui.core.gml_widgets.active_gml_layout", return_value=session):
        ui.segmented_meter("frmMeterPolitic", 0.5, (1.0, 0.5, 0.2, 1.0), "hud.politic")

    draw = native.get_window_draw_list.return_value
    assert draw.add_rect.call_count == 9
    assert draw.add_rect_filled.call_count == 14
    assert draw.add_rect.call_args_list[0].args[:2] == ((115.0, 273.0), (119.0, 280.0))
    ui.hitbox.assert_called_once_with("frmMeterPolitic", "hud.politic", tooltip=None)
