from types import SimpleNamespace

import src.client.ui.panels.military.unit_design_widgets as widgets_module
from src.client.ui.panels.military.unit_design_widgets import render_capability_rows
from src.shared.mod_api import ClientPresentationKeys
from tests.test_support.client_presentation import client_state


class FakeWidgets:
    def __init__(self):
        self.text_calls = []
        self.path_calls = []

    def text(self, slot, label, *, test_id):
        self.text_calls.append((slot, label, test_id))

    def path(self, slot):
        self.path_calls.append(slot)
        return f"resolved:{slot}"


def test_read_only_rows_clamp_values_skip_missing_and_show_hover_help(monkeypatch):
    ui = FakeWidgets()
    progress_calls = []
    hovered = iter((False, True))
    tooltips = []
    monkeypatch.setattr(
        widgets_module,
        "imgui",
        SimpleNamespace(
            progress_bar=lambda *args, **kwargs: progress_calls.append((args, kwargs)),
            is_item_hovered=lambda: next(hovered),
            set_tooltip=tooltips.append,
        ),
    )

    render_capability_rows(
        ui,
        "frmStats",
        {"gun_range": -10.0, "stealth": 1.5, "armor": None},
        client_state(),
        test_id_prefix="design.stats",
        visible_keys={"gun_range", "stealth", "armor"},
    )

    assert ui.text_calls == [
        ("frmStats/lblGunRange", "Gun range", "design.stats.gun_range.label"),
        ("frmStats/lblStealth", "Stealth", "design.stats.stealth.label"),
        ("frmStats/lblArmor", "Armor", "design.stats.armor.label"),
    ]
    assert [call[0][0] for call in progress_calls] == [0.0, 1.0]
    assert [call[1]["gml_id"] for call in progress_calls] == [
        "resolved:frmStats/frmGunRange",
        "resolved:frmStats/frmStealth",
    ]
    assert tooltips == ["Stealth: 1.5"]


def test_editable_rows_choose_precision_and_store_slider_values(monkeypatch):
    ui = FakeWidgets()
    slider_calls = []

    def slider_float(*args, **kwargs):
        slider_calls.append((args, kwargs))
        return True, 0.75 if ".stealth" in args[0] else 125.0

    monkeypatch.setattr(widgets_module, "imgui", SimpleNamespace(slider_float=slider_float))
    values = {"gun_range": 100.0, "stealth": 0.5}

    render_capability_rows(
        ui,
        "frmStats",
        values,
        client_state(),
        editable=True,
        test_id_prefix="design.editor",
        visible_keys={"gun_range", "stealth"},
    )

    assert [call[0][4] for call in slider_calls] == ["%.0f", "%.2f"]
    assert [call[1]["test_id"] for call in slider_calls] == [
        "design.editor.gun_range",
        "design.editor.stealth",
    ]
    assert values == {"gun_range": 125.0, "stealth": 0.75}
    assert ui.path_calls == [
        "frmStats/frmGunRange",
        "frmStats/frmStealth",
    ]


def test_read_only_row_handles_degenerate_capability_bounds(monkeypatch):
    ui = FakeWidgets()
    progress_calls = []
    state = client_state()
    state.client_presentation[ClientPresentationKeys.CAPABILITY_BOUNDS] = {
        "gun_range": (5.0, 5.0),
    }
    monkeypatch.setattr(
        widgets_module,
        "imgui",
        SimpleNamespace(
            progress_bar=lambda *args, **kwargs: progress_calls.append((args, kwargs)),
            is_item_hovered=lambda: False,
            set_tooltip=lambda _text: None,
        ),
    )

    render_capability_rows(
        ui,
        "frmStats",
        {"gun_range": 5.0},
        state,
        visible_keys={"gun_range"},
    )

    assert progress_calls[0][0][0] == 0.0


def test_rows_without_a_visibility_filter_and_without_values_only_draw_labels(monkeypatch):
    ui = FakeWidgets()
    monkeypatch.setattr(widgets_module, "imgui", SimpleNamespace())

    render_capability_rows(ui, "frmStats", {}, client_state())

    assert len(ui.text_calls) == len(widgets_module.DESIGN_METRICS)
