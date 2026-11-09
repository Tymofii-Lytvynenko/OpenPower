from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import polars as pl

from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.panels.service.mail_inbox_state import MailInboxState
from src.client.ui.panels.service.mail_panel import MailPanel
from src.client.ui.panels.service import mail_live as mail_module
from src.client.ui.panels.service.mail_live import LiveMailPanel
from src.shared.actions import ActionRespondTreaty


class FakeWidgets:
    results = {}
    calls = []

    def __init__(self, root):
        self.root = root

    def button(self, slot, label, test_id, *, enabled=True, **kwargs):
        self.calls.append(("button", self.root, slot, label, test_id, enabled, kwargs))
        return bool(enabled and self.results.get(test_id, False))


class FakeRow:
    results = {}
    calls = []

    def text(self, slot, value, **kwargs):
        self.calls.append(("text", slot, value, kwargs))

    def button(self, slot, label, test_id, **kwargs):
        self.calls.append(("button", slot, label, test_id, kwargs))
        return bool(self.results.get(test_id, False))


def install_mail_ui(monkeypatch, *, window_open=True):
    imgui = Mock()
    imgui.WindowFlags_ = SimpleNamespace(no_title_bar=1)
    imgui.Key = SimpleNamespace(escape="escape")
    imgui.PopupFlags_ = SimpleNamespace(any_popup_id="any_popup")
    imgui.get_main_viewport.return_value.size = SimpleNamespace(x=1280, y=800)
    imgui.get_main_viewport.return_value.pos = SimpleNamespace(x=10, y=20)
    imgui.is_window_focused.return_value = False
    imgui.is_key_pressed.return_value = False
    imgui.is_popup_open.return_value = False
    imgui.begin_child.return_value = True
    imgui.begin_popup.return_value = False
    imgui.button.return_value = False
    FakeWidgets.results = {}
    FakeWidgets.calls = []
    FakeRow.results = {}
    FakeRow.calls = []
    monkeypatch.setattr(mail_module, "imgui", imgui)
    monkeypatch.setattr(mail_module, "GMLWidgets", FakeWidgets)
    monkeypatch.setattr(mail_module, "get_gml_layout", lambda _name: SimpleNamespace(width=500, height=300))
    monkeypatch.setattr(mail_module, "main_bar_bounds", lambda *_args: SimpleNamespace(x=15, y=790, height=40))
    monkeypatch.setattr(mail_module, "draw_empty_state", Mock())
    windows = []

    @contextmanager
    def window(*args, **kwargs):
        windows.append((args, kwargs))
        yield window_open

    @contextmanager
    def row(*_args, **_kwargs):
        yield FakeRow()

    monkeypatch.setattr(mail_module.WindowManager, "window", staticmethod(window))
    monkeypatch.setattr(mail_module, "gml_row", row)
    return imgui, windows


def context(*, country="UKR", own=True, net_client=None, on_notice=None):
    return PanelRenderContext(
        target_tag=country,
        is_own_country=own,
        net_client=net_client,
        on_notice=on_notice,
    )


def test_render_clamps_window_and_handles_native_close_and_escape(monkeypatch):
    imgui, windows = install_mail_ui(monkeypatch)
    panel = LiveMailPanel()
    state = SimpleNamespace(tables={})

    assert panel.render(state, context()) is True
    assert windows[-1][0] == ("MAIL",)
    assert windows[-1][1]["x"] == 205
    assert windows[-1][1]["y"] == 460

    monkeypatch.setattr(mail_module.WindowManager, "window", staticmethod(
        lambda *_args, **_kwargs: _window_result(False)
    ))
    assert panel.render(state, context()) is False

    monkeypatch.setattr(mail_module.WindowManager, "window", staticmethod(
        lambda *_args, **_kwargs: _window_result(True)
    ))
    imgui.is_window_focused.return_value = True
    imgui.is_key_pressed.return_value = True
    assert panel.render(state, context()) is False

    imgui.is_popup_open.return_value = True
    assert panel.render(state, context()) is True


