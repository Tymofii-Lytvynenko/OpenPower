from imgui_bundle import imgui
from src.client.ui.composer import UIComposer
from src.client.services.network_client_service import NetworkClient

class SystemBar:
    def render(self, composer: UIComposer, net: NetworkClient, nav_service):
        viewport = imgui.get_main_viewport()
        
        # Padding from edges
        pad_x, pad_y = 10.0, 10.0

        # Anchor: TOP-RIGHT
        # We set pivot to (1, 0) -> (Right, Top)
        # Then position at (ScreenW - Pad, Pad)
        imgui.set_next_window_pos(
            imgui.ImVec2(viewport.size.x - pad_x, pad_y), 
            imgui.Cond_.always, 
            imgui.ImVec2(1.0, 0.0) 
        )
        
        flags = (imgui.WindowFlags_.no_decoration | 
                 imgui.WindowFlags_.no_move | 
                 imgui.WindowFlags_.always_auto_resize |
                 imgui.WindowFlags_.no_background)

        if imgui.begin("##System_Bar", True, flags):
            try:
                # Calculate button size relative to font size for DPI support
                font_size = imgui.get_font_size()
                btn_w = font_size * 4.5
                btn_h = font_size * 1.6
                btn_size = (btn_w, btn_h)
                
                # SAVE
                if imgui.button("SAVE", btn_size):
                    net.request_save()
                
                imgui.same_line()
                
                # LOAD
                if imgui.button("LOAD", btn_size):
                    if hasattr(net, 'session'):
                        nav_service.show_load_game_screen(net.session.config)
                
                imgui.same_line()
                
                # MENU
                if imgui.button("MENU", btn_size):
                    if hasattr(net, 'session'):
                        nav_service.show_main_menu(net.session.config)

            except Exception as e:
                print(f"[SystemBar] Error: {e}")
            finally:
                imgui.end()
        else:
            imgui.end()