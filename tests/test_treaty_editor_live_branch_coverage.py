from contextlib import contextmanager
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.panels.politics.treaty_editor_live import LiveTreatyEditorPanel


class _Definition:
    def __init__(self, *, two_sided, multi_member, long_term):
        self.two_sided = two_sided
        self.multi_member = multi_member
        self.long_term = long_term
        self.description = "Treaty terms are authoritative."


class _ParticipantDialog:
    def __init__(self):
        self.is_open = False
        self.updated_sides = None
        self.open_calls = []

    def open(self, **kwargs):
        self.open_calls.append(kwargs)

    def render(self, _state):
        return self.updated_sides


class _FakeImgui:
    def __init__(self, *, buttons=(), checkbox_values=None, slider_values=None):
        self.buttons = set(buttons)
        self.checkbox_values = checkbox_values or {}
        self.slider_values = slider_values or {}
        self.calls = []

    def text_disabled(self, text):
        self.calls.append(("text_disabled", text))

    def input_text(self, label, value, *_args, **_kwargs):
        self.calls.append(("input_text", label, value))
        return False, value

    def input_text_multiline(self, label, value, *_args, **_kwargs):
        self.calls.append(("input_text_multiline", label, value))
        return False, value

    def get_content_region_avail(self):
        return SimpleNamespace(x=500.0)

    def text_wrapped(self, text):
        self.calls.append(("text_wrapped", text))

    def separator(self):
        self.calls.append(("separator",))

    def text(self, text):
        self.calls.append(("text", text))

    def button(self, label, _size, *, test_id):
        self.calls.append(("button", label, test_id))
        return test_id in self.buttons

    def checkbox(self, label, value):
        self.calls.append(("checkbox", label, value))
        return label in self.checkbox_values, self.checkbox_values.get(label, value)

    def slider_float(self, label, value, *_args):
        self.calls.append(("slider_float", label, value))
        return label in self.slider_values, self.slider_values.get(label, value)

    def begin_disabled(self, disabled):
        self.calls.append(("begin_disabled", disabled))

    def end_disabled(self):
        self.calls.append(("end_disabled",))


def _state(country_tags=("USA", "CAN", "MEX")):
    return SimpleNamespace(
        tables={
            "countries_treaties": None,
            "pending_treaties": None,
            "country_governments": None,
        },
        country_tags=list(country_tags),
    )


def _install(monkeypatch, *, imgui=None, window_open=True, child_open=True, tables_ready=True):
    module = import_module("src.client.ui.panels.politics.treaty_editor_live")
    window_calls = []
    imgui = imgui or _FakeImgui()

    @contextmanager
    def window(*args, **kwargs):
        window_calls.append((args, kwargs))
        yield window_open

    @contextmanager
    def child_frame(*args, **kwargs):
        yield child_open

    monkeypatch.setattr(module, "imgui", imgui)
    monkeypatch.setattr(module, "WindowManager", SimpleNamespace(window=window))
    monkeypatch.setattr(module, "gml_child_frame", child_frame)
    monkeypatch.setattr(module, "draw_required_tables", lambda *_args: tables_ready)
    monkeypatch.setattr(module, "active_country_tags", lambda state: state.country_tags)
    monkeypatch.setattr(
        module,
        "treaty_type_labels",
        lambda: (("alliance", "Alliance"), ("bilateral", "Bilateral")),
    )
    monkeypatch.setattr(
        module,
        "TREATY_DEFINITIONS",
        {
            "alliance": _Definition(two_sided=False, multi_member=True, long_term=True),
            "bilateral": _Definition(two_sided=True, multi_member=False, long_term=False),
        },
    )
    monkeypatch.setattr(
        module,
        "Prims",
        SimpleNamespace(combo_row=lambda _label, index, _options, _width: index),
    )
    monkeypatch.setattr(module, "country_diplomacy_restriction", lambda *_args: None)
    monkeypatch.setattr(module, "treaty_title_restriction", lambda *_args: None)
    monkeypatch.setattr(module, "TreatyParticipantDialog", _ParticipantDialog)
    return module, imgui, window_calls


def _context(*, own=True, client=True, sponsor="USA", notice=None):
    net_client = SimpleNamespace(player_id="player-1", send_action=Mock()) if client else None
    return PanelRenderContext(
        target_tag=sponsor,
        is_own_country=own,
        net_client=net_client,
        on_notice=notice,
    )


def test_prepare_and_render_respect_window_and_participant_lifecycle(monkeypatch):
    module, imgui, window_calls = _install(monkeypatch, window_open=False)
    panel = LiveTreatyEditorPanel()
    panel.prepare("USA", "CAN", "bilateral", invert_sides=True)
    panel._title = "old title"
    panel._terms = "old terms"

    assert panel.render(_state(), _context()) is False
    assert panel._sponsor_tag == ""
    assert panel._invert_sides is False
    assert panel._title == "old title"
    assert window_calls[0][1]["test_id"] == "treaty_proposal.panel"

    module, imgui, window_calls = _install(monkeypatch, child_open=False)
    panel = LiveTreatyEditorPanel()
    panel._participant_dialog.updated_sides = ({"USA"}, {"CAN"})
    assert panel.render(_state(), _context()) is True
    assert panel._participant_sides == ({"USA"}, {"CAN"})
    assert window_calls
    assert imgui.calls == []

    module, imgui, _ = _install(monkeypatch, tables_ready=False)
    panel = LiveTreatyEditorPanel()
    panel.render(_state(), _context())
    assert imgui.calls == []

    _, imgui, _ = _install(monkeypatch)
    panel = LiveTreatyEditorPanel()
    panel.render(_state(), _context(own=False, client=False))
    assert ("text_disabled", "Select your own country to sponsor a treaty proposal.") in imgui.calls


