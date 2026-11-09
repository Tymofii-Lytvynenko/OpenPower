from types import SimpleNamespace
from unittest.mock import Mock, call

from src.client.ui.layouts import game_panel_registry


def test_unit_design_and_treaty_callbacks_route_through_panel_manager(monkeypatch):
    selection_actions = []

    class FakeUnitDesignSelection:
        def clear(self):
            selection_actions.append(("clear", None))

        def select(self, design_id):
            selection_actions.append(("select", design_id))

    panel_manager = SimpleNamespace(
        set_visible=Mock(),
        get_entries=Mock(
            return_value=[
                SimpleNamespace(
                    id="TREATIES",
                    instance=SimpleNamespace(request_treaty=Mock()),
                )
            ]
        ),
    )
    monkeypatch.setattr(game_panel_registry, "UnitDesignSelection", FakeUnitDesignSelection)
    monkeypatch.setattr(
        game_panel_registry,
        "MilitaryPanel",
        lambda **callbacks: SimpleNamespace(**callbacks),
    )
    monkeypatch.setattr(
        game_panel_registry,
        "UnitListPanel",
        lambda **callbacks: SimpleNamespace(**callbacks),
    )
    monkeypatch.setattr(
        game_panel_registry,
        "MailPanel",
        lambda **callbacks: SimpleNamespace(**callbacks),
    )

    specs = game_panel_registry.build_game_panel_specs(
        panel_manager,
        settings_service=object(),
        window=object(),
        mail_inbox_state=object(),
    )
    spec_by_id = {spec.id: spec for spec in specs}

    military_panel = spec_by_id["MIL"].factory()
    military_panel.open_design_cb()
    unit_list = spec_by_id["UNIT_LIST"].factory()
    unit_list.open_design_cb("design-42")
    mail_panel = spec_by_id["MAIL"].factory()
    mail_panel.open_treaty_cb("treaty-7")

    assert selection_actions == [("clear", None), ("select", "design-42")]
    assert panel_manager.set_visible.call_args_list == [
        call("UNIT_DESIGN", True),
        call("UNIT_DESIGN", True),
        call("TREATIES", True),
    ]
    panel_manager.get_entries.return_value[0].instance.request_treaty.assert_called_once_with(
        "treaty-7"
    )
