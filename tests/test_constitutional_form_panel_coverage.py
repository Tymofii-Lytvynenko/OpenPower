from contextlib import contextmanager
from types import SimpleNamespace

import polars as pl
import pytest

import src.client.ui.panels.politics.constitutional_form_panel as panel_module
from src.client.ui.components.shared.dirty_close_confirmation import CloseDecision
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.panels.politics.constitutional_form_panel import ConstitutionalFormPanel
from src.shared.actions import ActionSetCountryCapital, ActionSetGovernmentForm


def _state(tables=None, command_results=None):
    return SimpleNamespace(
        tables=tables or {},
        globals={},
        journal=SimpleNamespace(command_results=list(command_results or [])),
    )


def _summary(
    government_type="Democracy",
    martial_law=False,
    capital_name="Kyiv",
    next_election="2030-01-01",
):
    return SimpleNamespace(
        government_type=government_type,
        martial_law=martial_law,
        capital_name=capital_name,
        next_election=next_election,
    )


def _context(*, own=True, target="UKR", client=True, on_notice=None):
    actions = []
    net_client = (
        SimpleNamespace(player_id="player-1", send_action=actions.append)
        if client
        else None
    )
    return PanelRenderContext(
        target_tag=target,
        is_own_country=own,
        net_client=net_client,
        on_notice=on_notice,
    ), actions


def _government_tables(
    *, current_form="multi-party democracy", martial_law=False, crisis_status="none"
):
    return {
        "country_governments": pl.DataFrame(
            [
                {
                    "country_id": "UKR",
                    "capital_region_id": 1,
                    "government_form_id": current_form,
                    "government_type": "Democracy",
                    "martial_law": martial_law,
                    "crisis_status": crisis_status,
                }
            ]
        ),
        "government_form_rules": pl.DataFrame(
            [
                {
                    "government_form_id": "multi-party democracy",
                    "display_name": "Democracy",
                    "minimum_eligible_parties": 1,
                    "maximum_eligible_parties": 0,
                    "election_eligible": True,
                },
                {
                    "government_form_id": "coalition",
                    "display_name": "Coalition government",
                    "minimum_eligible_parties": 2,
                    "maximum_eligible_parties": 3,
                    "election_eligible": False,
                },
                {
                    "government_form_id": "military council",
                    "display_name": "Military Council",
                    "minimum_eligible_parties": 1,
                    "maximum_eligible_parties": 0,
                    "election_eligible": False,
                },
                {
                    "government_form_id": "single-party democracy",
                    "display_name": "Single-Party Democracy",
                    "minimum_eligible_parties": 1,
                    "maximum_eligible_parties": 1,
                    "election_eligible": True,
                },
            ]
        ),
        "political_parties": pl.DataFrame(
            [
                {"country_id": "UKR", "eligible": True},
                {"country_id": "UKR", "eligible": True},
            ]
        ),
        "regions": pl.DataFrame(
            [
                {"id": 1, "owner": "UKR", "controller": None, "name": "Kyiv"},
                {"id": 2, "owner": "UKR", "controller": None, "name": "Lviv"},
                {"id": 3, "owner": "POL", "controller": "UKR", "name": "Warsaw"},
                {"id": 4, "owner": "POL", "controller": "POL", "name": "Gdansk"},
            ]
        ),
    }


def _panel(tables=None, *, summary=None):
    panel = ConstitutionalFormPanel()
    view = summary or _summary()
    panel._presenter.build_summary = lambda _state, _country: view
    return panel


@pytest.mark.parametrize(
    ("tables", "expected"),
    [
        ({}, 0),
        ({"country_governments": pl.DataFrame({"id": ["UKR"]})}, 0),
        (
            {"country_governments": pl.DataFrame([{"country_id": "UKR", "capital_region_id": "bad"}])},
            0,
        ),
        (
            {
                "country_governments": pl.DataFrame(
                    [{"country_id": "ukr", "capital_region_id": "17"}]
                )
            },
            17,
        ),
    ],
)
def test_current_capital_id_handles_absent_malformed_and_normal_snapshots(tables, expected):
    assert ConstitutionalFormPanel._current_capital_id(_state(tables), "UKR") == expected


