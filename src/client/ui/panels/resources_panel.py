import polars as pl
from imgui_bundle import imgui

from src.client.ui.core.theme import GAMETHEME
from src.client.ui.core.primitives import UIPrimitives as Prims
from src.client.ui.core.containers import WindowManager

class ResourcesPanel:
    def render(self, state, **kwargs) -> bool:
        target_tag = kwargs.get("target_tag", "")
        # The window opens around center/left
        with WindowManager.window("RESOURCES", x=400, y=100, w=800, h=600) as is_open:
            if not is_open: return False
            self._render_content(state, target_tag)
            return True

    def _render_content(self, state, target_tag):
        # Top Table: Resources list
        # "RESOURCE | PRODUCTION | CONSUMPTION | TRADE | BALANCE"
        # We'll use a tree node for groupings, e.g. "Services", "Finished Goods"
        
        # Let's mock the data from domestic_production and trade if available
        # or just a stubbed table since we don't have consumption/balance strictly tracked right now.

        imgui.push_style_color(imgui.Col_.child_bg, (0.05, 0.05, 0.05, 1.0))
        imgui.begin_child("table_view", (0, 300), child_flags=imgui.ChildFlags_.borders)
        flags = (imgui.TableFlags_.scroll_y | 
                 imgui.TableFlags_.borders | 
                 imgui.TableFlags_.row_bg | 
                 imgui.TableFlags_.resizable)
        
        if imgui.begin_table("ResourcesTable", 5, flags):
            imgui.table_setup_scroll_freeze(0, 1)
            imgui.table_setup_column("RESOURCE", imgui.TableColumnFlags_.width_stretch)
            imgui.table_setup_column("PRODUCTION", imgui.TableColumnFlags_.width_fixed, 120)
            imgui.table_setup_column("CONSUMPTION", imgui.TableColumnFlags_.width_fixed, 120)
            imgui.table_setup_column("TRADE", imgui.TableColumnFlags_.width_fixed, 120)
            imgui.table_setup_column("BALANCE", imgui.TableColumnFlags_.width_fixed, 100)
            imgui.table_headers_row()
            
            # Example hardcoded structure similar to screenshot
            self._draw_category_row("Raw Materials", 514320, 555322, -225002, -17151)
            self._draw_category_row("Industrial Materials", 490755, 906706, -361757, -54194)
            self._draw_category_row("Finished Goods", 581313, 829946, -242442, -6190)
            
            # The one that is expanded in screenshot
            imgui.table_next_row()
            imgui.table_next_column()
            tree_open = imgui.tree_node_ex("Services", imgui.TreeNodeFlags_.default_open)
            # The values for the category overall
            imgui.table_next_column(); Prims.right_align_text("$ 7 740 430 M")
            imgui.table_next_column(); Prims.right_align_text("$ 5 851 134 M")
            imgui.table_next_column(); Prims.right_align_text("$ 1 889 295 M")
            imgui.table_next_column(); Prims.right_align_text("$ 0 M", GAMETHEME.colors.positive)
            
            if tree_open:
                self._draw_leaf_row("Construction", 1992605, 1462854, 529750, 0, selected=True)
                self._draw_leaf_row("Engineering", 747045, 615261, 131783, 0)
                self._draw_leaf_row("Health and care", 3088165, 2467611, 620553, 0)
                self._draw_leaf_row("Retail", 757045, 393235, 363809, 0)
                self._draw_leaf_row("Legal services", 797045, 610755, 186289, 0)
                self._draw_leaf_row("Market and advertising", 358525, 301416, 57109, 0)
                imgui.tree_pop()
                
            imgui.end_table()
        imgui.end_child()
        imgui.pop_style_color()

        imgui.dummy((0, 5))
        
        # Bottom half
        if imgui.begin_table("BottomLayout", 2):
            imgui.table_setup_column("Controls", imgui.TableColumnFlags_.width_fixed, 300)
            imgui.table_setup_column("Image", imgui.TableColumnFlags_.width_stretch)
            
            imgui.table_next_row()
            imgui.table_next_column()
            # Bottom Left: Controls
            self._render_controls()
            
            imgui.table_next_column()
            # Bottom Right: Image Placeholder
            w = imgui.get_content_region_avail().x
            # We don't have the stock market image, we will draw a placeholder or dummy background
            imgui.push_style_color(imgui.Col_.child_bg, (0.0, 0.0, 0.0, 1.0))
            imgui.begin_child("ImageHolder", (w, 0), child_flags=imgui.ChildFlags_.borders)
            text = "Market Graphic Placeholder"
            size = imgui.calc_text_size(text)
            avail = imgui.get_content_region_avail()
            imgui.set_cursor_pos(((avail.x - size.x)/2, (avail.y - size.y)/2))
            imgui.text_disabled(text)
            imgui.end_child()
            imgui.pop_style_color()
            
            imgui.end_table()

    def _draw_category_row(self, name, prod, cons, trade, bal):
        imgui.table_next_row()
        imgui.table_next_column()
        # It's a closed node
        expanded = imgui.tree_node_ex(name, 0)
        imgui.table_next_column()
        Prims.right_align_text(f"$ {prod:,} M".replace(",", " "))
        imgui.table_next_column()
        Prims.right_align_text(f"$ {cons:,} M".replace(",", " "))
        imgui.table_next_column()
        Prims.right_align_text(f"$ {trade:,} M".replace(",", " "))
        imgui.table_next_column()
        color = GAMETHEME.colors.negative if bal < 0 else GAMETHEME.colors.positive
        Prims.right_align_text(f"$ {bal:,} M".replace(",", " "), color)
        if expanded:
            imgui.tree_pop()

    def _draw_leaf_row(self, name, prod, cons, trade, bal, selected=False):
        imgui.table_next_row()
        imgui.table_next_column()
        
        # Add a bit of spacing / bullet
        imgui.dummy((15, 0))
        imgui.same_line()
        if selected:
            imgui.selectable(name, True, imgui.SelectableFlags_.span_all_columns)
        else:
            imgui.text(name)
            
        imgui.table_next_column()
        Prims.right_align_text(f"$ {prod:,} M".replace(",", " "))
        imgui.table_next_column()
        Prims.right_align_text(f"$ {cons:,} M".replace(",", " "))
        imgui.table_next_column()
        Prims.right_align_text(f"$ {trade:,} M".replace(",", " "))
        imgui.table_next_column()
        color = GAMETHEME.colors.negative if bal < 0 else GAMETHEME.colors.positive
        Prims.right_align_text(f"$ {bal:,} M".replace(",", " "), color)

    def _render_controls(self):
        # Global Tax mod, Management, Status, Sector Tax, % GDP, Market Share
        
        imgui.push_style_color(imgui.Col_.frame_bg, GAMETHEME.colors.bg_input)
        
        # Global Tax Mod
        imgui.begin_group()
        imgui.text_disabled("GLOBAL TAX MOD")
        imgui.same_line()
        # Right align the combo/spin box. Let's just draw dummy combo for UI parity.
        avail = imgui.get_content_region_avail()
        imgui.set_cursor_pos_x(imgui.get_cursor_pos_x() + avail.x - 100)
        imgui.set_next_item_width(100)
        if imgui.begin_combo("##gtm", "0.0 %"):
            imgui.end_combo()
        imgui.end_group()
        imgui.separator()
        
        # Management
        imgui.begin_group()
        imgui.text_disabled("MANAGEMENT")
        imgui.same_line(150)
        imgui.set_next_item_width(140)
        if imgui.begin_combo("##man", "Private"):
            imgui.end_combo()
        imgui.end_group()
        
        # Status
        imgui.begin_group()
        imgui.text_disabled("STATUS")
        imgui.same_line(150)
        imgui.set_next_item_width(140)
        if imgui.begin_combo("##sta", "Legal"):
            imgui.end_combo()
        imgui.end_group()
        
        # Sector tax
        imgui.begin_group()
        imgui.text_disabled("SECTOR TAX")
        imgui.same_line(150)
        imgui.set_next_item_width(140)
        if imgui.begin_combo("##st", "19.0 %"):
            imgui.end_combo()
        imgui.end_group()
        
        imgui.dummy((0,10))
        imgui.text_disabled("% OF GDP")
        imgui.same_line(150)
        imgui.text("32.31 %")
        
        imgui.text_disabled("MARKET SHARE")
        imgui.same_line(150)
        imgui.text("29.92 %")
        
        imgui.dummy((0,10))
        if imgui.button("INCREASE PRODUCTION", (-1, 30)): pass
        
        imgui.dummy((0,10))
        # Market availability
        imgui.text_disabled("MARKET AVAILABILITY")
        w = imgui.get_content_region_avail().x
        imgui.push_style_color(imgui.Col_.button, (0.05, 0.05, 0.05, 1.0))
        imgui.button("0 M", (w, 30))
        imgui.pop_style_color()
        
        imgui.dummy((0,10))
        imgui.text_disabled("TRADE")
        imgui.same_line(100)
        imgui.set_next_item_width(190)
        if imgui.begin_combo("##td", ""):
            imgui.end_combo()
            
        imgui.text_disabled("DESIRED")
        imgui.same_line(100)
        imgui.set_next_item_width(190)
        if imgui.begin_combo("##des", ""):
            imgui.end_combo()
            
        imgui.text_disabled("ACTUAL")
        imgui.same_line(100)
        imgui.push_style_color(imgui.Col_.button, (0.05, 0.05, 0.05, 1.0))
        imgui.button("", (190, 20))
        imgui.pop_style_color()
        
        imgui.dummy((0, 5))
        imgui.checkbox("Meet Domestic Consumption", False)
        
        imgui.pop_style_color()
