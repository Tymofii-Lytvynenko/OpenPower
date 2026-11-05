"""Compose the source map-attached frames without consuming map input."""
from src.client.renderers.flag_renderer import FlagRenderer
from src.client.ui.core.containers import WindowManager
from src.client.ui.core.gml_widgets import GMLWidgets
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.layouts.gml_layout import active_gml_layout
from src.client.ui.panels.military.map_information import selected_unit_composition, region_control


class MapInformationWindows:
    def __init__(self, viewer):
        self.viewer = viewer
        self._flags = FlagRenderer()

    @staticmethod
    def _flags_for_frame():
        return (imgui.WindowFlags_.no_decoration | imgui.WindowFlags_.no_inputs
                | imgui.WindowFlags_.no_focus_on_appearing | imgui.WindowFlags_.no_bring_to_front_on_focus
                | imgui.WindowFlags_.no_scrollbar | imgui.WindowFlags_.no_scroll_with_mouse)

    def render_selected_unit(self, state, selected_ids, get_projected, viewport_height, *, dragging=False):
        if dragging or len(selected_ids) != 1:
            return
        unit_id = next(iter(selected_ids))
        projected = get_projected(unit_id)
        values = selected_unit_composition(state, unit_id, self.viewer)
        if projected is None or values is None:
            return
        x = projected.screen_x + projected.width / 2 + 8
        y = viewport_height - projected.screen_y - projected.height / 2
        with WindowManager.window("Unit composition", x=x, y=y, flags=self._flags_for_frame(),
                                  closable=False, gml_template="Small_Unit_Info_Window",
                                  test_id="unit.map.composition", padding=(0, 0), follow_position=True):
            # The source's eleven-pixel rows need a smaller font than normal panels.
            style = imgui.get_style()
            scale = max(.1, float(style.font_scale_main) * float(style.font_scale_dpi))
            imgui.push_font(None, 10.0 / scale)
            try:
                ui = GMLWidgets("Small_Unit_Info_Window")
                for category, name in (("I", "Infantry"), ("G", "Ground"), ("N", "Naval"), ("A", "Air")):
                    ui.text("lbl" + category, category)
                    quantity = values.quantities[category]
                    ui.text("txt" + category, f"{quantity:,}".replace(",", " ") if quantity is not None else "?",
                            right=True, test_id="unit.map.quantity." + category)
                    ui.meter(f"frm{category}/frm{name}", values.fractions[category], (.25, .65, .9, 1))
            finally:
                imgui.pop_font()

    def render_region(self, state, region_id, mouse_position, *, active=False):
        values = region_control(state, region_id) if active else None
        if values is None:
            return
        style = imgui.get_style()
        scale = max(.1, float(style.font_scale_main) * float(style.font_scale_dpi))
        imgui.push_font(None, 12.0 / scale)
        try:
            width = max(145.0, imgui.calc_text_size(values.name).x + 14,
                        imgui.calc_text_size(values.political_name).x + 126,
                        imgui.calc_text_size(values.military_name).x + 126)
        finally:
            imgui.pop_font()
        x, y = mouse_position
        # The transient control frame belongs above map annotations, without taking focus.
        with WindowManager.window("Region control", x=x + 16, y=y - 16,
                                  flags=self._flags_for_frame() | imgui.WindowFlags_.tooltip,
                                  closable=False, gml_template="Sphere_Control_Window",
                                  test_id="map.region_control", padding=(0, 0), follow_position=True,
                                  size_override=(width, 56)):
            ui = GMLWidgets("Sphere_Control_Window")
            session = active_gml_layout()
            width = session.window_size[0]
            # REFERENCE UpdateSize grows these fields together to the longest live name.
            session.resize_component(ui.path("lblRegion"), width=width - 4)
            ui.text("lblRegion", values.name, test_id="map.region_control.region")
            for slot, caption, tag, name in (("Politic", "Political", values.political_tag, values.political_name),
                                            ("Military", "Military", values.military_tag, values.military_name)):
                session.resize_component(ui.path(f"frm{slot}Country"), width=width - 95)
                session.resize_component(ui.path(f"frm{slot}Country/lblCountry"), width=width - 120)
                ui.text("lblPolitical" if slot == "Politic" else "lblMilitary", caption)
                ui.picture(f"frm{slot}Country/picFlag", lambda w, h, country=tag: self._flags.draw_flag(country, w, h))
                ui.text(f"frm{slot}Country/lblCountry", name, test_id="map.region_control." + slot.lower())
