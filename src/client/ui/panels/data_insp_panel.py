import polars as pl
import dataclasses
from imgui_bundle import imgui

from src.client.ui.core.theme import GAMETHEME
from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext


class DataInspectorPanel:
    """
    A debugging tool to visualize the raw Polars DataFrames AND Python Objects/Dataclasses
    stored in GameState. Uses Composition (WindowManager).
    """
    def __init__(self):
        self.selected_key = None
        self.search_text = ""
        self._sort_columns: tuple[tuple[str, bool], ...] = ()
        self._display_source: pl.DataFrame | None = None
        self._display_signature: tuple | None = None
        self._display_frame: pl.DataFrame | None = None

    def render(self, state, context: PanelRenderContext) -> bool:
        # Replaces BasePanel logic with Context Manager
        with WindowManager.window("DATA INSPECTOR", x=300, y=100, w=1000, h=700) as is_open:
            if not is_open:
                return False
            self._render_content(state)
            return True

    def _render_content(self, state):
        """
        Renders the internal debug view.
        """
        
        # --- 1. Aggregation of Inspectable Data ---
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
        """Render a searchable, sortable, virtualized Polars DataFrame."""
        columns = df.columns
        num_cols = len(columns)

        if num_cols == 0:
            imgui.text_disabled("Empty DataFrame.")
            return

        imgui.set_next_item_width(240)
        _, self.search_text = imgui.input_text("Search", self.search_text)
        imgui.same_line()
        imgui.text_disabled(f"{df.height:,} rows")

        flags = (imgui.TableFlags_.scroll_y | 
                 imgui.TableFlags_.borders | 
                 imgui.TableFlags_.row_bg | 
                 imgui.TableFlags_.resizable | 
                 imgui.TableFlags_.reorderable | 
                 imgui.TableFlags_.hideable |
                 imgui.TableFlags_.sortable)

        if imgui.begin_table("DfGrid", num_cols, flags):
            for col in columns:
                imgui.table_setup_column(col)
            imgui.table_headers_row()
            self._update_sort_from_imgui(columns)
            display_df = self._display_data_frame(df)
            clipper = imgui.ListClipper()
            clipper.begin(display_df.height)
            while clipper.step():
                for row_index in range(clipper.display_start, clipper.display_end):
                    imgui.table_next_row()
                    for val in display_df.row(row_index):
                        imgui.table_next_column()
                        self._draw_value(val)
            imgui.end_table()

    def _update_sort_from_imgui(self, columns: list[str]) -> None:
        sort_specs = imgui.table_get_sort_specs()
        if sort_specs is None or not sort_specs.specs_dirty:
            return

        parsed_specs: list[tuple[int, str, bool]] = []
        for index in range(sort_specs.specs_count):
            spec = sort_specs.get_specs(index)
            column_index = int(spec.column_index)
            if not 0 <= column_index < len(columns):
                continue

            direction = spec.get_sort_direction()
            if direction == imgui.SortDirection_.ascending:
                parsed_specs.append((int(spec.sort_order), columns[column_index], True))
            elif direction == imgui.SortDirection_.descending:
                parsed_specs.append((int(spec.sort_order), columns[column_index], False))

        self._sort_columns = tuple(
            (column, ascending)
            for _, column, ascending in sorted(parsed_specs)
        )
        sort_specs.specs_dirty = False

    def _display_data_frame(self, df: pl.DataFrame) -> pl.DataFrame:
        query = self.search_text.strip().casefold()
        signature = (query, self._sort_columns)
        if self._display_source is df and self._display_signature == signature:
            return self._display_frame if self._display_frame is not None else df

        result = df
        if query and df.columns:
            search_columns = [
                pl.col(column)
                .cast(pl.String, strict=False)
                .fill_null("")
                .str.to_lowercase()
                .str.contains(query, literal=True)
                for column in df.columns
            ]
            result = result.filter(pl.any_horizontal(search_columns))

        sort_columns = [(column, ascending) for column, ascending in self._sort_columns if column in result.columns]
        if sort_columns:
            result = result.sort(
                by=[column for column, _ in sort_columns],
                descending=[not ascending for _, ascending in sort_columns],
                nulls_last=True,
                maintain_order=True,
            )

        # State snapshots are immutable DataFrames; retain the source object so cache identity cannot be recycled.
        self._display_source = df
        self._display_signature = signature
        self._display_frame = result
        return result

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
