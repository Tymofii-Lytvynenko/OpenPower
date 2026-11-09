from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import src.client.ui.panels.military.unit_attack_confirmation as confirmation_module
from src.client.ui.panels.military.unit_attack_confirmation import UnitAttackConfirmation


class Ui:
    def __init__(self, clicked):
        self.clicked = clicked
        self.texts = []

    def path(self, slot):
        return f"unit-attack/{slot}"

    def text(self, *args, **kwargs):
        self.texts.append((args, kwargs))

    def button(self, _slot, _label, test_id):
        return test_id in self.clicked


def test_render_confirms_and_cancels_the_matching_pending_orders(monkeypatch):
    coordinates = []

    @contextmanager
    def window(title, **kwargs):
        coordinates.append((title, kwargs))
        yield True

    imgui = SimpleNamespace(
        get_io=lambda: SimpleNamespace(display_size=SimpleNamespace(x=1000, y=800)),
        WindowFlags_=SimpleNamespace(no_title_bar=4),
        text_wrapped=Mock(),
    )
    monkeypatch.setattr(confirmation_module, "WindowManager", SimpleNamespace(window=window))
    monkeypatch.setattr(confirmation_module, "GMLWidgets", lambda _root: Ui({
        "unit.attack.yes.CAN", "unit.attack.no.MEX",
    }))
    monkeypatch.setattr(confirmation_module, "imgui", imgui)
    monkeypatch.setattr(confirmation_module, "resolve_country_name", lambda _state, tag: f"Country {tag}")
    orders = SimpleNamespace(pending={"CAN", "MEX"}, confirm=Mock(), cancel=Mock())

    UnitAttackConfirmation(orders).render(SimpleNamespace())

    assert {title for title, _ in coordinates} == {"Confirm attack###CAN", "Confirm attack###MEX"}
    assert all(kwargs["gml_template"] == "Unit_Attack_Confirm_Window" for _, kwargs in coordinates)
    assert all(kwargs["flags"] == 4 for _, kwargs in coordinates)
    assert orders.confirm.call_args_list == [(("CAN",),)]
    assert orders.cancel.call_args_list == [(("MEX",),)]
    assert imgui.text_wrapped.call_count == 2


def test_render_with_no_pending_orders_does_not_open_a_dialog(monkeypatch):
    opened = Mock()
    monkeypatch.setattr(confirmation_module, "WindowManager", SimpleNamespace(window=opened))
    imgui = SimpleNamespace(get_io=lambda: SimpleNamespace(display_size=SimpleNamespace(x=800, y=600)))
    monkeypatch.setattr(confirmation_module, "imgui", imgui)

    UnitAttackConfirmation(SimpleNamespace(pending=set())).render(SimpleNamespace())

    opened.assert_not_called()
