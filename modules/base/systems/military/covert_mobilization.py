"""Deterministic scoring of a covert mobilization observation."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MobilizationFactors:
    skill_index: int
    readiness: float
    observer_telecom: float
    target_telecom: float
    signal_coverage: float
    target_security: float
    domestic_coverage: float

    def detection_probability(self) -> float:
        return min(0.92, max(
            0.02,
            0.18 + self.skill_index * 0.10
            + self.readiness * 0.10
            + self.observer_telecom * 0.20
            + self.signal_coverage * 0.12
            + self.target_telecom * 0.05
            - self.target_security * 0.20
            - self.domestic_coverage * 0.20,
        ))

    def confidence(self) -> float:
        return min(0.95, max(
            0.1,
            0.20 + self.skill_index * 0.12
            + self.readiness * 0.15
            + self.observer_telecom * 0.20
            + self.signal_coverage * 0.15
            + self.target_telecom * 0.05
            - self.target_security * 0.10
            - self.domestic_coverage * 0.10,
        ))
