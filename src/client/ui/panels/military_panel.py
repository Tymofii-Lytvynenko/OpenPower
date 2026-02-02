from imgui_bundle import imgui
from src.client.ui.core.theme import GAMETHEME
from src.client.ui.core.primitives import UIPrimitives as Prims
from src.client.ui.core.containers import WindowManager

class MilitaryPanel:
    def render(self, state, **kwargs) -> bool:
        is_own = kwargs.get("is_own_country", False)
        
        with WindowManager.window("MILITARY", x=260, y=100, w=250, h=520) as is_open:
            if not is_open: return False
            
            Prims.header("CONVENTIONAL FORCES")
            
            flags = imgui.TableFlags_.borders_inner_h | imgui.TableFlags_.pad_outer_x
            if imgui.begin_table("MilStats", 3, flags):
                imgui.table_setup_column("", imgui.TableColumnFlags_.width_fixed, 80)
                imgui.table_setup_column("", imgui.TableColumnFlags_.width_stretch)
                imgui.table_setup_column("RANK", imgui.TableColumnFlags_.width_fixed, 40)
                
                self._row("ARMY", "4,200", "32")
                self._row("NAVY", "20", "50")
                self._row("AIR", "270", "37")
                
                imgui.end_table()

            imgui.dummy((0, 10))

            if is_own:
                w = (imgui.get_content_region_avail().x - 10) / 2
                imgui.button("RECRUIT", (w, 0))
                imgui.same_line()
                imgui.button("BUILD", (w, 0))
            else:
                imgui.text_disabled("[Actions Restricted]")

            return True

    def _row(self, label, count, rank):
        imgui.table_next_row()
        imgui.table_next_column()
        imgui.text_disabled(label)
        imgui.table_next_column()
        Prims.right_align_text(count)
        imgui.table_next_column()
        imgui.text_disabled(rank)