def test_capital_options_include_owned_and_controlled_regions_in_name_order():
    state = _state(_government_tables())

    options = ConstitutionalFormPanel._capital_options(state, "UKR", current_capital_id=1)

    assert options == [(1, "Kyiv"), (2, "Lviv"), (3, "Warsaw")]


def test_capital_options_skip_malformed_ids_and_require_region_columns(monkeypatch):
    monkeypatch.setattr(
        panel_module, "resolve_region_name", lambda _state, region_id: f"Region {region_id}"
    )
    malformed = pl.DataFrame(
        [
            {"id": "bad", "owner": "UKR", "name": "Bad"},
            {"id": 0, "owner": "UKR", "name": "Zero"},
            {"id": "2", "owner": "UKR", "name": "Lviv"},
        ]
    )
    assert ConstitutionalFormPanel._capital_options(
        _state({"regions": malformed}), "UKR", current_capital_id=0
    ) == [(2, "Region 2")]
    assert ConstitutionalFormPanel._capital_options(
        _state({"regions": pl.DataFrame({"id": [1]})}), "UKR", current_capital_id=0
    ) == []


def test_government_form_options_enforce_party_limits_and_keep_current_form():
    state = _state(_government_tables())

    options = ConstitutionalFormPanel._government_form_options(
        state, "UKR", "multi-party democracy", "Democracy"
    )

    assert options == [
        ("coalition", "Coalition government"),
        ("multi-party democracy", "Democracy"),
        ("military council", "Military Council"),
    ]


@pytest.mark.parametrize("crisis_status", ["pending", "active", "open", "escalated"])
def test_government_form_options_block_alternatives_during_country_crisis(crisis_status):
    tables = _government_tables()
    tables["political_crises"] = pl.DataFrame(
        [{"country_id": "ukr", "status": crisis_status}]
    )

    options = ConstitutionalFormPanel._government_form_options(
        _state(tables), "UKR", "multi-party democracy", "Democracy"
    )

    assert options == [("multi-party democracy", "Democracy")]


def test_government_form_options_keep_legacy_current_label_when_supporting_tables_are_missing():
    assert ConstitutionalFormPanel._government_form_options(
        _state(), "UKR", "legacy", "Legacy Republic"
    ) == [("legacy", "Legacy Republic")]


def test_government_form_options_fall_back_when_country_has_no_parties_or_government():
    tables = _government_tables()
    tables["political_parties"] = pl.DataFrame(
        schema={"country_id": pl.String, "eligible": pl.Boolean}
    )

    assert ConstitutionalFormPanel._government_form_options(
        _state(tables), "UKR", "legacy", "Legacy Republic"
    ) == [("legacy", "Legacy Republic")]


@pytest.mark.parametrize(
    ("tables", "label", "expected"),
    [
        ({}, "Transitional Republic", "transitional republic"),
        (
            {"country_governments": pl.DataFrame([{"country_id": "UKR", "government_form_id": "custom-id"}])},
            "Democracy",
            "custom-id",
        ),
        (
            {
                "country_governments": pl.DataFrame(
                    [{"country_id": "UKR", "government_type": "Democracy"}]
                ),
                "government_form_rules": pl.DataFrame(
                    [{"government_form_id": "multi-party democracy", "display_name": "Democracy"}]
                ),
            },
            "Democracy",
            "multi-party democracy",
        ),
    ],
)
def test_current_government_form_id_resolves_direct_and_legacy_labels(tables, label, expected):
    assert ConstitutionalFormPanel._current_government_form_id(
        _state(tables), "UKR", label
    ) == expected


