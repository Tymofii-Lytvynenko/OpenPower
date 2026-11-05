from src.client.ui.panels.politics.treaty_detail_lifecycle import TreatyDetailLifecycle


def activated(proposal_id):
    return {"event_type": "EventTreatyLifecycleChanged", "payload": {
        "proposal_id": proposal_id, "treaty_id": "new-agreement", "transition": "activated",
    }}


def test_missing_treaty_warns_only_once():
    observer = TreatyDetailLifecycle("missing", proposal=False)
    assert observer.update(None, []) == "The treaty is no longer available."
    assert observer.update(None, []) == ""
    assert observer.message


def test_activation_requires_exact_proposal_id_and_does_not_replay_history():
    history = [activated("proposal")]
    observer = TreatyDetailLifecycle("proposal", proposal=True, initial_events=history)
    assert observer.update({"id": "proposal"}, history) == ""
    history.append(activated("other"))
    assert observer.update({"id": "proposal"}, history) == ""
    history.append(activated("proposal"))
    assert observer.update(None, history) == "The treaty has been accepted."
    assert observer.update(None, history) == ""


def test_removed_or_dissolved_treaty_is_no_longer_editable():
    observer = TreatyDetailLifecycle("active", proposal=False)
    assert observer.update({"id": "active", "status": "active"}, []) == ""
    assert observer.update({"id": "active", "status": "dissolved"}, [])


def test_removed_proposal_retains_its_last_details_for_the_notice():
    observer = TreatyDetailLifecycle("proposal", proposal=True)
    row = {"id": "proposal", "title": "Compact"}
    assert observer.update(row, []) == ""
    row["title"] = "Changed elsewhere"
    assert observer.update(None, [activated("proposal")]) == "The treaty has been accepted."
    assert observer.last_row["title"] == "Compact"


def test_old_acknowledgement_cannot_close_a_new_inspection():
    from src.client.ui.panels.politics.treaties_live import LiveTreatiesPanel

    panel = LiveTreatiesPanel()
    previous = TreatyDetailLifecycle("old", proposal=False)
    current = TreatyDetailLifecycle("new", proposal=False)
    panel._show_details = True
    panel._detail_lifecycle = current
    panel._close_details_if_current(previous)
    assert panel._show_details
    panel._close_details_if_current(current)
    assert not panel._show_details
