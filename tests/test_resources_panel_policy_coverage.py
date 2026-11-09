from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import polars as pl
import pytest

from src.client.ui.components.shared.dirty_close_confirmation import CloseDecision
from src.client.ui.panels import resources_panel as resources_panel_module
from src.client.ui.panels.resources_panel import (
    PendingProductionIncrease,
    PendingResourcePolicy,
    ResourcePolicyDraft,
    ResourcesPanel,
)


def draft(baseline=(0, 0, 0), values=(0, 0, 0)) -> ResourcePolicyDraft:
    return ResourcePolicyDraft(*baseline, *values)


def state_with_policy(
    *,
    rows=None,
    command_results=None,
) -> SimpleNamespace:
    tables = {}
    if rows is not None:
        tables["domestic_production"] = pl.DataFrame(rows)
    return SimpleNamespace(
        tables=tables,
        journal=SimpleNamespace(command_results=command_results or []),
    )


def policy_row(**overrides):
    row = {
        "country_id": "USA",
        "game_resource_id": "grain",
        "is_gov_controlled": True,
        "is_legal": False,
        "tax_rate": 0.057,
    }
    row.update(overrides)
    return row


def test_resource_policy_draft_tracks_dirty_values_and_rebases_baseline() -> None:
    item = draft((0, 1, 10), (0, 1, 10))

    assert item.values == (0, 1, 10)
    assert item.baseline == (0, 1, 10)
    assert item.is_dirty is False

    item.tax = 25
    assert item.is_dirty is True
    item.rebase((1, 0, 30))

    assert item.baseline == (1, 0, 30)
    assert item.values == (1, 0, 30)
    assert item.is_dirty is False


@pytest.mark.parametrize(
    "amount,abbreviate,expected",
    [
        (None, False, "$ 0"),
        (None, True, "$ 0 M"),
        (950.0, True, "$ 950"),
        (1050.0, True, "$ 1.1 k"),
        (-1500000.0, True, "$ -1.5 M"),
        (10500.0, False, "$ 10 500"),
    ],
)
def test_money_formatter_handles_null_small_and_standard_values(amount, abbreviate, expected) -> None:
    assert ResourcesPanel()._fmt_money(amount, abbreviate=abbreviate) == expected


def test_resolve_pending_production_ignores_other_results_and_matches_normalized_key() -> None:
    panel = ResourcesPanel()
    key = ("USA", "grain")
    panel._pending_production_increases[key] = PendingProductionIncrease("player-1", 0)
    state = state_with_policy(command_results=[
        {"action_type": "OtherAction", "actor_id": "player-1"},
        {"action_type": "ActionIncreaseResourceProduction", "actor_id": "other", "country_id": "USA", "resource_id": "grain"},
        {"action_type": "ActionIncreaseResourceProduction", "player_id": "player-1", "country_id": "CAN", "resource_id": "grain"},
        {"action_type": "ActionIncreaseResourceProduction", "actor_id": "player-1", "country_id": " usa ", "resource_id": " GRAIN "},
    ])

    panel._resolve_pending_production_increases(state)

    assert panel._pending_production_increases == {}


def test_production_increase_dispatch_normalizes_values_and_deduplicates_pending_action() -> None:
    panel = ResourcesPanel()
    client = SimpleNamespace(player_id="player-1", send_action=Mock())
    state = state_with_policy(command_results=[{}, {}, {}])

    panel._dispatch_production_increase(client, " usa ", " Grain ", 15, state)
    panel._dispatch_production_increase(client, "USA", "grain", 25, state)
    panel._dispatch_production_increase(None, "CAN", "oil", 10, state)

    assert panel._pending_production_increases == {
        ("USA", "grain"): PendingProductionIncrease("player-1", 3),
    }
    client.send_action.assert_called_once()
    action = client.send_action.call_args.args[0]
    assert action.player_id == "player-1"
    assert action.country_tag == "USA"
    assert action.resource_id == "grain"
    assert action.increase_percent == 15


