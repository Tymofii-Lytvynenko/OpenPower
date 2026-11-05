"""Shared advisor mode vocabulary and REFERENCE-compatible preference mapping."""

from __future__ import annotations

ADVISOR_DOMAINS = ("economy", "politics", "military")
ADVISOR_MODES = frozenset({"manual", "automatic", "confirmations"})
ADVISOR_STATUS_COLUMNS = {
    "economy": "advisor_economy_status",
    "politics": "advisor_politics_status",
    "military": "advisor_military_status",
}
ADVISOR_MODE_PREFERENCE_KEYS = ("manual", "automatic", "confirmations")


def mode_from_preferences(preferences: dict[str, bool], domain: str) -> str:
    """Use the same priority as the source Save handler for its independent toggles."""
    if preferences.get(f"advisor_{domain}_manual", False):
        return "manual"
    if preferences.get(f"advisor_{domain}_automatic", False):
        return "automatic"
    return "confirmations"


def preferences_from_modes(modes: dict[str, str]) -> dict[str, bool]:
    """Expand authoritative single-mode values into the source toggle layout."""
    return {
        f"advisor_{domain}_{mode}": mode == selected
        for domain, selected in modes.items()
        for mode in ADVISOR_MODE_PREFERENCE_KEYS
    }