@contextmanager
def _window_result(is_open):
    yield is_open


def test_empty_content_shows_empty_state_and_delete_all_closes_when_every_item_is_gone(monkeypatch):
    imgui, _windows = install_mail_ui(monkeypatch)
    panel = LiveMailPanel(close_mail_cb=Mock())
    panel._presenter = Mock()
    panel._presenter.messages_for_country.return_value = []
    monkeypatch.setattr(mail_module, "journal_dispatches", lambda *_args: [])
    state = SimpleNamespace(tables={})

    panel._render_content(state, context())

    mail_module.draw_empty_state.assert_called_once_with(
        "No cabinet mail is available for the selected country yet."
    )
    imgui.dummy.assert_called_once_with((0.0, 0.0))
    imgui.end_child.assert_called_once_with()
    assert FakeWidgets.calls[0][4] == "mail.delete_all"
    panel._render_message_detail()
    panel._render_proposal_detail(context(), "UKR")

    panel._inbox_state.dismiss("message", "existing")
    items = [{"inbox_kind": "message", "id": "existing"}]
    panel._dismiss_items(items, "UKR")
    panel._close_if_empty(items)
    panel._close_mail_cb.assert_called_once_with()


def test_collects_visible_dispatches_messages_and_country_relevant_proposals(monkeypatch):
    _imgui, _windows = install_mail_ui(monkeypatch)
    inbox = MailInboxState()
    panel = LiveMailPanel(mail_inbox_state=inbox)
    panel._presenter = Mock()
    panel._presenter.messages_for_country.return_value = [
        {"id": "m1", "subject": "Message"},
    ]
    dispatches = [
        {"id": "d1", "kind": "battle", "subject": "Battle"},
        {"id": "hidden", "kind": "trade", "subject": "Hidden"},
    ]
    inbox.dismiss("dispatch", "hidden")
    journal = Mock(return_value=dispatches)
    monkeypatch.setattr(mail_module, "journal_dispatches", journal)
    state = SimpleNamespace(tables={
        "pending_treaties": pl.DataFrame({
            "id": ["p1", "p2"],
            "title": ["Offer", "Other"],
            "required_responses": [["ukr", "POL"], ["POL"]],
        }),
    })

    items = panel._items_for_country(state, "UKR")

    assert [(item["inbox_kind"], item["id"]) for item in items] == [
        ("dispatch", "d1"), ("message", "m1"), ("proposal", "p1"),
    ]
    journal.assert_called_once_with(state, "UKR", frozenset())
    panel._presenter.messages_for_country.assert_called_once_with(state, "UKR")


def test_content_renders_each_row_and_delete_all_dismisses_region_events(monkeypatch):
    imgui, _windows = install_mail_ui(monkeypatch)
    closed = Mock()
    panel = LiveMailPanel(close_mail_cb=closed)
    panel._presenter = Mock()
    panel._presenter.messages_for_country.return_value = [
        {"id": "m1", "subject": "Message"},
    ]
    dispatch = {
        "id": "gained:e1", "kind": "region_control", "subject": "Gained",
        "payload": {"event_ids": ["e1"]},
    }
    monkeypatch.setattr(mail_module, "journal_dispatches", lambda *_args: [dispatch])
    FakeWidgets.results = {"mail.delete_all": True}

    panel._render_content(SimpleNamespace(tables={}), context())

    assert imgui.begin_child.called
    assert [call[0] for call in FakeRow.calls].count("text") == 2
    assert panel._inbox_state.is_dismissed("dispatch", "gained:e1")
    assert panel._inbox_state.is_dismissed("message", "m1")
    assert panel._inbox_state.dismissed_region_event_ids("UKR") == frozenset({"e1"})
    closed.assert_called_once_with()
    assert LiveMailPanel._view_test_id({"inbox_kind": "proposal", "id": "p1"}) == "mail.treaty.p1.view"


