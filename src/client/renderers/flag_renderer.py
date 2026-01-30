import arcade
import arcade.gl
import ctypes
from pathlib import Path
from typing import Dict, Optional, Any
from PIL import Image
from imgui_bundle import imgui

class FlagTexture:
    """
    Wrapper to hold both the GL Object (to prevent Garbage Collection) 
    and the ID for ImGui.
    """
    def __init__(self, gl_obj: Any, gl_id: int, width: int, height: int):
        self.gl_obj = gl_obj  # CRITICAL: Holding this prevents the GPU from deleting the texture
        self.gl_id = gl_id
        self.width = width
        self.height = height

class FlagRenderer:
    """
    Manages loading, caching, and rendering of Country Flags.
    Encapsulates the specific ImGui image binding logic to decouple UI components
    from OpenGL/ImGui type casting complexities.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(FlagRenderer, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized: return
        
        current_path = Path(__file__).resolve()
        self.project_root = current_path
        # Traverse up to find the root
        for parent in current_path.parents:
            if (parent / "modules").exists():
                self.project_root = parent
                break
        
        self.flags_dir = self.project_root / "modules" / "base" / "assets" / "flags"
        self._cache: Dict[str, Optional[FlagTexture]] = {}
        self._fallback_tag = "XXX"
        self._error_printed = False # To prevent console spam on rendering failures
        self._initialized = True
        
        self._emergency_texture = self._create_emergency_texture()
        print(f"[FlagRenderer] Memory Persistence Mode. Flags at: {self.flags_dir}")

    def draw_flag(self, tag: str, width: float, height: float):
        """
        Public API to draw a flag in the current ImGui window.
        Handles lookup, fallback to emergency texture, and ImGui rendering.
        """
        texture = self.get_texture(tag)
        
        # If even the emergency texture fails, just draw a dummy box to preserve layout
        if not texture or texture.gl_id <= 0:
            imgui.dummy(imgui.ImVec2(width, height))
            return

        self._render_imgui_image(texture.gl_id, width, height)

    def _render_imgui_image(self, gl_id: int, w: float, h: float):
        """
        Internal helper: Attempts to render an image using multiple ImGui type casting strategies.
        This is necessary because imgui_bundle bindings can vary regarding how they accept
        raw OpenGL texture IDs (int vs ImTextureID vs ImTextureRef).
        """
        size = imgui.ImVec2(w, h)
        
        # ATTEMPT 1: Strict Binding Cast (ImTextureRef)
        # Some bindings require a specific reference object wrapper.
        try:
            if hasattr(imgui, "ImTextureRef"):
                tex_ref = imgui.ImTextureRef(gl_id) 
                imgui.image(tex_ref, size)
                return
        except Exception:
            pass

        # ATTEMPT 2: Fallback to ImTextureID (Standard ImGui name)
        try:
            if hasattr(imgui, "ImTextureID"):
                tex_id = imgui.ImTextureID(gl_id)
                imgui.image(tex_id, size)
                return
        except Exception:
            pass

        # ATTEMPT 3: Standard Int (Python dynamic typing)
        # Sometimes the bindings are smart enough to take a raw int.
        try:
            imgui.image(gl_id, size)
            return
        except TypeError:
            pass
            
        # ATTEMPT 4: Void Pointer (ctypes)
        # The lowest level approach: passing a raw C pointer.
        try:
            ptr = ctypes.c_void_p(gl_id)
            imgui.image(ptr, size)
            return
        except TypeError:
            pass

        # If we reach here, report strict error only once to avoid lag
        if not self._error_printed:
            print(f"[FlagRenderer] FAILED all cast attempts for ID {gl_id}.")
            self._error_printed = True
            
        # Draw placeholder text so the user knows something broke
        imgui.text("IMG_ERR")

    def _create_emergency_texture(self) -> Optional[FlagTexture]:
        """Creates a magenta square for missing assets."""
        try:
            img = Image.new('RGBA', (32, 32), (255, 0, 255, 255))
            return self._upload_to_gpu(img, "EMERGENCY")
        except Exception:
            return None

    def _upload_to_gpu(self, image: Image.Image, label: str) -> Optional[FlagTexture]:
        """
        Uploads PIL image and returns a wrapper that PROTECTS the texture from GC.
        """
        try:
            window = arcade.get_window()
            ctx = window.ctx
            
            # 1. Create Texture
            gl_texture = ctx.texture(
                (image.width, image.height),
                components=4,
                data=image.tobytes()
            )
            
            # 2. Configure for ImGui (No Mipmaps for crisp pixel art flags)
            gl_texture.filter = (ctx.LINEAR, ctx.LINEAR)
            
            # 3. Extract ID robustly (handle different Arcade versions)
            raw_glo = getattr(gl_texture, "glo", None)
            tex_id = 0
            
            if raw_glo is not None:
                if hasattr(raw_glo, "glo_id"): 
                    tex_id = int(raw_glo.glo_id)
                elif hasattr(raw_glo, "value"): 
                    tex_id = int(raw_glo.value)
                else:
                    tex_id = int(raw_glo)

            if tex_id == 0:
                return None
            
            # Return wrapper to keep gl_texture alive in self._cache
            return FlagTexture(gl_texture, tex_id, image.width, image.height)

        except Exception as e:
            print(f"[FlagRenderer] GPU Upload Error ({label}): {e}")
            return None

    def get_texture(self, tag: str) -> Optional[FlagTexture]:
        """Retrieves a texture from cache or loads it from disk."""
        if tag in self._cache:
            return self._cache[tag]

        clean_tag = tag.strip()
        flag_path = self.flags_dir / f"{clean_tag}.png"
        
        # Try exact match, then lowercase, then fallback
        if not flag_path.exists():
            lower_path = self.flags_dir / f"{clean_tag.lower()}.png"
            if lower_path.exists(): 
                flag_path = lower_path
            else: 
                flag_path = self.flags_dir / f"{self._fallback_tag}.png"

        if not flag_path.exists():
            return self._emergency_texture

        try:
            with Image.open(flag_path) as img:
                img = img.convert("RGBA")
                texture = self._upload_to_gpu(img, tag)
                if texture:
                    self._cache[tag] = texture
                    return texture
                return self._emergency_texture
        except Exception as e:
            print(f"[FlagRenderer] Load Error {tag}: {e}")
            return self._emergency_texture

    def clear_cache(self):
        self._cache.clear()