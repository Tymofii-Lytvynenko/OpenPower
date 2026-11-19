from __future__ import annotations

from collections.abc import Callable, Sequence

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.instrumented_imgui import imgui


class FreeplaySetupWindow:
    """Collect a country and optional party before starting open-ended play."""

    def render(
        self,
        screen_width: float,
        screen_height: float,
        country_options: Sequence[tuple[str, str]],
        selected_country_id: str | None,
        selected_party_name: str,
        party_available: bool,
        on_select_country: Callable[[str], None],
        on_open_profile: Callable[[], None],
        on_open_party: Callable[[], None],
        on_start: Callable[[], None],
        on_open_scenarios: Callable[[], None],
        on_cancel: Callable[[], None],
    ) -> None:
        window_open = True
        with WindowManager.window(
            "START FREEPLAY",
            x=(float(screen_width) - 390.0) / 2.0,
            y=(float(screen_height) - 240.0) / 2.0,
            w=390,
            h=240,
            test_id="new_game.freeplay.dialog",
            follow_position=True,
        ) as opened:
            window_open = opened
            if opened:
                self._render_content(
                    country_options,
                    selected_country_id,
                    selected_party_name,
                    party_available,
                    on_select_country,
                    on_open_profile,
                    on_open_party,
                    on_start,
                    on_open_scenarios,
                    on_cancel,
                )
        if not window_open:
            on_cancel()

    def _render_content(
        self,
        country_options: Sequence[tuple[str, str]],
        selected_country_id: str | None,
        selected_party_name: str,
        party_available: bool,
        on_select_country: Callable[[str], None],
        on_open_profile: Callable[[], None],
        on_open_party: Callable[[], None],
        on_start: Callable[[], None],
        on_open_scenarios: Callable[[], None],
        on_cancel: Callable[[], None],
    ) -> None:
        selected = str(selected_country_id or "").strip().upper()
        current_index = next(
            (index + 1 for index, (country_id, _) in enumerate(country_options)
             if str(country_id).strip().upper() == selected),
            0,
        )
        labels = ["Select a country", *(label for _, label in country_options)]

        imgui.text_wrapped("Choose a country to begin an open-ended game.")
        imgui.text("COUNTRY")
        imgui.set_next_item_width(250.0)
        changed, selected_index = imgui.combo(
            "##freeplay-country",
            current_index,
            labels,
            test_id="new_game.freeplay.country.select",
        )
        if changed:
            on_select_country(
                country_options[selected_index - 1][0]
                if 0 < selected_index <= len(country_options)
                else ""
            )

        imgui.same_line()
        if imgui.button("PROFILE", test_id="new_game.freeplay.profile.open"):
            on_open_profile()

        imgui.text(f"PARTY: {selected_party_name or 'Use the current government'}")
        imgui.begin_disabled(not bool(selected and party_available))
        try:
            if imgui.button("SELECT PARTY", test_id="new_game.freeplay.party.open"):
                on_open_party()
        finally:
            imgui.end_disabled()

        imgui.separator()
        imgui.begin_disabled(not bool(selected))
        try:
            if imgui.button("START FREEPLAY", test_id="new_game.freeplay.start"):
                on_start()
        finally:
            imgui.end_disabled()

        imgui.same_line()
        if imgui.button("SCENARIOS...", test_id="new_game.freeplay.scenarios.open"):
            on_open_scenarios()
        imgui.same_line()
        if imgui.button("CANCEL", test_id="new_game.freeplay.cancel"):
            on_cancel()
