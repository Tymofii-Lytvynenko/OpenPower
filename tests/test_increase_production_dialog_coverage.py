from contextlib import nullcontext
from types import SimpleNamespace

from src.client.ui.components.shared import increase_production_dialog as dialog_module


class _ImguiStub:
    Col_ = SimpleNamespace(button="button")

    def __init__(self, *, button_clicks=(), hovered=()):
        self.button_clicks = set(button_clicks)
        self.hovered = iter(hovered)
        self.disabled = False
        self.calls = []

    def get_main_viewport(self):
        return SimpleNamespace(
            pos=SimpleNamespace(x=100, y=50),
            size=SimpleNamespace(x=1000, y=600),
        )

    def push_style_color(self, color, value):
        self.calls.append(("push_style_color", color, value))

    def button(self, label, *, test_id, gml_id):
        self.calls.append(("button", label, test_id, gml_id, self.disabled))
        return test_id in self.button_clicks and not self.disabled

    def pop_style_color(self):
        self.calls.append(("pop_style_color",))

    def text(self, label, *, test_id, gml_id):
        self.calls.append(("text", label, test_id, gml_id))

    def is_item_hovered(self):
        return next(self.hovered, False)

    def set_tooltip(self, text):
        self.calls.append(("tooltip", text))

    def begin_disabled(self, disabled):
        self.disabled = disabled
        self.calls.append(("begin_disabled", disabled))

    def end_disabled(self):
        self.disabled = False
        self.calls.append(("end_disabled",))

    def get_window_pos(self):
        return SimpleNamespace(x=10, y=20)

    def set_cursor_screen_pos(self, position):
        self.calls.append(("cursor_screen_pos", position))

    def text_disabled(self, text):
        self.calls.append(("text_disabled", text))


def _install_render_stubs(monkeypatch, *, window_open=True, button_clicks=(), hovered=()):
    calls = {"window": []}
    imgui = _ImguiStub(button_clicks=button_clicks, hovered=hovered)

    def window(*args, **kwargs):
        calls["window"].append((args, kwargs))
        return nullcontext(window_open)

    monkeypatch.setattr(dialog_module, "imgui", imgui)
    monkeypatch.setattr(dialog_module.WindowManager, "window", window)
    return calls, imgui


def test_open_rejects_empty_identifiers_and_exposes_reset_state():
    dialog = dialog_module.IncreaseProductionDialog()

    assert not dialog.is_open
    assert dialog.country_tag == ""
    assert dialog.resource_id == ""
    dialog.open("", "grain")
    dialog.open("UKR", "")
    assert not dialog.is_open

    dialog.open("ukr", 42)
    dialog._toggle_percent(2)
    dialog.open("pol", "coal")

    assert dialog.is_open
    assert dialog.country_tag == "POL"
    assert dialog.resource_id == "coal"
    assert dialog._selected_percents == set()


def test_render_when_closed_does_not_open_a_window(monkeypatch):
    calls, _imgui = _install_render_stubs(monkeypatch)
    dialog = dialog_module.IncreaseProductionDialog()

    assert dialog.render(SimpleNamespace(), can_apply=True) is None
    assert calls["window"] == []


def test_render_without_basis_shows_unavailable_and_disables_apply(monkeypatch):
    dialog = dialog_module.IncreaseProductionDialog()
    dialog.open("ukr", "grain")
    monkeypatch.setattr(dialog, "_PERCENTAGES", (2, 25), raising=False)
    monkeypatch.setattr(dialog_module, "production_increase_basis", lambda *_args: None)
    calls, imgui = _install_render_stubs(
        monkeypatch,
        button_clicks=("resources.increase_production.apply",),
        hovered=(True, False),
    )

    assert dialog.render(SimpleNamespace(), can_apply=True) is None

    assert dialog.is_open
    assert calls["window"][0][0] == ("Increase production",)
    assert calls["window"][0][1]["x"] == 430.0
    assert calls["window"][0][1]["y"] == 270.0
    assert calls["window"][0][1]["test_id"] == "resources.increase_production.dialog"
    assert [call[1] for call in imgui.calls if call[0] == "text"] == ["Unavailable", "Unavailable"]
    assert [call[1] for call in imgui.calls if call[0] == "begin_disabled"] == [True]
    assert [call[1] for call in imgui.calls if call[0] == "tooltip"] == [
        "No positive production value is available for this resource."
    ]
    assert ("text_disabled", "OpenPower estimate: one year of added output.") in imgui.calls


def test_render_with_basis_toggles_percent_and_applies_largest_selection(monkeypatch):
    dialog = dialog_module.IncreaseProductionDialog()
    dialog.open("ukr", "grain")
    dialog._selected_percents.add(2)
    monkeypatch.setattr(dialog, "_PERCENTAGES", (2, 25), raising=False)
    basis = SimpleNamespace(annual_value_usd=1_200_000, source="regional")
    monkeypatch.setattr(dialog_module, "production_increase_basis", lambda *_args: basis)
    monkeypatch.setattr(
        dialog_module,
        "estimate_production_increase_cost",
        lambda annual_value, percent: annual_value * percent / 100,
    )
    calls, imgui = _install_render_stubs(
        monkeypatch,
        button_clicks=(
            "resources.increase_production.percent.25",
            "resources.increase_production.apply",
        ),
        hovered=(True, True),
    )

    result = dialog.render(SimpleNamespace(), can_apply=True)

    assert result == 25
    assert not dialog.is_open
    assert calls["window"][0][1]["gml_template"] == "Increase_Production_Window"
    assert [call[1] for call in imgui.calls if call[0] == "text"] == ["$24,000", "$300,000"]
    assert [call[1] for call in imgui.calls if call[0] == "begin_disabled"] == [False]
    assert [call[1] for call in imgui.calls if call[0] == "tooltip"] == [
        "OpenPower estimate based on controlled regional output: one year of added production value. "
        "Estimated investment: $24,000.00.",
        "OpenPower estimate based on controlled regional output: one year of added production value. "
        "Estimated investment: $300,000.00.",
    ]
    assert any(
        call[0] == "push_style_color" and call[2] == (0.20, 0.35, 0.50, 1.0)
        for call in imgui.calls
    )
    assert ("cursor_screen_pos", (47.0, 167.0)) in imgui.calls


def test_render_closed_window_resets_open_state(monkeypatch):
    dialog = dialog_module.IncreaseProductionDialog()
    dialog.open("ukr", "grain")
    monkeypatch.setattr(dialog_module, "production_increase_basis", lambda *_args: None)
    _install_render_stubs(monkeypatch, window_open=False)

    assert dialog.render(SimpleNamespace(), can_apply=False) is None
    assert not dialog.is_open


def test_cost_tooltip_describes_regional_and_national_basis():
    assert dialog_module.IncreaseProductionDialog._cost_tooltip(None, None) == (
        "No positive production value is available for this resource."
    )
    assert "controlled regional output" in dialog_module.IncreaseProductionDialog._cost_tooltip(
        SimpleNamespace(source="regional"), 1000
    )
    assert "national output" in dialog_module.IncreaseProductionDialog._cost_tooltip(
        SimpleNamespace(source="national"), 1000
    )
