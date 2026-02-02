import arcade
import threading
from typing import Callable, Any
from src.client.services.imgui_service import ImGuiService
from src.client.ui.composer import UIComposer
from src.client.ui.theme import GAMETHEME
from src.client.interfaces.loading import LoadingTask

class LoadingView(arcade.View):
    def __init__(self, 
                 task: LoadingTask, 
                 on_success: Callable[[Any], arcade.View],
                 on_failure: Callable[[Exception], None] | None = None):
        
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

        self._finalizing_frame_rendered = False 

    def on_show_view(self):
        # We use a transparent/dark bg so it looks nice if the renderer is missing
        self.window.background_color = (10, 10, 10, 255)
        self.thread.start()

    def _worker(self):
        try:
            self.result = self.task.run()
        except Exception as e:
            self.error = e
        finally:
            self.is_finished = True

    def on_update(self, delta_time: float):
        # If thread is done...
        if self.is_finished:
            if self.error:
                if self.on_failure: self.on_failure(self.error)
                else: raise self.error
            else:
                # Delay switching by 1 frame to allow "100%" text to render
                if not self._finalizing_frame_rendered:
                    self.task.status_text = "Finalizing Graphics..."
                    self.task.progress = 1.0
                    self._finalizing_frame_rendered = True
                    return 

                # Switch Views
                next_view = self.on_success(self.result)
                if next_view:
                    self.window.show_view(next_view)

    def on_resize(self, width: int, height: int):
        self.imgui.resize(width, height)

    def on_draw(self):
        self.clear()
        
        # 1. Start ImGui
        self.imgui.new_frame()
        self.ui.setup_frame()

        # 2. Render Background Globe (If available)
        # This keeps the visualization consistent during transition
        if hasattr(self.window, "shared_renderer") and self.window.shared_renderer:
            # CRITICAL: Reset OpenGL state
            ctx = self.window.ctx
            ctx.scissor = None
            ctx.viewport = (0, 0, self.window.width, self.window.height)
            ctx.enable_only((ctx.DEPTH_TEST, ctx.BLEND))
            
            # Draw the globe (reuses existing camera position)
            self.window.shared_renderer.draw()

        # 3. Render Loading UI
        screen_w, screen_h = self.window.get_size()
        
        if self.ui.begin_centered_panel("Loader", screen_w, screen_h, w=400, h=150):
            self.ui.draw_title("PROCESSING")
            self.ui.draw_progress_bar(self.task.progress, self.task.status_text)
            
            if self.error:
                from imgui_bundle import imgui
                imgui.text_colored(GAMETHEME.colors.error, "OPERATION FAILED")

            self.ui.end_panel()

        self.imgui.render()