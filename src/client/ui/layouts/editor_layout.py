from imgui_bundle import imgui
from src.client.ui.core.theme import GAMETHEME

class EditorLayout:
    def __init__(self, net_client, viewport_ctrl):
        self.net = net_client
        self.viewport_ctrl = viewport_ctrl
        self.current_layer_label = "Political"
        self.layer_map = {"Political": "political", "Terrain": "terrain"}

    def get_current_render_mode(self):
        return self.layer_map.get(self.current_layer_label, "political")

    def render(self, fps: float):
        GAMETHEME.apply()
        
        # Main Menu Bar
        if imgui.begin_main_menu_bar():
            if imgui.begin_menu("File"):
                # FIX: Explicitly pass p_selected=False to satisfy signature
                if imgui.menu_item("Save Map", "Ctrl+S", False)[0]:
                    self.net.request_save()
                imgui.end_menu()
            
            if imgui.begin_menu("View"):
                if imgui.begin_combo("Layer", self.current_layer_label):
                    for label in self.layer_map:
                        if imgui.selectable(label, label == self.current_layer_label)[0]:
                            self.current_layer_label = label
                    imgui.end_combo()
                imgui.end_menu()
            imgui.end_main_menu_bar()

        # FPS Overlay
        imgui.set_next_window_pos((10, 50))
        if imgui.begin("##Overlay", True, imgui.WindowFlags_.no_decoration | imgui.WindowFlags_.always_auto_resize | imgui.WindowFlags_.no_background):
            imgui.text_colored(GAMETHEME.colors.positive, f"FPS: {fps:.0f}")
        imgui.end()