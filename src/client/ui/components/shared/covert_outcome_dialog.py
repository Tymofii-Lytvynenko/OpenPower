"""Mission-specific result views, using the same visibility model as covert ops."""
from __future__ import annotations

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.gml_widgets import GMLWidgets
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.window_placement import center_window
from src.client.ui.layouts.gml_layout import gml_child_frame
from src.client.ui.panels.military.presenter import MilitaryPresenter
from src.shared.covert_mission_options import UNIT_CATEGORY_OPTIONS, mission_sector, resource_label


class CovertOutcomeDialog:
    def __init__(self):
        self._mission_id = ""
        self._viewer = ""
        self._presenter = MilitaryPresenter()

    def show(self, mission_id, viewer):
        self._mission_id, self._viewer = str(mission_id), str(viewer).upper()

    def render(self, state):
        if not self._mission_id:
            return
        mission = next((row for row in self._presenter.covert_missions_for_country(state,self._viewer)
                        if str(row.get("id"))==self._mission_id and row.get("result")),None)
        if mission is None:
            self._mission_id = ""
            return
        own = str(mission.get("owner_country_id"))==self._viewer
        framed = mission.get("_viewer_role") == "framed"
        template = "Covert_Actions_Mission_Outcome" if own else "Covert_Actions_Mission_Outcome_Attacked"
        region = "covert.outcome.own" if own else "covert.outcome.attacked"
        width,height = (451,252) if own else (401,105)
        viewport = imgui.get_io().display_size
        x, y = center_window((viewport.x, viewport.y), (width, height))
        # Only the bounded result/effect slots scroll. A root scrollbar would
        # cover the attacked-window close button at the source's right edge.
        flags = imgui.WindowFlags_.no_scrollbar | imgui.WindowFlags_.no_scroll_with_mouse
        if not own:
            flags |= imgui.WindowFlags_.no_title_bar
        with WindowManager.window("Mission outcome",x=x,y=y,
                                  w=width,h=height,test_id=region,gml_template=template,flags=flags) as opened:
            if not opened:
                self._mission_id = ""
                return
            raw_mission_type = str(mission.get("mission_type") or "Unknown").strip().lower()
            if raw_mission_type.startswith(("civilian_", "military_")):
                mission_type = raw_mission_type.split("_", 1)[1].replace("_", " ").title()
            else:
                mission_type = raw_mission_type.replace("_", " ").title()
            outcome = str(mission.get("result") or "Unknown").replace("_"," ").title()
            summary = self._summary(state) or "No public effect summary was recorded."
            target_sector = str(mission.get("target_sector") or mission_sector(raw_mission_type)).lower()
            if not own and not framed:
                target_description = self._target_description(mission, target_sector)
                if target_description:
                    summary = f"{summary}\nTarget: {target_description}"
            if own:
                ui = GMLWidgets(template+"/frmInner/frmMission")
                cells = state.tables.get("covert_cells")
                cell = next((row for row in cells.to_dicts() if str(row.get("id"))==str(mission.get("cell_id"))
                             and str(row.get("country_id"))==self._viewer),{}) if cells is not None else {}
                sector = target_sector.title() if target_sector else "Not recorded"
                unit_labels = dict(UNIT_CATEGORY_OPTIONS)
                resource_unit = (
                    resource_label(mission.get("target_resource_id"))
                    if target_sector == "civilian" and mission.get("target_resource_id") else
                    unit_labels.get(str(mission.get("target_unit_category") or ""), "Not recorded")
                    if target_sector == "military" else "Not recorded"
                )
                fields = (("CellName","CELL",cell.get("cell_name") or mission.get("cell_id") or "Unavailable"),
                          ("MissionType","MISSION",mission_type),("TargetSector","SECTOR",sector),
                           ("Complexity","COMPLEXITY",str(mission.get("complexity") or "Not recorded").title()),
                           ("ResourceUnit","RESOURCE / UNIT",resource_unit),
                          ("TargetCountry","TARGET COUNTRY",mission.get("target_country_id") or "Unknown"),
                          ("FramedCountry","FRAMED COUNTRY",mission.get("framed_country_id") or "None"))
                for slot,label,value in fields:
                    ui.text("lbl"+slot,label)
                    ui.text("txtSector" if slot=="TargetSector" else "txt"+slot,value,
                            test_id=f"covert.outcome.{slot.lower()}")
                ui.text("lblResult","RESULT",test_id="covert.outcome.result.label")
                with gml_child_frame(ui.path("txtResult"),padding=(0,0),bordered=False) as visible:
                    if visible:
                        imgui.text_wrapped(f"{outcome}\n{summary}",test_id="covert.outcome.result")
            else:
                ui = GMLWidgets(template)
                ui.text("lblTitle","YOUR COUNTRY WAS FRAMED" if framed else "DISCOVERED OPERATION")
                fields = (("Mission","MISSION",mission_type),
                          ("Country","TARGET COUNTRY" if framed else "ATTRIBUTION",
                           mission.get("target_country_id") if framed else mission.get("owner_country_id") or "Unknown"))
                if not framed:
                    fields += (("Outcome","OUTCOME",outcome),)
                for slot,label,value in fields:
                    ui.text("lbl"+slot,label)
                    ui.text("txt"+slot,value,test_id=f"covert.outcome.attacked.{slot.lower()}")
                ui.text("lblEffect","EFFECT" if not framed else "IMPLICATION",
                        test_id="covert.outcome.attacked.effect.label")
                with gml_child_frame(ui.path("txtEffect"),padding=(0,0),bordered=False) as visible:
                    if visible:
                        imgui.text_wrapped(
                            "Your country was implicated in a covert operation." if framed else summary,
                            test_id="covert.outcome.attacked.effect")
                if ui.button("btnExit","x","covert.outcome.attacked.close"):
                    self._mission_id = ""

    def _summary(self,state):
        incidents = state.tables.get("covert_incidents")
        if incidents is None:
            return ""
        return "\n".join(str(row.get("summary") or "") for row in incidents.to_dicts()
                         if str(row.get("mission_id"))==self._mission_id
                         and self._viewer in (row.get("audience_country_ids") or []))

    @staticmethod
    def _target_description(mission, target_sector):
        if target_sector == "civilian" and mission.get("target_resource_id"):
            return f"Civilian · {resource_label(mission.get('target_resource_id'))}"
        if target_sector == "military" and mission.get("target_unit_category"):
            label = dict(UNIT_CATEGORY_OPTIONS).get(str(mission.get("target_unit_category")), "")
            if label:
                return f"Military · {label}"
        return ""
