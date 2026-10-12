import time
import threading
import polars as pl
import arcade
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Any

from src.shared.config import GameConfig
from src.client.utils.coords_util import calculate_centroid
from src.client.tasks.session_startup import (
    check_cancelled,
    create_session_until_ready,
    shutdown_session,
    wait_for_initial_state,
)

@dataclass
class NewGameContext:
    session: Any
    player_tag: str
    start_pos: Optional[tuple[float, float]]

class NewGameTask:
    def __init__(
        self,
        window: arcade.Window,
        config: GameConfig,
        player_tag: str,
        scenario_id: str = "open_sandbox",
    ):
        self.window = window
        self.config = config
        self.player_tag = player_tag
        self.scenario_id = scenario_id
        self.progress: float = 0.0
        self.status_text: str = "Preparing Campaign..."
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

    def run(self) -> NewGameContext:
        new_session = None
        try:
            check_cancelled(self._cancel_event)
            self.status_text = "Stopping previous session..."
            self.progress = 0.05
            if getattr(self.window, "session", None):
                self.window.session.shutdown()

            self.status_text = "Starting simulation server..."
            self.progress = 0.1

            def update_progress(progress: float, text: str) -> None:
                self.progress = 0.1 + progress * 0.6
                self.status_text = text

            new_session = create_session_until_ready(
                self.window.session_factory,
                self.config,
                player_tag=self.player_tag,
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

            from src.client.services.network_client_service import NetworkClient
            from src.shared.actions import ActionStartCampaign

            self.status_text = "Applying scenario setup and campaign objectives..."
            self.progress = 0.86
            campaign_client = NetworkClient(new_session)
            campaign_client.send_action(
                ActionStartCampaign(
                    player_id=campaign_client.player_id,
                    scenario_id=self.scenario_id,
                    country_tag=self.player_tag,
                )
            )
            # Campaign setup follows full-world bootstrap and queued fixed steps;
            # the initial 5-second deadline could reject a healthy busy server.
            campaign_ready_deadline = time.perf_counter() + 60.0
            campaign_started = False
            while time.perf_counter() < campaign_ready_deadline:
                check_cancelled(self._cancel_event)
                new_session.tick(0.0)
                state = new_session.get_state_snapshot()
                campaigns = state.tables.get("campaigns") if state is not None else None
                if campaigns is not None and not campaigns.is_empty():
                    campaign_started = any(
                        row.get("scenario_id") == self.scenario_id
                        and str(row.get("actor_country_id", "")).upper() == self.player_tag.upper()
                        for row in campaigns.to_dicts()
                    )
                    if campaign_started:
                        break
                self._cancel_event.wait(0.05)
            if not campaign_started:
                results = [] if state is None else state.journal.command_results
                failure = next(
                    (
                        str(row.get("reason"))
                        for row in reversed(results)
                        if row.get("action_type") == "ActionStartCampaign"
                        and row.get("status") == "rejected"
                    ),
                    "The server did not confirm campaign setup.",
                )
                raise RuntimeError(f"Could not start campaign '{self.scenario_id}': {failure}")

            start_pos = None
            try:
                if "regions" in state.tables:
                    df = state.tables["regions"]
                    owned_regions = df.filter(pl.col("owner") == self.player_tag)
                    map_height = new_session.map_data.height
                    map_width = new_session.map_data.width
                    start_pos = calculate_centroid(owned_regions, map_height, map_width)
            except Exception as e:
                print(f"Error calculating centroid: {e}")

            self.status_text = "Pre-loading map assets..."
            self.progress = 0.9
            self._warmup_file("map/regions.png")
            check_cancelled(self._cancel_event)
            self._warmup_file("map/terrain.png")
            check_cancelled(self._cancel_event)

            self.progress = 1.0
            self.status_text = "Ready."
            return NewGameContext(new_session, self.player_tag, start_pos)
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

    def _warmup_file(self, asset_path_str: str):
        """Reads a file into void just to force OS caching."""
        path = self.config.get_asset_path(asset_path_str)
        if path and path.exists():
            with open(path, "rb") as f:
                f.read()
