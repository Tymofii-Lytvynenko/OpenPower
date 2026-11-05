"""GML-sized split dialogs and compatible-unit merge selection."""
from __future__ import annotations

from contextlib import contextmanager
import math

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.gml_widgets import GMLWidgets
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.theme import GAMETHEME
from src.client.ui.layouts.gml_layout import gml_child_frame
from src.shared.actions import ActionMergeUnits, ActionSplitUnit, ActionListUsedUnit, ActionWithdrawUsedUnitListing
from src.client.ui.panels.military.unit_training_confirmation import (
    UnitTrainingConfirmation, training_offer, training_unavailable_reason,
)


@contextmanager
def _quantity_popup_style():
    imgui.push_style_color(imgui.Col_.window_bg,GAMETHEME.colors.bg_popup)
    imgui.push_style_var(imgui.StyleVar_.window_border_size,1.0)
    try:
        yield
    finally:
        imgui.pop_style_var()
        imgui.pop_style_color()


class UnitReorganizationWindows:
    def __init__(self, client, player_country,notify=None):
        self.client = client
        self.player_country = player_country
        self._notify = notify
        self._unit_id = ""
        self._mode = ""
        self._detached = 0
        self._quantity_direction = ""
        self._quantity = 0
        self._quantity_capacity = 0
        self._merge_sources: set[str] = set()
        self._list_unit_id = ""
        self._direct_split = False
        self._training = UnitTrainingConfirmation(client, player_country, notify)

    def open_unit_list(self,unit_id):
        self._list_unit_id = str(unit_id)

    def open_split(self, unit_id):
        self._unit_id, self._mode = str(unit_id), "split"
        self._detached = 0
        self._quantity_direction = ""
        self._direct_split = False

    def open_merge(self, unit_id):
        self._unit_id, self._mode = str(unit_id), "merge"
        self._merge_sources.clear()

    def open_training(self, state, unit_ids, *, on_accept=None):
        return self._training.request_many(state, unit_ids, on_accept=on_accept)

    def _rows(self, state):
        table = state.tables.get("units")
        return table.to_dicts() if table is not None else []

    def render(self, state):
        if self._list_unit_id:
            self._legacy_list(state)
        self._training.render(state)
        if not self._mode:
            return
        rows = self._rows(state)
        unit = next((row for row in rows if str(row.get("id")) == self._unit_id), None)
        if unit is None or str(unit.get("owner")) != self.player_country:
            if self._notify is not None:
                self._notify("Unit reorganization","The selected unit is unavailable or is not owned by you.",severity="warning")
            self._mode = ""
            return
        if self._mode == "split":
            if not self._direct_split:
                self._split(unit)
            if self._mode and self._quantity_direction:
                self._quantity_window()
        else:
            self._merge(unit, rows)

    def _split(self, unit):
        total = max(0,int(unit.get("strength") or 0))
        self._detached = min(total,max(0,self._detached))
        root = "Split_Group_Window"
        size = imgui.get_io().display_size
        with WindowManager.window("Split group", x=(size.x-631)/2,y=(size.y-347)/2,w=631,h=347,
                                  test_id="unit.split.group",gml_template=root) as opened:
            if not opened:
                self._mode = ""
                return
            ui = GMLWidgets(root+"/frmInner")
            ui.text("frmOriginal/lblTitle","ORIGINAL UNIT")
            ui.text("frmNew/lblTitle","DETACHED UNIT")
            for frame, count, side in (("frmOriginal",total-self._detached,"original"),
                                        ("frmNew",self._detached,"new")):
                with gml_child_frame(ui.path(frame+"/lstGroup"),bordered=False) as visible:
                    if visible:
                        imgui.dummy((0,4))
                        imgui.set_cursor_pos_x(imgui.get_cursor_pos_x()+5)
                        imgui.selectable(f"{unit.get('unit_type') or unit.get('type') or 'Unit'}: {count:,}",True,
                                         size=(max(1,imgui.get_content_region_avail().x-5),0),
                                         test_id=f"unit.split.{side}.row")
                        imgui.text(f"Personnel: {count}",test_id=f"unit.split.{side}.strength")
                        equipment = max(0,int(unit.get("equipment_quantity") or 0))
                        detached_equipment = equipment*self._detached//total if total else 0
                        imgui.text(f"Equipment: {equipment-detached_equipment if side=='original' else detached_equipment}")
            if ui.button("btnRight",">","unit.split.to_new",enabled=total-self._detached>0 and not self._quantity_direction):
                self._open_quantity("right",total-self._detached)
            if ui.button("btnLeft","<","unit.split.to_original",enabled=self._detached>0 and not self._quantity_direction):
                self._open_quantity("left",self._detached)
            if ui.button("btnSplitEqually","Split equally","unit.split.equally",enabled=total>1 and not self._quantity_direction):
                self._detached = total//2
            header = GMLWidgets(root+"/frmTitle")
            if header.button("btnApply","OK","unit.split.apply",
                             enabled=0<self._detached<total and not self._quantity_direction and self._available(unit),
                             tooltip="Apply the split" if self._available(unit) else "The unit must be stationary and available."):
                self.client.send_action(ActionSplitUnit(self.client.player_id,self._unit_id,self._detached))
                self._mode = ""

    @staticmethod
    def _available(unit):
        return (not bool(unit.get("is_moving")) and str(unit.get("unit_lifecycle") or "available")=="available"
                and not unit.get("readiness_transition_id") and not unit.get("engagement_mode")
                and str(unit.get("training_state") or "") not in {"queued","training","in_progress","blocked"})

    def _open_quantity(self,direction,capacity):
        self._quantity_direction,self._quantity_capacity = direction,capacity
        self._quantity = 0

    def _quantity_window(self):
        root = "Unit_Split_Window"
        size = imgui.get_io().display_size
        with _quantity_popup_style(), WindowManager.window("Split quantity",x=(size.x-289)/2,y=(size.y-66)/2,w=289,h=66,
            test_id="unit.split.quantity",gml_template=root,closable=False,
            flags=imgui.WindowFlags_.no_title_bar|imgui.WindowFlags_.no_scrollbar|imgui.WindowFlags_.no_scroll_with_mouse) as opened:
            ui = GMLWidgets(root)
            ui.text("frmTitle/txtTransparentLabel1","TRANSFER PERSONNEL")
            remaining = self._quantity_capacity-self._quantity
            ui.text("frmSplit/txtTransparentLabel1","REMAIN")
            ui.text("frmSplit/txtTransparentLabel2","TRANSFER")
            changed, value = imgui.input_int("##remaining",remaining,0,0,
                test_id="unit.split.quantity.remaining",gml_id=ui.path("frmSplit/edtGroupA"))
            if changed:
                self._quantity = self._quantity_capacity-max(0,min(self._quantity_capacity,value))
            changed, value = imgui.input_int("##transfer",self._quantity,0,0,
                test_id="unit.split.quantity.transfer",gml_id=ui.path("frmSplit/edtGroupB"))
            if changed:
                self._quantity = max(0,min(self._quantity_capacity,value))
            _, self._quantity = imgui.slider_int("##transfer_ratio",self._quantity,0,self._quantity_capacity,
                test_id="unit.split.quantity.ratio",gml_id=ui.path("frmSplit/frmSplit"))
            if ui.button("frmSplit/frmDown/btnDown","-","unit.split.quantity.down",enabled=self._quantity>0):
                self._quantity -= 1
            if ui.button("frmSplit/frmDown1/btnUp","+","unit.split.quantity.up",enabled=self._quantity<self._quantity_capacity):
                self._quantity += 1
            if not opened or ui.button("frmTitle/btnClose","x","unit.split.quantity.close",tooltip="Use this transfer quantity"):
                self._detached += self._quantity if self._quantity_direction=="right" else -self._quantity
                self._quantity_direction = ""
                if self._direct_split:
                    if 0<self._detached<self._quantity_capacity:
                        self.client.send_action(ActionSplitUnit(self.client.player_id,self._unit_id,self._detached))
                    self._mode = ""

    def _legacy_list(self,state):
        rows = self._rows(state)
        unit = next((row for row in rows if str(row.get("id"))==self._list_unit_id),None)
        if unit is None:
            self._list_unit_id = ""
            if self._notify is not None:
                self._notify("Unit group","The selected unit is no longer available.",severity="warning")
            return
        own = str(unit.get("owner"))==self.player_country
        root = "Unit_List_Window"
        with WindowManager.window("Selected unit group",x=420,y=100,w=343,h=492,
                                  test_id="unit.group.list",gml_template=root) as opened:
            if not opened:
                self._list_unit_id = ""
                return
            ui = GMLWidgets(root+"/frmInner")
            with gml_child_frame(ui.path("frmList/frmInner/frmTree"),bordered=False) as visible:
                if visible and own:
                    for row in rows:
                        key = str(row.get("id"))
                        if str(row.get("owner"))!=self.player_country or row.get("current_region_id")!=unit.get("current_region_id"):
                            continue
                        imgui.dummy((0,4))
                        imgui.set_cursor_pos_x(imgui.get_cursor_pos_x()+5)
                        if imgui.selectable(key,self._list_unit_id==key,
                            size=(max(1,imgui.get_content_region_avail().x-5),0),test_id=f"unit.group.select.{key}")[0]:
                            self._list_unit_id = key
                        imgui.text(str(row.get("unit_type") or row.get("type") or "Unit"))
                        imgui.text(f"Personnel: {int(row.get('strength') or 0)}")
                        imgui.text(f"Equipment: {int(row.get('equipment_quantity') or 0)}")
                elif visible:
                    imgui.text_wrapped("Foreign force details require an authorized intelligence observation.")
            if not own:
                ui.text("frmInformationAccuracy/lblTitle","INFORMATION ACCURACY")
                ui.text("frmInformationAccuracy/txtValue","Unknown")
                return
            if ui.button("frmActions/btnSplit","Split","unit.group.split",enabled=int(unit.get("strength") or 0)>1 and self._available(unit),
                         dynamic_enabled=True):
                self.open_split(self._list_unit_id)
                self._direct_split = True
                self._open_quantity("right",int(unit.get("strength") or 0))
            if ui.button("frmActions/btnMerge","Merge","unit.group.merge",dynamic_enabled=True):
                self.open_merge(self._list_unit_id)
            offer = training_offer(state, self._list_unit_id, self.player_country)
            if ui.button("frmActions/btnTrain","Train","unit.group.train",enabled=offer is not None,
                         tooltip="Review training cost and duration" if offer else
                             training_unavailable_reason(state, self._list_unit_id, self.player_country)):
                self._training.request(state, self._list_unit_id)
            listings = state.tables.get("unit_market_listings")
            listing = next((row for row in listings.to_dicts() if str(row.get("unit_id"))==self._list_unit_id
                            and str(row.get("status"))=="listed"),None) if listings is not None else None
            if ui.button("frmActions/btnSell","Withdraw" if listing else "Sell","unit.group.sell"):
                if listing:
                    self.client.send_action(ActionWithdrawUsedUnitListing(self.client.player_id,self.player_country,str(listing["id"])))
                else:
                    self.client.send_action(ActionListUsedUnit(self.client.player_id,self.player_country,self._list_unit_id))

    def _merge(self,unit,rows):
        with WindowManager.window("Merge units",x=360,y=180,w=420,h=300,test_id="unit.merge.dialog") as opened:
            if not opened:
                self._mode = ""
                return
            imgui.text_wrapped(f"Merge into {self._unit_id}")
            traits = ("owner","unit_type","design_id","unit_domain","readiness_status","training_level","combat_posture","current_region_id")
            candidates = [row for row in rows if str(row.get("id"))!=self._unit_id and self._available(row)
                          and all(row.get(key)==unit.get(key) for key in traits)
                          and all(math.isclose(float(row.get(key) or 0),float(unit.get(key) or 0),abs_tol=1e-6,rel_tol=0)
                                  for key in ("latitude","longitude"))]
            self._merge_sources.intersection_update(str(row.get("id")) for row in candidates)
            for row in candidates:
                key = str(row.get("id"))
                changed, selected = imgui.checkbox(f"{key} ({int(row.get('strength') or 0)})",key in self._merge_sources,
                                                   test_id=f"unit.merge.select.{key}")
                if changed:
                    if selected:self._merge_sources.add(key)
                    else:self._merge_sources.discard(key)
            if not candidates:
                imgui.text_wrapped("No compatible units share this location and status.")
            imgui.begin_disabled(not self._merge_sources or not self._available(unit))
            if imgui.button("Merge",test_id="unit.merge.apply"):
                self.client.send_action(ActionMergeUnits(self.client.player_id,self._unit_id,sorted(self._merge_sources)))
                self._mode = ""
            imgui.end_disabled()
