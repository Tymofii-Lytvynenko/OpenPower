from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import polars as pl
import pytest

import src.client.ui.panels.politics.identity_policy_view as view_module
from src.client.ui.core.containers import WindowManager
from src.client.ui.panels.politics.identity_policy_view import IdentityPolicyView


def profile_rows():
    return [
        {
            "country_id": "USA", "identity_type": "language", "identity_id": "en",
            "display_name": "English", "population_share": 70.0, "legal_status": "legal",
            "is_other_bucket": False, "source_year": 2024, "source_reference": "Census",
            "source_note": "Normalized source data",
        },
        {
            "country_id": "USA", "identity_type": "language", "identity_id": "other",
            "display_name": "Other", "population_share": 30.0, "legal_status": "official",
            "is_other_bucket": True, "source_year": None, "source_reference": None,
            "source_note": None,
        },
    ]


def context(*, own=True, client=None, on_notice=None):
    return SimpleNamespace(
        target_tag=" usa ",
        is_own_country=own,
        net_client=client,
        on_notice=on_notice,
    )


class Client:
    player_id = "player-1"

    def __init__(self):
        self.actions = []

    def send_action(self, action):
        self.actions.append(action)


class GmlRow:
    def __init__(self, *, hit=False):
        self.hit = hit
        self.text = Mock()

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def hitbox(self, *_args, **_kwargs):
        return self.hit

    def path(self, value):
        return value


def setup_imgui(monkeypatch, *, combo=None, details=None, tabs=None, hovered=True):
    imgui = Mock()
    imgui.TableFlags_.row_bg = 1
    imgui.TableColumnFlags_.width_stretch = 2
    imgui.TableColumnFlags_.width_fixed = 3
    imgui.HoveredFlags_.allow_when_disabled = 4
    imgui.begin_table.return_value = True
    imgui.combo.side_effect = combo or (lambda *_args, **_kwargs: (False, 1))
    imgui.small_button.side_effect = details or (lambda *_args, **_kwargs: False)
    imgui.button.side_effect = tabs or (lambda *_args, **_kwargs: False)
    imgui.is_item_hovered.return_value = hovered
    monkeypatch.setattr(view_module, "imgui", imgui)
    monkeypatch.setattr(view_module.Prims, "header", Mock())
    monkeypatch.setattr(view_module, "draw_empty_state", Mock())
    return imgui


def test_full_render_sorts_rows_dispatches_policy_and_shows_details_and_result(monkeypatch):
    answers = iter([(True, 2), (True, 3)])
    detail_answers = iter([False, True])
    imgui = setup_imgui(
        monkeypatch,
        combo=lambda *_args, **_kwargs: next(answers),
        details=lambda *_args, **_kwargs: next(detail_answers),
    )
    client = Client()
    state = SimpleNamespace(
        tables={"country_identity_groups": pl.DataFrame(profile_rows())},
        journal=SimpleNamespace(command_results=[{
            "player_id": client.player_id,
            "action_type": "ActionSetCountryIdentityPolicy",
            "status": "accepted",
            "reason": "Policy updated",
        }]),
    )
    view = IdentityPolicyView(notice=Mock())

    view.render(state, context(client=client))

    assert imgui.begin_table.called
    assert client.actions[0].country_tag == "USA"
    assert client.actions[0].identity_id == "en"
    assert client.actions[0].status == "restricted"
    assert imgui.set_tooltip.call_count == 2
    assert view._details_key == ("USA", "language", "other")
    assert any("Other combines unspecified groups" in call.args[0] for call in imgui.text_wrapped.call_args_list)
    assert any("Latest policy result" in call.args[0] for call in imgui.text_wrapped.call_args_list)


