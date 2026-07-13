from dataclasses import dataclass

from src.shared.events import DomainGameEvent


@dataclass
class EventEnergyPolicyChanged(DomainGameEvent):
    country_tag: str
    policy: str
    response_level: float
