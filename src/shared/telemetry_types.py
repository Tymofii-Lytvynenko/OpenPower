"""Messages shared by telemetry processes, independent of game commands."""
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class TelemetryControl:
    operation: Literal["enable", "disable", "reset"]
