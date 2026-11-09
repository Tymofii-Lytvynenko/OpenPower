from types import SimpleNamespace

import pytest

from src.client.ui.panels.military.unit_research_panel import (
    UnitResearchPanel,
    _DETAIL_TABS,
)
from src.client.ui.components.shared.dirty_close_confirmation import CloseDecision
from src.shared.actions import ActionUpdateResearchFunding


class Client:
    player_id = "player-7"

    def __init__(self):
        self.actions = []

    def send_action(self, action):
        self.actions.append(action)


def panel_with_funding(country="USA", baseline=None):
    panel = UnitResearchPanel()
    panel._draft_country_tag = country
    panel._funding_baseline = dict(baseline or {})
    panel._funding_draft = dict(baseline or {})
    return panel


@pytest.mark.parametrize(
    "branch,expected",
    [("ground", "GROUND"), ("air", "AIR"), ("naval", "NAVAL"), ("strategic", "STRATEGIC"), ("unknown", "UNKNOWN")],
)
def test_branch_label_names_research_categories(branch, expected):
    assert UnitResearchPanel._branch_label(branch) == expected


@pytest.mark.parametrize(
    "value,expected",
    [(None, 0.0), ("bad", 0.0), (-0.5, 0.0), (0.35, 0.35), (2, 1.0)],
)
def test_funding_ratio_parses_and_clamps_values(value, expected):
    assert UnitResearchPanel._ratio(value) == expected


def test_tracks_by_branch_normalizes_keys_and_ignores_empty_branch():
    rows = [
        {"branch": " Ground ", "id": "g"},
        {"branch": "AIR", "id": "a"},
        {"branch": "", "id": "ignored"},
        {"id": "missing"},
    ]

    assert UnitResearchPanel._tracks_by_branch(rows) == {
        "ground": rows[0],
        "air": rows[1],
    }


def test_funding_branches_combine_categories_and_strategic_tracks():
    assert UnitResearchPanel._funding_branches() == (
        "ground", "air", "naval", "strategic",
        "strategic_program", "strategic_weapons", "strategic_defense",
    )
    assert tuple(tab[0] for tab in _DETAIL_TABS) == ("technology", "progress", "funding")


def test_sync_funding_draft_clamps_snapshot_and_preserves_pending_values():
    panel = panel_with_funding()
    panel._pending_funding_by_country["USA"] = {"ground": 0.65, "strategic_weapons": 0.25}

    panel._sync_funding_draft("USA", {
        "ground": {"funding_ratio": 0.2},
        "air": {"funding_ratio": 1.4},
        "naval": {"funding_ratio": "bad"},
    })

    assert panel._draft_country_tag == "USA"
    assert panel._funding_baseline["ground"] == 0.65
    assert panel._funding_draft["ground"] == 0.65
    assert panel._funding_draft["air"] == 1.0
    assert panel._funding_draft["naval"] == 0.0
    assert panel._funding_draft["strategic_weapons"] == 0.25
    assert panel._has_changes is False


def test_stage_funding_redistributes_linked_ratios_within_each_group():
    panel = panel_with_funding(baseline={
        "ground": 0.4,
        "air": 0.3,
        "naval": 0.2,
        "strategic": 0.1,
        "strategic_program": 0.5,
        "strategic_weapons": 0.3,
        "strategic_defense": 0.2,
    })

    panel._stage_funding("ground", 0.6)
    assert panel._funding_draft["ground"] == pytest.approx(0.6)
    assert panel._funding_draft["air"] == pytest.approx(0.2)
    assert panel._funding_draft["naval"] == pytest.approx(0.1333333333)
    assert panel._funding_draft["strategic"] == pytest.approx(0.0666666667)
    assert sum(panel._funding_draft[key] for key in ("ground", "air", "naval", "strategic")) == pytest.approx(1.0)

    panel._stage_funding("strategic_program", 0.6)
    assert panel._funding_draft["strategic_program"] == pytest.approx(0.6)
    assert panel._funding_draft["strategic_weapons"] == pytest.approx(0.24)
    assert panel._funding_draft["strategic_defense"] == pytest.approx(0.16)
    assert panel._funding_draft["ground"] == pytest.approx(0.6)
    assert panel._has_changes is True


def test_apply_funding_draft_skips_unchanged_and_unconnected_requests():
    panel = panel_with_funding(baseline={"ground": 0.4})
    client = Client()
    context = SimpleNamespace(net_client=client)
    state = SimpleNamespace(journal=SimpleNamespace(command_results=[]))

    panel._apply_funding_draft({}, context, state)
    assert client.actions == []

    panel._funding_draft["ground"] = 0.7
    panel._apply_funding_draft({}, SimpleNamespace(net_client=None), state)
    assert client.actions == []


