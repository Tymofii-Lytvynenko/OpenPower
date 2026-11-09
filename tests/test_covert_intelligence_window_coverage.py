from contextlib import contextmanager
from types import SimpleNamespace

from src.client.ui.panels.military import covert_intelligence_window
from src.client.ui.panels.military.covert_intelligence_window import CovertIntelligenceWindow


class Imgui:
    def __init__(self):
        self.wrapped = []
        self.disabled = []
        self.texts = []
        self.separators = 0

    def text_wrapped(self, value):
        self.wrapped.append(value)

    def text_disabled(self, value):
        self.disabled.append(value)

    def text(self, value):
        self.texts.append(value)

    def separator(self):
        self.separators += 1


class Presenter:
    def __init__(self, missions=(), findings=()):
        self.missions = list(missions)
        self.findings = list(findings)
        self.calls = []

    def covert_missions_for_country(self, state, country_tag):
        self.calls.append(("missions", country_tag))
        return self.missions

    def covert_findings_for_country(self, state, country_tag):
        self.calls.append(("findings", country_tag))
        return self.findings


def install_window(monkeypatch, opened=True):
    @contextmanager
    def window(*args, **kwargs):
        yield opened

    monkeypatch.setattr(covert_intelligence_window.WindowManager, "window", window)
    fake = Imgui()
    monkeypatch.setattr(covert_intelligence_window, "imgui", fake)
    return fake


def test_closed_window_and_non_owner_avoid_authorized_intelligence_queries(monkeypatch):
    fake = install_window(monkeypatch)
    empty_states = []
    monkeypatch.setattr(covert_intelligence_window, "draw_empty_state", empty_states.append)
    window = CovertIntelligenceWindow()
    presenter = Presenter()

    window.render(object(), SimpleNamespace(is_own_country=True, target_tag="USA"), presenter)
    assert presenter.calls == []

    window.is_open = True
    install_window(monkeypatch, opened=False)
    window.render(object(), SimpleNamespace(is_own_country=True, target_tag="USA"), presenter)
    assert window.is_open is False
    assert presenter.calls == []

    window.is_open = True
    fake = install_window(monkeypatch)
    window.render(object(), SimpleNamespace(is_own_country=False, target_tag="CAN"), presenter)
    assert fake.wrapped == ["Select your country to inspect authorized intelligence."]
    assert presenter.calls == []
    assert empty_states == []


def test_window_shows_empty_states_and_authorized_mission_and_finding_provenance(monkeypatch):
    fake = install_window(monkeypatch)
    empty_states = []
    monkeypatch.setattr(covert_intelligence_window, "draw_empty_state", empty_states.append)
    window = CovertIntelligenceWindow()
    window.is_open = True
    presenter = Presenter()

    window.render(object(), SimpleNamespace(is_own_country=True, target_tag="USA"), presenter)

    assert empty_states == [
        "No pending or discovered operations.",
        "No intelligence findings are available.",
    ]
    assert fake.texts == ["KNOWN OPERATIONS", "INTELLIGENCE FINDINGS"]
    assert fake.separators == 1
    assert presenter.calls == [("missions", "USA"), ("findings", "USA")]

    fake = install_window(monkeypatch)
    window.is_open = True
    presenter = Presenter(
        missions=[
            {"_viewer_role": "framed", "target_country_id": "CAN"},
            {"mission_type": "sabotage", "result": "Detected", "target_country_id": "MEX", "owner_country_id": "USA"},
            {"mission_type": None, "status": "pending"},
        ],
        findings=[
            {"source_country_id": "USA", "category": "military", "information_status": "confirmed", "confidence": 0.75, "freshness": 0.25},
            {"source_country_id": "can", "category": None, "confidence": 0.5, "freshness": 1.0},
            {"source_country_id": "", "category": "economic", "information_status": None, "confidence": 0.0, "freshness": 0.0},
        ],
    )

    window.render(object(), SimpleNamespace(is_own_country=True, target_tag="USA"), presenter)

    assert "Detected operation · your country was implicated" in fake.wrapped
    assert "Sabotage · Detected" in fake.wrapped
    assert "Unknown · pending" in fake.wrapped
    assert "Military · confirmed · Confidence 75% · Freshness 25%" in fake.wrapped
    assert "Unknown · unknown · Confidence 50% · Freshness 100%" in fake.wrapped
    assert "Economic · unknown · Confidence 0% · Freshness 0%" in fake.wrapped
    assert "Your country was framed · Target CAN" in fake.disabled
    assert "Target MEX · Attribution USA" in fake.disabled
    assert "Collected directly" in fake.disabled
    assert "Shared by CAN" in fake.disabled
    assert "Shared by ally" in fake.disabled
