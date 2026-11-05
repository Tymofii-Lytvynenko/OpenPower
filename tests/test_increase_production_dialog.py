from src.client.ui.components.shared.increase_production_dialog import IncreaseProductionDialog


def test_production_percent_toggles_match_source_independent_group_state():
    dialog = IncreaseProductionDialog()

    dialog.open("ukr", "cereals")
    assert dialog._selected_percents == set()

    dialog._toggle_percent(2)
    dialog._toggle_percent(25)
    assert dialog._selected_percents == {2, 25}

    dialog._toggle_percent(2)
    assert dialog._selected_percents == {25}

    dialog.open("ukr", "oil")
    assert dialog._selected_percents == set()
