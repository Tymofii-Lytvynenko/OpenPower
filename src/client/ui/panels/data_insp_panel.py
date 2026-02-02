import polars as pl
import dataclasses
from imgui_bundle import imgui

from src.client.ui.core.theme import GAMETHEME
from src.client.ui.core.containers import WindowManager

class DataInspectorPanel:
    def __init__(self):
        self.selected_key = None
        self.row_limit = 50

    def render(self, state, **kwargs) -> bool:
        with WindowManager.window("DATA INSPECTOR", x=300, y=100, w=1000, h=700) as is_open:
            if not is_open: return False
            self._render_content(state)
            return True

    def _render_content(self, state):
        # Gather Data
        data_map = {}
        if hasattr(state, "time"): data_map["[Obj] Time"] = state.time
        if hasattr(state, "tables"): 
            for k,v in state.tables.items(): data_map[f"[Table] {k}"] = v
        
        keys = sorted(data_map.keys())
        if not keys: return

        if not self.selected_key: self.selected_key = keys[0]

        # Header Controls
        imgui.set_next_item_width(250)
        if imgui.begin_combo("Source", self.selected_key):
            for k in keys:
                if imgui.selectable(k, k == self.selected_key)[0]:
                    self.selected_key = k
            imgui.end_combo()

        data = data_map.get(self.selected_key)
        
        # DataFrame specific controls
        if isinstance(data, pl.DataFrame):
            imgui.same_line()
            _, self.row_limit = imgui.slider_int("Limit", self.row_limit, 10, 500)

        imgui.separator()
        
        # Render Logic
        if isinstance(data, pl.DataFrame):
            self._render_df(data)
        elif dataclasses.is_dataclass(data):
            self._render_dataclass(data)
        else:
            imgui.text_wrapped(str(data))

    def _render_df(self, df):
        if df.is_empty(): 
            imgui.text_disabled("Empty")
            return
            
        flags = imgui.TableFlags_.scroll_y | imgui.TableFlags_.borders | imgui.TableFlags_.resizable
        cols = df.columns
        if imgui.begin_table("DfTable", len(cols), flags):
            for c in cols: imgui.table_setup_column(c)
            imgui.table_headers_row()
            
            for row in df.head(self.row_limit).iter_rows():
                imgui.table_next_row()
                for val in row:
                    imgui.table_next_column()
                    imgui.text(str(val))
            imgui.end_table()

    def _render_dataclass(self, obj):
        fields = dataclasses.fields(obj)
        if imgui.begin_table("DcTable", 2, imgui.TableFlags_.borders):
            for f in fields:
                imgui.table_next_row()
                imgui.table_next_column()
                imgui.text_colored(GAMETHEME.colors.accent, f.name)
                imgui.table_next_column()
                imgui.text(str(getattr(obj, f.name)))
            imgui.end_table()