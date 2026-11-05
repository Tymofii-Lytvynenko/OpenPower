from __future__ import annotations

from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, metadata

from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.components.reference_credit_roster import (
    REFERENCE_CREDIT_SUPPLEMENTAL_TEXT,
    REFERENCE_STEAM_CREDIT_GROUPS,
)
from src.client.ui.layouts.gml_layout import GMLComponent, GMLRect, get_gml_layout


@dataclass(frozen=True, slots=True)
class ProjectCredits:
    project_name: str
    version: str
    authors: tuple[str, ...]
    license_name: str


def load_project_credits() -> ProjectCredits:
    """Read attribution from the installed distribution metadata sourced by pyproject.toml."""
    try:
        project = metadata("openpower-engine")
    except PackageNotFoundError:
        return ProjectCredits("OpenPower Engine", "", (), "")

    authors = tuple(project.get_all("Author") or ())
    license_text = project.get("License", "") or ""
    license_name = next(
        (line.lstrip("# ").strip() for line in license_text.splitlines() if line.strip()),
        "",
    )
    return ProjectCredits(
        project_name="OpenPower Engine",
        version=project.get("Version", ""),
        authors=authors,
        license_name=license_name,
    )


class ProjectCreditsContent:
    """Render OpenPower package attribution and the source game's credit roster."""

    _GROUP_TITLE_FONT_SIZE = 13.0
    _CREDIT_FONT_SIZE = 9.0
    _GML_CREDITS_PATH = "Credits_Window/frmInner/frmCredits/frmInner"
    _SOURCE_RUNTIME_SHIFT_Y = 140.0
    _GOLEMLABS_ART_TEAM_SLOT = "lblTitle5"
    _GOLEMLABS_ROLE_SLOTS = (
        "lblTitle1", "lblTitle2", "lblTitle3", "lblTitle4",
        "lblTitle21", "lblTitle22", "lblTitle23", "lblTitle25", "lblTitle6", "lblTitle7",
        "lblTitle8", "lblTitle87", "lblTitle89",
    )
    _UNMAPPED_GOLEMLABS_PEOPLE_SLOTS = {"lblTitle35"}
    _NORDIC_ROLE_SLOTS = ("lblDevDirector", "lblNGManagement")
    _NORDIC_PEOPLE_SLOTS = (
        "lblReinhardPollice", "lblKlemensKreuzer", "lblLarsWingefors",
    )

    def __init__(self, credits: ProjectCredits | None = None):
        self._credits = credits or load_project_credits()
        self._layout = get_gml_layout("Credits_Window")
        self._slots = self._build_source_slots()

    @staticmethod
    def _push_font_size(font_size: float) -> None:
        style = imgui.get_style()
        scale = max(0.1, float(style.font_scale_main) * float(style.font_scale_dpi))
        imgui.push_font(None, font_size / scale)

    def _component(self, component_id: str) -> GMLComponent:
        component = self._layout.component(f"{self._GML_CREDITS_PATH}/{component_id}")
        if component is None:
            raise RuntimeError(f"Missing GML credits slot {component_id!r}.")
        return component

    def _column_slots(
        self,
        *,
        x: float,
        width: float,
        minimum_y: float,
        maximum_y: float | None = None,
        excluded: set[str] | None = None,
    ) -> tuple[GMLComponent, ...]:
        excluded_ids = excluded or set()
        components = (
            component for component in self._layout.components
            if component.path.startswith(f"{self._GML_CREDITS_PATH}/")
            and component.component_id.startswith("lblTitle")
            and component.component_id not in excluded_ids
            and component.local_rect.x == x
            and component.local_rect.width == width
            and component.local_rect.y >= minimum_y
            and (maximum_y is None or component.local_rect.y < maximum_y)
        )
        return tuple(sorted(components, key=lambda item: item.local_rect.y))

    def _build_source_slots(self) -> dict[str, tuple[tuple[GMLComponent, ...], tuple[GMLComponent, ...]]]:
        golem_roles = tuple(self._component(name) for name in self._GOLEMLABS_ROLE_SLOTS)
        golem_people = self._column_slots(
            x=250.0,
            width=150.0,
            minimum_y=38.0,
            maximum_y=636.0,
            excluded=self._UNMAPPED_GOLEMLABS_PEOPLE_SLOTS,
        )
        nordic_roles = tuple(self._component(name) for name in self._NORDIC_ROLE_SLOTS)
        nordic_people = tuple(self._component(name) for name in self._NORDIC_PEOPLE_SLOTS)
        dream_roles = self._column_slots(x=0.0, width=249.0, minimum_y=636.0)
        dream_people = self._column_slots(x=250.0, width=150.0, minimum_y=636.0)
        slots = {
            "golemlabs": (golem_roles, golem_people),
            "nordic_games": (nordic_roles, nordic_people),
            "dreamcatcher": (dream_roles, dream_people),
        }
        for group in REFERENCE_STEAM_CREDIT_GROUPS:
            role_slots, people_slots = slots[group.id]
            expected_people = sum(len(entry.people) for entry in group.entries)
            if len(role_slots) != len(group.entries) or len(people_slots) != expected_people:
                raise RuntimeError(
                    f"GML credits slot mismatch for {group.id}: "
                    f"{len(role_slots)} roles/{len(people_slots)} names, "
                    f"expected {len(group.entries)}/{expected_people}."
                )
        return slots

    def _runtime_rect(self, component: GMLComponent) -> GMLRect:
        rect = component.local_rect
        # GCreditsWindow::OnCreate moves every lblTitle at source y >= 636 by 140px.
        if "lblTitle" in component.component_id and rect.y >= 636.0:
            return GMLRect(rect.x, rect.y + self._SOURCE_RUNTIME_SHIFT_Y, rect.width, rect.height)
        return rect

    def _render_source_label(
        self,
        component: GMLComponent,
        value: str,
        *,
        fallback_font_size: float,
        test_id: str | None = None,
    ) -> float:
        font_size = component.font_size or fallback_font_size
        self._push_font_size(font_size)
        try:
            # Measure after selecting the source font so text placement uses the same metrics as rendering.
            rect = self._runtime_rect(component)
            text_size = imgui.calc_text_size(value)
            text_width = float(text_size.x)
            text_height = float(text_size.y)
            alignment = component.text_align
            x = rect.x
            if alignment.endswith("Right"):
                x += rect.width - text_width
            elif alignment.endswith("Center"):
                x += (rect.width - text_width) / 2.0
            y = rect.y
            if alignment.startswith("Middle"):
                y += max(0.0, (rect.height - text_height) / 2.0)
            x += component.text_offset[0]
            y += component.text_offset[1]

            window_position = imgui.get_window_pos()
            scroll_x = float(imgui.get_scroll_x())
            scroll_y = float(imgui.get_scroll_y())
            clip_min = (
                float(window_position.x) + rect.x - scroll_x,
                float(window_position.y) + rect.y - scroll_y,
            )
            clip_max = (clip_min[0] + rect.width, clip_min[1] + rect.height)
            imgui.push_clip_rect(clip_min, clip_max, True)
            try:
                imgui.set_cursor_pos((x, y))
                imgui.text(value, test_id=test_id)
            finally:
                imgui.pop_clip_rect()
            return text_width
        finally:
            imgui.pop_font()

    def render(self, test_id_prefix: str = "project_credits") -> None:
        for group in REFERENCE_STEAM_CREDIT_GROUPS:
            title_component_id = {
                "golemlabs": "lblTitle",
                "nordic_games": "lblNordicGames",
                "dreamcatcher": "lblTitle9",
            }[group.id]
            group_test_id = (
                f"{test_id_prefix}.source.title"
                if group.id == "golemlabs"
                else f"{test_id_prefix}.source.group.{group.id}"
            )
            self._render_source_label(
                self._component(title_component_id),
                group.name,
                fallback_font_size=self._GROUP_TITLE_FONT_SIZE,
                test_id=group_test_id,
            )

            if group.id == "golemlabs":
                # The heading has its own slot before the individual credit rows.
                self._render_source_label(
                    self._component(self._GOLEMLABS_ART_TEAM_SLOT),
                    "Art team",
                    fallback_font_size=self._CREDIT_FONT_SIZE,
                    test_id=f"{test_id_prefix}.source.golemlabs.section.art_team",
                )

            role_slots, people_slots = self._slots[group.id]
            people_slot_index = 0
            for entry_index, entry in enumerate(group.entries):
                row_id = f"{test_id_prefix}.source.{group.id}.{entry_index}"
                self._render_source_label(
                    role_slots[entry_index],
                    entry.role,
                    fallback_font_size=self._CREDIT_FONT_SIZE,
                    test_id=f"{row_id}.role",
                )
                for person_index, person in enumerate(entry.people):
                    person_slot = people_slots[people_slot_index]
                    people_slot_index += 1
                    person_test_id = (
                        f"{row_id}.people"
                        if person_index == len(entry.people) - 1
                        else f"{row_id}.person.{person_index}"
                    )
                    text_width = self._render_source_label(
                        person_slot,
                        person,
                        fallback_font_size=self._CREDIT_FONT_SIZE,
                        test_id=person_test_id,
                    )
                    if imgui.is_item_hovered() and text_width > (
                        person_slot.local_rect.width - abs(person_slot.text_offset[0])
                    ):
                        imgui.set_tooltip(person)

        contact_url = REFERENCE_CREDIT_SUPPLEMENTAL_TEXT[("golemlabs", "Sound and Music")]
        # The published credits list appends this URL to Eric Vigneault; GML gives it a separate row.
        # The row-to-URL mapping is inferred because the original localization token is not included.
        self._render_source_label(
            self._component("lblTitle35"),
            contact_url,
            fallback_font_size=self._CREDIT_FONT_SIZE,
            test_id=f"{test_id_prefix}.source.golemlabs.music_contact",
        )
        if imgui.is_item_hovered():
            imgui.set_tooltip(
                "Published with Eric Vigneault; mapped to the separate credits row by layout."
            )

        copyright_text = REFERENCE_CREDIT_SUPPLEMENTAL_TEXT[("golemlabs", "Copyright")]
        # The manual places this footer after the credits, and GML has a final full-width row.
        # The label mapping remains inferred until the original localization token is recovered.
        self._render_source_label(
            self._component("lblTitle91"),
            copyright_text,
            fallback_font_size=self._CREDIT_FONT_SIZE,
            test_id=f"{test_id_prefix}.source.golemlabs.copyright",
        )
        if imgui.is_item_hovered():
            imgui.set_tooltip(
                "Inferred from the final credits row and the copyright footer in the source documentation."
            )

        imgui.separator()
        imgui.text("OPENPOWER ENGINE", test_id=f"{test_id_prefix}.openpower.title")
        imgui.text(self._credits.project_name, test_id=f"{test_id_prefix}.openpower.name")
        if self._credits.version:
            imgui.text(f"Version: {self._credits.version}")

        if self._credits.authors:
            imgui.text("AUTHORS")
            for author in self._credits.authors:
                imgui.bullet_text(author)

        if self._credits.license_name:
            imgui.text("LICENSE")
            imgui.text_wrapped(
                self._credits.license_name,
                test_id=f"{test_id_prefix}.openpower.license",
            )

        if not self._credits.authors and not self._credits.license_name:
            imgui.text_wrapped(
                "Project attribution metadata is unavailable.",
                test_id=f"{test_id_prefix}.openpower.license",
            )
