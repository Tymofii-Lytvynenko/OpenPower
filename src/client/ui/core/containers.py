from contextlib import contextmanager
from typing import Optional
from imgui_bundle import imgui

class WindowManager:
    """
    Context manager for creating ImGui windows.
    """
    
    @staticmethod
    @contextmanager
    def window(title: str, x: float = 0, y: float = 0, w: float = 300, h: float = 400, 
               closable: bool = True, flags=0):
        """
        Creates a standard panel window.
        Yields 'True' if the window is open and expanded.
        """
        imgui.set_next_window_pos((x, y), imgui.Cond_.first_use_ever)
        imgui.set_next_window_size((w, h), imgui.Cond_.first_use_ever)
        
        final_flags = flags | imgui.WindowFlags_.no_collapse

        expanded, opened = imgui.begin(title, closable, final_flags)
        
        try:
            # Yield 'opened' state to caller so they know if 'X' was clicked
            if expanded:
                yield opened
            else:
                # Still yield opened state even if collapsed, so we can detect close
                yield opened
        finally:
            imgui.end()

    @staticmethod
    @contextmanager
    def popup(title: str):
        if imgui.begin_popup(title):
            try:
                yield
            finally:
                imgui.end_popup()

    @staticmethod
    @contextmanager
    def centered_modal(name: str, sw: float, sh: float, w: float = 300, h: float = 400):
        pos_x = (sw - w) / 2
        pos_y = (sh - h) / 2
        
        imgui.set_next_window_pos((pos_x, pos_y))
        imgui.set_next_window_size((w, h))
        
        flags = (imgui.WindowFlags_.no_title_bar | 
                 imgui.WindowFlags_.no_resize | 
                 imgui.WindowFlags_.no_move)
        
        if imgui.begin(name, None, flags):
            try:
                yield
            finally:
                imgui.end()