@pytest.mark.parametrize(
    "context,state,expected",
    [
        (_context(own=False), _state(), "Select your own country to sponsor a treaty proposal."),
        (_context(own=True, client=False), _state(), "Select your own country to sponsor a treaty proposal."),
        (_context(own=True), _state(("USA",)), "No eligible counterpart countries are available."),
    ],
)
def test_render_content_rejects_missing_sponsor_client_or_counterpart(
    monkeypatch, context, state, expected,
):
    _, imgui, _ = _install(monkeypatch)
    LiveTreatyEditorPanel()._render_content(state, context)

    assert ("text_disabled", expected) in imgui.calls


def test_render_content_builds_and_sends_long_term_multimember_proposal(monkeypatch):
    imgui = _FakeImgui(
        buttons={"treaty.proposal.edit_participants", "treaty.proposal.submit"},
        checkbox_values={
            "Open to eligible new members": True,
            "Allow members to be at war": True,
        },
        slider_values={
            "Minimum relation": 10.0,
            "Maximum distance (km)": 1500.0,
            "Max. military ratio": 2.0,
            "Max. economic ratio": 3.0,
            "Max. research ratio": 4.0,
        },
    )
    module, _, _ = _install(monkeypatch, imgui=imgui)
    context = _context()
    client = context.net_client
    panel = LiveTreatyEditorPanel()
    panel.prepare("USA", "CAN", "alliance")
    panel._terms = "  mutual defense  "
    panel._participant_sides = ({"USA"}, {"CAN", "MEX"})

    panel._render_content(_state(), context)

    dialog = panel._participant_dialog
    assert dialog.open_calls == [
        {
            "side_a": {"USA", "CAN", "MEX"},
            "side_b": set(),
            "two_sided": False,
            "protected_a": {"USA"},
            "protected_b": set(),
        }
    ]
    assert client.send_action.call_count == 1
    action = client.send_action.call_args.args[0]
    assert action.treaty_type == "alliance"
    assert action.source_country_tag == "USA"
    assert action.target_country_tag == "CAN"
    assert action.side_a_country_tags == ["CAN", "MEX", "USA"]
    assert action.side_b_country_tags == []
    assert action.member_country_tags == ["CAN", "MEX", "USA"]
    assert action.title == "USA Alliance"
    assert action.terms == "mutual defense"
    assert action.conditions == {
        "minimum_relation": 10.0,
        "maximum_geographic_distance_km": 1500.0,
        "max_military_strength_ratio": 2.0,
        "max_economic_strength_ratio": 3.0,
        "max_research_ratio": 4.0,
        "government_type": "",
        "allow_members_at_war": True,
    }
    assert action.open_to_new_members is True
    assert panel._terms == ""
    assert ("begin_disabled", False) in imgui.calls


def test_bilateral_proposal_inverts_sides_and_checks_restriction_notice(monkeypatch):
    imgui = _FakeImgui(buttons={"treaty.proposal.submit"})
    module, _, _ = _install(monkeypatch, imgui=imgui)
    panel = LiveTreatyEditorPanel()
    panel.prepare("USA", "CAN", "bilateral", invert_sides=True)
    context = _context()

    panel._render_content(_state(), context)

    action = context.net_client.send_action.call_args.args[0]
    assert action.side_a_country_tags == ["CAN"]
    assert action.side_b_country_tags == ["USA"]
    assert action.member_country_tags == ["CAN", "USA"]
    assert action.open_to_new_members is False

    notice = Mock()
    rejected_context = _context(notice=notice)
    monkeypatch.setattr(module, "country_diplomacy_restriction", lambda *_args: "No mandate")
    rejected = LiveTreatyEditorPanel()
    rejected._type_options = [("bilateral", "Bilateral")]
    rejected._type_index = 0
    rejected._title = "Existing proposal"
    rejected._render_content(_state(), rejected_context)

    notice.assert_called_once_with("Treaty proposal", "No mandate")
    rejected_context.net_client.send_action.assert_not_called()
    assert ("end_disabled",) in imgui.calls


def test_side_sync_preserves_extra_participants_and_reseeds_only_when_needed(monkeypatch):
    module, _, _ = _install(monkeypatch)
    panel = LiveTreatyEditorPanel()
    bilateral = module.TREATY_DEFINITIONS["bilateral"]
    panel._invert_sides = True
    panel._participant_sides = ({"USA", "MEX"}, {"CAN"})

    panel._sync_participant_sides("USA", "CAN", "bilateral", bilateral)
    assert panel._participant_sides == ({"CAN"}, {"MEX", "USA"})
    first_seed = panel._participant_seed
    panel._sync_participant_sides("USA", "CAN", "bilateral", bilateral)
    assert panel._participant_seed == first_seed
    assert panel._participant_sides == ({"CAN"}, {"MEX", "USA"})

    alliance = module.TREATY_DEFINITIONS["alliance"]
    panel._invert_sides = False
    panel._sync_participant_sides("USA", "CAN", "alliance", alliance)
    assert panel._participant_sides == ({"CAN", "MEX", "USA"}, set())


def test_country_tags_exclude_sponsor_and_empty_tags(monkeypatch):
    _install(monkeypatch)
    panel = LiveTreatyEditorPanel()
    assert panel._country_tags(_state(), "USA") == ["CAN", "MEX"]
