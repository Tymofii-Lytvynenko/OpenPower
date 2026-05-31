import random
import uuid
from typing import List, Dict, Any

from src.engine.interfaces import ISystem
from src.server.state import GameState
from src.shared.events import EventNewDay, EventRandomEventTriggered


# ──────────────────────────────────────────────────────────────
# Event catalog — each entry defines a visual event type and its
# base probability weight. Extending this list is the only step
# needed to add new event flavors.
# ──────────────────────────────────────────────────────────────
EVENT_CATALOG: list[dict[str, Any]] = [
    {"type": "earthquake",     "label": "🌍 Earthquake",     "weight": 1.0, "duration_days": 3},
    {"type": "flood",          "label": "🌊 Flood",          "weight": 1.2, "duration_days": 4},
    {"type": "wildfire",       "label": "🔥 Wildfire",       "weight": 1.0, "duration_days": 5},
    {"type": "tornado",        "label": "🌪️ Tornado",        "weight": 0.8, "duration_days": 2},
    {"type": "volcanic_eruption", "label": "🌋 Eruption",    "weight": 0.4, "duration_days": 7},
    {"type": "drought",        "label": "☀️ Drought",        "weight": 0.9, "duration_days": 10},
    {"type": "epidemic",       "label": "🦠 Epidemic",       "weight": 0.6, "duration_days": 14},
    {"type": "economic_boom",  "label": "📈 Economic Boom",  "weight": 0.7, "duration_days": 7},
    {"type": "strike",         "label": "✊ Strike",          "weight": 0.8, "duration_days": 3},
    {"type": "tsunami",        "label": "🌊 Tsunami",        "weight": 0.3, "duration_days": 4},
]

# Pre-compute cumulative weights for weighted random selection
_TOTAL_WEIGHT = sum(e["weight"] for e in EVENT_CATALOG)

# Daily probability of *at least one* event spawning (0.0–1.0)
BASE_DAILY_CHANCE = 0.35

# Hard cap — prevents the globe from being cluttered
MAX_ACTIVE_EVENTS = 5

# Duration of one in-game day in total-minutes (24 * 60)
_MINUTES_PER_DAY = 1440


class RandomEventsSystem(ISystem):
    """
    Periodically generates random world events and manages their lifecycle.

    Responsibilities:
    - Listens for ``EventNewDay`` to roll for new random events.
    - Stores active events in ``state.globals["active_events"]`` so the
      Client can render placards without importing module code.
    - Emits ``EventRandomEventTriggered`` on the event bus so other
      simulation systems can attach gameplay effects.
    - Prunes expired events each day.

    Data contract stored in ``state.globals["active_events"]``::

        [
            {
                "id":            str,   # unique event instance id
                "event_type":    str,   # catalog key (e.g. "earthquake")
                "label":         str,   # display text with emoji
                "region_id":     int,   # affected region
                "severity":      float, # 0.0–1.0 random magnitude
                "start_minute":  int,   # game total_minutes when created
                "expire_minute": int,   # game total_minutes when it expires
            },
            ...
        ]
    """

    @property
    def id(self) -> str:
        return "base.random_events"

    @property
    def dependencies(self) -> List[str]:
        # Needs time to be ticked first so EventNewDay is available
        return ["base.time"]

    def update(self, state: GameState, delta_time: float) -> None:
        # Ensure the container exists
        if "active_events" not in state.globals:
            state.globals["active_events"] = []

        active: list[dict] = state.globals["active_events"]
        now = state.time.total_minutes

        # 1. React to EventNewDay — roll for events & prune expired
        for event in state.events:
            if not isinstance(event, EventNewDay):
                continue

            # --- Prune expired events ---
            active[:] = [e for e in active if e["expire_minute"] > now]

            # --- Roll for a new event ---
            if len(active) >= MAX_ACTIVE_EVENTS:
                continue

            if random.random() > BASE_DAILY_CHANCE:
                continue

            new_event = self._generate_event(state, now)
            if new_event is not None:
                active.append(new_event)

                state.events.append(EventRandomEventTriggered(
                    event_id=new_event["id"],
                    event_type=new_event["event_type"],
                    region_id=new_event["region_id"],
                    severity=new_event["severity"],
                ))

    # ── Private helpers ──────────────────────────────────────

    def _generate_event(self, state: GameState, now_minutes: int) -> dict | None:
        """Pick a random event type and a random region."""
        if "regions" not in state.tables:
            return None

        regions = state.tables["regions"]
        if regions.is_empty() or "id" not in regions.columns:
            return None

        # Pick a weighted-random event template
        template = self._weighted_choice()

        # Pick a random region
        region_ids = regions["id"].to_list()
        region_id = random.choice(region_ids)

        severity = round(random.uniform(0.2, 1.0), 2)
        duration_minutes = template["duration_days"] * _MINUTES_PER_DAY

        return {
            "id": uuid.uuid4().hex[:12],
            "event_type": template["type"],
            "label": template["label"],
            "region_id": int(region_id),
            "severity": severity,
            "start_minute": now_minutes,
            "expire_minute": now_minutes + duration_minutes,
        }

    @staticmethod
    def _weighted_choice() -> dict:
        """Select a catalog entry proportional to its weight."""
        r = random.uniform(0, _TOTAL_WEIGHT)
        cumulative = 0.0
        for entry in EVENT_CATALOG:
            cumulative += entry["weight"]
            if r <= cumulative:
                return entry
        # Fallback (shouldn't happen, but satisfies the type checker)
        return EVENT_CATALOG[0]
