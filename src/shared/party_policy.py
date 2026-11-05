"""Passive metadata for declared party-count constitutional transitions."""
from dataclasses import dataclass
import json


@dataclass(frozen=True)
class PartyCountTransition:
    target_form_id: str
    minimum: int
    maximum: int

    def matches(self, count):
        return self.minimum <= count and (self.maximum == 0 or count <= self.maximum)


def party_count_transitions(rule):
    try:
        records = json.loads(str(rule.get("party_count_transitions_json") or "[]"))
    except (TypeError, ValueError):
        return ()
    if not isinstance(records, list):
        return ()
    result = []
    for record in records:
        if not isinstance(record, dict):
            continue
        target = str(record.get("target_form_id") or "").strip().casefold()
        low, high = record.get("minimum", 1), record.get("maximum", 0)
        if (not target or type(low) is not int or type(high) is not int
                or low < 1 or high < 0 or (high and high < low)):
            continue
        result.append(PartyCountTransition(target, low, high))
    return tuple(result)