def test_pending_proposals_require_table_schema_and_match_normalized_country():
    assert LiveMailPanel._pending_for_country(SimpleNamespace(tables={}), "UKR") == []
    assert LiveMailPanel._pending_for_country(
        SimpleNamespace(tables={"pending_treaties": pl.DataFrame()}), "UKR"
    ) == []
    assert LiveMailPanel._pending_for_country(
        SimpleNamespace(tables={"pending_treaties": pl.DataFrame({"id": ["p1"]})}), "UKR"
    ) == []
    pending = pl.DataFrame({
        "id": ["p1", "p2"],
        "required_responses": [[" ukr ", "POL"], ["POL"]],
    })
    assert LiveMailPanel._pending_for_country(SimpleNamespace(tables={"pending_treaties": pending}), "UKR") == [
        {"id": "p1", "required_responses": [" ukr ", "POL"]},
    ]


def test_dispatch_and_notice_rows_view_then_dismiss_and_close(monkeypatch):
    _imgui, _windows = install_mail_ui(monkeypatch)
    closed = Mock()
    opened_dispatches = []
    inbox = MailInboxState()
    panel = LiveMailPanel(
        open_dispatch_cb=opened_dispatches.append,
        mail_inbox_state=inbox,
        close_mail_cb=closed,
    )
    dispatch = {
        "inbox_kind": "dispatch", "id": "region-gained:e1", "kind": "region_control",
        "subject": "Territory gained", "payload": {"event_ids": ["e1"]},
    }
    items = [dispatch]
    FakeRow.results = {"mail.dispatch.region-gained:e1": True}

    panel._render_mail_row(dispatch, items, "UKR", context())

    assert opened_dispatches == [dispatch]
    assert inbox.is_dismissed("dispatch", dispatch["id"])
    assert inbox.dismissed_region_event_ids("UKR") == frozenset({"e1"})
    closed.assert_called_once_with()
    assert FakeRow.calls[0][0] == "text"
    assert FakeRow.calls[1][3] == "mail.dispatch.region-gained:e1"

    notice = Mock()
    panel = LiveMailPanel(mail_inbox_state=MailInboxState(), close_mail_cb=Mock())
    message = {"inbox_kind": "message", "id": "m1", "subject": "Budget", "body": "Review"}
    FakeRow.results = {"mail.message.m1.view": True}
    panel._render_mail_row(message, [message], "UKR", context(on_notice=notice))
    notice.assert_called_once_with("Budget", "Review")
    assert panel._inbox_state.is_dismissed("message", "m1")


def test_delete_rows_and_bulk_dismiss_keep_unread_detail_open(monkeypatch):
    _imgui, _windows = install_mail_ui(monkeypatch)
    closed = Mock()
    panel = LiveMailPanel(close_mail_cb=closed)
    message = {"inbox_kind": "message", "id": "m2", "title": "Delete me"}
    FakeRow.results = {"mail.item.message:m2.delete": True}

    panel._render_mail_row(message, [message], "UKR", context())

    assert panel._inbox_state.is_dismissed("message", "m2")
    closed.assert_called_once_with()
    panel._message_detail = {"subject": "open"}
    panel._close_if_empty([message])
    closed.assert_called_once_with()
    panel._message_detail = None
    panel._close_if_empty([])
    panel._close_if_empty([{"inbox_kind": "message", "id": "still-visible"}])
    closed.assert_called_once_with()
    LiveMailPanel()._close_if_empty([message])


