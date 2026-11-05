import pytest

from src.client.ui.core.formatting import format_currency, format_signed_currency
from src.client.ui.panels.budget_panel import BudgetPanel
from src.client.ui.panels.economic_health_panel import EconomicHealthPanel
from src.client.ui.panels.economy_panel import EconomyPanel
from src.client.ui.panels.military.unit_market_panel import UnitMarketPanel
from src.client.ui.panels.military.unit_production_panel import UnitProductionPanel


@pytest.mark.parametrize(
    ("value", "ordinary", "signed"),
    [(1234, "$ 1 234", "$ 1 234"), (-1234, "$ -1 234", "$ - 1 234"), (0, "$ 0", "$ 0")],
)
def test_currency_styles_preserve_each_panel_convention(value, ordinary, signed):
    assert format_currency(value) == ordinary
    assert format_signed_currency(value) == signed
    assert EconomyPanel._fmt_money(value) == ordinary
    assert UnitMarketPanel._format_money(value) == ordinary
    assert BudgetPanel._fmt_money(None, value) == signed
    assert EconomicHealthPanel._fmt_money(None, value) == signed
    assert UnitProductionPanel._format_money(value) == format_currency(max(0.0, value))
