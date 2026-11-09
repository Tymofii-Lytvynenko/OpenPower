from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock, call

import src.client.ui.panels.politics.internal_laws_panel as laws_module
from src.client.ui.components.shared.dirty_close_confirmation import CloseDecision
from src.client.ui.panels.politics.internal_laws_panel import InternalLawsPanel


def _imgui_mock(monkeypatch):
    imgui = Mock()
    imgui.StyleVar_.cell_padding = 1
    imgui.StyleVar_.frame_padding = 2
    imgui.HoveredFlags_.allow_when_disabled = 1
    monkeypatch.setattr(laws_module, "imgui", imgui)
    return imgui


def test_apply_drafts_preflights_every_draft_before_sending():
    panel = InternalLawsPanel()
    law_action, identity_action, party_action = object(), object(), object()
    panel._law_draft = SimpleNamespace(
        pending={"law": 1}, prepare=Mock(return_value=([], "stale law")),
    )
    panel._identity_draft = SimpleNamespace(pending={"identity": 1}, prepare=Mock())
    panel._party_draft = SimpleNamespace(pending={"party": 1}, prepare=Mock())
    client = Mock()
    context = SimpleNamespace(net_client=client)

    assert panel._apply_drafts(SimpleNamespace(), context) == "stale law"
    panel._identity_draft.prepare.assert_not_called()
    client.send_action.assert_not_called()

    panel._law_draft.pending.clear()
    panel._law_draft.prepare.return_value = ([law_action], "")
    panel._identity_draft.prepare.return_value = ([identity_action], "")
    panel._party_draft.prepare.return_value = ([party_action], "")

    assert panel._apply_drafts(SimpleNamespace(), context) == ""
    assert client.send_action.call_args_list == [
        call(law_action), call(identity_action), call(party_action),
    ]
    assert panel._law_draft.pending == {}
    assert panel._identity_draft.pending == {}
    assert panel._party_draft.pending == {}


def test_choose_party_restores_rejected_drafts_and_notifies_stale_confirmation():
    panel = InternalLawsPanel()
    panel._party_draft = Mock()
    panel._party_draft.checkpoint.return_value = "previous"
    panel._party_draft.transition_target.return_value = None
    panel._party_question = Mock()
    context = SimpleNamespace(on_notice=Mock())
    party = SimpleNamespace(party_id="reform")

    panel._choose_party(SimpleNamespace(), context, party, True, "presidential")
    panel._party_question.show.assert_not_called()

    panel._party_draft.transition_target.return_value = ("parliamentary", "Parliamentary")
    panel._party_question.show.return_value = False
    panel._choose_party(SimpleNamespace(), context, party, False, "presidential")
    panel._party_draft.restore.assert_called_with("previous")

    panel._party_question.show.side_effect = lambda _message, accept, _cancel: (accept(), True)[1]
    panel._party_draft.confirm_transition.return_value = False
    panel._choose_party(SimpleNamespace(), context, party, True, "presidential")
    context.on_notice.assert_called_once_with(
        "Internal laws", "The party draft changed. Choose the status again.", severity="warning",
    )


def test_render_content_composes_drafts_party_authority_and_apply_notice(monkeypatch):
    imgui = _imgui_mock(monkeypatch)
    imgui.combo.side_effect = [(False, 0), (True, 0), (False, 0)]
    imgui.button.return_value = True
    monkeypatch.setattr(laws_module, "GMLWidgets", Mock())
    draw_empty_state = Mock()
    monkeypatch.setattr(laws_module, "draw_empty_state", draw_empty_state)
    monkeypatch.setattr(
        laws_module,
        "party_policy_context",
        Mock(return_value=({"government_form_id": "presidential"}, {"party_policy_editable": True})),
    )
    frame_count = {"value": 0}

    @contextmanager
    def child_frame(*_args, **_kwargs):
        frame_count["value"] += 1
        yield True

    @contextmanager
    def row_frame(*_args, **_kwargs):
        yield Mock()

    monkeypatch.setattr(laws_module, "gml_child_frame", child_frame)
    monkeypatch.setattr(laws_module, "gml_row", row_frame)
    panel = InternalLawsPanel(open_politics_cb=Mock())
    panel._identity.identity_type = "language"
    panel._identity.render = Mock()
    panel._identity.render_tabs = Mock()
    parties = [
        SimpleNamespace(party_id="ruling", display_name="Ruling", support_pct=None, is_ruling=True, eligible=True),
        SimpleNamespace(party_id="reform", display_name="Reform", support_pct=32.5, is_ruling=False, eligible=True),
        SimpleNamespace(party_id="unknown", display_name="Unknown", support_pct=10.0, is_ruling=False, eligible=None),
    ]
    overview = SimpleNamespace(parties=parties, laws=[], pending_law_transitions=[])
    panel._politics.build = Mock(return_value=overview)
    panel._party_draft.status = Mock(return_value=False)
    panel._choose_party = Mock()
    panel._render_migration = Mock()
    panel._apply_drafts = Mock(return_value="The draft is stale.")
    open_politics = panel._open_politics
    notice = Mock()
    context = SimpleNamespace(
        target_tag="USA",
        is_own_country=True,
        net_client=Mock(),
        save_confirmation_preferences=None,
        on_notice=notice,
    )
    state = SimpleNamespace(tables={})

    panel._render_content(state, context)

    assert frame_count["value"] == 3
    panel._identity.render.assert_called_once_with(state, context, compact=True)
    panel._identity.render_tabs.assert_called_once()
    panel._politics.build.assert_called_once_with(state, "USA")
    panel._choose_party.assert_called_once_with(state, context, parties[1], True, "presidential")
    assert imgui.set_tooltip.call_count == 2
    open_politics.assert_called_once_with()
    panel._render_migration.assert_called_once_with(state, context, panel._render_migration.call_args.args[2])
    panel._apply_drafts.assert_called_once_with(state, context)
    notice.assert_called_once_with("Internal laws", "The draft is stale.", severity="warning")

    panel._politics.build.return_value = SimpleNamespace(
        parties=[], laws=[], pending_law_transitions=[],
    )
    panel._render_content(state, context)

    draw_empty_state.assert_any_call("No party records available.")