def test_form_display_name_and_election_eligibility_use_rules_with_safe_fallbacks():
    state = _state(_government_tables())

    assert ConstitutionalFormPanel._form_display_name(state, "COALITION") == "Coalition government"
    assert ConstitutionalFormPanel._form_display_name(state, "missing") == "missing"
    assert ConstitutionalFormPanel._is_election_eligible_form(
        state, "multi-party democracy"
    )
    assert not ConstitutionalFormPanel._is_election_eligible_form(state, "coalition")
    assert not ConstitutionalFormPanel._is_election_eligible_form(_state(), "unknown")


@pytest.mark.parametrize(
    ("options", "current", "expected"),
    [
        (["one", "two"], "TWO", 1),
        (["one", "two"], "missing", 0),
        ([], "missing", 0),
    ],
)
def test_selected_form_index_is_case_insensitive_and_defaults_to_first(options, current, expected):
    assert ConstitutionalFormPanel._selected_form_index(options, current) == expected


def test_military_override_requires_one_unique_alternative():
    options = [
        ("multi-party democracy", "Democracy"),
        ("military council", "Military Council"),
    ]
    assert ConstitutionalFormPanel._military_override_form(
        options, "multi-party democracy"
    ) == ("military council", "Military Council")
    assert ConstitutionalFormPanel._military_override_form(options[:1], options[0][0]) is None
    assert ConstitutionalFormPanel._military_override_form(
        options + [("military junta", "Military Junta")], options[0][0]
    ) is None


def test_stage_government_form_preserves_expected_form_and_clears_non_military_law():
    panel = ConstitutionalFormPanel()

    assert not panel._stage_government_form("current", " ")
    assert panel._stage_government_form("current", "coalition")
    assert panel._expected_government_form_id == "current"
    assert panel._pending_government_form_id == "coalition"
    assert panel._pending_martial_law is False
    panel._stage_government_form("current", "military council", "Military Council")
    assert panel._expected_government_form_id == "current"
    assert panel._pending_martial_law is False
    panel._stage_government_form("current", "CURRENT")
    assert panel._pending_government_form_id is None
    assert panel._expected_government_form_id is None


@pytest.mark.parametrize(
    ("pending_capital", "pending_form", "submitted", "expected"),
    [
        (None, None, None, False),
        (2, None, None, True),
        (1, None, None, False),
        (None, "coalition", None, True),
        (None, "coalition", "coalition", False),
    ],
)
def test_pending_change_detection_ignores_confirmed_submission(
    pending_capital, pending_form, submitted, expected
):
    panel = _panel()
    panel._pending_capital_region_id = pending_capital
    panel._pending_government_form_id = pending_form
    panel._submitted_government_form_id = submitted
    panel._submitted_form_country = "UKR"
    state = _state(_government_tables())

    assert panel._has_pending_change(state, "UKR") is expected


def test_apply_changes_sends_capital_and_form_actions_with_expected_state():
    panel = _panel()
    panel._draft_country = "ukr"
    panel._pending_capital_region_id = 2
    panel._pending_government_form_id = "coalition"
    panel._expected_government_form_id = "custom-expected"
    panel._pending_martial_law = False
    context, actions = _context()
    state = _state(_government_tables())

    assert panel._apply_changes(state, context) == ""

    capital, government = actions
    assert isinstance(capital, ActionSetCountryCapital)
    assert (capital.country_tag, capital.expected_capital_region_id, capital.target_region_id) == (
        "UKR",
        1,
        2,
    )
    assert isinstance(government, ActionSetGovernmentForm)
    assert government.expected_form_id == "custom-expected"
    assert government.target_form_id == "coalition"
    assert government.expected_martial_law is False
    assert panel._submitted_form_country == "UKR"
    assert panel._pending_capital_region_id is None


def test_apply_changes_clears_noop_and_reports_missing_network_client():
    panel = _panel()
    panel._draft_country = "UKR"
    panel._pending_government_form_id = "multi-party democracy"
    panel._pending_capital_region_id = 1
    no_client, _ = _context(client=False)
    state = _state(_government_tables())

    assert panel._apply_changes(state, no_client) == ""
    assert panel._pending_government_form_id is None
    panel._pending_government_form_id = "coalition"
    assert panel._apply_changes(state, no_client) == (
        "Connect to a game session before applying constitutional changes."
    )


