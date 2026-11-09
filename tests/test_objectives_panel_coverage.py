from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import polars as pl
import pytest

from src.client.ui.panels.service import objectives_panel as panel_module
from src.client.ui.panels.service.objectives_panel import ObjectivesPanel
from src.shared.actions import ActionResolveAdvisorRecommendation, ActionSetSphereDelegation


class FakeClient:
    player_id = "player-1"

    def __init__(self):
        self.actions = []

    def send_action(self, action):
        self.actions.append(action)


def panel_context(*, own=True, client=None, review=None, question=None, notice=None):
    return SimpleNamespace(
        is_own_country=own, target_tag="UKR", net_client=client,
        on_advisor_recommendation=review, on_question=question, on_notice=notice,
    )


def install_imgui(monkeypatch):
    imgui = Mock()
    imgui.get_main_viewport.return_value.size = SimpleNamespace(x=1200, y=800)
    monkeypatch.setattr(panel_module, "imgui", imgui)
    return imgui


def test_panel_render_respects_window_state_and_places_window_inside_viewport(monkeypatch):
    imgui = install_imgui(monkeypatch)
    monkeypatch.setattr(panel_module, "get_gml_layout", lambda _name: SimpleNamespace(width=400, height=300))
    opened_values = iter((False, True))
    window_calls = []

    @contextmanager
    def window(*args, **kwargs):
        window_calls.append((args, kwargs))
        yield next(opened_values)

    monkeypatch.setattr(panel_module.WindowManager, "window", staticmethod(window))
    panel = ObjectivesPanel()
    panel._render_content = Mock()

    assert panel.render(object(), panel_context()) is False
    assert panel.render(object(), panel_context()) is True

    assert len(window_calls) == 2
    assert window_calls[0][0] == ("OBJECTIVES",)
    assert window_calls[0][1]["x"] == 790.0
    assert window_calls[0][1]["y"] == 120.0
    assert window_calls[0][1]["w"] == 400
    assert window_calls[0][1]["h"] == 300
    assert window_calls[0][1]["test_id"] == "objectives.panel"
    assert window_calls[0][1]["avoid_overlaps"] is True
    panel._render_content.assert_called_once()
    assert imgui.get_main_viewport.call_count == 2


def test_render_content_builds_overview_and_passes_advice_callback(monkeypatch):
    panel = ObjectivesPanel()
    panel._presenter.build_overview = Mock(return_value=object())
    panel._window_content.render = Mock()
    state = SimpleNamespace(time=SimpleNamespace(total_minutes=321))
    context = panel_context()

    panel._render_content(state, context)

    panel._presenter.build_overview.assert_called_once_with(state, "UKR")
    panel._window_content.render.assert_called_once()
    args = panel._window_content.render.call_args.args
    assert args[:3] == (panel._presenter.build_overview.return_value, "UKR", 321)
    assert callable(panel._window_content.render.call_args.kwargs["render_openpower_advice"])


def test_advice_controls_compose_recommendations_delegations_and_empty_state(monkeypatch):
    imgui = install_imgui(monkeypatch)
    empty = Mock()
    monkeypatch.setattr(panel_module, "draw_empty_state", empty)
    panel = ObjectivesPanel()
    context = panel_context(client=FakeClient())
    overview = SimpleNamespace(recommendations=[{"id": "r1"}], campaign={"id": "c1"}, delegations=[{"id": "d1"}])
    panel._render_recommendations = Mock()
    panel._render_delegation_controls = Mock()

    state = object()
    panel._render_advice_controls(state, context, overview, "UKR", 50)

    panel._render_recommendations.assert_called_once_with(context, overview.recommendations, "UKR", 50)
    panel._render_delegation_controls.assert_called_once_with(state, context, list(overview.delegations), "UKR")
    empty.assert_not_called()
    imgui.separator.assert_called_once_with()

    panel._render_recommendations.reset_mock()
    panel._render_delegation_controls.reset_mock()
    panel._render_advice_controls(object(), panel_context(own=False, client=FakeClient()),
                                 SimpleNamespace(recommendations=[], campaign={"id": "c1"}, delegations=[]),
                                 "UKR", 50)
    panel._render_delegation_controls.assert_not_called()
    empty.assert_called_once_with("No advisor recommendations or delegated scopes are available.")

    panel._render_advice_controls(object(), panel_context(),
                                 SimpleNamespace(recommendations=[], campaign=None, delegations=[]), "UKR", 50)
    assert empty.call_count == 2


