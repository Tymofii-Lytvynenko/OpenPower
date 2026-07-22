"""Live treaty proposal editor backed by the authoritative action contract."""

from __future__ import annotations

from imgui_bundle import imgui

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.core.primitives import UIPrimitives as Prims
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
        self._selected_members: set[str] = set()

    def render(self, state, context: PanelRenderContext) -> bool:
        with WindowManager.window("Treaty proposal", x=350, y=160, w=650, h=650) as is_open:
            if not is_open:
                return False
            self._render_content(state, context)
            return True

    def _render_content(self, state, context: PanelRenderContext) -> None:
        draw_required_tables(state, ("countries_treaties", "pending_treaties", "countries_relations"))
        country_tag = str(context.target_tag or "").upper()
        countries = self._country_tags(state, country_tag)
        if not context.is_own_country or context.net_client is None:
            imgui.text_disabled("Select your own country to sponsor a treaty proposal.")
            return
        if not countries:
            imgui.text_disabled("No eligible counterpart countries are available.")
            return

        type_labels = [label for _, label in self._type_options]
        self._type_index = Prims.combo_row("TYPE", self._type_index, type_labels, 140.0)
        treaty_type, treaty_label = self._type_options[self._type_index]
        definition = TREATY_DEFINITIONS[treaty_type]
        self._target_index = min(self._target_index, len(countries) - 1)
        self._target_index = Prims.combo_row("COUNTERPART", self._target_index, countries, 140.0)
        target = countries[self._target_index]

        if not self._title:
            self._title = f"{country_tag} {treaty_label}"
        _, self._title = imgui.input_text("NAME", self._title, 160)
        _, self._terms = imgui.input_text_multiline("TERMS", self._terms, (-1, 72))
        imgui.text_wrapped(definition.description)

        if definition.multi_member:
            imgui.separator()
            imgui.text("INITIAL MEMBERS")
            imgui.text_disabled("Selected countries are invited alongside the chosen counterpart.")
            imgui.begin_child("treaty_members", (0.0, 145.0), True)
            for member in countries:
                checked = member in self._selected_members
                changed, checked = imgui.checkbox(f"{member}##member-{member}", checked)
                if changed:
                    if checked:
                        self._selected_members.add(member)
                    else:
                        self._selected_members.discard(member)
            imgui.end_child()

        if definition.long_term:
            _, self._open_membership = imgui.checkbox("Open to eligible new members", self._open_membership)
            changed, self._minimum_relation = imgui.slider_float(
                "Minimum relation", self._minimum_relation, -100.0, 100.0, "%.0f"
            )
            _, self._maximum_geographic_distance = imgui.slider_float(
                "Maximum distance (km)", self._maximum_geographic_distance, 0.0, 20_000.0, "%.0f"
            )
            _, self._maximum_military_ratio = imgui.slider_float(
                "Maximum military-strength ratio", self._maximum_military_ratio, 0.0, 10.0, "%.2f"
            )
            _, self._maximum_economic_ratio = imgui.slider_float(
                "Maximum economic-strength ratio", self._maximum_economic_ratio, 0.0, 10.0, "%.2f"
            )
            _, self._maximum_research_ratio = imgui.slider_float(
                "Maximum research-capacity ratio", self._maximum_research_ratio, 0.0, 10.0, "%.2f"
            )
            _, self._government_type = imgui.input_text("Required government type", self._government_type, 64)
            _, self._allow_members_at_war = imgui.checkbox("Allow members to be at war", self._allow_members_at_war)

        imgui.separator()
        can_submit = bool(country_tag and target and target != country_tag)
        imgui.begin_disabled(not can_submit)
        if imgui.button("SEND PROPOSAL", (-1, 30)):
            members = sorted({country_tag, target, *self._selected_members})
            side_a = [country_tag]
            side_b = [target] if definition.two_sided else []
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

    def _country_tags(self, state, own_country_tag: str) -> list[str]:
        countries = state.tables.get("countries")
        if countries is None or countries.is_empty() or "id" not in countries.columns:
            return []
        return sorted(
            str(country_id).upper()
            for country_id in countries["id"].to_list()
            if str(country_id).upper() != own_country_tag
        )
