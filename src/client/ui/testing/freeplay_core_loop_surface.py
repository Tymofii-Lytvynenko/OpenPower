from __future__ import annotations

from dataclasses import replace

from src.client.ui.components.shared.country_profile_window import CountryProfileWindow
from src.client.ui.components.shared.freeplay_setup_window import FreeplaySetupWindow
from src.client.ui.components.shared.party_selection_window import PartySelectionWindow
from src.client.ui.layouts.game_layout import GameLayout
from src.client.ui.panels.shared.panel_data import resolve_country_name


def build_freeplay_core_loop_surface(
    state,
    client,
    context,
    settings,
    window,
    navigation,
    viewport,
):
    """Exercise the production freeplay setup and HUD with deterministic ports."""
    countries = state.tables.get("countries")
    country_options = []
    if countries is not None and "id" in countries.columns:
        country_options = [
            (
                str(row["id"]).strip().upper(),
                f"{str(row['id']).strip().upper()} - "
                f"{resolve_country_name(state, str(row['id']).strip().upper())}",
            )
            for row in countries.sort("id").iter_rows(named=True)
        ]

    selected: dict[str, str | None] = {"country": None}
    layout: dict[str, GameLayout | None] = {"value": None}
    setup = FreeplaySetupWindow()
    profile = CountryProfileWindow(lambda country: select_country(country))
    party = PartySelectionWindow(lambda party_id: selected.update(party=party_id))
    active_context = {"value": context}

    def select_country(country_id: str) -> None:
        country = str(country_id or "").strip().upper() or None
        selected["country"] = country
        if country is None:
            selected["party"] = ""
            return
        selected["party"] = PartySelectionWindow.default_party_id(state, country)

    def open_profile() -> None:
        eligible_ids = [country_id for country_id, _ in country_options]
        profile.show(state, eligible_ids)

    def open_party() -> None:
        country = selected["country"]
        if country:
            party.show(state, country, str(selected.get("party") or ""))

    def start_freeplay() -> None:
        country = selected["country"]
        if not country:
            return
        client.player_country = country
        active_context["value"] = replace(
            context,
            target_tag=country,
            player_country_tag=country,
            is_own_country=True,
        )
        layout["value"] = GameLayout(
            client,
            country,
            viewport,
            settings,
            window,
        )

    def render() -> None:
        width, height = window.get_size()
        if layout["value"] is None:
            country = selected["country"]
            party_options = PartySelectionWindow.party_options(state, country or "")
            selected_party = next(
                (
                    row for row in party_options
                    if str(row.get("party_id") or "") == str(selected.get("party") or "")
                ),
                None,
            )
            setup.render(
                width,
                height,
                country_options,
                country,
                str(selected_party.get("display_name") or selected.get("party") or "")
                if selected_party
                else "",
                bool(party_options),
                select_country,
                open_profile,
                open_party,
                start_freeplay,
                lambda: navigation.requests.append({"type": "scenario_setup_requested"}),
                lambda: navigation.show_main_menu(None, window.game_config),
            )
            profile.render(width, height)
            party.render(width, height)
            return

        game_layout = layout["value"]
        game_layout.render(
            active_context["value"].selected_region_id,
            60.0,
            navigation,
            client.get_state(),
        )

    return render
