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
            try:
                imgui.table_setup_scroll_freeze(0, 1)
                imgui.table_setup_column("RESOURCE", imgui.TableColumnFlags_.width_stretch)
                imgui.table_setup_column("PRODUCTION", imgui.TableColumnFlags_.width_fixed, 120)
                imgui.table_setup_column("CONSUMPTION", imgui.TableColumnFlags_.width_fixed, 120)
                imgui.table_setup_column("TRADE", imgui.TableColumnFlags_.width_fixed, 120)
                imgui.table_setup_column("BALANCE", imgui.TableColumnFlags_.width_fixed, 100)
                imgui.table_headers_row()
                if "resource_ledger" in state.tables:
                    ledger = state.tables["resource_ledger"]
                    if target_tag:
                        ledger = ledger.filter(pl.col("country_id") == target_tag)
                    
                    if not ledger.is_empty():
                        # Group by category, sort deterministically to prevent random shifting
                        categories = ledger.select("category").unique().to_series().to_list()
                        categories.sort()
                        for cat in categories:
                            cat_df = ledger.filter(pl.col("category") == cat)
                            
                            cat_prod_usd = cat_df.select(pl.col("production_usd")).sum().item()
                            cat_cons_usd = cat_df.select(pl.col("consumption_usd")).sum().item()
                            cat_trade_usd = cat_df.select(pl.col("trade_usd")).sum().item()
                            cat_bal_usd = cat_df.select(pl.col("balance_usd")).sum().item()
                            
                            imgui.table_next_row()
                            imgui.table_next_column()
                            safe_cat = str(cat) if cat is not None else "Unclassified"
                            tree_open = imgui.tree_node_ex(safe_cat, imgui.TreeNodeFlags_.default_open if safe_cat == "Services" else 0)
                            
                            imgui.table_next_column(); Prims.right_align_text(self._fmt_money(cat_prod_usd))
                            imgui.table_next_column(); Prims.right_align_text(self._fmt_money(cat_cons_usd))
                            imgui.table_next_column(); Prims.right_align_text(self._fmt_money(cat_trade_usd))
                            
                            color = GAMETHEME.colors.negative if (cat_bal_usd is not None and cat_bal_usd < 0) else GAMETHEME.colors.positive
                            imgui.table_next_column(); Prims.right_align_text(self._fmt_money(cat_bal_usd), color)
                            
                            if tree_open:
                                res_df = cat_df.group_by(["game_resource_id", "unit_str"]).agg(
                                    pl.col("production_vol").sum(), pl.col("production_usd").sum(),
                                    pl.col("consumption_vol").sum(), pl.col("consumption_usd").sum(),
                                    pl.col("trade_vol").sum(), pl.col("trade_usd").sum(),
                                    pl.col("balance_vol").sum(), pl.col("balance_usd").sum()
                                ).sort("game_resource_id")
                                
                                for row in res_df.iter_rows(named=True):
                                    g_id = row.get("game_resource_id")
                                    res_name = str(g_id).replace("_", " ").title() if g_id else "Unknown"
                                    self._draw_leaf_row(
                                        res_name,
                                        row["production_vol"], row["production_usd"],
                                        row["consumption_vol"], row["consumption_usd"],
                                        row["trade_vol"], row["trade_usd"],
                                        row["balance_vol"], row["balance_usd"],
                                        str(row.get("unit_str", ""))
                                    )
                                imgui.tree_pop()
                else:
                    imgui.table_next_row()
                    imgui.table_next_column()
                    imgui.text_disabled("No resource data available. Unpause the game to calculate.")
            except Exception as e:
                import traceback
                print("Exception in ResourcesPanel:")
                traceback.print_exc()

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

    def _fmt_money(self, val) -> str:
        if val is None: return "$ 0 M"
        return f"$ {val/1_000_000:,.0f} M".replace(",", " ")

    def _fmt_vol(self, val, unit) -> str:
        if val is None: return f"0 {unit}"
        if unit == "man hours": # typically huge
            return f"{val/1_000_000:,.1f}M Mh".replace(",", " ")
        if val > 1_000_000:
            return f"{val/1_000_000:,.1f}M {unit}".replace(",", " ")
        elif val > 1_000:
            return f"{val/1_000:,.1f}k {unit}".replace(",", " ")
        return f"{val:,.0f} {unit}".replace(",", " ")

    def _draw_leaf_row(self, name, p_vol, p_usd, c_vol, c_usd, t_vol, t_usd, b_vol, b_usd, unit, selected=False):
        imgui.table_next_row()
        imgui.table_next_column()
        
        # Add a bit of spacing / bullet
        imgui.dummy((15, 0))
        imgui.same_line()
        if selected:
            imgui.selectable(name, True, imgui.SelectableFlags_.span_all_columns)
        else:
            imgui.text(name)
            
        # Draw physical volume on the first line, money on the second or just combine them
        # We can draw two texts right-aligned sequentially using a trick or just one string
        
        imgui.table_next_column()
        Prims.right_align_text(self._fmt_vol(p_vol, unit))
        Prims.right_align_text(self._fmt_money(p_usd), GAMETHEME.colors.text_dim)
        
        imgui.table_next_column()
        Prims.right_align_text(self._fmt_vol(c_vol, unit))
        Prims.right_align_text(self._fmt_money(c_usd), GAMETHEME.colors.text_dim)
        
        imgui.table_next_column()
        Prims.right_align_text(self._fmt_vol(t_vol, unit))
        Prims.right_align_text(self._fmt_money(t_usd), GAMETHEME.colors.text_dim)
        
        imgui.table_next_column()
        color = GAMETHEME.colors.negative if (b_vol and b_vol < 0) else GAMETHEME.colors.positive
        Prims.right_align_text(self._fmt_vol(b_vol, unit), color)
        color_usd = GAMETHEME.colors.negative if (b_usd and b_usd < 0) else GAMETHEME.colors.positive
        Prims.right_align_text(self._fmt_money(b_usd), color_usd)

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
