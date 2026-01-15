import arcade
import threading
from typing import Callable, Any
from src.client.services.imgui_service import ImGuiService
from src.client.ui.composer import UIComposer
from src.client.ui.theme import GAMETHEME
from src.client.interfaces.loading import LoadingTask

class LoadingView(arcade.View):
    """
    A generic loading screen.
    Can be used for Startup, Level Loading, Save Loading, etc.
    """
    def __init__(self, 
                 task: LoadingTask, 
                 on_success: Callable[[Any], arcade.View],
                 on_failure: Callable[[Exception], None] = None):
        
        super().__init__()
        self.task = task
        self.on_success = on_success
        self.on_failure = on_failure
        
        self.imgui = ImGuiService(self.window)
        self.ui = UIComposer(GAMETHEME)
        
        # Threading Logic
        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.is_finished = False
        self.result = None
        self.error = None

    def on_show_view(self):
        # Removed hardcoded arcade.color.BLACK
        self.window.background_color = GAMETHEME.col_black
        self.thread.start()

    def _worker(self):
        """Runs the generic task in background."""
        try:
            self.result = self.task.run()
        except Exception as e:
            self.error = e
        finally:
            self.is_finished = True

    def on_update(self, delta_time: float):
        if self.is_finished:
            if self.error:
                print(f"[LoadingView] Task Failed: {self.error}")
                if self.on_failure:
                    self.on_failure(self.error)
                else:
                    # Default error handling: Crash to console
                    raise self.error
            else:
                # Success: Delegate to the callback to create the next view
                next_view = self.on_success(self.result)
                self.window.show_view(next_view)

    def on_resize(self, width: int, height: int):
        self.imgui.resize(width, height)

    def on_draw(self):
        self.clear()
        self.imgui.new_frame()
        self.ui.setup_frame()

        screen_w, screen_h = self.window.get_size()
        
        # Draw the universal loader panel
        if self.ui.begin_centered_panel("Loader", screen_w, screen_h, w=400, h=150):
            
            self.ui.draw_title("PROCESSING")
            
            # Read properties from the abstract task
            self.ui.draw_progress_bar(self.task.progress, self.task.status_text)
            
            if self.error:
                from imgui_bundle import imgui
                imgui.text_colored(GAMETHEME.col_error, "OPERATION FAILED")

            self.ui.end_panel()

        self.imgui.render()