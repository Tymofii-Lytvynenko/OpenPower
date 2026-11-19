from __future__ import annotations

import threading
import logging
from dataclasses import dataclass
from typing import Any

import arcade
import polars as pl

from src.client.services.campaign_selection import filter_playable_countries
from src.client.tasks.session_startup import (
    check_cancelled,
    create_session_until_ready,
    shutdown_session,
    wait_for_initial_state,
)
from src.client.utils.coords_util import calculate_centroid
from src.shared.config import GameConfig

logger = logging.getLogger(__name__)


@dataclass
class FreeplayStartContext:
    session: Any
    player_tag: str
    start_pos: tuple[float, float] | None
    player_party_id: str = ""


class FreeplayStartTask:
    """Start a country-led game without creating campaign state."""

    def __init__(
        self,
        window: arcade.Window,
        config: GameConfig,
        player_tag: str,
        player_party_id: str = "",
    ) -> None:
        self.window = window
        self.config = config
        self.player_tag = str(player_tag or "").strip().upper()
        self.player_party_id = str(player_party_id or "").strip()
        self.progress = 0.0
        self.status_text = "Preparing freeplay..."
        self._cancel_event = threading.Event()
        self._finished = threading.Event()
        self._lifecycle_lock = threading.Lock()
        self._session = None
        self._session_lock = threading.Lock()
        self._session_released = False

    def cancel(self) -> None:
        self._cancel_event.set()
        with self._lifecycle_lock:
            finished = self._finished.is_set()
        if finished:
            self._release_session()

    def _release_session(self) -> None:
        with self._session_lock:
            if self._session_released:
                return
            self._session_released = True
            session = self._session
            self._session = None
        shutdown_session(session)

    def run(self) -> FreeplayStartContext:
        new_session = None
        try:
            check_cancelled(self._cancel_event)
            if not self.player_tag:
                raise ValueError("Choose a playable country before starting freeplay.")

            def update_progress(progress: float, text: str) -> None:
                self.progress = 0.1 + progress * 0.6
                self.status_text = text

            self.status_text = "Starting simulation server..."
            self.progress = 0.1
            new_session = create_session_until_ready(
                self.window.session_factory,
                self.config,
                player_tag=self.player_tag,
                player_party_id=self.player_party_id,
                cancel_event=self._cancel_event,
                on_progress=update_progress,
            )
            self._session = new_session

            self.status_text = "Synchronizing game state..."
            self.progress = 0.8
            state = wait_for_initial_state(
                new_session,
                cancel_event=self._cancel_event,
            )
            self._validate_player_context(state)
            start_pos = self._start_position(state, new_session)

            self.status_text = "Pre-loading map assets..."
            self.progress = 0.9
            self._warmup_file("map/regions.png")
            check_cancelled(self._cancel_event)
            self._warmup_file("map/terrain.png")
            check_cancelled(self._cancel_event)

            self.progress = 1.0
            self.status_text = "Ready."
            return FreeplayStartContext(
                new_session,
                self.player_tag,
                start_pos,
                self.player_party_id,
            )
        except Exception:
            if new_session is not None:
                self._release_session()
            raise
        finally:
            with self._lifecycle_lock:
                self._finished.set()
                cancelled_after_work = self._cancel_event.is_set()
            if cancelled_after_work:
                self._release_session()

    def _validate_player_context(self, state) -> None:
        tables = getattr(state, "tables", {})
        countries = tables.get("countries")
        if countries is None or "id" not in countries.columns:
            raise RuntimeError(
                "Freeplay could not start because the initial world snapshot has no country data."
            )

        playable = filter_playable_countries(countries)
        country_ids = {
            str(value or "").strip().upper()
            for value in playable["id"].to_list()
        }
        if self.player_tag not in country_ids:
            raise RuntimeError(
                f"Freeplay could not start because '{self.player_tag}' is not a playable country in the loaded world."
            )

        globals_state = getattr(state, "globals", {})
        authoritative_player = str(globals_state.get("player_tag") or "").strip().upper()
        if authoritative_player != self.player_tag:
            raise RuntimeError(
                f"Freeplay could not start because the server did not confirm '{self.player_tag}' as the player country."
            )
        if self.player_party_id:
            parties = tables.get("political_parties")
            if (
                globals_state.get("player_party_id") != self.player_party_id
                or parties is None
                or not {"country_id", "party_id"}.issubset(parties.columns)
                or parties.filter(
                    (pl.col("country_id") == self.player_tag)
                    & (pl.col("party_id") == self.player_party_id)
                ).is_empty()
            ):
                raise RuntimeError("The selected political party is unavailable in the new freeplay world.")

    def _start_position(self, state, session) -> tuple[float, float] | None:
        regions = getattr(state, "tables", {}).get("regions")
        map_data = getattr(session, "map_data", None)
        if (
            regions is None
            or not {"id", "owner"}.issubset(regions.columns)
            or map_data is None
        ):
            return None

        owned_regions = regions.filter(
            pl.col("owner").cast(pl.Utf8).str.to_uppercase() == self.player_tag
        )
        if owned_regions.is_empty():
            return None
        return calculate_centroid(
            owned_regions,
            map_data.height,
            map_data.width,
        )

    def _warmup_file(self, asset_path: str) -> None:
        path = self.config.get_asset_path(asset_path)
        if path is not None and path.exists():
            try:
                # Prefetch incrementally without keeping a second copy of the map in memory.
                with path.open("rb") as asset_file:
                    while asset_file.read(1024 * 1024):
                        check_cancelled(self._cancel_event)
            except OSError:
                # Prefetch is optional; actual asset loading reports actionable failures.
                logger.warning("Could not prefetch map asset %s", path, exc_info=True)
