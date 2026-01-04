# src/client/ui/editor_layout.py
from imgui_bundle import imgui

class EditorLayout:
    """
    Handles the high-level layout of the Editor UI panels.
    Follows Composition over Inheritance: EditorView delegates UI rendering to this class.
    """
    def __init__(self):
        pass

    def render(self, selected_region_id: int | None, fps: float):
        """
        Draws all active editor panels.
        
        Args:
            selected_region_id: The ID of the currently selected region (or None).
            fps: Current frames per second for debug info.
        """
        self._render_main_menu()
        self._render_inspector(selected_region_id)
        self._render_debug_info(fps)

    def _render_main_menu(self):
        if imgui.begin_main_menu_bar():
            if imgui.begin_menu("File"):
                if imgui.menu_item("Save Map", "Ctrl+S")[0]:
                    print("Save requested (not implemented)")
                if imgui.menu_item("Exit", "Alt+F4")[0]:
                    print("Exit requested")
                imgui.end_menu()
            
            if imgui.begin_menu("View"):
                imgui.menu_item("Toggle Grid")
                imgui.end_menu()
                
            imgui.end_main_menu_bar()

    def _render_inspector(self, region_id: int | None):
        """
        Displays details about the selected region.
        """
        # Set a fixed position/size for the first run, or let the user float it
        imgui.set_next_window_size((300, 400), imgui.Cond.first_use_ever)
        
        if imgui.begin("Region Inspector"):
            if region_id is not None:
                imgui.text_colored((0.2, 1.0, 0.2, 1.0), f"SELECTED REGION ID: {region_id}")
                imgui.separator()
                
                # Placeholder for future data editing
                imgui.text("Ownership: Neutral")
                imgui.text("Population: 0")
                
                if imgui.button("Claim Region"):
                    print(f"Logic to claim region {region_id}")
            else:
                imgui.text_disabled("No region selected.")
                imgui.text_wrapped("Click on the map to inspect a region.")
        
        imgui.end()

    def _render_debug_info(self, fps: float):
        """Simple overlay for performance stats."""
        bg_flags = imgui.WindowFlags.no_decoration | imgui.WindowFlags.always_auto_resize | imgui.WindowFlags.no_saved_settings | imgui.WindowFlags.no_focus_on_appearing | imgui.WindowFlags.no_nav
        
        # Position in top-right corner
        viewport = imgui.get_main_viewport()
        work_pos = viewport.work_pos
        work_size = viewport.work_size
        pad = 10.0
        
        pos = (work_pos.x + work_size.x - pad, work_pos.y + pad + 20) # +20 to avoid menu bar
        pivot = (1.0, 0.0)
        
        imgui.set_next_window_pos(pos, imgui.Cond.always, pivot)
        imgui.set_next_window_bg_alpha(0.35)
        
        if imgui.begin("DebugOverlay", flags=bg_flags):
            imgui.text(f"FPS: {fps:.1f}")
            imgui.text("Mode: Editor")
        imgui.end()