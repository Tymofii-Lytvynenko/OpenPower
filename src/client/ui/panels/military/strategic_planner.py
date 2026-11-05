"""Compose the REFERENCE target, missile-list and launch windows around OpenPower actions."""
from __future__ import annotations

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.gml_widgets import GMLWidgets
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.primitives import UIPrimitives
from src.client.ui.layouts.gml_layout import gml_child_frame
from src.client.ui.panels.military.strategic_plan import StrategicPlan
from src.client.ui.panels.shared.panel_data import resolve_region_name, safe_int


class StrategicPlanner:
    def __init__(self, presenter):
        self.presenter = presenter
        self.plan = StrategicPlan()
        self.phase = ""
        self.multiple = False
        self._selection_origin: int | None = None
        self._missile_selection: set[str] = set()
        self._feedback = ""

    def open(self, country, region_id=None, *, payload_levels: dict[str, int] | None = None):
        self.plan = StrategicPlan(
            country=str(country),
            target_region=region_id,
            payload_levels=dict(payload_levels or {}),
        )
        self.phase = "country"
        self.multiple = False
        self._feedback = ""

    def _rows(self, state, name):
        table = state.tables.get(name)
        return table.to_dicts() if table is not None else []

    def _targets(self, state):
        return [row for row in self._rows(state, "regions")
                if str(row.get("owner") or "") not in {"", "None", self.plan.country}]

    def render(self, state, context):
        if not self.phase:
            return
        # Selecting a foreign map region changes the HUD's inspected country.
        # The draft must retain its original owner throughout that selection.
        phases = {"country": self._country, "multiple": self._multiple,
                  "missiles": self._missiles, "select": self._select, "launch": self._launch}
        phases[self.phase](state, context)

    def _window(self, template, title, region, size, *, at_bottom=False):
        viewport = imgui.get_io().display_size
        w, h = size
        flags = imgui.WindowFlags_.no_scrollbar | imgui.WindowFlags_.no_scroll_with_mouse
        if template in {"Strategic_Select_Target_Window", "Strategic_Launch_Window",
                        "Strategic_Target_Country_Window"}:
            # These source frames have no title bar. Native chrome covered the
            # select-target message and moved the launch controls visually.
            flags |= imgui.WindowFlags_.no_title_bar
        return WindowManager.window(title, x=0 if at_bottom else max(0, (viewport.x-w)/2),
            y=max(0, viewport.y-h) if at_bottom else max(0, (viewport.y-h)/2), w=w, h=h,
            test_id=region, gml_template=template,
            flags=flags)

    def _render_country_selection(self, state, context, ui):
        targets = self._targets(state)
        tags = sorted({str(row["owner"]) for row in targets})
        selected_region = next((row for row in targets if row["id"] == self.plan.target_region), None)
        if self.plan.target_country not in tags:
            self.plan.target_country = str(selected_region["owner"]) if selected_region else (tags[0] if tags else "")
        labels = [*tags, "Specific location", "Multiple countries"]
        index = tags.index(self.plan.target_country) if self.plan.target_country in tags else 0
        ui.text("frmCountry/lblTitle", "TARGET COUNTRY")
        changed, index = imgui.combo("##strategic_country", index, labels,
            test_id="strategic.target.country_choice", gml_id=ui.path("frmCountry/cboCountry"))
        if changed:
            if index == len(tags):
                self._selection_origin = context.selected_region_id
                self.phase = "select"
            elif index == len(tags)+1:
                self.multiple = True
                self.phase = "multiple"
            else:
                self.plan.target_country = tags[index]
                self.plan.target_region = None
        regions = [row for row in targets if str(row["owner"]) == self.plan.target_country]
        if self.plan.target_region not in {row["id"] for row in regions}:
            self.plan.target_region = int(regions[0]["id"]) if regions else None
        return targets, regions

    def _render_weapon_selection(self, state, ui):
        weapons = self.presenter.strategic_inventory_for_country(state, self.plan.country)
        options = [str(row.get("id")) for row in weapons]
        current = next((i for i,key in enumerate(options) if key in self.plan.selected_weapons),0)
        ui.text("frmAttackStrength/lblTitle", "WEAPON SYSTEM")
        contexts = ["", *self.presenter.strategic_authorization_contexts(state)]
        authorization = contexts.index(self.plan.authorization_context) if self.plan.authorization_context in contexts else 0
        _, authorization = ui.combo_at("frmAttackStrength/frmAttackStrengthValue",
            "##strategic_authorization", authorization,
            ["Default authorization", *contexts[1:]], "strategic.target.authorization")
        self.plan.authorization_context = contexts[authorization]
        if options:
            _, current = imgui.combo("##strategic_weapon", current, options,
                test_id="strategic.target.weapon", gml_id=ui.path("frmAttackStrength/cboMissileType"))
            self.plan.selected_weapons = {options[current]}
        return options

    def _country(self, state, context):
        root = "Strategic_Target_Country_Window"
        with self._window(root, "Strategic target", "strategic.target.country", (294,335)) as opened:
            if not opened:
                self.phase = ""
                return
            ui = GMLWidgets(root)
            targets, regions = self._render_country_selection(state, context, ui)
            ui.text("frmAttackType/lblTitle", "TARGET TYPE")
            _, attack = imgui.combo("##strategic_attack", int(self.plan.target_mode == "civilian"),
                ["Military", "Civilian"], test_id="strategic.target.mode",
                gml_id=ui.path("frmAttackType/cboAttackType"))
            self.plan.target_mode = ("military", "civilian")[attack]
            options = self._render_weapon_selection(state, ui)
            ui.text("frmAttackStrength/lblAvailMissiles", "AVAILABLE")
            ui.text("frmAttackStrength/txtAvailMissiles", str(len(options)))
            ui.text("frmAttackStrength/lblMissileUsed", "SELECTED")
            ui.text("frmAttackStrength/txtMissilesUsed", str(len(self.plan.selected_weapons)))
            ui.text("frmAttackStrength/lblProjectedCasualities", "TARGET REGION")
            target = next((row for row in targets if row["id"] == self.plan.target_region), {})
            ui.text("frmAttackStrength/txtNbTargets", target.get("name") or self.plan.target_region or "—")
            if ui.button("frmAttackStrength/btnSuggested", "Suggest", "strategic.target.suggested", enabled=bool(regions)):
                self.plan.target_region = int(regions[0]["id"])
            _, reasons = self.plan.actions(state, self.presenter, context.net_client.player_id if context.net_client else "")
            reason = "; ".join(reasons) or "Review the plan before launch."
            if ui.button("btnPrepare", "Prepare launch", "strategic.target.prepare",
                         enabled=not reasons and context.net_client is not None, tooltip=reason):
                self.multiple = False
                self.phase = "launch"
            if ui.button("btnReturn", "Return", "strategic.target.return"):
                self.phase = ""

    def _select(self, state, context):
        root = "Strategic_Select_Target_Window"
        with self._window(root, "Select target", "strategic.target.select", (197,54)) as opened:
            ui = GMLWidgets(root)
            ui.text("frmMessage/txtMessage", "Select target on map")
            if not opened or ui.button("frmMessage/btnCancel", "Cancel", "strategic.target.cancel"):
                self.phase = "country"
                return
            if context.selected_region_id != self._selection_origin:
                target = next((row for row in self._targets(state) if row["id"] == context.selected_region_id), None)
                if target:
                    self.plan.target_region = int(target["id"])
                    self.plan.target_country = str(target["owner"])
                    self.phase = "country"

    def _render_assignment_row(self, row, targets) -> None:
        key = str(row.get("id"))
        enabled = key in self.plan.selected_weapons
        changed, enabled = imgui.checkbox(UIPrimitives.fit_text(key,170)+f"##{key}", enabled,
            test_id=f"strategic.multiple.weapon.{key}")
        if changed:
            if enabled:
                self.plan.selected_weapons.add(key)
            else:
                self.plan.selected_weapons.discard(key)
        if targets:
            selected = self.plan.assignments.get(key, self.plan.target_region)
            index = next((i for i,r in enumerate(targets) if r["id"]==selected),0)
            imgui.same_line(204)
            imgui.text(self.plan.target_mode.title())
            imgui.same_line(322)
            imgui.set_next_item_width(135)
            _, index = imgui.combo(f"##target-{key}", index,
                [f"{r['owner']}: {r.get('name') or r['id']}" for r in targets],
                test_id=f"strategic.multiple.target.{key}")
            self.plan.assignments[key] = int(targets[index]["id"])
            for offset,value in ((466,int(row.get("ready") or 0)),
                                 (549,int(enabled)),(633,int(enabled))):
                imgui.same_line(offset)
                imgui.text(str(value))

    def _multiple(self, state, context):
        root = "Strategic_Target_Multiple_Countries_Window"
        with self._window(root, "Multiple targets", "strategic.target.multiple", (782,267)) as opened:
            if not opened:
                self.phase = "country"
                self.multiple = False
                return
            ui = GMLWidgets(root+"/frmInner/frmList")
            for slot, label in (("lblCountry","SYSTEM / TARGET"),("lblAttackType","TYPE"),
                                ("lblPotentialTargets","REGION"),("lblAvailMissiles","AVAILABLE"),
                                ("lblMissileUsed","SELECTED"),("lblNbTargets","TARGETS")):
                ui.text(slot,label)
            targets = self._targets(state)
            weapons = self.presenter.strategic_inventory_for_country(state,self.plan.country)
            with gml_child_frame(ui.path("lstAttackList"), bordered=False) as visible:
                if visible:
                    for row in weapons:
                        self._render_assignment_row(row, targets)
            ui.text("lblProjCasualities", "CASUALTIES")
            ui.text("txtCasualities", "Not estimated")
            ui.text("lblProjDamage", "DAMAGE")
            ui.text("txtDamage", self._feedback or "Not estimated")
            if ui.button("btnMissileList", "Missile list", "strategic.multiple.missiles"):
                self._missile_selection = set(self.plan.selected_weapons)
                self.phase = "missiles"
            _, reasons = self.plan.actions(state,self.presenter,
                context.net_client.player_id if context.net_client else "",multiple=True)
            if ui.button("btnPrepareLaunch", "Prepare launch", "strategic.multiple.prepare",
                         enabled=not reasons and context.net_client is not None,tooltip="; ".join(reasons)):
                self.phase = "launch"

    def _missile_row_labels(self, state, row, payload_profiles) -> tuple[str, str, str, str, str]:
        key = str(row.get("id"))
        ready = row.get("ready")
        quantity = row.get("quantity")
        stock = (f"{safe_int(ready)}/{safe_int(quantity)}"
                 if ready is not None and quantity is not None else None)
        missile_label = f"{key} ({stock})" if stock is not None else key

        payload_level = safe_int(
            self.plan.payload_levels.get(key, row.get("payload_level")), 1,
        )
        payload = payload_profiles.get(payload_level)
        payload_label = f"{payload[0]:g} kt" if payload is not None else "\u2014"

        origin_id = safe_int(row.get("origin_region_id"), 0)
        origin_label = resolve_region_name(state, origin_id) if origin_id > 0 else "\u2014"
        target_id = safe_int(self.plan.assignments.get(key), 0)
        target_label = resolve_region_name(state, target_id) if target_id > 0 else "\u2014"
        return key, missile_label, payload_label, origin_label, target_label

    def _missiles(self, state, context):
        root = "Strategic_Missile_List_Window"
        with self._window(root, "Missile list", "strategic.missiles.dialog", (580,272)) as opened:
            if not opened:
                self.phase = "multiple"
                return
            ui = GMLWidgets(root+"/frmInner")
            for slot,label in (("lblMissiles","MISSILES"),("lblYield","YIELD"),
                               ("lblLocation","LOCATION"),("lblTarget","TARGET")):
                ui.text("frmList/"+slot,label)
            weapons = self.presenter.strategic_inventory_for_country(state,self.plan.country)
            payload_profiles = self.presenter.strategic_payload_profiles(state)
            with gml_child_frame(ui.path("frmList/lstMissileList"),bordered=False) as visible:
                if visible:
                    for row in weapons:
                        key, missile_label, payload_label, origin_label, target_label = (
                            self._missile_row_labels(state, row, payload_profiles)
                        )
                        changed, enabled = imgui.checkbox(UIPrimitives.fit_text(missile_label,160)+f"##{key}",key in self._missile_selection,
                            test_id=f"strategic.missiles.weapon.{key}")
                        if changed:
                            if enabled:
                                self._missile_selection.add(key)
                            else:
                                self._missile_selection.discard(key)
                        imgui.same_line(198)
                        imgui.text(
                            payload_label,
                            test_id=f"strategic.missiles.yield.{key}",
                        )
                        imgui.same_line(252)
                        imgui.text(
                            origin_label,
                            test_id=f"strategic.missiles.origin.{key}",
                        )
                        imgui.same_line(452)
                        imgui.text(
                            target_label,
                            test_id=f"strategic.missiles.target.{key}",
                        )
            if ui.button("btnSelectAll","Select all","strategic.missiles.all"):
                self._missile_selection = {str(row.get("id")) for row in weapons}
            if ui.button("btnSelectNone","Select none","strategic.missiles.none"):
                self._missile_selection.clear()
            if ui.button("btnConfirm","Confirm","strategic.missiles.confirm"):
                self.plan.selected_weapons = set(self._missile_selection)
                self.phase = "multiple"

    def _launch(self, state, context):
        root = "Strategic_Launch_Window"
        with self._window(root,"Launch authorization","strategic.launch.dialog",(265,226),at_bottom=True) as opened:
            ui = GMLWidgets(root)
            if not opened or ui.button("btnAbort","Abort","strategic.launch.abort"):
                self.phase = "multiple" if self.multiple else "country"
                return
            actions,reasons = self.plan.actions(state,self.presenter,
                context.net_client.player_id if context.net_client else "",multiple=self.multiple)
            # The source animation frame is the launch hit target. A real button
            # in that same rectangle preserves keyboard access and testability.
            if ui.button("frmButton/frmLaunch",f"Launch {len(actions)} system(s)","strategic.launch.confirm",
                         enabled=bool(actions) and context.net_client is not None,tooltip="; ".join(reasons)):
                for action in actions:
                    context.net_client.send_action(action)
                self.plan.selected_weapons.clear()
                self.phase = "country"
