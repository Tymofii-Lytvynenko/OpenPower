"""Source-sized confirmations for queued movement into neutral territory."""
from src.client.ui.core.containers import WindowManager
from src.client.ui.core.gml_widgets import GMLWidgets
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.panels.shared.panel_data import resolve_country_name


class UnitAttackConfirmation:
    def __init__(self, orders):
        self.orders = orders

    def render(self, state):
        size = imgui.get_io().display_size
        for index, country in enumerate(tuple(self.orders.pending)):
            with WindowManager.window("Confirm attack###" + country,
                                      x=(size.x - 225) / 2 + index * 16,
                                      y=(size.y - 144) / 2 + index * 16,
                                      flags=imgui.WindowFlags_.no_title_bar, padding=(0, 0),
                                      closable=False, gml_template="Unit_Attack_Confirm_Window",
                                      test_id="unit.attack.confirm." + country):
                ui = GMLWidgets("Unit_Attack_Confirm_Window")
                ui.text("txtTransparentLabel1", "Confirm military order")
                imgui.text_wrapped("You are entering the territory of",
                                   gml_id=ui.path("txtTransparentLabel2"))
                ui.text("txtCountry", resolve_country_name(state, country), test_id="unit.attack.country." + country)
                ui.text("txtTransparentLabel3", "This will declare war.")
                if ui.button("btnYes", "YES", "unit.attack.yes." + country):
                    self.orders.confirm(country)
                if ui.button("btnNo", "NO", "unit.attack.no." + country):
                    self.orders.cancel(country)
