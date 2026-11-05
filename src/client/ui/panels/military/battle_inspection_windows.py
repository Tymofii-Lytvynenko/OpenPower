"""Source-sized battle inspection composed with OpenPower's battle commands."""
from src.client.ui.components.shared.battle_summary_dialog import BattleSummaryDialog
from src.client.renderers.flag_renderer import FlagRenderer
from src.client.ui.core.containers import WindowManager
from src.client.ui.core.gml_widgets import GMLWidgets
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.layouts.gml_layout import gml_child_frame
from src.client.ui.core.theme import GAMETHEME
from src.client.ui.panels.military.battle_inspection import BattleInspection, category_counts
from src.client.ui.panels.military.battle_position_map import render_battle_positions
from src.client.ui.panels.military.battle_force_cards import render_battle_force_cards
from src.client.ui.panels.military.battle_public_counts import observed_category_counts
from src.client.ui.panels.shared.panel_data import normalize_side, resolve_country_name, resolve_region_name


class BattleInspectionWindows:
    def __init__(self, client, country):
        self.selection = BattleInspection(country, client.send_action, client.player_id)
        self._summary = BattleSummaryDialog("battle.inspection.summary")
        self._ally = self._enemy = ""
        self._strategy = 0
        self._selected_force = None
        self._flags = FlagRenderer()

    def open(self, state, battle_id):
        if self.selection.open(state, str(battle_id)):
            self._summary.dismiss()
            self._ally = self._enemy = ""
            self._strategy = 0
            self._selected_force = None
            return True
        return False

    def close(self):
        self.selection.close()
        self._summary.dismiss()
        self._selected_force = None

    def render(self, state):
        if not self.selection.battle_id:
            return
        result = self.selection.poll_result(state)
        row = self.selection.display_row(state)
        if result is not None:
            self._summary.show(result, losses=self.selection.recorded_losses(state))
        if row is None:
            self.close()
            return
        if self.selection.full:
            self._render_full(state, row)
        else:
            self._render_small(state, row)
        if self.selection.battle_id:
            self._summary.render(state)

    def _render_small(self, state, row):
        with WindowManager.window("Battle info", x=320, y=120, w=225, h=203,
                                  test_id="battle.info.dialog", gml_template="Battle_Info_Window") as opened:
            if not opened:
                self.close()
                return
            title_ui = GMLWidgets("Battle_Info_Window/frmTitle")
            title_ui.button(
                "btnApply",
                "A",
                "battle.info.apply",
            )
            ui = GMLWidgets("Battle_Info_Window/frmInner/frmInner/frmBattleInfo")
            observed = True
            for slot, side, title in (("A", "defender_side", "DEFENDERS"), ("B", "attacker_side", "ATTACKERS")):
                counts = observed_category_counts(state, row, "B" if slot == "A" else "A")
                observed = observed and counts is not None
                ui.text(f"lblSide{slot}", title)
                with gml_child_frame(
                    ui.path(f"lstCountries{slot}"), bordered=False,
                    test_id=f"battle.info.country_list.{slot}",
                ) as visible:
                    if visible:
                        countries = normalize_side(row.get(side))
                        if countries:
                            # GML's 52x16 list item gives each flag and country code its own clipped row.
                            for index, tag in enumerate(countries):
                                imgui.set_cursor_pos((2.0, 2.0 + index * 16.0))
                                self._flags.draw_flag(tag, 22.0, 13.0)
                                imgui.same_line(25.0)
                                imgui.text(tag, test_id=f"battle.info.countries.{slot}.{index}")
                                if imgui.is_item_hovered():
                                    imgui.set_tooltip(resolve_country_name(state, tag))
                        else:
                            imgui.text("Unknown", test_id=f"battle.info.countries.{slot}.0")
                for category in "IGAN":
                    ui.text(f"lbl{category}{slot}", category)
                    ui.text(f"txt{category}Perc{slot}", str(counts[category]) if counts is not None else "—",
                            tooltip="Published unit quantity; individual foreign rosters remain unavailable.",
                            test_id=f"battle.info.count.{slot}.{category}")
            GMLWidgets("Battle_Info_Window/frmInner/frmInner").text(
                "frmSideA", "Public unit totals" if observed else "Counts not observed",
                test_id="battle.info.observation_status",
            )

    def _render_full(self, state, row):
        flags = imgui.WindowFlags_.no_title_bar | imgui.WindowFlags_.horizontal_scrollbar
        with WindowManager.window("Battle", x=0, y=0, w=1024, h=768, flags=flags,
                                  test_id="battle.inspection.dialog", gml_template="Battle_Window",
                                  closable=False, padding=(0, 0)) as opened:
            if not opened:
                self.close()
                return
            ui = GMLWidgets("Battle_Window")
            ui.text("lblTitle", resolve_region_name(state, int(row.get("region_id") or 0)),
                    test_id="battle.inspection.region")
            if ui.button("btnExit", "x", "battle.inspection.close"):
                self.close()
                return
            groups = self.selection.groups(state)
            a, b = normalize_side(row.get("attacker_side")), normalize_side(row.get("defender_side"))
            allies, enemies = (a, b) if self.selection.country in a else (b, a)
            self._ally = self._ally if self._ally in allies else self.selection.country
            self._enemy = self._enemy if self._enemy in enemies else next(iter(enemies), "")
            for slot, countries, own in (("lstFlagsYou", allies, True), ("lstFlagsEnemy", enemies, False)):
                self._render_country_flag_grid(state, ui, slot, countries, own=own)
            for slot, tag in (("frmTrimYou/frmFlagYou/picFlag", self._ally),
                              ("frmTrimEnemy/frmFlagEnemy/picFlag", self._enemy)):
                ui.picture(slot, lambda width, height, country=tag:
                           self._flags.draw_flag(country, width, height))
            balance = max(0.0, min(1.0, float(row.get("balance") or 0.0)))
            ui.meter(
                "frmOverviewMeter/btnUnfilled",
                balance if self.selection.country in a else 1 - balance,
                (0.0, 1.0, 0.0, 1.0),
                background_color=(1.0, 0.0, 0.0, 1.0),
                marker_slot="frmOverviewMeter/btnSeparator1",
                marker_color=(1.0, 1.0, 1.0, 1.0),
            )
            with gml_child_frame(ui.path("frmBattle/frm3D"), bordered=False) as visible:
                if visible:
                    self._render_forces(state, row, groups)
            with gml_child_frame(ui.path("frmBattle/frmMap"), bordered=False) as visible:
                if visible:
                    render_battle_positions(
                        groups,
                        own_side="A" if self.selection.country in a else "B",
                        selected_force=self._selected_force,
                        on_select=self._select_force,
                    )
            can_command = row.get("status") == "active" and any(g["country_id"] == self.selection.country for g in groups)
            imgui.begin_disabled(not can_command)
            labels = [value.replace("_", " ").title() for value in self.selection.STRATEGIES]
            changed, self._strategy = imgui.combo("##battle_strategy", self._strategy, labels,
                gml_id=ui.path("frmBattle/cboStrategies"), test_id="battle.inspection.strategy")
            if changed:
                self.selection.command(state, self.selection.STRATEGIES[self._strategy])
            if ui.button("frmBattle/btnRetreat", "RETREAT", "battle.inspection.retreat"):
                self.selection.command(state, "retreat")
            imgui.end_disabled()

    def _render_country_flag_grid(self, state, ui, slot, countries, *, own):
        """Render the source list's seven 22x13 flag slots per 15px row."""
        flag_x_positions = (1.0, 25.0, 49.0, 73.0, 96.0, 119.0, 143.0)
        side = "ally" if own else "enemy"
        with gml_child_frame(
            ui.path(slot), padding=(0.0, 0.0), bordered=False,
            test_id=f"battle.inspection.flags.{side}",
        ) as visible:
            if not visible:
                return
            if not countries:
                imgui.text_disabled("Unknown")
                return
            for index, tag in enumerate(countries):
                row, column = divmod(index, len(flag_x_positions))
                position = (flag_x_positions[column], float(row * 15 + 1))
                imgui.set_cursor_pos(position)
                self._flags.draw_flag(tag, 22.0, 13.0)
                imgui.set_cursor_pos(position)
                if imgui.invisible_button(
                    f"##battle_country_{slot}_{tag}",
                    (22.0, 13.0),
                    test_id=f"battle.inspection.country.{tag}",
                ):
                    if own:
                        self._ally = tag
                    else:
                        self._enemy = tag
                if imgui.is_item_hovered():
                    imgui.set_tooltip(resolve_country_name(state, tag))
                selected = tag == (self._ally if own else self._enemy)
                if selected:
                    minimum, maximum = imgui.get_item_rect_min(), imgui.get_item_rect_max()
                    imgui.get_window_draw_list().add_rect(
                        (minimum.x, minimum.y), (maximum.x, maximum.y),
                        imgui.get_color_u32(GAMETHEME.colors.accent),
                    )

    def _render_forces(self, state, row, groups):
        imgui.text(f"{row.get('mode') or 'Unknown'} | Round {int(row.get('round') or 0)} | {row.get('status') or 'Unknown'}",
                   test_id="battle.inspection.status")
        render_battle_force_cards(
            groups, self._ally, self._enemy, self.selection.country,
            active=row.get("status") == "active",
            command=lambda strategy, unit_type: self.selection.command(state, strategy, unit_type),
            losses=self.selection.recorded_losses(state),
            postures=self.selection.own_postures(state),
            selected_force=self._selected_force,
            on_select=self._select_force,
        )
        imgui.separator()
        imgui.text("Observed known categories (I / G / A / N)")
        for side in ("A", "B"):
            counts = category_counts(groups, side)
            imgui.text(f"{side}: " + " / ".join(str(counts[key]) for key in "IGAN"))

    def _select_force(self, key):
        self._selected_force = key
