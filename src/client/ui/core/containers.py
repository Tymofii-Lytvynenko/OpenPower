from contextlib import contextmanager
from typing import Optional
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.testability import semantic_region

class WindowManager:
    """
    Context manager for creating ImGui windows.
    """
    
    @staticmethod
    @contextmanager
    def window(title: str, x: float = 0, y: float = 0, w: float = 300, h: float = 400, 
               closable: bool = True, flags=0, test_id: str | None = None):
        """
        Creates a standard panel window.
        Yields 'True' if the window is open and expanded.
        """
        viewport = imgui.get_io().display_size
        # Panels authored on a wide desktop must remain reachable on smaller
        # viewports; overflowing content remains accessible through scrolling.
        if viewport.x > 0 and viewport.y > 0:
            w, h = min(w, viewport.x), min(h, viewport.y)
            x, y = max(0, min(x, viewport.x - w)), max(0, min(y, viewport.y - h))
        imgui.set_next_window_pos((x, y), imgui.Cond_.first_use_ever)
        imgui.set_next_window_size((w, h), imgui.Cond_.first_use_ever)
        
        final_flags = flags | imgui.WindowFlags_.no_collapse

        expanded, opened = imgui.begin(title, closable, final_flags)
        
        try:
            # Yield 'opened' state to caller so they know if 'X' was clicked
            if test_id is not None:
                with semantic_region(test_id, title, visible=opened and expanded):
                    yield opened
            else:
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
                 imgui.WindowFlags_.no_move)
        
        if imgui.begin(name, None, flags):
            try:
                yield
            finally:
                imgui.end()