def test_foreign_apply_waits_for_confirmation_then_sends_confirmed_form_action():
    panel = _panel()
    panel._draft_country = "UKR"
    panel._pending_government_form_id = "coalition"
    panel._expected_government_form_id = "multi-party democracy"
    context, actions = _context(own=False)
    state = _state(_government_tables())
    confirmation = {}

    class Question:
        def show(self, _message, on_confirm, on_cancel):
            confirmation["confirm"] = on_confirm
            confirmation["cancel"] = on_cancel
            return True

    panel._foreign_question = Question()
    panel._foreign_change_tooltip = lambda *_args: ""
    panel._can_edit_form = lambda *_args: True

    assert panel._request_apply(state, context) == ""
    assert actions == []
    confirmation["confirm"]()

    assert len(actions) == 1
    assert isinstance(actions[0], ActionSetGovernmentForm)
    assert actions[0].confirmed_foreign_change is True


def test_foreign_changes_cannot_change_capital_even_after_confirmation():
    panel = _panel()
    panel._draft_country = "UKR"
    panel._pending_capital_region_id = 2
    panel._foreign_change_tooltip = lambda *_args: ""
    context, actions = _context(own=False)

    assert panel._apply_changes(
        _state(_government_tables()), context, confirmed_foreign_change=True
    ) == "Foreign constitutional changes can only change the government form."
    assert actions == []


def test_submission_reconciliation_clears_confirmed_change_and_reports_rejection():
    notices = []
    panel = _panel(summary=_summary(government_type="Coalition government"))
    panel._submitted_government_form_id = "coalition"
    panel._submitted_expected_form_id = "multi-party democracy"
    panel._submitted_target_martial_law = False
    panel._submitted_expected_martial_law = False
    panel._submitted_form_country = "UKR"
    panel._pending_government_form_id = "coalition"
    context, _ = _context(on_notice=lambda *args, **kwargs: notices.append((args, kwargs)))
    confirmed = _state(_government_tables(current_form="coalition"))

    panel._reconcile_government_form_submission(confirmed, context, "UKR")

    assert panel._submitted_government_form_id is None
    assert panel._pending_government_form_id is None
    assert notices == []

    panel._submitted_government_form_id = "coalition"
    panel._submitted_expected_form_id = "multi-party democracy"
    panel._submitted_target_martial_law = False
    panel._submitted_expected_martial_law = False
    panel._submitted_form_country = "UKR"
    panel._pending_government_form_id = "coalition"
    rejected = _state(
        _government_tables(),
        [
            {
                "action_type": "ActionSetGovernmentForm",
                "country_id": "UKR",
                "target_form_id": "coalition",
                "target_martial_law": False,
                "status": "rejected",
                "reason": "A coalition is not eligible.",
            }
        ],
    )

    panel._reconcile_government_form_submission(rejected, context, "UKR")

    assert panel._submitted_government_form_id is None
    assert notices[-1][0][1] == "A coalition is not eligible."


class _RecordingWidgets:
    combo_results = {}
    button_results = {}
    last = None

    def __init__(self, _layout):
        self.calls = []
        type(self).last = self

    def frame(self, path):
        self.calls.append(("frame", path))

    def text(self, path, value):
        self.calls.append(("text", path, value))

    def combo_at(self, path, _label, selected, values, test_id, **kwargs):
        self.calls.append(("combo", test_id, selected, tuple(values), kwargs))
        return type(self).combo_results.get(test_id, (False, selected))

    def button(self, _path, _label, test_id, **kwargs):
        self.calls.append(("button", test_id, kwargs))
        return type(self).button_results.get(test_id, False)


@pytest.fixture
def render_widgets(monkeypatch):
    _RecordingWidgets.combo_results = {}
    _RecordingWidgets.button_results = {}
    monkeypatch.setattr(panel_module, "GMLWidgets", _RecordingWidgets)
    return _RecordingWidgets


