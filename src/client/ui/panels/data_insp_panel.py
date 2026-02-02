import polars as pl
import dataclasses
from imgui_bundle import imgui

# Base Architecture
from src.client.ui.panels.base_panel import BasePanel
from src.client.ui.composer import UIComposer
from src.client.ui.theme import GAMETHEME
from src.server.state import GameState

class DataInspectorPanel(BasePanel):
    """
    A debugging tool to visualize the raw Polars DataFrames AND Python Objects/Dataclasses
    stored in GameState.
    """
    def __init__(self):
        # Position: Centered-ish, large window
        super().__init__("DATA INSPECTOR", x=300, y=100, w=1000, h=700)
        
        self.selected_key = None
        self.row_limit = 50 

    def _render_content(self, composer: UIComposer, state: GameState, **kwargs):
        """
        Renders the internal debug view.
        BasePanel handles the Window Begin/End.
        """
        
        # --- 1. Aggregation of Inspectable Data ---
        # We combine Tables, Globals, and specific Attributes into one list
        inspectables = {}
        
        # Add Attributes (like Time)
        if hasattr(state, "time"):
            inspectables["[Obj] Time"] = state.time

        # Add DataFrames
        if hasattr(state, "tables"):
            for name, df in state.tables.items():
                inspectables[f"[Table] {name}"] = df
        
        # Add Globals
        if hasattr(state, "globals") and isinstance(state.globals, dict):
            for k, v in state.globals.items():
                inspectables[f"[Global] {k}"] = v

        item_keys = sorted(list(inspectables.keys()))

        # --- 2. Control Header ---
        if not item_keys:
            imgui.text_disabled("GameState is empty.")
        else:
            # Default selection
            if self.selected_key not in inspectables:
                self.selected_key = item_keys[0]

            # Selector
            imgui.align_text_to_frame_padding()
            imgui.text("Target:")
            imgui.same_line()
            imgui.set_next_item_width(250)
            
            # Ensure we pass a string, even if selected_key is None
            preview_val = self.selected_key if self.selected_key else ""
            
            if imgui.begin_combo("##InspectorSel", preview_val):
                for key in item_keys:
                    is_selected = (key == self.selected_key)
                    if imgui.selectable(key, is_selected)[0]:
                        self.selected_key = key
                    if is_selected:
                        imgui.set_item_default_focus()
                imgui.end_combo()

            # Get selected object
            data = inspectables.get(self.selected_key)

            # Show specific controls based on type
            if isinstance(data, pl.DataFrame):
                imgui.same_line()
                imgui.text_disabled("|")
                imgui.same_line()
                imgui.set_next_item_width(150)
                _, self.row_limit = imgui.slider_int("Row Limit", self.row_limit, 10, 1000)
                imgui.same_line()
                imgui.text_colored(GAMETHEME.colors.info, f"Shape: {data.shape}")
            
            elif dataclasses.is_dataclass(data):
                imgui.same_line()
                imgui.text_colored(GAMETHEME.colors.politics, "Type: Dataclass")

            elif isinstance(data, dict):
                imgui.same_line()
                imgui.text_colored(GAMETHEME.colors.politics, f"Type: Dict ({len(data)} keys)")

        imgui.separator()

        # --- 3. Render Content ---
        if self.selected_key and self.selected_key in inspectables:
            target_data = inspectables[self.selected_key]
            
            if isinstance(target_data, pl.DataFrame):
                self._render_dataframe(target_data)
            elif dataclasses.is_dataclass(target_data):
                self._render_dataclass(target_data)
            elif isinstance(target_data, dict):
                self._render_dict(target_data)
            else:
                self._render_generic_object(target_data)

    def _render_dataframe(self, df: pl.DataFrame):
        """Renders Polars DataFrame."""
        columns = df.columns
        num_cols = len(columns)
        
        if num_cols == 0:
            imgui.text_disabled("Empty DataFrame.")
            return

        flags = (imgui.TableFlags_.scroll_y | 
                 imgui.TableFlags_.borders | 
                 imgui.TableFlags_.row_bg | 
                 imgui.TableFlags_.resizable | 
                 imgui.TableFlags_.reorderable | 
                 imgui.TableFlags_.hideable)

        if imgui.begin_table("DfGrid", num_cols, flags):
            for col in columns:
                imgui.table_setup_column(col)
            imgui.table_headers_row()

            display_df = df.head(self.row_limit)
            for row in display_df.iter_rows():
                imgui.table_next_row()
                for val in row:
                    imgui.table_next_column()
                    self._draw_value(val)
            imgui.end_table()

    def _render_dataclass(self, obj):
        """Renders a Python Dataclass as a 2-column table."""
        fields = dataclasses.fields(obj)
        
        flags = (imgui.TableFlags_.borders | 
                 imgui.TableFlags_.row_bg | 
                 imgui.TableFlags_.resizable)

        if imgui.begin_table("DcGrid", 2, flags):
            imgui.table_setup_column("Field", imgui.TableColumnFlags_.width_fixed, 150)
            imgui.table_setup_column("Value", imgui.TableColumnFlags_.width_stretch)
            imgui.table_headers_row()

            for field in fields:
                val = getattr(obj, field.name)
                imgui.table_next_row()
                
                # Column 1: Name
                imgui.table_next_column()
                imgui.text_colored(GAMETHEME.colors.accent, field.name)
                
                # Column 2: Value
                imgui.table_next_column()
                self._draw_value(val)
            
            imgui.end_table()

    def _render_dict(self, data: dict):
        """Renders a Dictionary."""
        flags = (imgui.TableFlags_.borders | imgui.TableFlags_.row_bg | imgui.TableFlags_.resizable)
        
        if imgui.begin_table("DictGrid", 2, flags):
            imgui.table_setup_column("Key", imgui.TableColumnFlags_.width_fixed, 150)
            imgui.table_setup_column("Value", imgui.TableColumnFlags_.width_stretch)
            imgui.table_headers_row()

            for k, v in data.items():
                imgui.table_next_row()
                imgui.table_next_column()
                imgui.text_colored(GAMETHEME.colors.accent, str(k))
                imgui.table_next_column()
                self._draw_value(v)
            
            imgui.end_table()

    def _render_generic_object(self, obj):
        """Fallback for generic objects (lists, primitives, etc)."""
        imgui.text_wrapped(str(obj))

    def _draw_value(self, val):
        """Helper to color-code values based on type."""
        val_str = str(val)
        
        if isinstance(val, (int, float)):
            imgui.text_colored(GAMETHEME.colors.accent, val_str)
        elif isinstance(val, bool):
            col = GAMETHEME.colors.positive if val else GAMETHEME.colors.negative
            imgui.text_colored(col, val_str)
        elif val is None:
            imgui.text_disabled("None")
        else:
            imgui.text(val_str)