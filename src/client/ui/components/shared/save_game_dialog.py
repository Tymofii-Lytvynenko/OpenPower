"""Source-sized save selection with injected persistence and navigation ports."""
from __future__ import annotations

from collections.abc import Callable

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.gml_widgets import GMLWidgets
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.primitives import UIPrimitives
from src.client.ui.layouts.gml_layout import gml_child_frame
from src.core.saves import validate_save_name


class SaveGameDialog:
    def __init__(self, list_saves: Callable[[], list[dict]], save: Callable[[str], None],
                 load: Callable[[str], None], notify: Callable[..., None],
                 on_close: Callable[[], None] | None = None):
        self._list_saves = list_saves
        self._save = save
        self._load = load
        self._notify = notify
        self._on_close = on_close
        self._mode = ""
        self._rows: list[dict] = []
        self._name = ""
        self._selected = ""

    def toggle(self, mode: str) -> None:
        if mode not in {"save", "load"}:
            raise ValueError(f"Unknown save dialog mode: {mode}")
        if self._mode == mode:
            self._mode = ""
            return
        self._mode = mode
        self._rows = self._list_saves()
        self._selected = ""
        self._name = ""

    def submit(self) -> None:
        try:
            name = validate_save_name(self._name if self._mode == "save" else self._selected)
        except ValueError as error:
            self._notify("Save game", str(error), severity="warning")
            return
        if self._mode == "save":
            self._save(name)
        elif self._mode == "load":
            self._load(name)
        self._mode = ""

    def render(self) -> None:
        if not self._mode:
            return
        saving = self._mode == "save"
        template = "Save_Game_Window" if saving else "Load_Saved_Game"
        prefix = f"{self._mode}_game"
        width = 773 if saving else 774
        viewport = imgui.get_io().display_size
        with WindowManager.window(
            "Save game" if saving else "Load game", x=max(0, (viewport.x - width) / 2),
            y=max(0, (viewport.y - 290) / 2), w=width, h=290,
            test_id=f"{prefix}.dialog", gml_template=template,
        ) as opened:
            if not opened:
                self._mode = ""
                if self._on_close is not None:
                    self._on_close()
                return
            ui = GMLWidgets(f"{template}/frmInner")
            frame = "frmSave" if saving else "frmList"
            for slot, text in (("lblSavegame", "SAVE GAME"), ("lblDate", "DATE"),
                               ("lblScenarios", "SCENARIO"), ("lblCountry", "COUNTRY"),
                               ("lblGametime", "GAME TIME")):
                ui.text(f"{frame}/{slot}", text)
            with gml_child_frame(ui.path(f"{frame}/{'lstSaves' if saving else 'lstGames'}"),
                                 bordered=False) as list_open:
                if list_open:
                    if not self._rows:
                        imgui.text_disabled("No saved games.")
                    for row in self._rows:
                        name = str(row.get("name") or "")
                        # Source columns have fixed widths; an unbounded slot
                        # name previously painted over the date column.
                        label = UIPrimitives.fit_text(name, 132.0)
                        # Dear ImGui expands selectable hit rectangles by two
                        # pixels; inset the first column so it stays inside the
                        # clipped GML list frame.
                        imgui.set_cursor_pos_x(imgui.get_cursor_pos_x() + 2.0)
                        if imgui.selectable(f"{label}##slot-{name}", self._selected == name,
                                            size=(132.0, 0.0),
                                            test_id=f"{prefix}.slot.{name}")[0]:
                            self._selected = name
                            if saving:
                                self._name = name
                        if imgui.is_item_hovered():
                            imgui.set_tooltip(name)
                        imgui.same_line(150)
                        imgui.text_disabled(str(row.get("timestamp") or "")[:16].replace("T", " "))
                        for offset, key, width in ((261, "scenario", 125), (396, "country_tag", 180),
                                                   (588, "game_time", 112)):
                            imgui.same_line(offset)
                            value = str(row.get(key) or "—")
                            imgui.text_disabled(UIPrimitives.fit_text(value, width))
                            if imgui.is_item_hovered():
                                imgui.set_tooltip(value)
            if saving:
                ui.text("frmSave/lblSaveName", "Save name")
                _, self._name = imgui.input_text("##save_name", self._name,
                    test_id="save_game.name", gml_id=ui.path("frmSave/edtSaveName"))
            if ui.button("btnSaveGame" if saving else "btnLoadGame",
                         "Save" if saving else "Load", f"{prefix}.submit",
                         enabled=bool(self._name.strip() if saving else self._selected)):
                self.submit()