def test_policy_dispatch_sends_only_dirty_unpending_drafts_for_target_country() -> None:
    panel = ResourcesPanel()
    panel._policy_drafts = {
        ("USA", "grain"): draft((0, 0, 0), (1, 1, 25)),
        ("USA", "oil"): draft((1, 0, 10), (1, 0, 10)),
        ("CAN", "grain"): draft((0, 0, 0), (1, 1, 80)),
        ("USA", "wood"): draft((0, 0, 0), (0, 1, 5)),
    }
    panel._pending_policy_updates[("USA", "wood")] = PendingResourcePolicy((0, 1, 5), "player-1", 0)
    client = SimpleNamespace(player_id="player-1", send_action=Mock())
    state = state_with_policy(command_results=[{}, {}])

    panel._dispatch_policy_updates(client, " usa ", state)

    assert panel._pending_policy_updates[("USA", "grain")] == PendingResourcePolicy((1, 1, 25), "player-1", 2)
    assert client.send_action.call_count == 1
    action = client.send_action.call_args.args[0]
    assert action.country_tag == "USA"
    assert action.resource_id == "grain"
    assert action.is_gov_controlled is True
    assert action.is_legal is False
    assert action.tax_rate == pytest.approx(0.25)
    assert panel.has_unsaved_changes is True


def test_finish_close_applies_pending_policy_or_discards_unsubmitted_drafts(monkeypatch) -> None:
    panel = ResourcesPanel()
    client = SimpleNamespace(player_id="player-1")
    state = state_with_policy()
    panel._policy_drafts = {("USA", "grain"): draft((0, 0, 0), (1, 0, 0))}
    dispatch = Mock()
    sync = Mock()
    monkeypatch.setattr(panel, "_dispatch_policy_updates", dispatch)
    monkeypatch.setattr(panel, "_sync_policy_from_state", sync)

    panel._finish_close(CloseDecision.APPLY, state, "USA", client)
    dispatch.assert_called_once_with(client, "USA", state)
    sync.assert_not_called()

    panel._finish_close(CloseDecision.DISCARD, state, "USA", client)
    sync.assert_called_once_with(state, "USA")
    assert panel._policy_drafts == {}
    assert panel.current_policy_key is None


@pytest.mark.parametrize(
    "rows,expected,diagnostic",
    [
        (None, (0, 0, 0), "Domestic production data is unavailable."),
        ([{"country_id": "USA"}], (0, 0, 0), "Domestic production is missing columns"),
        ([{"country_id": "CAN", "game_resource_id": "grain"}], (0, 0, 0), None),
        (
            [{"country_id": " usa ", "game_resource_id": " Grain "}],
            (0, 0, 0),
            None,
        ),
        (
            [policy_row(is_gov_controlled=False, is_legal=True, tax_rate=1.5)],
            (0, 0, 100),
            None,
        ),
        (
            [policy_row(tax_rate=float("nan"))],
            (1, 1, 0),
            "Domestic production tax rate is invalid",
        ),
    ],
)
def test_policy_reader_handles_missing_rows_optional_fields_and_invalid_tax(rows, expected, diagnostic) -> None:
    panel = ResourcesPanel()
    state = state_with_policy(rows=rows)

    assert panel._read_policy_values(state, ("USA", "grain")) == expected
    if diagnostic is None:
        assert panel._panel_diagnostic is None
    else:
        assert diagnostic in panel._panel_diagnostic


def test_sync_policy_creates_draft_then_preserves_local_edits_until_rebased() -> None:
    panel = ResourcesPanel()
    panel.selected_resource = " Grain "
    state = state_with_policy(rows=[policy_row()])

    panel._sync_policy_from_state(state, " usa ")

    key = ("USA", "grain")
    assert panel._policy_drafts[key].baseline == (1, 1, 6)
    assert panel._policy_drafts[key].values == (1, 1, 6)
    assert panel.current_policy_key == key
    assert (panel.draft_management, panel.draft_status, panel.draft_tax) == (1, 1, 6)

    panel._policy_drafts[key].tax = 15
    panel._sync_policy_from_state(state_with_policy(rows=[policy_row(tax_rate=0.2)]), "USA")

    assert panel._policy_drafts[key].baseline == (1, 1, 6)
    assert panel._policy_drafts[key].values == (1, 1, 15)
    assert panel.has_unsaved_changes is True


