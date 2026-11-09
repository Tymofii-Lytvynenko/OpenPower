from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import src.client.ui.panels.politics.political_overview_panel as overview_module
from src.client.ui.panels.politics.political_overview_panel import PoliticalOverviewPanel


def political_overview(**overrides):
    values = {
        "country_id": "USA",
        "government_form": "Republic",
        "ruling_party": "Civic Party",
        "election_eligible": True,
        "days_to_next_election": 0,
        "approval_pct": 70.0,
        "stability_pct": 60.0,
        "corruption_pct": 10.0,
        "crisis_status": "Stable",
        "election_override_options": [],
        "recent_elections": [],
        "parties": [],
        "laws": [],
        "pending_law_transitions": [],
        "recent_causes": [],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def override_option(**overrides):
    values = {
        "override_type": "emergency",
        "default_duration_days": 10,
        "minimum_duration_days": 1,
        "maximum_duration_days": 30,
        "cost": 100.0,
        "approval_delta": -5.0,
        "stability_delta": -2.0,
        "available": True,
        "unavailable_reason": "Unavailable",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def panel_with_overview(monkeypatch, overview):
    imgui = Mock()
    imgui.small_button.side_effect = lambda label: "Emergency" in label
    imgui.slider_int.return_value = (True, 7)
    empty_state = Mock()
    monkeypatch.setattr(overview_module, "imgui", imgui)
    monkeypatch.setattr(overview_module, "draw_empty_state", empty_state)
    panel = PoliticalOverviewPanel()
    panel._presenter = Mock()
    panel._presenter.build.return_value = overview
    panel._legacy_presenter = Mock()
    panel._legacy_presenter.build_summary.return_value = SimpleNamespace(
        capital_name="Washington", martial_law=False, election_risk_pct=12.0, ideology_balance=0.4,
    )
    return panel, imgui, empty_state


class Client:
    player_id = "player-1"

    def __init__(self):
        self.actions = []

    def send_action(self, action):
        self.actions.append(action)


def test_render_content_displays_political_data_and_routes_override_states(monkeypatch):
    overview = political_overview(
        election_override_options=[
            override_option(),
            override_option(override_type="blocked", available=False, unavailable_reason="No mandate"),
            override_option(override_type="foreign"),
            override_option(override_type="offline"),
            override_option(override_type="fixed", minimum_duration_days=5, maximum_duration_days=5),
        ],
        recent_elections=[
            SimpleNamespace(status="resolved", winner_party_id=None, turnout_pct=65.0,
                            override_type="emergency", reason="Term ended"),
            SimpleNamespace(status="scheduled", scheduled_at_minute=240, override_type="", reason=""),
        ],
        parties=[SimpleNamespace(display_name="Civic Party", support_pct=45.0, is_ruling=True)],
        laws=[SimpleNamespace(title="Speech", value="Protected", status="active")],
        pending_law_transitions=[SimpleNamespace(law_id="speech", target_value="Limited", effective_at_minute=80)],
        recent_causes=[SimpleNamespace(event_type="ElectionHeld", reason="Term reached")],
    )
    panel, imgui, empty_state = panel_with_overview(monkeypatch, overview)
    client = Client()
    context = SimpleNamespace(is_own_country=True, net_client=client, target_tag="USA")

    panel._render_content(SimpleNamespace(), context)

    assert empty_state.call_count == 0
    assert len(client.actions) == 1
    action = client.actions[0]
    assert action.country_tag == "USA"
    assert action.override_type == "emergency"
    assert action.duration_days == 7
    assert imgui.slider_int.call_count == 4
    imgui.text_disabled.assert_any_call("No mandate")
    panel._render_election_overrides(
        overview,
        SimpleNamespace(is_own_country=False, net_client=client),
    )
    imgui.text_disabled.assert_any_call("Select your own country to issue this action.")
    panel._render_election_overrides(
        political_overview(election_override_options=[override_option()]),
        SimpleNamespace(is_own_country=True, net_client=None),
    )
    imgui.text_disabled.assert_any_call("The authoritative game connection is unavailable.")
    assert any("Election: Due" == call.args[0] for call in imgui.text.call_args_list)
    assert any("Resolved: Unavailable" in call.args[0] for call in imgui.text.call_args_list)
    assert any("Scheduled at minute 240" in call.args[0] for call in imgui.text.call_args_list)


def test_render_content_uses_empty_states_when_sections_are_unavailable(monkeypatch):
    panel, _imgui, empty_state = panel_with_overview(
        monkeypatch,
        political_overview(election_eligible=None, days_to_next_election=None),
    )
    panel._render_content(SimpleNamespace(), SimpleNamespace(target_tag="USA", is_own_country=False, net_client=None))

    assert [call.args[0] for call in empty_state.call_args_list] == [
        "No election override rules are configured for this government.",
        "No election results or override records are available.",
        "No party records are available.",
        "No law records are available.",
        "No recorded political causes are available.",
    ]
    assert panel._election_summary(None, 4) == "Unavailable"
    assert panel._election_summary(False, 4) == "Not scheduled for this government form"
    assert panel._election_summary(True, None) == "Unscheduled"
    assert panel._election_summary(True, 3) == "In 3 game days"
    assert panel._percent(None) == "Unavailable"
    assert panel._percent(12.34) == "12.3%"


def test_render_returns_window_state_and_centers_the_existing_panel(monkeypatch):
    opened = False
    calls = []

    @contextmanager
    def window(*args, **kwargs):
        calls.append((args, kwargs))
        yield opened

    monkeypatch.setattr(overview_module.WindowManager, "window", window)
    panel = PoliticalOverviewPanel()
    panel._render_content = Mock()
    state = SimpleNamespace()
    context = SimpleNamespace(target_tag="USA")

    assert panel.render(state, context) is False
    opened = True
    assert panel.render(state, context) is True
    assert calls[0][1] == {"x": 260, "y": 120, "w": 520, "h": 640, "test_id": "political_overview.panel"}
    panel._render_content.assert_called_once_with(state, context)
