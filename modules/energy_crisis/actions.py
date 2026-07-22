from dataclasses import dataclass

from src.shared.actions import GameAction


@dataclass
class ActionSetEnergyPolicy(GameAction):
    country_tag: str
    policy: str
    response_level: float