def test_render_selects_drafts_and_renders_open_content(monkeypatch):
    @contextmanager
    def open_window(*_args, **_kwargs):
        yield True

    monkeypatch.setattr(laws_module, "WindowManager", SimpleNamespace(window=open_window))
    panel = InternalLawsPanel()
    panel._law_draft.select_country = Mock()
    panel._identity_draft.select_country = Mock()
    panel._party_draft.select_country = Mock()
    panel._render_content = Mock()
    panel._close_confirmation.render = Mock(return_value=None)
    panel._party_question.render = Mock()
    panel._identity.render_notices = Mock()
    state = SimpleNamespace()
    context = SimpleNamespace(
        target_tag="USA",
        save_confirmation_preferences=None,
        is_own_country=True,
        net_client=Mock(),
    )

    assert panel.render(state, context) is True

    panel._law_draft.select_country.assert_called_once_with("USA")
    panel._identity_draft.select_country.assert_called_once_with("USA")
    panel._party_draft.select_country.assert_called_once_with("USA")
    panel._render_content.assert_called_once_with(state, context)


def test_render_laws_handles_empty_and_editable_rows_with_discard(monkeypatch):
    imgui = _imgui_mock(monkeypatch)
    imgui.combo.return_value = (True, 1)
    imgui.button.return_value = True

    @contextmanager
    def row_frame(*_args, **_kwargs):
        yield Mock()

    monkeypatch.setattr(laws_module, "gml_row", row_frame)
    draw_empty_state = Mock()
    monkeypatch.setattr(laws_module, "draw_empty_state", draw_empty_state)
    monkeypatch.setattr(laws_module, "law_choices", lambda _row: ("Low", "High"))
    panel = InternalLawsPanel()
    panel._law_draft.select_country("USA")
    panel._law_draft.pending["existing"] = object()
    panel._law_draft.choose = Mock()
    state = SimpleNamespace(tables={
        "country_laws": SimpleNamespace(iter_rows=lambda **_kwargs: iter([
            {"country_id": "USA", "law_id": "tax", "value": "Low"},
        ])),
    })
    law = SimpleNamespace(law_id="tax", title="Tax rate", value="Low")
    overview = SimpleNamespace(
        laws=[law],
        pending_law_transitions=[SimpleNamespace(law_id="tax", target_value="High")],
    )
    context = SimpleNamespace(is_own_country=True, net_client=Mock())

    panel._render_laws(state, context, overview)

    panel._law_draft.choose.assert_called_once_with(
        {"country_id": "USA", "law_id": "tax", "value": "Low"}, "High",
    )
    assert panel._law_draft.pending == {}
    imgui.text_wrapped.assert_called_once_with("Pending: tax -> High")
    imgui.begin_disabled.assert_called_once_with(False)

    panel._render_laws(SimpleNamespace(tables={}), context, SimpleNamespace(
        laws=[], pending_law_transitions=[],
    ))
    draw_empty_state.assert_called_once_with("No law records available.")


def test_render_migration_shows_unavailable_and_available_rates(monkeypatch):
    panel = InternalLawsPanel(open_migration_cb=Mock())
    table = SimpleNamespace(iter_rows=lambda **_kwargs: iter([{"country_id": "USA"}]))
    summary = SimpleNamespace(entry_rate=0.125, exit_rate=None)
    panel._migration.present_country = Mock(return_value=summary)
    ui = Mock()
    ui.rect.side_effect = [None, None, SimpleNamespace(width=80.0, height=20.0),
                           SimpleNamespace(width=80.0, height=20.0)]
    ui.button_at.side_effect = [False, True, False, False]
    context = SimpleNamespace(target_tag="usa")

    panel._render_migration(SimpleNamespace(tables={}), context, ui)
    panel._render_migration(SimpleNamespace(tables={"migration_policies": table}), context, ui)

    assert ui.text.call_args_list[3].args == ("frmInner/frmHumanMigration/txtImmigrationValue", "—")
    assert ui.text.call_args_list[4].args == ("frmInner/frmHumanMigration/txtEmigrationValue", "—")
    assert ui.text.call_args_list[8].args == ("frmInner/frmHumanMigration/txtImmigrationValue", "12.5%")
    assert ui.text.call_args_list[9].args == ("frmInner/frmHumanMigration/txtEmigrationValue", "—")
    panel._migration.present_country.assert_called_once_with(
        SimpleNamespace(tables={"migration_policies": table}), "USA",
    )
    panel._open_migration.assert_called_once_with()
    assert ui.button_at.call_args_list[0].kwargs["size"] == (140.0, 16.0)
    assert ui.button_at.call_args_list[2].kwargs["size"] == (80.0, 20.0)


def test_finish_close_discards_or_keeps_rejected_drafts_visible():
    notice = Mock()
    context = SimpleNamespace(on_notice=notice)
    panel = InternalLawsPanel()
    panel._law_draft.pending["law"] = object()

    assert panel._finish_close(CloseDecision.DISCARD, SimpleNamespace(), context) is False
    assert panel._law_draft.pending == {}

    panel._apply_drafts = Mock(return_value="stale draft")
    panel._law_draft.pending["law"] = object()
    assert panel._finish_close(CloseDecision.APPLY, SimpleNamespace(), context) is True
    notice.assert_called_once_with("Internal laws", "stale draft", severity="warning")