def test_render_content_stages_form_and_capital_selected_in_controls(render_widgets):
    panel = _panel(summary=_summary())
    context, _ = _context()
    state = _state(_government_tables())
    render_widgets.combo_results = {
        "constitutional_form.government_form": (True, 0),
        "constitutional_form.capital": (True, 1),
    }

    panel._render_content(state, context)

    assert panel._pending_government_form_id == "coalition"
    assert panel._pending_capital_region_id == 2
    apply_call = next(
        call for call in render_widgets.last.calls
        if call[:2] == ("button", "constitutional_form.apply")
    )
    assert apply_call[2]["enabled"] is True


def test_render_content_electoral_override_stages_the_unique_military_successor(render_widgets):
    panel = _panel(summary=_summary())
    context, _ = _context()
    state = _state(_government_tables())
    render_widgets.button_results = {"constitutional_form.override": True}

    panel._render_content(state, context)

    assert panel._pending_government_form_id == "military council"
    override_call = next(
        call for call in render_widgets.last.calls
        if call[:2] == ("button", "constitutional_form.override")
    )
    assert override_call[2]["enabled"] is True


def test_render_content_disables_controls_without_a_network_client(render_widgets):
    panel = _panel(summary=_summary())
    context, _ = _context(client=False)
    state = _state(_government_tables())

    panel._render_content(state, context)

    apply_call = next(
        call for call in render_widgets.last.calls
        if call[:2] == ("button", "constitutional_form.apply")
    )
    assert apply_call[2]["enabled"] is False
    assert apply_call[2]["tooltip"] == (
        "Connect to a game session before applying constitutional changes."
    )


def test_render_closed_clean_panel_returns_false_without_prompt(monkeypatch):
    panel = _panel(summary=_summary())

    @contextmanager
    def closed_window(*_args, **_kwargs):
        yield False

    monkeypatch.setattr(panel_module.WindowManager, "window", closed_window)
    panel._notice.render = lambda: None
    context, _ = _context()

    assert panel.render(_state(), context) is False


def test_clear_pending_changes_resets_all_staged_values():
    panel = ConstitutionalFormPanel()
    panel._pending_capital_region_id = 4
    panel._pending_government_form_id = "coalition"
    panel._expected_government_form_id = "multi-party democracy"
    panel._pending_martial_law = True

    panel._clear_pending_changes()

    assert panel._pending_capital_region_id is None
    assert panel._pending_government_form_id is None
    assert panel._expected_government_form_id is None
    assert panel._pending_martial_law is None


def test_clear_submission_resets_acknowledgement_cursor():
    panel = ConstitutionalFormPanel()
    panel._submitted_government_form_id = "coalition"
    panel._submitted_expected_form_id = "multi-party democracy"
    panel._submitted_target_martial_law = True
    panel._submitted_expected_martial_law = False
    panel._submitted_form_country = "UKR"
    panel._submitted_result_start = 19

    panel._clear_government_form_submission()

    assert panel._submitted_government_form_id is None
    assert panel._submitted_expected_form_id is None
    assert panel._submitted_target_martial_law is None
    assert panel._submitted_expected_martial_law is None
    assert panel._submitted_form_country == ""
    assert panel._submitted_result_start == 0