def test_compact_render_uses_gml_rows_and_keeps_details_for_notice_window(monkeypatch):
    answers = iter([(True, 2), (False, 1)])
    imgui = setup_imgui(monkeypatch, combo=lambda *_args, **_kwargs: next(answers), hovered=True)
    rows = profile_rows()
    client = Client()
    row_context = context(client=client)
    monkeypatch.setattr(
        view_module,
        "gml_row",
        lambda *_args, **_kwargs: GmlRow(hit=str(_args[1]).endswith(".en")),
    )
    view = IdentityPolicyView(notice=Mock())
    state = SimpleNamespace(tables={"country_identity_groups": pl.DataFrame(rows)})

    view.render(state, row_context, compact=True)

    assert view._details_row["identity_id"] == "en"
    assert client.actions[0].identity_id == "en"
    assert imgui.begin_table.called is False
    assert imgui.text_disabled.called is False

    opened = False

    @contextmanager
    def window(*_args, **_kwargs):
        yield opened

    monkeypatch.setattr(WindowManager, "window", window)
    view.render_notices()
    assert view._details_row is None
    assert view._details_key is None

    opened = True
    view._details_row = rows[0]
    view.render_notices()
    assert imgui.text_wrapped.call_count >= 2
    view._notice.render.assert_called()


def test_render_handles_no_profile_read_only_mode_and_a_closed_table(monkeypatch):
    imgui = setup_imgui(monkeypatch)
    imgui.begin_table.return_value = False
    state = SimpleNamespace(tables={"country_identity_groups": pl.DataFrame(profile_rows())})
    view = IdentityPolicyView(notice=Mock())

    view.render(state, context(own=False))
    assert any("Viewing another country" in call.args[0] for call in imgui.text_disabled.call_args_list)

    view.render(SimpleNamespace(tables={}), context(own=False))
    view_module.draw_empty_state.assert_called_once_with("No language profile is available for USA.")


def test_tabs_support_imgui_and_gml_controls(monkeypatch):
    answers = iter([True, True])
    imgui = setup_imgui(monkeypatch, tabs=lambda *_args, **_kwargs: next(answers))
    view = IdentityPolicyView()
    view._details_key = ("USA", "language", "en")

    view.render_tabs()

    assert view.identity_type == "language"
    assert view._details_key is None
    imgui.same_line.assert_called_once()

    ui = SimpleNamespace(button_at=Mock(side_effect=[True, True]))
    view.render_tabs(ui)
    assert ui.button_at.call_count == 2
    assert view.identity_type == "language"


def test_policy_requests_validate_control_drafts_and_recognition_rules():
    notice = Mock()
    view = IdentityPolicyView(notice=notice)
    client = Client()
    own_context = context(client=client)
    rows = profile_rows()

    assert view.request_policy(rows, rows[0], "official", context(own=False, client=client)) is False
    assert view.request_policy(rows, rows[0], "official", context()) is False
    assert view.request_policy(rows, rows[1], "illegal", own_context) is False

    callback = Mock()
    assert view.request_policy([rows[0]], rows[0], "illegal", context(client=client, on_notice=callback)) is False
    callback.assert_called_once()

    draft = Mock()
    draft.choose.return_value = "choose a valid replacement"
    view = IdentityPolicyView(notice=notice, draft=draft)
    assert view.request_policy(rows, rows[0], "restricted", own_context) is False
    notice.enqueue.assert_called_once_with("Internal laws", "choose a valid replacement", severity="warning")

    draft.choose.return_value = ""
    assert view.request_policy(rows, rows[0], "restricted", own_context) is True
    assert draft.choose.call_count == 2

    view = IdentityPolicyView(notice=notice)
    assert view.request_policy(rows, rows[0], "restricted", own_context) is True
    assert client.actions[-1].identity_type == "language"


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, 0.0), ("bad", 0.0), (float("inf"), 0.0), (-2, 0.0), (120, 100.0), (30, 30.0)],
)
def test_share_values_are_finite_and_clamped(value, expected):
    assert IdentityPolicyView._share(value) == expected
