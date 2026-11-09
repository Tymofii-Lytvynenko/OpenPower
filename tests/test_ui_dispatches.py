from contextlib import nullcontext
from types import SimpleNamespace

import polars as pl

from src.client.ui.components.shared.save_game_dialog import SaveGameDialog
from src.client.ui.components.shared import save_game_dialog as save_game_dialog_module
from src.client.ui.panels.politics.treaties_live import LiveTreatiesPanel
from src.client.ui.panels.service.journal_dispatches import journal_dispatches


def test_dispatches_filter_country_and_preserve_event_context():
    payload = dict(battle_id="battle-one", participant_countries=["UKR"], side_a_losses=42)
    state = SimpleNamespace(journal=SimpleNamespace(domain_events=[
        dict(event_id="end-one", event_type="EventBattleEnded", payload=payload),
    ]))
    assert journal_dispatches(state, "POL") == []
    dispatch = journal_dispatches(state, "UKR")[0]
    assert dispatch["reference"] == "battle-one"
    assert dispatch["payload"]["side_a_losses"] == 42
    assert payload == dict(battle_id="battle-one", participant_countries=["UKR"], side_a_losses=42)


def test_refusal_dispatch_is_visible_only_to_the_recorded_sponsor():
    payload = dict(treaty_id="deleted", source_country_tag="UKR", title="Compact",
                   responder_country_tag="POL", accepted_country_tags=["UKR"])
    state = SimpleNamespace(journal=SimpleNamespace(domain_events=[
        dict(event_id="refused", event_type="EventTreatyRefused", payload=payload),
        dict(event_id="legacy", event_type="EventTreatyRefused", payload={"treaty_id": "old"}),
    ]))
    assert journal_dispatches(state, "POL") == []
    dispatch = journal_dispatches(state, "UKR")[0]
    assert dispatch["reference"] == "deleted"
    assert dispatch["payload"] == payload


def test_trade_and_treaty_proposal_dispatches_include_actionable_context():
    state = SimpleNamespace(
        journal=SimpleNamespace(
            domain_events=[
                {
                    "event_id": "trade-updated",
                    "event_type": "EventDiplomaticTradeChanged",
                    "payload": {
                        "deal_id": "deal-7",
                        "source_country_id": "UKR",
                        "status": "amended",
                        "reason": "The requested quantity changed.",
                    },
                },
                {
                    "event_id": "treaty-proposed",
                    "event_type": "EventTreatyProposed",
                    "payload": {
                        "treaty_id": "treaty-9",
                        "source_country_tag": "UKR",
                    },
                },
            ]
        )
    )

    dispatches = journal_dispatches(state, "UKR")

    by_kind = {dispatch["kind"]: dispatch for dispatch in dispatches}
    assert by_kind["trade"]["reference"] == "deal-7"
    assert by_kind["trade"]["subject"] == "Trade amended: deal-7"
    assert by_kind["trade"]["body"] == "The requested quantity changed."
    assert by_kind["treaty"]["reference"] == "treaty-9"
    assert by_kind["treaty"]["subject"] == "Treaty proposal: treaty-9"


def test_refusal_report_uses_recorded_acceptances_and_explicit_missing_reason():
    from src.client.ui.panels.service.treaty_refusal_report import treaty_refusal_report

    state = SimpleNamespace(tables={"countries": pl.DataFrame({"id": ["UKR", "POL"],
                                                              "name": ["Ukraine", "Poland"]})})
    report = treaty_refusal_report(state, dict(title="Compact", accepted_country_tags=["UKR"],
                                               responder_country_tag="POL"))
    assert report == "Compact\n\nACCEPTED\nUkraine\n\nREFUSED\nPoland (Reason not recorded)"


def test_external_treaty_selection_clears_stale_active_selection():
    panel = LiveTreatiesPanel()
    panel._selected_treaty_id = "previous"
    state = SimpleNamespace(tables={
        "countries_treaties": pl.DataFrame([dict(id="previous")]),
        "pending_treaties": pl.DataFrame([dict(id="incoming")]),
    })
    assert panel.show_treaty(state, "incoming")
    assert panel._selected_treaty_id == ""
    assert panel._selected_pending_id == "incoming"
    assert not panel.show_treaty(state, "missing")
    assert panel._selected_pending_id == "incoming"


def test_save_name_validation_does_not_dispatch_bad_paths():
    saved, loaded, notices = [], [], []
    dialog = SaveGameDialog(lambda: [], saved.append, loaded.append,
                            lambda *args, **kwargs: notices.append(args))
    dialog.toggle("save")
    dialog._name = "../invalid"
    dialog.submit()
    assert not saved and not loaded
    assert notices
    dialog._name = "named-slot"
    dialog.submit()
    assert saved == ["named-slot"]


def test_load_calls_navigation_with_selected_slot_only():
    loaded = []
    dialog = SaveGameDialog(lambda: [dict(name="slot-a")], lambda name: None,
                            loaded.append, lambda *args, **kwargs: None)
    dialog.toggle("load")
    dialog._selected = "slot-a"
    dialog.submit()
    assert loaded == ["slot-a"]


def test_save_dialog_close_callback_runs_once(monkeypatch):
    closed = []
    dialog = SaveGameDialog(lambda: [], lambda _name: None, lambda _name: None,
                            lambda *args, **kwargs: None,
                            on_close=lambda: closed.append(True))
    dialog.toggle("load")
    monkeypatch.setattr(save_game_dialog_module, "imgui", SimpleNamespace(
        get_io=lambda: SimpleNamespace(display_size=SimpleNamespace(x=1280, y=720))))
    monkeypatch.setattr(save_game_dialog_module.WindowManager, "window",
                        lambda *args, **kwargs: nullcontext(False))

    dialog.render()
    dialog.render()

    assert closed == [True]