def test_recommendations_limit_rows_clamp_urgency_and_show_truncation_tooltips(monkeypatch):
    imgui = install_imgui(monkeypatch)
    imgui.is_item_hovered.return_value = True
    fit = Mock(side_effect=lambda text, _width: text[:8])
    monkeypatch.setattr(panel_module.Prims, "fit_text", fit)
    panel = ObjectivesPanel()
    panel._presenter.recommendation_action_label = Mock(return_value="")
    recommendations = [
        {"id": str(index), "title": f"Recommendation {index}", "reason": "A detailed recommendation reason.",
         "urgency": 1.5, "expires_at_minute": 10, "source_signal": "ai_policy:budget" if index == 0 else ""}
        for index in range(6)
    ]

    panel._render_recommendations(panel_context(own=False), recommendations, "UKR", 1000)

    assert imgui.text.call_count == 5
    assert imgui.text.call_args_list[0].args == ("AI PROPO",)
    assert imgui.text_colored.call_count == 5
    assert imgui.text_disabled.call_args_list[0].args == ("Expires in 0 day(s)",)
    assert imgui.set_tooltip.call_count == 10
    assert imgui.separator.call_count == 4
    assert fit.call_count == 10


def test_recommendation_review_uses_inline_callback_when_available(monkeypatch):
    imgui = install_imgui(monkeypatch)
    imgui.small_button.return_value = True
    monkeypatch.setattr(panel_module.Prims, "fit_text", lambda text, _width: text)
    panel = ObjectivesPanel()
    panel._presenter.recommendation_action_label = Mock(return_value="increase investment")
    review = Mock()
    item = {"id": "r-1", "title": "Invest", "reason": "Production is low."}

    panel._render_recommendations(panel_context(client=FakeClient(), review=review), [item], "UKR", 10)

    imgui.small_button.assert_called_once_with("Review##r-1", test_id="objectives.recommendation.review.r-1")
    review.assert_called_once_with(item)


def test_recommendation_review_question_resolves_accept_and_decline(monkeypatch):
    imgui = install_imgui(monkeypatch)
    imgui.small_button.return_value = True
    monkeypatch.setattr(panel_module.Prims, "fit_text", lambda text, _width: text)
    panel = ObjectivesPanel()
    panel._presenter.recommendation_action_label = Mock(return_value="sign a treaty")
    client = FakeClient()
    question = Mock()
    item = {"id": "r-2", "title": "Treaty", "reason": "Relations are favorable."}

    panel._render_recommendations(
        panel_context(client=client, question=question), [item], "UKR", 20,
    )

    question.assert_called_once()
    message, accept, decline = question.call_args.args
    assert "Suggested action: sign a treaty. Apply it?" in message
    accept()
    decline()
    assert [type(action) for action in client.actions] == [
        ActionResolveAdvisorRecommendation, ActionResolveAdvisorRecommendation,
    ]
    assert [action.accept for action in client.actions] == [True, False]
    assert [action.recommendation_id for action in client.actions] == ["r-2", "r-2"]


def test_recommendation_read_notice_acknowledges_by_dismissing(monkeypatch):
    imgui = install_imgui(monkeypatch)
    imgui.small_button.return_value = True
    monkeypatch.setattr(panel_module.Prims, "fit_text", lambda text, _width: text)
    panel = ObjectivesPanel()
    panel._presenter.recommendation_action_label = Mock(return_value="")
    notice = Mock()
    client = FakeClient()
    item = {"id": "r-3", "title": "Read me", "reason": "More context"}

    panel._render_recommendations(panel_context(client=client, notice=notice), [item], "UKR", 0)

    notice.assert_called_once()
    assert notice.call_args.args == ("Read me", "More context")
    notice.call_args.kwargs["on_acknowledge"]()
    assert len(client.actions) == 1
    assert client.actions[0].accept is False