def test_legacy_form_fallbacks_and_notice_queue_cover_incomplete_snapshots():
    tables = _government_tables()
    rules = tables["government_form_rules"]
    tables["government_form_rules"] = pl.concat(
        [
            rules,
            pl.DataFrame(
                [{
                    "government_form_id": "",
                    "display_name": "",
                    "minimum_eligible_parties": 1,
                    "maximum_eligible_parties": 0,
                    "election_eligible": True,
                }],
                schema=rules.schema,
            ),
        ]
    )
    options = ConstitutionalFormPanel._government_form_options(
        _state(tables), "UKR", "multi-party democracy", "Democracy"
    )
    assert all(form_id for form_id, _ in options)

    legacy_options = ConstitutionalFormPanel._government_form_options(
        _state(_government_tables()), "UKR", "legacy-form", "Legacy Republic"
    )
    assert ("legacy-form", "Legacy Republic") in legacy_options
    assert ConstitutionalFormPanel._current_government_form_id(
        _state({"country_governments": pl.DataFrame([{"country_id": "POL"}])}),
        "UKR",
        "Legacy Democracy",
    ) == "legacy democracy"
    assert ConstitutionalFormPanel._current_government_form_id(
        _state({
            "country_governments": pl.DataFrame(
                [{"country_id": "UKR", "government_type": "Historical Republic"}]
            ),
            "government_form_rules": pl.DataFrame(
                [{"government_form_id": "other", "display_name": "Other"}]
            ),
        }),
        "UKR",
        "Democracy",
    ) == "historical republic"

    panel = ConstitutionalFormPanel()
    queued = []
    panel._notice = SimpleNamespace(enqueue=lambda *args, **kwargs: queued.append((args, kwargs)))
    context, _ = _context()
    panel._notify(context, "Review the staged form.")
    assert queued[0][0][1] == "Review the staged form."


def test_render_returns_early_for_an_open_foreign_confirmation():
    panel = _panel()
    calls = []
    panel._foreign_question = SimpleNamespace(is_open=True, render=lambda: calls.append("question"))
    panel._notice = SimpleNamespace(render=lambda: calls.append("notice"))
    context, _ = _context()

    assert panel.render(_state(), context) is True
    assert calls == ["question", "notice"]


def test_render_open_panel_draws_content(monkeypatch):
    panel = _panel()
    panel._draft_country = "UKR"
    calls = []
    panel._render_content = lambda _state, _context: calls.append("content")
    panel._foreign_question = SimpleNamespace(is_open=False, render=lambda: calls.append("question"))
    panel._notice = SimpleNamespace(render=lambda: calls.append("notice"))
    panel._close_confirmation = SimpleNamespace(pending=False, render=lambda *_args, **_kwargs: None)
    context, _ = _context()

    @contextmanager
    def open_window(*_args, **_kwargs):
        yield True

    monkeypatch.setattr(panel_module.WindowManager, "window", open_window)

    assert panel.render(_state(), context) is True
    assert calls == ["content", "question", "notice"]


@pytest.mark.parametrize(
    ("decision", "expected"),
    [(None, True), (CloseDecision.DISCARD, False), (CloseDecision.APPLY, False)],
)
def test_render_handles_dirty_close_wait_discard_and_apply(decision, expected, monkeypatch):
    panel = _panel()
    panel._draft_country = "UKR"
    panel._pending_government_form_id = "coalition"
    panel._close_confirmation = SimpleNamespace(
        pending=False,
        request_close=lambda *_args, **_kwargs: decision,
        render=lambda *_args, **_kwargs: None,
    )
    panel._foreign_question = SimpleNamespace(is_open=False, render=lambda: None)
    panel._notice = SimpleNamespace(render=lambda: None)
    panel._request_apply = lambda *_args: ""
    context, _ = _context()

    @contextmanager
    def closed_window(*_args, **_kwargs):
        yield False

    monkeypatch.setattr(panel_module.WindowManager, "window", closed_window)

    assert panel.render(_state(_government_tables()), context) is expected
    if decision is CloseDecision.DISCARD:
        assert panel._pending_government_form_id is None


@pytest.mark.parametrize("outcome", ["foreign-question", "reason"])
def test_render_keeps_dirty_close_open_for_confirmation_or_apply_errors(outcome, monkeypatch):
    notices = []
    panel = _panel()
    panel._draft_country = "UKR"
    panel._pending_government_form_id = "coalition"
    panel._close_confirmation = SimpleNamespace(
        pending=False,
        request_close=lambda *_args, **_kwargs: CloseDecision.APPLY,
        render=lambda *_args, **_kwargs: None,
    )
    panel._foreign_question = SimpleNamespace(is_open=False, render=lambda: None)
    panel._notice = SimpleNamespace(render=lambda: None)
    context, _ = _context(on_notice=lambda *args, **kwargs: notices.append((args, kwargs)))

    def request_apply(*_args):
        if outcome == "foreign-question":
            panel._foreign_question.is_open = True
            return ""
        return "The staged form was rejected."

    panel._request_apply = request_apply

    @contextmanager
    def closed_window(*_args, **_kwargs):
        yield False

    monkeypatch.setattr(panel_module.WindowManager, "window", closed_window)

    assert panel.render(_state(_government_tables()), context) is True
    if outcome == "reason":
        assert notices[0][0][1] == "The staged form was rejected."


