import polars as pl
from imgui_bundle import imgui, icons_fontawesome_6

from src.client.ui.core.theme import GAMETHEME
from src.client.ui.core.primitives import UIPrimitives as Prims
from src.client.ui.core.containers import WindowManager

class ResourcesPanel:
    """
    Resources Directory Menu.
    Uses Menu Bar for clean actions.
    """
    def __init__(self):
        self.selected_resource = None
        
        self.has_unsaved_changes = False
        self.show_close_confirm = False
        
        self.opts_man = ["Private Market", "State Monopoly"]
        self.opts_sta = ["Legalized", "Banned"]
        self.opts_tax = [f"{i:.1f} %" for i in range(0, 31)]
        
        self.draft_management = 0
        self.draft_status = 0
        self.draft_tax = 50

    def render(self, state, **kwargs) -> bool:
        target_tag = kwargs.get("target_tag", "")
        is_own = kwargs.get("is_own_country", False)
        
        flags = imgui.WindowFlags_.menu_bar

        with WindowManager.window("RESOURCES MENU", x=400, y=100, w=850, h=710, flags=flags) as is_open:
            
            if not is_open and not self.show_close_confirm:
                if self.has_unsaved_changes:
                    self.show_close_confirm = True
                else:
                    return False
                    
            # 2. Rendering the Menu Bar for window actions
            if imgui.begin_menu_bar():
                avail_w = imgui.get_content_region_avail().x
                # Push the button to the far right of the bar
                imgui.dummy((max(0.0, avail_w - 32.0), 0))
                
                if self.has_unsaved_changes:
                    # State: Active (using theme's interaction colors)
                    imgui.push_style_color(imgui.Col_.text, GAMETHEME.colors.text_main)
                    imgui.push_style_color(imgui.Col_.button, GAMETHEME.colors.interaction_active)
                    imgui.push_style_color(imgui.Col_.button_hovered, GAMETHEME.colors.accent)
                else:
                    # State: Inactive (dimmed, transparent background, non-clickable)
                    imgui.begin_disabled()
                    imgui.push_style_color(imgui.Col_.text, GAMETHEME.colors.text_dim)
                    imgui.push_style_color(imgui.Col_.button, (0, 0, 0, 0))

                # Render the Checkmark icon button
                if imgui.button("apply"):
                    # Apply draft changes to the persistent state
                    if hasattr(self, 'draft_allocations'):
                        self.allocations = self.draft_allocations.copy()
                    if hasattr(self, 'has_unsaved_changes'):
                        self.has_unsaved_changes = False
                    
                    # NOTE: Network action should be dispatched here to notify the server

                # Cleanup style stack
                imgui.pop_style_color(2)
                if self.has_unsaved_changes:
                    imgui.pop_style_color()
                else:
                    imgui.end_disabled()
                    
                imgui.end_menu_bar()

            # 3. Контент
            self._render_content(state, target_tag, is_own)
            
            # 4. Модалка
            if self.show_close_confirm:
                imgui.open_popup("Unsaved Changes##Resources")
                
            if self._render_close_modal():
                return False

            return True

    def _render_close_modal(self) -> bool:
        viewport = imgui.get_main_viewport()
        imgui.set_next_window_pos(viewport.get_center(), imgui.Cond_.appearing, imgui.ImVec2(0.5, 0.5))
        
        flags = imgui.WindowFlags_.always_auto_resize | imgui.WindowFlags_.no_saved_settings
        if imgui.begin_popup_modal("Unsaved Changes##Resources", None, flags)[0]:
            imgui.text("You have unapplied resource policies.")
            imgui.text("Do you want to discard them and close?")
            imgui.dummy((0, 15))
            
            if imgui.button("Discard & Close", (140, 30)):
                self.has_unsaved_changes = False 
                self.show_close_confirm = False
                imgui.close_current_popup()
                imgui.end_popup()
                return True
                
            imgui.same_line()
            
            if imgui.button("Cancel", (100, 30)):
                self.show_close_confirm = False
                imgui.close_current_popup()
                
            imgui.end_popup()
        return False

    def _render_content(self, state, target_tag, is_own):
        abbreviate = state.globals.get("abbreviate_numbers", False)

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
                pass

            imgui.end_table()
        imgui.end_child()
        imgui.pop_style_color()

        imgui.dummy((0, 5))
        
        # Bottom half
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
            if abs(val) < 1_000_000: return f"$ {val/1_000:,.0f} k".replace(",", " ")
            return f"$ {val/1_000_000:,.1f} M".replace(",", " ")
        return f"$ {val:,.0f}".replace(",", " ")

    def _draw_leaf_row(self, resource_id, name, p_usd, c_usd, t_usd, b_usd, abbreviate=False):
        imgui.table_next_row()
        imgui.table_next_column()
        imgui.dummy((15, 0)); imgui.same_line()
        
        is_selected = (self.selected_resource == resource_id)
        if imgui.selectable(name, is_selected, imgui.SelectableFlags_.span_all_columns)[0]:
            self.selected_resource = resource_id
            
        imgui.table_next_column(); Prims.right_align_text(self._fmt_money(p_usd, abbreviate))
        imgui.table_next_column(); Prims.right_align_text(self._fmt_money(c_usd, abbreviate))
        imgui.table_next_column(); Prims.right_align_text(self._fmt_money(t_usd, abbreviate))
        
        color_usd = GAMETHEME.colors.negative if (b_usd and b_usd < 0) else GAMETHEME.colors.positive
        imgui.table_next_column(); Prims.right_align_text(self._fmt_money(b_usd, abbreviate), color_usd)

    def _render_controls(self, state, target_tag, is_own):
        imgui.push_style_color(imgui.Col_.frame_bg, GAMETHEME.colors.bg_input)
        if not is_own: imgui.begin_disabled()
        
        pct_gdp_str, mkt_share_str, avail_str = "-- %", "-- %", "0 M"
        res_name = "Select a Resource"
        
        if self.selected_resource and "resource_ledger" in state.tables and "countries" in state.tables:
            res_name = self.selected_resource.replace("_", " ").upper()
            ledger, countries = state.tables["resource_ledger"], state.tables["countries"]
            
            c_row = ledger.filter((pl.col("country_id") == target_tag) & (pl.col("game_resource_id") == self.selected_resource))
            if not c_row.is_empty():
                c_prod, c_bal = c_row["production_usd"][0], c_row["balance_usd"][0]
                avail_str = self._fmt_money(c_bal, abbreviate=True).replace("$ ", "")
                
                country_data = countries.filter(pl.col("id") == target_tag)
                if not country_data.is_empty() and country_data["gdp"][0]:
                    pct_gdp_str = f"{(c_prod / country_data['gdp'][0]) * 100:.2f} %"
                    
                w_row = ledger.filter(pl.col("game_resource_id") == self.selected_resource)
                world_prod = w_row["production_usd"].sum()
                if world_prod:
                    mkt_share_str = f"{(c_prod / world_prod) * 100:.2f} %"

        imgui.text_colored(GAMETHEME.colors.accent, f"POLICY: {res_name}")
        imgui.separator(); imgui.dummy((0, 5))

        imgui.begin_group(); imgui.text_disabled("SECTOR CONTROL"); imgui.same_line(150); imgui.set_next_item_width(180)
        changed, self.draft_management = imgui.combo("##man", self.draft_management, self.opts_man)
        if changed: self.has_unsaved_changes = True
        imgui.end_group()
        
        imgui.begin_group(); imgui.text_disabled("LEGAL STATUS"); imgui.same_line(150); imgui.set_next_item_width(180)
        changed, self.draft_status = imgui.combo("##sta", self.draft_status, self.opts_sta)
        if changed: self.has_unsaved_changes = True
        imgui.end_group()
        
        imgui.begin_group(); imgui.text_disabled("RESOURCE TAX"); imgui.same_line(150); imgui.set_next_item_width(180)
        changed, self.draft_tax = imgui.combo("##st", self.draft_tax, self.opts_tax)
        if changed: self.has_unsaved_changes = True
        imgui.end_group()
        
        imgui.dummy((0, 10)); imgui.text_disabled("SHARE OF GDP"); imgui.same_line(150); imgui.text(pct_gdp_str)
        imgui.text_disabled("GLOBAL MKT SHARE"); imgui.same_line(150); imgui.text(mkt_share_str)
        
        imgui.dummy((0, 10))
        if imgui.button("SUBSIDIZE PRODUCTION", (-1, 30)): pass
        
        imgui.dummy((0, 10)); imgui.text_disabled("UNUSED INVENTORY")
        imgui.push_style_color(imgui.Col_.button, (0.05, 0.05, 0.05, 1.0))
        imgui.button(avail_str, (imgui.get_content_region_avail().x, 30))
        imgui.pop_style_color()
        
        if not is_own: imgui.end_disabled()
        imgui.pop_style_color()

    def _render_graphic_placeholder(self):
        w, h = imgui.get_content_region_avail().x, imgui.get_content_region_avail().y
        imgui.push_style_color(imgui.Col_.child_bg, (0.02, 0.02, 0.02, 1.0))
        imgui.begin_child("ImageHolder", (w, h), child_flags=imgui.ChildFlags_.borders)
        
        text = "Global Trade Flow"
        size, avail = imgui.calc_text_size(text), imgui.get_content_region_avail()
        imgui.set_cursor_pos(((avail.x - size.x)/2, (avail.y - size.y)/2))
        imgui.text_disabled(text)
        
        imgui.end_child()
        imgui.pop_style_color()