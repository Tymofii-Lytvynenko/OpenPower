import ctypes
import os
from pathlib import Path
from typing import List

# We import the package itself to find its installation path
import imgui_bundle
from imgui_bundle import imgui, icons_fontawesome_6

class FontLoader:
    """
    Manages loading of TrueType fonts and merging icon sets.
    """
    
    # Static storage to prevent Garbage Collection of C-arrays
    _keep_alive_storage: List[ctypes.Array] = []

    @staticmethod
    def get_imgui_bundle_assets_path() -> str:
        """
        Reliably finds the 'assets' folder inside the installed imgui_bundle package.
        """
        package_dir = os.path.dirname(imgui_bundle.__file__)
        assets_path = os.path.join(package_dir, "assets")
        
        if not os.path.exists(assets_path):
            print(f"[FontLoader] CRITICAL: Could not find assets at {assets_path}")
            
        return assets_path

    @staticmethod
    def load_primary_font(io, font_path: Path, size_pixels: float = 16.0, load_cjk: bool = False, load_icons: bool = True):
        """
        Loads the main UI font and optionally merges CJK characters and FontAwesome icons.
        
        Includes robust error handling for Python binding quirks.
        """
        if not font_path.exists():
            print(f"[FontLoader] Warning: Font not found at {font_path}. Using ImGui Default.")
            return

        print(f"[FontLoader] Loading primary font: {font_path.name} ({size_pixels:.1f}px)")
        
        # 1. Clear existing fonts
        io.fonts.clear()

        # 2. Setup Ranges for Main Font (Latin + Cyrillic)
        ranges_list = [
            0x0020, 0x00FF, # Basic Latin + Supplement
            0x0400, 0x052F, # Cyrillic + Supplement
            0 # Null Terminator
        ]
        
        RangeArrayType = ctypes.c_ushort * len(ranges_list)
        c_ranges = RangeArrayType(*ranges_list)
        FontLoader._keep_alive_storage.append(c_ranges)
        ranges_ptr = ctypes.addressof(c_ranges)

        # 3. Configure Main Font
        font_cfg = imgui.ImFontConfig()
        font_cfg.oversample_h = 2
        font_cfg.oversample_v = 1
        font_cfg.pixel_snap_h = True
        
        # --- Attempt to set ranges on config (May fail in some bindings) ---
        try:
            font_cfg.glyph_ranges = ranges_ptr # type: ignore
        except AttributeError:
            pass # Binding does not expose this field

        # 4. Load Base Font
        # We try strict 4-arg signature first, then fallback to 3-arg
        try:
            io.fonts.add_font_from_file_ttf(str(font_path), size_pixels, font_cfg, ranges_ptr)
        except TypeError:
            # Fallback for bindings that strictly enforce 3 arguments
            print("[FontLoader] Warning: 4-arg AddFont signature failed. Loading without explicit ranges.")
            io.fonts.add_font_from_file_ttf(str(font_path), size_pixels, font_cfg)

        # 5. Optional Merges
        if load_cjk:
            FontLoader._merge_cjk(io, str(font_path), size_pixels)

        if load_icons:
            FontLoader._merge_icons(io, size_pixels)

    @staticmethod
    def _merge_cjk(io, font_path_str: str, size_pixels: float):
        try:
            merge_cfg = imgui.ImFontConfig()
            merge_cfg.merge_mode = True 
            merge_cfg.pixel_snap_h = True
            
            cjk_ranges = 0
            if hasattr(io.fonts, "get_glyph_ranges_chinese_full"):
                cjk_ranges = io.fonts.get_glyph_ranges_chinese_full()
            
            try:
                io.fonts.add_font_from_file_ttf(font_path_str, size_pixels, merge_cfg, cjk_ranges)
                print("[FontLoader] CJK Glyphs merged.")
            except TypeError:
                # Fallback if 4-arg fails
                io.fonts.add_font_from_file_ttf(font_path_str, size_pixels, merge_cfg)
                
        except Exception as e:
            print(f"[FontLoader] Skipped CJK merge: {e}")

    @staticmethod
    def _merge_icons(io, size_pixels: float):
        try:
            # 1. Setup Config for Icons
            icon_cfg = imgui.ImFontConfig()
            icon_cfg.merge_mode = True 
            icon_cfg.pixel_snap_h = True
            icon_cfg.glyph_offset = imgui.ImVec2(0, 0)
            
            # 2. Define Ranges
            icon_ranges = [icons_fontawesome_6.ICON_MIN_FA, icons_fontawesome_6.ICON_MAX_FA, 0]
            IconRangeType = ctypes.c_ushort * len(icon_ranges)
            c_icon_ranges = IconRangeType(*icon_ranges)
            FontLoader._keep_alive_storage.append(c_icon_ranges)
            icon_ranges_ptr = ctypes.addressof(c_icon_ranges)
            
            # Try to set on config
            try:
                icon_cfg.glyph_ranges = icon_ranges_ptr # type: ignore
            except AttributeError:
                pass

            # 3. Locate FontAwesome .ttf
            assets_path = FontLoader.get_imgui_bundle_assets_path()
            icon_font_path = os.path.join(assets_path, "fonts", "fontawesome-webfont.ttf")
            
            if os.path.exists(icon_font_path):
                icon_size = size_pixels * 0.9 
                
                try:
                    io.fonts.add_font_from_file_ttf(icon_font_path, icon_size, icon_cfg, icon_ranges_ptr)
                    print(f"[FontLoader] Icons merged from: {icon_font_path}")
                except TypeError:
                     # Fallback: Load without ranges (Icons might not show, but app won't crash)
                    io.fonts.add_font_from_file_ttf(icon_font_path, icon_size, icon_cfg)
                    print(f"[FontLoader] Icons merged (Fallback Mode): {icon_font_path}")
            else:
                print(f"[FontLoader] ERROR: Icon font file missing at: {icon_font_path}")

        except Exception as e:
            print(f"[FontLoader] Failed to load Icons: {e}")