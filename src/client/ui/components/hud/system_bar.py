from imgui_bundle import imgui
from src.client.ui.composer import UIComposer
from src.client.services.network_client_service import NetworkClient

class SystemBar:
    def render(self, composer: UIComposer, net: NetworkClient, nav_service):
        vp_w = imgui.get_main_viewport().size.x
        
        # Position: Top-Right
        imgui.set_next_window_pos((vp_w - 260, 10))
        
        flags = (imgui.WindowFlags_.no_decoration | 
                 imgui.WindowFlags_.no_move | 
                 imgui.WindowFlags_.always_auto_resize |
                 imgui.WindowFlags_.no_background)

        if imgui.begin("##System_Bar", True, flags):
            try:
                btn_size = (70, 25)
                
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