def test_render_content_keeps_legacy_capital_and_pending_form_options(render_widgets):
    tables = _government_tables()
    tables["regions"] = pl.DataFrame(
        [{"id": 2, "owner": "POL", "controller": "POL", "name": "Gdansk"}]
    )
    panel = _panel()
    panel._pending_government_form_id = "legacy-form"
    context, _ = _context()

    panel._render_content(_state(tables), context)

    form_call = next(
        call for call in render_widgets.last.calls
        if call[:2] == ("combo", "constitutional_form.government_form")
    )
    capital_call = next(
        call for call in render_widgets.last.calls
        if call[:2] == ("combo", "constitutional_form.capital")
    )
    assert "legacy-form" in form_call[3]
    assert "Kyiv" in capital_call[3]


@pytest.mark.parametrize(
    ("case", "expected_tooltip"),
    [
        ("martial-law", "End martial law before using Override."),
        ("foreign", "Override is available only for your country."),
        ("no-election", "The current government form has no scheduled election."),
        ("non-electoral-id", "Override is available for single-party and multi-party democracies."),
        ("no-successor", "No unique eligible military-led successor is defined by the current rules."),
    ],
)
def test_render_content_explains_each_disabled_override_state(case, expected_tooltip, render_widgets):
    tables = _government_tables()
    summary = _summary()
    context, _ = _context()
    if case == "martial-law":
        summary = _summary(martial_law=True)
    elif case == "foreign":
        context, _ = _context(own=False)
    elif case == "no-election":
        tables = _government_tables(current_form="coalition")
        summary = _summary(government_type="Coalition government")
    elif case == "non-electoral-id":
        tables = _government_tables(current_form="coalition")
        tables["government_form_rules"] = tables["government_form_rules"].with_columns(
            pl.when(pl.col("government_form_id") == "coalition")
            .then(pl.lit(True))
            .otherwise(pl.col("election_eligible"))
            .alias("election_eligible")
        )
        summary = _summary(government_type="Coalition government")
    elif case == "no-successor":
        tables["government_form_rules"] = tables["government_form_rules"].filter(
            pl.col("government_form_id") != "military council"
        )

    panel = _panel(summary=summary)
    panel._render_content(_state(tables), context)

    override_call = next(
        call for call in render_widgets.last.calls
        if call[:2] == ("button", "constitutional_form.override")
    )
    assert override_call[2]["tooltip"] == expected_tooltip


def test_render_content_stages_martial_law_and_reports_apply_feedback(render_widgets):
    notices = []
    panel = _panel()
    context, _ = _context(on_notice=lambda *args, **kwargs: notices.append((args, kwargs)))
    panel._request_apply = lambda *_args: "A current rule blocks this change."
    render_widgets.button_results = {
        "constitutional_form.martial_law": True,
        "constitutional_form.apply": True,
    }

    panel._render_content(_state(_government_tables()), context)

    assert panel._pending_martial_law is True
    assert notices[0][0][1] == "A current rule blocks this change."


