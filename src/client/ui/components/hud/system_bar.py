from imgui_bundle import imgui

class SystemBar:
    def render(self, net_client, nav_service):
        viewport = imgui.get_main_viewport()
        pad_x, pad_y = 10.0, 10.0

        # Anchor Top-Right
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
            font_size = imgui.get_font_size()
            btn_size = (font_size * 4.5, font_size * 1.6)
            
            if imgui.button("SAVE", btn_size):
                net_client.request_save()
            
            imgui.same_line()
            
            if imgui.button("LOAD", btn_size):
                if hasattr(net_client, 'session'):
                    nav_service.show_load_game_screen(net_client.session.config)
            
            imgui.same_line()
            
            if imgui.button("MENU", btn_size):
                if hasattr(net_client, 'session'):
                    nav_service.show_main_menu(net_client.session, net_client.session.config)

            imgui.end()