def test_recommendation_controls_are_hidden_for_foreign_context_or_missing_client(monkeypatch):
    imgui = install_imgui(monkeypatch)
    monkeypatch.setattr(panel_module.Prims, "fit_text", lambda text, _width: text)
    panel = ObjectivesPanel()
    panel._presenter.recommendation_action_label = Mock(return_value="apply")
    item = {"id": "r-4", "title": "Policy", "reason": "Reason"}
    imgui.small_button.return_value = True

    panel._render_recommendations(panel_context(own=False, client=FakeClient(), question=Mock()), [item], "UKR", 0)
    panel._render_recommendations(panel_context(own=True, question=Mock()), [item], "UKR", 0)

    imgui.small_button.assert_not_called()


def test_recommendation_question_is_noop_without_question_callback():
    panel = ObjectivesPanel()

    panel._open_recommendation_question(
        panel_context(question=None), "UKR", {"id": "r-5"}, "apply policy",
    )


def test_resolve_recommendation_is_noop_without_client_and_sends_with_client():
    ObjectivesPanel._resolve_recommendation(panel_context(client=None), "UKR", "r-1", accept=True)
    client = FakeClient()
    ObjectivesPanel._resolve_recommendation(panel_context(client=client), "UKR", "r-1", accept=True)
    assert client.actions == [ActionResolveAdvisorRecommendation(
        player_id="player-1", recommendation_id="r-1", accept=True,
    )]


def test_delegation_controls_return_existing_scope_and_delegate_party_and_sphere(monkeypatch):
    imgui = install_imgui(monkeypatch)
    client = FakeClient()
    panel = ObjectivesPanel()
    panel._selected_sphere_id = ""
    imgui.button.side_effect = lambda label: label.startswith("Return country") or label in {
        "Delegate ruling-party politics to AI", "Delegate treaty diplomacy to AI",
    }
    imgui.begin_combo.return_value = True
    imgui.selectable.side_effect = lambda treaty_id, _selected: (treaty_id == "S2", None)
    state = SimpleNamespace(tables={
        "country_governments": pl.DataFrame({"country_id": ["UKR"], "ruling_party_id": ["PAR"]}),
        "countries_treaties": pl.DataFrame({
            "id": ["S2", "S1", "inactive", "other"],
            "members": [["UKR", "POL"], ["UKR"], ["UKR"], ["POL"]],
            "status": ["active", "active", "pending", "active"],
        }),
    })
    delegations = [
        {"owner_country_id": " ukr ", "active": True, "scope_type": "country", "scope_id": "UKR",
         "delegate_id": "ai", "authority_json": '["economy"]', "priorities_json": '["campaign_objectives"]'},
        {"owner_country_id": "POL", "active": True, "scope_type": "country", "scope_id": "POL"},
        {"owner_country_id": "UKR", "active": False, "scope_type": "party", "scope_id": "PAR"},
    ]

    panel._render_delegation_controls(state, panel_context(client=client), delegations, "ukr")

    assert "Delegate economic policy to AI" not in [call.args[0] for call in imgui.button.call_args_list]
    imgui.begin_combo.assert_called_once_with("Treaty sphere", "S1")
    assert panel._selected_sphere_id == "S2"
    assert [type(action) for action in client.actions] == [
        ActionSetSphereDelegation, ActionSetSphereDelegation, ActionSetSphereDelegation,
    ]
    returned, party, sphere = client.actions
    assert returned.active is False
    assert returned.authority == ["economy"]
    assert returned.priorities == ["campaign_objectives"]
    assert (party.scope_type, party.scope_id, party.authority, party.priorities) == (
        "party", "PAR", ["politics"], ["campaign_politics"],
    )
    assert (sphere.scope_type, sphere.scope_id, sphere.authority, sphere.priorities) == (
        "sphere", "S2", ["diplomacy"], ["treaty_membership"],
    )