def test_render_content_distinguishes_missing_session_from_no_staged_change(render_widgets):
    panel = _panel()
    no_client, _ = _context(client=False)
    panel._can_edit_form = lambda *_args: True
    panel._render_content(_state(_government_tables()), no_client)
    apply_call = next(
        call for call in render_widgets.last.calls
        if call[:2] == ("button", "constitutional_form.apply")
    )
    assert apply_call[2]["tooltip"] == "Connect to a game session before applying constitutional changes."

    panel = _panel()
    context, _ = _context()
    panel._render_content(_state(_government_tables()), context)
    apply_call = next(
        call for call in render_widgets.last.calls
        if call[:2] == ("button", "constitutional_form.apply")
    )
    assert apply_call[2]["tooltip"] == "Choose a government form, capital region, or martial-law status to apply."


def test_apply_request_and_foreign_confirmation_cover_restriction_paths():
    panel = _panel()
    state = _state(_government_tables())
    no_client, _ = _context(client=False)
    assert panel._request_apply(state, no_client).startswith("Connect to a game session")

    foreign, _ = _context(own=False)
    panel._can_edit_form = lambda *_args: False
    panel._foreign_change_tooltip = lambda *_args: "The issuer cannot change this government."
    assert panel._request_apply(state, foreign) == "The issuer cannot change this government."
    panel._can_edit_form = lambda *_args: True
    panel._foreign_question = SimpleNamespace(show=lambda *_args: False)
    assert panel._request_apply(state, foreign) == "A foreign constitutional change is already awaiting confirmation."

    own, actions = _context()
    panel._apply_changes = lambda *_args, **_kwargs: "Applied through the local client."
    assert panel._request_apply(state, own) == "Applied through the local client."
    assert actions == []

    notices = []
    panel._apply_changes = lambda *_args, **_kwargs: "The foreign form is no longer eligible."
    panel._notify = lambda _context, reason: notices.append(reason)
    panel._apply_confirmed_foreign_change(state, foreign)
    assert notices == ["The foreign form is no longer eligible."]


def test_apply_changes_restricts_foreign_edits_and_clears_capital_only_state():
    panel = _panel()
    panel._draft_country = "UKR"
    panel._pending_government_form_id = "coalition"
    foreign, _ = _context(own=False)
    state = _state(_government_tables())
    panel._foreign_change_tooltip = lambda *_args: "Foreign government edits are restricted."
    assert panel._apply_changes(state, foreign, confirmed_foreign_change=True) == (
        "Foreign government edits are restricted."
    )
    panel._foreign_change_tooltip = lambda *_args: ""
    assert panel._apply_changes(state, foreign) == (
        "Confirm this foreign government-form change before applying it."
    )

    panel = _panel()
    panel._draft_country = "UKR"
    panel._pending_capital_region_id = 2
    panel._pending_government_form_id = "multi-party democracy"
    panel._expected_government_form_id = "multi-party democracy"
    own, actions = _context()
    assert panel._apply_changes(_state(_government_tables()), own) == ""
    assert len(actions) == 1 and isinstance(actions[0], ActionSetCountryCapital)
    assert panel._pending_government_form_id is None
    assert panel._expected_government_form_id is None


def test_foreign_authority_helpers_and_changed_submission_reconciliation():
    notices = []
    panel = _panel()
    state = _state(_government_tables())
    foreign, _ = _context(own=False, on_notice=lambda *args, **kwargs: notices.append((args, kwargs)))
    assert not panel._can_edit_form(state, foreign)
    assert panel._foreign_change_tooltip(state, foreign)

    for current_form, martial_law, expected_notice in (
        ("single-party democracy", False, "government form changed"),
        ("multi-party democracy", True, "Martial law changed"),
    ):
        panel = _panel(summary=_summary(martial_law=martial_law))
        panel._submitted_government_form_id = "coalition"
        panel._submitted_expected_form_id = "multi-party democracy"
        panel._submitted_target_martial_law = False
        panel._submitted_expected_martial_law = False
        panel._submitted_form_country = "UKR"
        context, _ = _context(on_notice=lambda *args, **kwargs: notices.append((args, kwargs)))
        panel._reconcile_government_form_submission(
            _state(_government_tables(current_form=current_form)), context, "UKR"
        )
        assert panel._submitted_government_form_id is None
        assert expected_notice.casefold() in notices[-1][0][1].casefold()
