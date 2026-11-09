from contextlib import contextmanager
from types import SimpleNamespace

import polars as pl

from src.client.ui.panels import region_inspector
from src.client.ui.panels.region_inspector import RegionInspectorPanel


class Imgui:
    def __init__(self, *, opened=True, clicked=False):
        self.opened = opened
        self.clicked = clicked
        self.texts = []
        self.disabled = []
        self.colored = []
        self.separators = 0

    def text_disabled(self, value):
        self.disabled.append(value)

    def text_colored(self, color, value):
        self.colored.append((color, value))

    def text(self, value):
        self.texts.append(value)

    def separator(self):
        self.separators += 1

    def button(self, label):
        return self.clicked


def install_imgui(monkeypatch, **kwargs):
    fake = Imgui(**kwargs)

    @contextmanager
    def window(*args, **window_kwargs):
        yield fake.opened

    monkeypatch.setattr(region_inspector.WindowManager, "window", window)
    monkeypatch.setattr(region_inspector, "imgui", fake)
    return fake


def test_region_inspector_window_handles_closed_and_unselected_region(monkeypatch):
    fake = install_imgui(monkeypatch, opened=False)
    panel = RegionInspectorPanel()
    assert panel.render(object(), SimpleNamespace(selected_region_id=1)) is False

    fake = install_imgui(monkeypatch)
    assert panel.render(object(), SimpleNamespace(selected_region_id=None)) is True
    assert fake.disabled == ["Select a region..."]


def test_region_inspector_renders_a_selected_region_in_the_window(monkeypatch):
    fake = install_imgui(monkeypatch)
    panel = RegionInspectorPanel()
    state = SimpleNamespace(
        tables={"regions": pl.DataFrame([{"id": 3, "name": "Coast", "owner": "UKR"}])}
    )
    context = SimpleNamespace(
        selected_region_id=3,
        on_focus_request=None,
        target_tag="UKR",
    )

    assert panel.render(state, context) is True

    assert fake.colored == [(region_inspector.GAMETHEME.colors.accent, "Coast")]


def test_details_ignore_missing_table_and_report_invalid_region(monkeypatch):
    fake = install_imgui(monkeypatch)
    panel = RegionInspectorPanel()

    panel._render_details(SimpleNamespace(tables={}), 1, None)
    assert fake.texts == []

    panel._render_details(
        SimpleNamespace(tables={"regions": pl.DataFrame({"id": [1], "name": ["One"]})}),
        2,
        None,
    )
    assert fake.colored[-1] == (region_inspector.GAMETHEME.colors.error, "Invalid Region ID")


def test_details_render_recognition_occupation_and_focus_action(monkeypatch):
    fake = install_imgui(monkeypatch, clicked=True)
    panel = RegionInspectorPanel()
    recognition_calls = []
    panel._recognition_presenter.for_region = lambda state, region_id, country: recognition_calls.append((region_id, country)) or {
        "claimant_id": "CAN",
        "former_owner_id": "USA",
        "status": "pending_vote",
        "yes_votes": 3,
        "eligible_count": 4,
        "recognized_count": 2,
        "country_status": "recognized",
    }
    state = SimpleNamespace(tables={
        "regions": pl.DataFrame({
            "id": [7],
            "name": ["North"],
            "owner": ["CAN"],
            "controller": ["USA"],
            "biome": ["tundra"],
        }),
        "occupations": pl.DataFrame({
            "region_id": [7],
            "controller_country_id": ["USA"],
            "garrison_strength": [120],
            "resistance": [3.25],
            "occupation_status": ["contested"],
            "started_at_minute": [9],
            "contested": [True],
        }),
    })
    focused = []

    panel._render_details(state, 7, focused.append, "CAN")

    assert fake.colored[0] == (region_inspector.GAMETHEME.colors.accent, "North")
    assert "Controller: USA" in fake.texts
    assert "UN Recognition" in fake.texts
    assert "Claimant: CAN" in fake.texts
    assert "Former owner: USA" in fake.texts
    assert "Case: Pending Vote" in fake.texts
    assert "Yes votes: 3 / 4 eligible" in fake.texts
    assert "Recognizing countries: 2" in fake.texts
    assert "Selected country: Recognized" in fake.texts
    assert "Military occupation" in fake.texts
    assert "Resistance: 3.2" in fake.texts
    assert "Contested: Yes" in fake.texts
    assert "Biome: tundra" in fake.texts
    assert focused == [7]
    assert recognition_calls == [(7, "CAN")]


def test_details_skip_optional_occupation_and_recognition_fields(monkeypatch):
    fake = install_imgui(monkeypatch)
    panel = RegionInspectorPanel()
    panel._recognition_presenter.for_region = lambda *args: None
    state = SimpleNamespace(tables={
        "regions": pl.DataFrame({"id": [1], "owner": ["USA"], "biome": [None]}),
        "occupations": pl.DataFrame({"other_id": [1]}),
    })

    panel._render_details(state, 1, None)

    assert "Controller: " not in " ".join(fake.texts)
    assert "UN Recognition" not in fake.texts
    assert "Military occupation" not in fake.texts
    assert "Biome: None" in fake.texts