def test_apply_funding_draft_sends_changed_branches_and_tracks_pending_batch():
    panel = panel_with_funding(baseline={"ground": 0.4, "air": 0.3})
    panel._funding_draft.update(ground=0.7, air=0.3)
    client = Client()
    state = SimpleNamespace(journal=SimpleNamespace(command_results=[{}, {}]))

    panel._apply_funding_draft(
        {"ground": {"priority": "bad"}},
        SimpleNamespace(net_client=client),
        state,
    )

    assert len(client.actions) == 1
    action = client.actions[0]
    assert isinstance(action, ActionUpdateResearchFunding)
    assert action.country_tag == "USA"
    assert action.branch == "ground"
    assert action.funding_ratio == pytest.approx(0.7)
    assert action.priority == 1
    assert panel._pending_funding_by_country == {"USA": {"ground": 0.7}}
    assert panel._pending_result_cursors == {"USA": 2}
    assert panel._pending_player_ids == {"USA": "player-7"}
    assert panel._funding_baseline == panel._funding_draft
    assert panel._has_changes is False


def test_apply_funding_draft_uses_track_priority_and_keeps_existing_batch_cursor():
    panel = panel_with_funding(baseline={"air": 0.25})
    panel._pending_funding_by_country["USA"] = {"ground": 0.5}
    panel._pending_result_cursors["USA"] = 1
    panel._pending_player_ids["USA"] = "player-7"
    panel._funding_draft["air"] = 0.6
    client = Client()

    panel._apply_funding_draft(
        {"air": {"priority": 8}},
        SimpleNamespace(net_client=client),
        SimpleNamespace(journal=SimpleNamespace(command_results=[])),
    )

    assert client.actions[0].priority == 8
    assert panel._pending_result_cursors["USA"] == 1
    assert panel._pending_player_ids["USA"] == "player-7"
    assert panel._pending_funding_by_country["USA"] == {"ground": 0.5, "air": 0.6}


def test_reconcile_waits_for_authoritative_snapshot_and_updates_unpending_branches():
    panel = panel_with_funding(baseline={"ground": 0.4, "air": 0.3})
    panel._funding_draft.update(ground=0.7, air=0.3)
    panel._pending_funding_by_country["USA"] = {"ground": 0.7}
    panel._pending_result_cursors["USA"] = 0
    panel._pending_player_ids["USA"] = "player-7"

    panel._reconcile_funding_snapshot(
        "USA",
        {"ground": {"funding_ratio": 0.4}, "air": {"funding_ratio": 0.5}},
        SimpleNamespace(journal=SimpleNamespace(command_results=[])),
    )

    assert panel._pending_funding_by_country["USA"] == {"ground": 0.7}
    assert panel._funding_baseline["ground"] == 0.4
    assert panel._funding_baseline["air"] == 0.5
    assert panel._funding_draft["air"] == 0.5
    assert panel._funding_draft["ground"] == 0.7


def test_reconcile_clears_matching_snapshot_and_rejected_result():
    panel = panel_with_funding(baseline={"ground": 0.4})
    panel._funding_draft["ground"] = 0.7
    panel._pending_funding_by_country["USA"] = {"ground": 0.7}
    panel._pending_result_cursors["USA"] = 0
    panel._pending_player_ids["USA"] = "player-7"

    panel._reconcile_funding_snapshot(
        "USA",
        {"ground": {"funding_ratio": 0.7}},
        SimpleNamespace(journal=SimpleNamespace(command_results=[])),
    )

    assert panel._pending_funding_by_country == {}
    assert panel._pending_result_cursors == {}
    assert panel._pending_player_ids == {}
    assert panel._funding_baseline["ground"] == 0.7

    panel._pending_funding_by_country["USA"] = {"ground": 0.9, "air": 0.2}
    panel._pending_result_cursors["USA"] = 1
    panel._pending_player_ids["USA"] = "player-7"
    panel._funding_baseline["ground"] = 0.9
    panel._funding_draft["ground"] = 0.9
    panel._reconcile_funding_snapshot(
        "USA",
        {"ground": {"funding_ratio": 0.3}, "air": {"funding_ratio": 0.1}},
        SimpleNamespace(journal=SimpleNamespace(command_results=[
            {"action_type": "ActionUpdateResearchFunding", "player_id": "player-7", "status": "rejected"},
            {"action_type": "ActionUpdateResearchFunding", "player_id": "other", "status": "rejected"},
            {"action_type": "ActionUpdateResearchFunding", "player_id": "player-7", "status": "REJECTED"},
        ])),
    )

    assert panel._pending_funding_by_country == {}
    assert panel._funding_baseline["ground"] == 0.3
    assert panel._funding_baseline["air"] == 0.1


def test_discard_and_finish_close_apply_or_restore_current_snapshot(monkeypatch):
    panel = panel_with_funding(baseline={"ground": 0.2})
    panel._funding_draft["ground"] = 0.8
    panel._discard_funding_draft("USA", {"ground": {"funding_ratio": 0.45}})
    assert panel._funding_draft["ground"] == 0.45
    assert panel._has_changes is False

    panel._funding_draft["ground"] = 0.7
    panel._draft_country_tag = "USA"
    client = Client()
    panel._presenter.research_tracks_for_country = lambda state, country: [
        {"branch": "ground", "funding_ratio": 0.45, "priority": 4},
    ]
    panel._finish_close(
        CloseDecision.APPLY,
        SimpleNamespace(journal=SimpleNamespace(command_results=[])),
        SimpleNamespace(net_client=client),
        "USA",
    )

    assert len(client.actions) == 1
    assert client.actions[0].funding_ratio == pytest.approx(0.7)
    assert client.actions[0].priority == 4