def test_message_view_uses_notice_or_fallback_popup_and_closes_cleanly(monkeypatch):
    imgui, _windows = install_mail_ui(monkeypatch)
    panel = LiveMailPanel()
    message = {"inbox_kind": "message", "id": "m1", "body": "Body"}
    panel._view_item(message, context(on_notice=None))
    assert panel._message_detail == message
    assert panel._message_detail_pending is True

    panel._render_message_detail()
    imgui.open_popup.assert_called_once_with("MailMessageDetails")
    assert panel._message_detail is None
    assert panel._message_detail_pending is False

    panel._message_detail = {"body": "Body"}
    imgui.begin_popup.return_value = True
    imgui.button.return_value = False
    panel._render_message_detail()
    imgui.text_colored.assert_called_with(
        mail_module.GAMETHEME.colors.text_main,
        "Untitled dispatch",
        test_id="mail.message.details.subject",
    )
    imgui.text_disabled.assert_not_called()
    imgui.text_unformatted.assert_called_with("Body", test_id="mail.message.details.body")
    assert panel._message_detail is not None

    panel._message_detail = {"subject": "Known", "created_at": "now", "body": "Details"}
    imgui.button.return_value = True
    panel._render_message_detail()
    imgui.text_disabled.assert_called_once_with("now")
    imgui.close_current_popup.assert_called_once_with()
    imgui.end_popup.assert_called()
    assert panel._message_detail is None


def test_proposal_detail_opens_callbacks_and_sends_accept_or_reject_actions(monkeypatch):
    imgui, _windows = install_mail_ui(monkeypatch)
    treaty_opened = Mock()
    net_client = Mock()
    net_client.player_id = "player-1"
    panel = LiveMailPanel(open_treaty_cb=treaty_opened)
    proposal = {
        "id": "proposal-1", "title": "Alliance", "terms": "Mutual defense",
        "required_responses": ["ukr", "pol"], "accepted_members": ["POL"],
    }
    panel._view_item({"inbox_kind": "proposal", **proposal}, context())
    assert panel._proposal_detail["id"] == "proposal-1"
    imgui.open_popup.assert_called_once_with("MailTreatyProposal")
    panel._render_proposal_detail(context(), "UKR")
    imgui.end_popup.assert_not_called()

    imgui.begin_popup.return_value = True
    imgui.button.side_effect = lambda _label, *args, **kwargs: kwargs.get("test_id") in {
        "mail.treaty.proposal-1.details", "mail.treaty.proposal-1.accept",
    }
    panel._render_proposal_detail(context(net_client=net_client), "UKR")
    treaty_opened.assert_called_once_with("proposal-1")
    net_client.send_action.assert_called_once()
    accept = net_client.send_action.call_args.args[0]
    assert isinstance(accept, ActionRespondTreaty)
    assert (accept.player_id, accept.treaty_id, accept.responder_country_tag, accept.accept) == (
        "player-1", "proposal-1", "UKR", True,
    )
    imgui.same_line.assert_called_once_with()

    net_client.send_action.reset_mock()
    imgui.button.side_effect = lambda _label, *args, **kwargs: kwargs.get("test_id") == "mail.treaty.proposal-1.reject"
    panel._render_proposal_detail(context(net_client=net_client), "UKR")
    reject = net_client.send_action.call_args.args[0]
    assert isinstance(reject, ActionRespondTreaty)
    assert reject.accept is False


def test_proposal_controls_hide_when_popup_is_closed_or_country_cannot_respond(monkeypatch):
    imgui, _windows = install_mail_ui(monkeypatch)
    panel = LiveMailPanel()
    panel._proposal_detail = {"id": "p2", "required_responses": ["UKR"]}

    panel._render_proposal_detail(context(), "UKR")
    imgui.button.assert_not_called()
    imgui.begin_popup.return_value = True
    panel._render_proposal_detail(context(own=False, net_client=Mock()), "UKR")
    panel._render_proposal_detail(context(own=True, net_client=Mock()), "POL")
    imgui.button.assert_not_called()
    assert imgui.end_popup.call_count == 2


def test_inbox_state_empty_dismissals_do_not_advance_revision():
    inbox = MailInboxState()

    assert inbox.revision == 0
    inbox.dismiss("notice", "")
    inbox.dismiss_region_events("", {"event-1"})
    inbox.dismiss_region_events("UKR", [])

    assert inbox.revision == 0
    assert inbox.dismissed_region_event_ids("UKR") == frozenset()


def test_legacy_mail_panel_import_reuses_the_live_panel():
    assert MailPanel is LiveMailPanel