def test_delegation_controls_offer_country_scope_when_no_scope_is_active(monkeypatch):
    imgui = install_imgui(monkeypatch)
    imgui.button.return_value = True
    panel = ObjectivesPanel()
    client = FakeClient()

    panel._render_delegation_controls(SimpleNamespace(tables={}), panel_context(client=client), [], "UKR")

    assert len(client.actions) == 1
    action = client.actions[0]
    assert (action.scope_type, action.scope_id, action.authority, action.priorities) == (
        "country", "UKR", ["economy"], ["campaign_objectives"],
    )


def test_advice_controls_skip_delegation_for_unowned_or_unconnected_campaigns(monkeypatch):
    install_imgui(monkeypatch)
    monkeypatch.setattr(panel_module, "draw_empty_state", Mock())
    panel = ObjectivesPanel()
    panel._render_recommendations = Mock()
    panel._render_delegation_controls = Mock()
    data = SimpleNamespace(recommendations=[], campaign={"id": "campaign"}, delegations=[])

    panel._render_advice_controls(object(), panel_context(own=True, client=None), data, "UKR", 0)
    panel._render_advice_controls(object(), panel_context(own=False, client=FakeClient()), data, "UKR", 0)

    panel._render_delegation_controls.assert_not_called()


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ('["economy", "", 2]', ["economy", "2"]),
        (("politics", "diplomacy"), ["politics", "diplomacy"]),
        ({"trade", "security"}, ["trade", "security"]),
        ("{}", []),
        ("invalid json", []),
        (None, []),
    ],
)
def test_json_values_accepts_supported_containers_and_rejects_invalid_data(value, expected):
    result = ObjectivesPanel._json_values(value)
    assert sorted(result) == sorted(expected)


def test_ruling_party_lookup_prefers_government_then_falls_back_to_party_table():
    government_state = SimpleNamespace(tables={
        "country_governments": pl.DataFrame({"country_id": ["ukr"], "ruling_party_id": ["GOV-PARTY"]}),
    })
    assert ObjectivesPanel._ruling_party_id(government_state, "UKR") == "GOV-PARTY"

    party_state = SimpleNamespace(tables={
        "country_governments": pl.DataFrame({"country_id": ["UKR"], "other": [1]}),
        "political_parties": pl.DataFrame({
            "country_id": ["POL", "UKR"], "party_id": ["P1", "P2"], "is_ruling": [True, True],
        }),
    })
    assert ObjectivesPanel._ruling_party_id(party_state, "UKR") == "P2"
    assert ObjectivesPanel._ruling_party_id(SimpleNamespace(tables={}), "UKR") == ""


@pytest.mark.parametrize(
    ("tables", "expected"),
    [
        ({}, []),
        ({"countries_treaties": pl.DataFrame({"id": ["S1"]})}, []),
        ({"countries_treaties": pl.DataFrame({
            "id": ["S2", "S1", "paused", "bad", "other"],
            "members": ['["UKR","POL"]', '["UKR"]', '["UKR"]', "not json", '["POL"]'],
            "status": ["active", "active", "paused", "active", "active"],
        })}, ["S1", "S2"]),
    ],
)
def test_active_treaty_scopes_parse_members_and_filter_inactive_or_invalid_rows(tables, expected):
    assert ObjectivesPanel._active_treaty_scopes(SimpleNamespace(tables=tables), "UKR") == expected


def test_send_delegation_emits_active_scope_action():
    client = FakeClient()

    ObjectivesPanel._send_delegation(
        panel_context(client=client), "UKR", "sphere", "S1", ["diplomacy"], ["treaty_membership"],
    )

    assert client.actions == [ActionSetSphereDelegation(
        player_id="player-1", country_tag="UKR", scope_type="sphere", scope_id="S1",
        delegate_id="ai", authority=["diplomacy"], priorities=["treaty_membership"], active=True,
    )]