def test_sync_policy_acceptance_rebases_pending_draft_to_authoritative_values() -> None:
    panel = ResourcesPanel()
    key = ("USA", "grain")
    panel.selected_resource = "grain"
    panel._policy_drafts[key] = draft((0, 0, 0), (1, 1, 25))
    panel._pending_policy_updates[key] = PendingResourcePolicy((1, 1, 25), "player-1", 0)

    panel._sync_policy_from_state(state_with_policy(rows=[policy_row(tax_rate=0.25)]), "USA")

    assert key not in panel._pending_policy_updates
    assert panel._policy_drafts[key].baseline == (1, 1, 25)
    assert panel._policy_drafts[key].values == (1, 1, 25)
    assert panel.has_unsaved_changes is False


def test_sync_policy_rejection_keeps_submitted_values_against_latest_baseline() -> None:
    panel = ResourcesPanel()
    key = ("USA", "grain")
    panel.selected_resource = "grain"
    panel._policy_drafts[key] = draft((0, 0, 0), (1, 1, 25))
    panel._pending_policy_updates[key] = PendingResourcePolicy((1, 1, 25), "player-1", 0)
    rejected = {
        "action_type": "ActionUpdateResourcePolicy",
        "player_id": "player-1",
        "status": "rejected",
        "country_id": "USA",
        "resource_id": "grain",
    }
    state = state_with_policy(rows=[policy_row(tax_rate=0.1)], command_results=[rejected])

    panel._sync_policy_from_state(state, "USA")

    assert key not in panel._pending_policy_updates
    assert panel._policy_drafts[key].baseline == (1, 1, 10)
    assert panel._policy_drafts[key].values == (1, 1, 25)
    assert panel.has_unsaved_changes is True


def test_pending_unconfirmed_policy_is_preserved_when_draft_did_not_exist() -> None:
    panel = ResourcesPanel()
    key = ("USA", "grain")
    panel.selected_resource = "grain"
    panel._pending_policy_updates[key] = PendingResourcePolicy((0, 0, 20), "player-1", 0)

    panel._sync_policy_from_state(state_with_policy(rows=[policy_row()]), "USA")

    assert panel._policy_drafts[key].baseline == (1, 1, 6)
    assert panel._policy_drafts[key].values == (0, 0, 20)
    assert (panel.draft_management, panel.draft_status, panel.draft_tax) == (0, 0, 20)


def test_policy_draft_mutation_refresh_and_discard_keep_only_pending_values() -> None:
    panel = ResourcesPanel()
    pending_key = ("USA", "grain")
    dirty_key = ("USA", "oil")
    clean_key = ("CAN", "grain")
    panel._policy_drafts = {
        pending_key: draft((0, 0, 0), (1, 0, 10)),
        dirty_key: draft((0, 0, 0), (0, 1, 20)),
        clean_key: draft((1, 1, 10), (1, 1, 10)),
    }
    panel._pending_policy_updates[pending_key] = PendingResourcePolicy((1, 0, 10), "player-1", 0)
    panel.current_policy_key = dirty_key
    panel.draft_management, panel.draft_status, panel.draft_tax = (1, 1, 30)

    panel._set_current_draft_value("tax", 40)
    assert panel._policy_drafts[dirty_key].tax == 40
    assert panel.has_unsaved_changes is True

    panel._refresh_current_draft()
    assert panel._policy_drafts[dirty_key].values == (1, 1, 30)
    panel.current_policy_key = pending_key
    panel.draft_management, panel.draft_status, panel.draft_tax = (0, 0, 0)
    panel._refresh_current_draft()
    assert panel._policy_drafts[pending_key].values == (1, 0, 10)

    panel._discard_unsubmitted_drafts()
    assert set(panel._policy_drafts) == {pending_key}
    assert panel.current_policy_key is None
    assert panel.has_unsaved_changes is False


def test_tax_draft_is_clamped_and_requires_a_change_to_mark_dirty() -> None:
    panel = ResourcesPanel()
    key = ("USA", "grain")
    panel.current_policy_key = key
    panel._policy_drafts[key] = draft((0, 0, 50), (0, 0, 50))
    panel.draft_tax = 50

    panel._set_draft_tax(50)
    assert panel.draft_tax == 50
    assert panel.has_unsaved_changes is False

    panel.draft_tax = 50
    panel._set_draft_tax(140)
    assert panel.draft_tax == 100
    assert panel._policy_drafts[key].tax == 100
    assert panel.has_unsaved_changes is True
