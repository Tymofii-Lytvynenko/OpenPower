"""Normalize passive unit metadata without importing a gameplay module."""
import re

from src.shared.military_constants import ROLE_ALIASES, UNIT_ROLE_DOMAINS


def unit_category(unit_type):
    role = re.sub(r"[^a-z0-9]+", "_", str(unit_type or "").strip().lower()).strip("_")
    role = ROLE_ALIASES.get(role, role)
    return "I" if role == "infantry" else {"land": "G", "air": "A", "naval": "N"}.get(UNIT_ROLE_DOMAINS.get(role))
