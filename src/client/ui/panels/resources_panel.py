import polars as pl
from imgui_bundle import imgui

from src.client.ui.core.theme import GAMETHEME
from src.client.ui.core.primitives import UIPrimitives as Prims
from src.client.ui.core.containers import WindowManager

class ResourcesPanel:
    def __init__(self):
        # Track selected resource for the details panel
        self.selected_resource = None

    def render(self, state, **kwargs) -> bool:
        target_tag = kwargs.get("target_tag", "")
        is_own = kwargs.get("is_own_country", False)

        with WindowManager.window("RESOURCES DIRECTORY", x=400, y=100, w=850, h=650) as is_open:
            if not is_open: return False
            self._render_content(state, target_tag, is_own)
            return True

    def _render_content(self, state, target_tag, is_own):
        abbreviate = state.globals.get("abbreviate_numbers", False)

        # Top half: Datatable
        imgui.push_style_color(imgui.Col_.child_bg, (0.05, 0.05, 0.05, 1.0))
        imgui.begin_child("table_view", (0, 350), child_flags=imgui.ChildFlags_.borders)
        flags = (imgui.TableFlags_.scroll_y | 
                 imgui.TableFlags_.borders | 
                 imgui.TableFlags_.row_bg | 
                 imgui.TableFlags_.resizable)
        
        if imgui.begin_table("ResourcesTable", 5, flags):
            try:
                imgui.table_setup_scroll_freeze(0, 1)
                imgui.table_setup_column("RESOURCE", imgui.TableColumnFlags_.width_stretch)
                imgui.table_setup_column("PRODUCTION", imgui.TableColumnFlags_.width_fixed, 130)
                imgui.table_setup_column("CONSUMPTION", imgui.TableColumnFlags_.width_fixed, 130)
                imgui.table_setup_column("TRADE (NET)", imgui.TableColumnFlags_.width_fixed, 130)
                imgui.table_setup_column("BALANCE", imgui.TableColumnFlags_.width_fixed, 120)
                imgui.table_headers_row()
                
                if "resource_ledger" in state.tables:
                    ledger_full = state.tables["resource_ledger"]
                    ledger_country = ledger_full.filter(pl.col("country_id") == target_tag) if target_tag else ledger_full
                    
                    if not ledger_country.is_empty():
                        categories = ledger_country.select("category").unique().to_series().to_list()
                        categories.sort()
                        
                        for cat in categories:
                            cat_df = ledger_country.filter(pl.col("category") == cat)
                            
                            cat_prod_usd = cat_df["production_usd"].sum()
                            cat_cons_usd = cat_df["consumption_usd"].sum()
                            cat_trade_usd = cat_df["trade_usd"].sum()
                            cat_bal_usd = cat_df["balance_usd"].sum()
                            
                            imgui.table_next_row()
                            imgui.table_next_column()
                            safe_cat = str(cat) if cat is not None else "Unclassified"
                            tree_open = imgui.tree_node_ex(safe_cat, imgui.TreeNodeFlags_.default_open if safe_cat == "Services" else 0)
                            
                            imgui.table_next_column(); Prims.right_align_text(self._fmt_money(cat_prod_usd, abbreviate))
                            imgui.table_next_column(); Prims.right_align_text(self._fmt_money(cat_cons_usd, abbreviate))
                            imgui.table_next_column(); Prims.right_align_text(self._fmt_money(cat_trade_usd, abbreviate))
                            
                            color = GAMETHEME.colors.negative if (cat_bal_usd is not None and cat_bal_usd < 0) else GAMETHEME.colors.positive
                            imgui.table_next_column(); Prims.right_align_text(self._fmt_money(cat_bal_usd, abbreviate), color)
                            
                            if tree_open:
                                res_df = cat_df.sort("game_resource_id")
                                for row in res_df.iter_rows(named=True):
                                    g_id = row.get("game_resource_id")
                                    res_name = str(g_id).replace("_", " ").title() if g_id else "Unknown"
                                    
                                    self._draw_leaf_row(
                                        g_id, res_name,
                                        row["production_usd"], row["consumption_usd"],
                                        row["trade_usd"], row["balance_usd"],
                                        abbreviate
                                    )
                                imgui.tree_pop()
                    else:
                        imgui.table_next_row()
                        imgui.table_next_column()
                        imgui.text_disabled("No resource data available.")
            except Exception as e:
                import traceback
                print("Exception in ResourcesPanel:")
                traceback.print_exc()

            imgui.end_table()
        imgui.end_child()
        imgui.pop_style_color()

        imgui.dummy((0, 5))
        
        # Bottom half: Resource Policy Controls
        if imgui.begin_table("BottomLayout", 2):
            imgui.table_setup_column("Controls", imgui.TableColumnFlags_.width_fixed, 350)
            imgui.table_setup_column("Image", imgui.TableColumnFlags_.width_stretch)
            
            imgui.table_next_row()
            imgui.table_next_column()
            self._render_controls(state, target_tag, is_own)
            
            imgui.table_next_column()
            self._render_graphic_placeholder()
            
            imgui.end_table()

    def _fmt_money(self, val, abbreviate=False) -> str:
        if val is None: return "$ 0 M" if abbreviate else "$ 0"
        if abbreviate:
            if abs(val) < 1_000_000:
                return f"$ {val/1_000:,.0f} k".replace(",", " ")
            return f"$ {val/1_000_000:,.1f} M".replace(",", " ")
        else:
            return f"$ {val:,.0f}".replace(",", " ")

    def _draw_leaf_row(self, resource_id, name, p_usd, c_usd, t_usd, b_usd, abbreviate=False):
        imgui.table_next_row()
        imgui.table_next_column()
        
        imgui.dummy((15, 0))
        imgui.same_line()
        
        is_selected = (self.selected_resource == resource_id)
        if imgui.selectable(name, is_selected, imgui.SelectableFlags_.span_all_columns)[0]:
            self.selected_resource = resource_id
            
        imgui.table_next_column()
        Prims.right_align_text(self._fmt_money(p_usd, abbreviate))
        
        imgui.table_next_column()
        Prims.right_align_text(self._fmt_money(c_usd, abbreviate))
        
        imgui.table_next_column()
        Prims.right_align_text(self._fmt_money(t_usd, abbreviate))
        
        imgui.table_next_column()
        color_usd = GAMETHEME.colors.negative if (b_usd and b_usd < 0) else GAMETHEME.colors.positive
        Prims.right_align_text(self._fmt_money(b_usd, abbreviate), color_usd)

    def _render_controls(self, state, target_tag, is_own):
        imgui.push_style_color(imgui.Col_.frame_bg, GAMETHEME.colors.bg_input)
        
        if not is_own: imgui.begin_disabled()
        
        # Calculate dynamic data for the selected resource
        pct_gdp_str = "-- %"
        mkt_share_str = "-- %"
        avail_str = "0 M"
        res_name = "Select a Resource"
        
        if self.selected_resource and "resource_ledger" in state.tables and "countries" in state.tables:
            res_name = self.selected_resource.replace("_", " ").upper()
            ledger = state.tables["resource_ledger"]
            countries = state.tables["countries"]
            
            # Country specific resource row
            c_row = ledger.filter((pl.col("country_id") == target_tag) & (pl.col("game_resource_id") == self.selected_resource))
            if not c_row.is_empty():
                c_prod = c_row["production_usd"][0]
                c_bal = c_row["balance_usd"][0]
                avail_str = self._fmt_money(c_bal, abbreviate=True).replace("$ ", "")
                
                # % of GDP calculation
                country_data = countries.filter(pl.col("id") == target_tag)
                if not country_data.is_empty():
                    total_gdp = country_data["gdp"][0]
                    if total_gdp and total_gdp > 0:
                        pct_gdp_str = f"{(c_prod / total_gdp) * 100:.2f} %"
                        
                # Market Share calculation
                w_row = ledger.filter(pl.col("game_resource_id") == self.selected_resource)
                world_prod = w_row["production_usd"].sum()
                if world_prod and world_prod > 0:
                    mkt_share_str = f"{(c_prod / world_prod) * 100:.2f} %"

        # Controls Header
        imgui.text_colored(GAMETHEME.colors.accent, f"POLICY: {res_name}")
        imgui.separator()
        imgui.dummy((0, 5))

        # Management Setup (IsGovControlled)
        imgui.begin_group()
        imgui.text_disabled("SECTOR CONTROL")
        imgui.same_line(150)
        imgui.set_next_item_width(180)
        if imgui.begin_combo("##man", "Private Market"):
            # Options: Private Market, State Monopoly
            imgui.end_combo()
        imgui.end_group()
        
        # Status Setup (IsLegal)
        imgui.begin_group()
        imgui.text_disabled("LEGAL STATUS")
        imgui.same_line(150)
        imgui.set_next_item_width(180)
        if imgui.begin_combo("##sta", "Legalized"):
            # Options: Legalized, Banned (Black Market)
            imgui.end_combo()
        imgui.end_group()
        
        # Sector tax (TaxRate)
        imgui.begin_group()
        imgui.text_disabled("RESOURCE TAX")
        imgui.same_line(150)
        imgui.set_next_item_width(180)
        if imgui.begin_combo("##st", "5.0 %"):
            imgui.end_combo()
        imgui.end_group()
        
        imgui.dummy((0, 10))
        imgui.text_disabled("SHARE OF GDP")
        imgui.same_line(150)
        imgui.text(pct_gdp_str)
        
        imgui.text_disabled("GLOBAL MKT SHARE")
        imgui.same_line(150)
        imgui.text(mkt_share_str)
        
        imgui.dummy((0, 10))
        if imgui.button("SUBSIDIZE PRODUCTION", (-1, 30)): pass
        
        imgui.dummy((0, 10))
        imgui.text_disabled("UNUSED INVENTORY")
        w = imgui.get_content_region_avail().x
        imgui.push_style_color(imgui.Col_.button, (0.05, 0.05, 0.05, 1.0))
        imgui.button(avail_str, (w, 30))
        imgui.pop_style_color()
        
        if not is_own: imgui.end_disabled()
        imgui.pop_style_color()

    def _render_graphic_placeholder(self):
        w = imgui.get_content_region_avail().x
        h = imgui.get_content_region_avail().y
        
        imgui.push_style_color(imgui.Col_.child_bg, (0.02, 0.02, 0.02, 1.0))
        imgui.begin_child("ImageHolder", (w, h), child_flags=imgui.ChildFlags_.borders)
        
        text = "Global Trade Flow"
        size = imgui.calc_text_size(text)
        avail = imgui.get_content_region_avail()
        imgui.set_cursor_pos(((avail.x - size.x)/2, (avail.y - size.y)/2))
        imgui.text_disabled(text)
        
        imgui.end_child()
        imgui.pop_style_color()