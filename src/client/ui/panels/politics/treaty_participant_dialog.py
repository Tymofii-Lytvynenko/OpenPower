from __future__ import annotations

from src.client.renderers.flag_renderer import FlagRenderer
from src.client.ui.core.containers import WindowManager
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.layouts.gml_layout import active_gml_layout
from src.client.ui.panels.shared.panel_data import active_country_tags, resolve_country_name


class TreatyParticipantDialog:
    """Edits draft treaty sides with OpenPower's current country catalog."""

    _ROOT = "Add_Remove_Window/frmInner/frmItems"

    def __init__(self) -> None:
        self._open = False
        self._two_sided = False
        self._protected_a: set[str] = set()
        self._protected_b: set[str] = set()
        self._side_a: set[str] = set()
        self._side_b: set[str] = set()
        self._ineligible_tags: set[str] = set()
        self._selected_by_list: dict[str, set[str]] = {"available": set(), "a": set(), "b": set()}
        self._selection_anchors: dict[str, str] = {"available": "", "a": "", "b": ""}
        self._waiting_for_result = False
        self._flags = FlagRenderer()

    @property
    def is_open(self) -> bool:
        return self._open

    def resolve_result(self, *, applied: bool) -> None:
        """Keep rejected drafts editable and close only after authoritative acceptance."""
        if not self._open:
            return
        self._waiting_for_result = False
        if applied:
            self._open = False

    def open(
        self,
        *,
        side_a: set[str],
        side_b: set[str],
        two_sided: bool,
        protected_a: set[str],
        protected_b: set[str],
        ineligible_tags: set[str] | frozenset[str] = frozenset(),
    ) -> None:
        self._side_a = set(side_a)
        self._side_b = set(side_b)
        self._two_sided = bool(two_sided)
        self._protected_a = set(protected_a)
        self._protected_b = set(protected_b)
        self._ineligible_tags = set(ineligible_tags)
        self._clear_selections()
        self._waiting_for_result = False
        self._open = True

    def dismiss(self) -> None:
        """Discard a draft whose owning inspection is no longer valid."""
        self._open = False

    def _clear_selections(self) -> None:
        for selection in self._selected_by_list.values():
            selection.clear()
        for list_name in self._selection_anchors:
            self._selection_anchors[list_name] = ""

    def remove_ineligible(self) -> None:
        """Stage invalid-member removal in the same draft used by Apply."""
        self._side_a.difference_update(self._ineligible_tags)
        self._side_b.difference_update(self._ineligible_tags)
        self._selected_by_list["a"].difference_update(self._ineligible_tags)
        self._selected_by_list["b"].difference_update(self._ineligible_tags)
        self._ineligible_tags.clear()

    def mark_ineligible(self, country_tags: set[str] | frozenset[str]) -> None:
        self._ineligible_tags.update(country_tags)

    def render(
        self,
        state,
        *,
        ineligible_tags: set[str] | frozenset[str] = frozenset(),
    ) -> tuple[set[str], set[str]] | None:
        if not self._open:
            return None

        self._ineligible_tags.update(ineligible_tags)

        countries = self._country_options(state)
        country_by_tag = dict(countries)
        all_tags = set(country_by_tag)
        self._ineligible_tags.update((self._side_a | self._side_b) - all_tags)
        sort_by_name = lambda tag: (country_by_tag.get(tag, tag).casefold(), tag)
        available = sorted(all_tags - self._side_a - self._side_b, key=sort_by_name)
        side_a = sorted(self._side_a, key=sort_by_name)
        side_b = sorted(self._side_b, key=sort_by_name)
        committed = None

        with WindowManager.window(
            "Treaty participants",
            x=320,
            y=130,
            w=635,
            h=437,
            test_id="treaty.participants.dialog",
            gml_template="Add_Remove_Window",
            avoid_overlaps=True,
            bottom_clearance=104.0,
        ) as is_open:
            if not is_open:
                self._open = False
                self._waiting_for_result = False
                return None

            imgui.begin_disabled(self._waiting_for_result)
            if not self._two_sided:
                session = active_gml_layout()
                if session is not None:
                    source_available = session.rect_for(f"{self._ROOT}/frmUnselected/lstUnselected")
                    session.resize_component(
                        f"{self._ROOT}/frmSideA/lstSelectedA",
                        height=source_available.height,
                    )
            self._render_country_list(
                "Available countries",
                available,
                country_by_tag,
                list_name="available",
                selected_test_id="treaty.participants.available",
                frame_path=f"{self._ROOT}/frmUnselected/lstUnselected",
                heading_path=f"{self._ROOT}/txtTransparentLabel1",
            )
            self._render_country_list(
                "Side A",
                side_a,
                country_by_tag,
                list_name="a",
                selected_test_id="treaty.participants.side_a",
                frame_path=f"{self._ROOT}/frmSideA/lstSelectedA",
                heading_path=f"{self._ROOT}/txtTransparentLabel2",
            )
            if self._two_sided:
                self._render_country_list(
                    "Side B",
                    side_b,
                    country_by_tag,
                    list_name="b",
                    selected_test_id="treaty.participants.side_b",
                    frame_path=f"{self._ROOT}/frmSideB/lstSelectedB",
                    heading_path=f"{self._ROOT}/txtTransparentLabel3",
                )
            self._render_transfer_buttons()

            imgui.begin_disabled(len(self._side_a | self._side_b) < 2)
            if imgui.button(
                "✓",
                test_id="treaty.participants.apply",
                gml_id="Add_Remove_Window/frmTitle/btnApply",
            ):
                committed = (set(self._side_a), set(self._side_b))
                self._waiting_for_result = True
            imgui.end_disabled()
            imgui.end_disabled()

        return committed

    def _render_country_list(
        self,
        heading: str,
        tags: list[str],
        country_by_tag: dict[str, str],
        *,
        list_name: str,
        selected_test_id: str,
        frame_path: str,
        heading_path: str,
    ) -> None:
        imgui.text_disabled(heading.upper(), gml_id=heading_path)
        if not imgui.begin_child(
            frame_path.rsplit("/", 1)[-1],
            (0.0, 0.0),
            child_flags=imgui.ChildFlags_.borders,
            gml_id=frame_path,
            test_id=f"treaty.participants.list.{list_name}",
        ):
            imgui.end_child()
            return
        try:
            for tag in tags:
                suffix = "  [INELIGIBLE]" if tag in self._ineligible_tags else ""
                label = f"{tag}  {country_by_tag.get(tag, tag)}{suffix}##{tag}"
                self._flags.draw_flag(tag, 18.0, 12.0)
                flag_clicked = imgui.is_item_clicked()
                imgui.same_line()
                selected = tag in self._selected_by_list[list_name]
                clicked = imgui.selectable(
                    label,
                    selected,
                    size=(max(1.0, float(imgui.get_content_region_avail().x)), 16.0),
                    test_id=f"{selected_test_id}.{tag}",
                )[0]
                if flag_clicked or clicked:
                    self._select_country(list_name, tags, tag)
        finally:
            imgui.end_child()

    def _render_transfer_buttons(self) -> None:
        def transfer(label: str, component: str, test_id: str, callback, *, enabled=True):
            imgui.begin_disabled(not enabled)
            if imgui.button(
                label,
                test_id=test_id,
                gml_id=f"{self._ROOT}/{component}",
            ):
                callback()
            imgui.end_disabled()

        transfer(
            "→",
            "btnRightA",
            "treaty.participants.add_a",
            lambda: self._move_to_side("a"),
            enabled=bool(self._selected_by_list["available"]),
        )
        transfer(
            "←",
            "btnLeftA",
            "treaty.participants.remove_a",
            lambda: self._move_to_available("a"),
            enabled=bool(self._selected_by_list["a"] - self._protected_a),
        )
        if self._two_sided:
            transfer(
                "→",
                "btnRightB",
                "treaty.participants.add_b",
                lambda: self._move_to_side("b"),
                enabled=bool(self._selected_by_list["available"]),
            )
            transfer(
                "←",
                "btnLeftB",
                "treaty.participants.remove_b",
                lambda: self._move_to_available("b"),
                enabled=bool(self._selected_by_list["b"] - self._protected_b),
            )
        transfer(
            "⇄",
            "btnRightAB",
            "treaty.participants.move_a_to_b",
            lambda: self._move_between_sides("a", "b"),
            enabled=self._two_sided
            and bool(self._selected_by_list["a"] - self._protected_a),
        )
        transfer(
            "⇄",
            "btnLeftAB",
            "treaty.participants.move_b_to_a",
            lambda: self._move_between_sides("b", "a"),
            enabled=self._two_sided
            and bool(self._selected_by_list["b"] - self._protected_b),
        )

    def _move_to_side(self, side: str) -> None:
        if side == "b" and not self._two_sided:
            return
        selected = self._selected_by_list["available"]
        target, other = (self._side_a, self._side_b) if side == "a" else (self._side_b, self._side_a)
        moved = set(selected)
        target.update(moved)
        other.difference_update(moved)
        selected.clear()

    def _move_to_available(self, side: str) -> None:
        if side == "b" and not self._two_sided:
            return
        selected = self._selected_by_list[side]
        movable = selected - (self._protected_a | self._protected_b)
        target = self._side_a if side == "a" else self._side_b
        target.difference_update(movable)
        self._ineligible_tags.difference_update(movable)
        selected.difference_update(movable)

    def _move_between_sides(self, source: str, target: str) -> None:
        if not self._two_sided:
            return
        selected = self._selected_by_list[source]
        protected = self._protected_a if source == "a" else self._protected_b
        movable = selected - protected
        source_set, target_set = (
            (self._side_a, self._side_b)
            if source == "a"
            else (self._side_b, self._side_a)
        )
        source_set.difference_update(movable)
        target_set.update(movable)
        selected.difference_update(movable)

    def _select_country(self, list_name: str, tags: list[str], tag: str) -> None:
        selected = self._selected_by_list[list_name]
        io = imgui.get_io()
        anchor = self._selection_anchors[list_name]
        if io.key_shift and anchor in tags:
            start, end = sorted((tags.index(anchor), tags.index(tag)))
            selected.clear()
            selected.update(tags[start : end + 1])
        elif io.key_ctrl:
            if tag in selected:
                selected.remove(tag)
            else:
                selected.add(tag)
            self._selection_anchors[list_name] = tag
        else:
            selected.clear()
            selected.add(tag)
            self._selection_anchors[list_name] = tag

    @staticmethod
    def _country_options(state) -> list[tuple[str, str]]:
        return [(tag, resolve_country_name(state, tag)) for tag in active_country_tags(state)]
