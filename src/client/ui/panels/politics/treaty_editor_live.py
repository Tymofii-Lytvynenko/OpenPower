"""Live treaty proposal editor backed by the authoritative action contract."""

from __future__ import annotations

from modules.base.systems.world.treaty_proposal_policy import (
    country_diplomacy_restriction,
    treaty_title_restriction,
)
from src.client.ui.core.containers import WindowManager
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.core.primitives import UIPrimitives as Prims
from src.client.ui.layouts.gml_layout import gml_child_frame
from src.client.ui.panels.politics.treaty_participant_dialog import (
    TreatyParticipantDialog,
)
from src.client.ui.panels.shared.panel_data import active_country_tags
from src.client.ui.panels.shared.panel_widgets import draw_required_tables
from src.shared.actions import ActionCreateTreaty
from src.shared.treaties import TREATY_DEFINITIONS, treaty_type_labels


class LiveTreatyEditorPanel:
    """Builds proposals from current state instead of presentation-only mock data."""

    def __init__(self) -> None:
        self._type_options = list(treaty_type_labels())
        self._type_index = 0
        self._target_index = 0
        self._title = ""
        self._terms = ""
        self._open_membership = False
        self._minimum_relation = -100.0
        self._maximum_geographic_distance = 0.0
        self._maximum_military_ratio = 0.0
        self._maximum_economic_ratio = 0.0
        self._maximum_research_ratio = 0.0
        self._government_type = ""
        self._allow_members_at_war = False
        self._participant_dialog = TreatyParticipantDialog()
        self._participant_sides: tuple[set[str], set[str]] = (set(), set())
        self._participant_seed: tuple[str, str, str] | None = None
        self._sponsor_tag = ""
        self._prepared_target = ""
        self._invert_sides = False

    def prepare(self, sponsor: str, target: str, treaty_type: str, *, invert_sides=False) -> None:
        """Open a country-context proposal without changing the selected map country."""
        self._type_index = next(i for i, option in enumerate(self._type_options) if option[0] == treaty_type)
        self._sponsor_tag, self._prepared_target = sponsor, target
        self._invert_sides = invert_sides
        self._title = self._terms = ""
        self._participant_sides = (set(), set())
        self._participant_seed = None

    def render(self, state, context: PanelRenderContext) -> bool:
        if not self._participant_dialog.is_open:
            with WindowManager.window(
                "Treaty proposal", x=350, y=160, w=650, h=650,
                test_id="treaty_proposal.panel",
            ) as is_open:
                if not is_open:
                    self._sponsor_tag = ""
                    self._invert_sides = False
                    return False
                # OpenPower's editable conditions exceed the source's fixed fields.
                # Keep them in its scrollable inner frame; mixing one fixed button
                # with flowing rows moved the cursor back over existing text.
                with gml_child_frame("Treaty_Details_Window/frmInner", padding=(6.0, 6.0)) as opened:
                    if opened and draw_required_tables(
                        state, ("countries_treaties", "pending_treaties")
                    ):
                        self._render_content(state, context)
        updated_sides = self._participant_dialog.render(state)
        if updated_sides is not None:
            self._participant_sides = updated_sides
        return True

    def _render_content(self, state, context: PanelRenderContext) -> None:
        country_tag = self._sponsor_tag or str(context.target_tag or "").upper()
        countries = self._country_tags(state, country_tag)
        if (not context.is_own_country and not self._sponsor_tag) or context.net_client is None:
            imgui.text_disabled("Select your own country to sponsor a treaty proposal.")
            return
        if not countries:
            imgui.text_disabled("No eligible counterpart countries are available.")
            return

        type_labels = [label for _, label in self._type_options]
        if self._prepared_target:
            if self._prepared_target in countries:
                self._target_index = countries.index(self._prepared_target)
            self._prepared_target = ""
        self._type_index = Prims.combo_row("TYPE", self._type_index, type_labels, 140.0)
        treaty_type, treaty_label = self._type_options[self._type_index]
        definition = TREATY_DEFINITIONS[treaty_type]
        self._target_index = min(self._target_index, len(countries) - 1)
        self._target_index = Prims.combo_row("COUNTERPART", self._target_index, countries, 140.0)
        target = countries[self._target_index]

        self._sync_participant_sides(country_tag, target, treaty_type, definition)

        if not self._title:
            self._title = f"{country_tag} {treaty_label}"
        _, self._title = imgui.input_text(
            "NAME", self._title, 160, test_id="treaty.proposal.title"
        )
        _, self._terms = imgui.input_text_multiline(
            "TERMS", self._terms, (max(100.0, imgui.get_content_region_avail().x - 50.0), 72.0),
            test_id="treaty.proposal.terms"
        )
        imgui.text_wrapped(definition.description)

        if definition.multi_member:
            imgui.separator()
            imgui.text("INITIAL MEMBERS")
            imgui.text_disabled("Choose the proposed treaty sides from OpenPower countries.")
            if imgui.button(
                "EDIT PARTICIPANTS",
                (190.0, 25.0),
                test_id="treaty.proposal.edit_participants",
            ):
                side_a, side_b = self._participant_sides
                self._participant_dialog.open(
                    side_a=side_a,
                    side_b=side_b,
                    two_sided=definition.two_sided,
                    protected_a={target if self._invert_sides else country_tag},
                    protected_b=({country_tag if self._invert_sides else target}
                                 if definition.two_sided else set()),
                )

        if definition.long_term:
            _, self._open_membership = imgui.checkbox("Open to eligible new members", self._open_membership)
            changed, self._minimum_relation = imgui.slider_float(
                "Minimum relation", self._minimum_relation, -100.0, 100.0, "%.0f"
            )
            _, self._maximum_geographic_distance = imgui.slider_float(
                "Maximum distance (km)", self._maximum_geographic_distance, 0.0, 20_000.0, "%.0f"
            )
            _, self._maximum_military_ratio = imgui.slider_float(
                "Max. military ratio", self._maximum_military_ratio, 0.0, 10.0, "%.2f"
            )
            _, self._maximum_economic_ratio = imgui.slider_float(
                "Max. economic ratio", self._maximum_economic_ratio, 0.0, 10.0, "%.2f"
            )
            _, self._maximum_research_ratio = imgui.slider_float(
                "Max. research ratio", self._maximum_research_ratio, 0.0, 10.0, "%.2f"
            )
            _, self._government_type = imgui.input_text("Government type", self._government_type, 64)
            _, self._allow_members_at_war = imgui.checkbox("Allow members to be at war", self._allow_members_at_war)

        imgui.separator()
        can_submit = bool(country_tag and target and target != country_tag)
        imgui.begin_disabled(not can_submit)
        if imgui.button("SEND PROPOSAL", (-1, 30), test_id="treaty.proposal.submit"):
            # Recheck the latest snapshot: a draft can outlive a government
            # change or another proposal reserving its name.
            reason = country_diplomacy_restriction(state.tables.get("country_governments"), country_tag)
            reason = reason or treaty_title_restriction(
                self._title.strip() or treaty_label,
                state.tables.get("countries_treaties"), state.tables.get("pending_treaties"),
            )
            if reason:
                if context.on_notice:
                    context.on_notice("Treaty proposal", reason)
                imgui.end_disabled()
                return
            selected_a, selected_b = self._participant_sides
            if definition.two_sided:
                side_a = sorted(selected_a | {target if self._invert_sides else country_tag})
                side_b = sorted(selected_b | {country_tag if self._invert_sides else target})
                members = sorted(set(side_a) | set(side_b))
            else:
                side_a = sorted(selected_a | {country_tag, target})
                side_b = []
                members = side_a
            context.net_client.send_action(
                ActionCreateTreaty(
                    player_id=context.net_client.player_id,
                    source_country_tag=country_tag,
                    target_country_tag=target,
                    treaty_type=treaty_type,
                    title=self._title.strip() or treaty_label,
                    terms=self._terms.strip(),
                    side_a_country_tags=side_a,
                    side_b_country_tags=side_b,
                    member_country_tags=members,
                    conditions={
                        "minimum_relation": self._minimum_relation,
                        "maximum_geographic_distance_km": self._maximum_geographic_distance,
                        "max_military_strength_ratio": self._maximum_military_ratio,
                        "max_economic_strength_ratio": self._maximum_economic_ratio,
                        "max_research_ratio": self._maximum_research_ratio,
                        "government_type": self._government_type.strip(),
                        "allow_members_at_war": self._allow_members_at_war,
                    },
                    open_to_new_members=self._open_membership,
                )
            )
            self._terms = ""
        imgui.end_disabled()

    def _sync_participant_sides(self, source: str, target: str, treaty_type: str, definition) -> None:
        # Inverted requests must show the same sides that will be dispatched.
        if definition.two_sided and self._invert_sides:
            source, target = target, source
        seed = (source, target, treaty_type)
        if self._participant_seed != seed:
            old_a, old_b = self._participant_sides
            existing = old_a | old_b
            if definition.two_sided:
                extras = existing - {source, target}
                self._participant_sides = ({source}, {target, *extras})
            else:
                self._participant_sides = (existing | {source, target}, set())
            self._participant_seed = seed

        side_a, side_b = self._participant_sides
        if definition.two_sided:
            side_a.add(source)
            side_b.add(target)
            side_a.difference_update(side_b)
        else:
            side_a.update((source, target))
            side_b.clear()

    def _country_tags(self, state, own_country_tag: str) -> list[str]:
        return [tag for tag in active_country_tags(state) if tag != own_country_tag]
