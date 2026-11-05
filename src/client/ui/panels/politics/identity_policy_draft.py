"""Staged identity statuses with snapshot validation and safe dispatch ordering."""
from dataclasses import dataclass
import math

from src.shared.actions import ActionSetCountryIdentityPolicy


STATUSES = ("official", "legal", "restricted", "illegal")


def recognized(row):
    try:
        share = float(row.get("population_share") or 0)
    except (ValueError, TypeError, OverflowError):
        return False
    return math.isfinite(share) and share > 0 and row.get("legal_status") in {"official", "legal"}


@dataclass(frozen=True)
class IdentityDraft:
    original: str
    target: str


class IdentityPolicyDraft:
    def __init__(self):
        self.country = ""
        self.pending = {}
        self._countries = {}

    def select_country(self, country):
        country = str(country or "").strip().upper()
        if country != self.country:
            self._countries[self.country] = self.pending
            self.pending = self._countries.setdefault(country, {})
            self.country = country

    def status(self, row):
        draft = self.pending.get((row.get("identity_type"), row.get("identity_id")))
        return draft.target if draft else str(row.get("legal_status") or "legal").casefold()

    def choose(self, rows, row, status):
        if row.get("is_other_bucket") or status not in STATUSES:
            return "This group's status cannot be changed."
        kind = row.get("identity_type")
        if status in {"restricted", "illegal"} and not any(
            other.get("identity_id") != row.get("identity_id")
            and recognized({**other, "legal_status": self.status(other)}) for other in rows
            if other.get("identity_type") == kind
        ):
            return f"At least one other {kind} group must remain legally recognized."
        key = (kind, row.get("identity_id"))
        original = str(row.get("legal_status") or "legal").casefold()
        if status == original:
            self.pending.pop(key, None)
        else:
            self.pending[key] = IdentityDraft(original, status)
        return ""

    def prepare(self, state, context):
        if not self.pending:
            return [], ""
        if not context.is_own_country or context.net_client is None or str(context.target_tag or "").upper() != self.country:
            return [], "This country's identity policy is outside your control."
        frame = state.tables.get("country_identity_groups")
        rows = [] if frame is None else [r for r in frame.iter_rows(named=True) if str(r.get("country_id") or "").upper() == self.country]
        index = {(r.get("identity_type"), r.get("identity_id")): r for r in rows}
        for key, draft in self.pending.items():
            row = index.get(key)
            if row is None or row.get("is_other_bucket") or str(row.get("legal_status") or "legal").casefold() != draft.original:
                return [], "The identity groups changed while editing. Discard the draft and choose again."
            if draft.target in {"restricted", "illegal"} and not any(
                other.get("identity_id") != key[1] and recognized({**other, "legal_status": self.status(other)})
                for other in rows if other.get("identity_type") == key[0]
            ):
                return [], "At least one group of each edited identity type must remain legally recognized."
        # Recognition expansions must precede restrictions so the server never
        # observes a temporary loss of the last recognized group during a swap.
        ordered = sorted(self.pending.items(), key=lambda item: item[1].target not in {"official", "legal"})
        return [ActionSetCountryIdentityPolicy(context.net_client.player_id, self.country, kind, identity, draft.target)
                for (kind, identity), draft in ordered], ""
