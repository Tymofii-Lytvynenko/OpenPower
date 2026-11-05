"""Local party eligibility drafts using published government policy metadata."""
from src.shared.actions import ActionSetPartyEligibility
from src.shared.party_policy import party_count_transitions


def party_policy_context(state, country):
    governments = state.tables.get("country_governments")
    government = None if governments is None else next(
        (row for row in governments.iter_rows(named=True)
         if str(row.get("country_id") or "").upper() == country), None
    )
    rules = state.tables.get("government_form_rules")
    rule = None if rules is None or government is None else next(
        (row for row in rules.iter_rows(named=True)
         if str(row.get("government_form_id") or "").casefold()
         == str(government.get("government_form_id") or "").casefold()), None
    )
    return government, rule


def _country_parties(table, country):
    if table is None:
        return []
    return [row for row in table.iter_rows(named=True)
            if str(row.get("country_id") or "").upper() == country]


def _eligible_count(rows, pending):
    return sum(
        bool(pending.get(str(row.get("party_id") or ""),
                         (row.get("eligible"), row.get("eligible")))[1])
        for row in rows
    )


def _count_limits(rule):
    return rule.get("minimum_eligible_parties", 1), rule.get("maximum_eligible_parties", 0)


def _within_limits(count, minimum, maximum):
    return count >= minimum and (not maximum or count <= maximum)


class PartyPolicyDraft:
    def __init__(self):
        self.country = ""
        self.pending = {}
        self._countries = {}
        self._forms = {}
        self._confirmed = {}

    def select_country(self, country):
        country = str(country or "").strip().upper()
        if country != self.country:
            self._countries[self.country] = self.pending
            self.pending = self._countries.setdefault(country, {})
            self.country = country

    def choose(self, party, eligible, form):
        if party.is_ruling or party.eligible is None or type(eligible) is not bool:
            return
        self._confirmed.pop(self.country, None)
        if not self.pending:
            self._forms[self.country] = str(form)
        if eligible == party.eligible:
            self.pending.pop(party.party_id, None)
        else:
            self.pending[party.party_id] = (party.eligible, eligible)

    def status(self, party):
        return self.pending.get(party.party_id, (party.eligible, party.eligible))[1]

    def fingerprint(self):
        return tuple(sorted((key, original, target) for key, (original, target) in self.pending.items()))

    def checkpoint(self):
        return dict(self.pending), self._confirmed.get(self.country)

    def restore(self, checkpoint):
        pending, confirmed = checkpoint
        self.pending.clear()
        self.pending.update(pending)
        if confirmed is None:
            self._confirmed.pop(self.country, None)
        else:
            self._confirmed[self.country] = confirmed

    def confirm_transition(self, target, fingerprint):
        if fingerprint == self.fingerprint():
            self._confirmed[self.country] = (fingerprint, target)
            return True
        return False

    def transition_target(self, state):
        government, rule = party_policy_context(state, self.country)
        table = state.tables.get("political_parties")
        if not self.pending or not government or not rule or table is None:
            return None
        count = _eligible_count(_country_parties(table, self.country), self.pending)
        low, high = _count_limits(rule)
        if type(low) is not int or type(high) is not int or _within_limits(count, low, high):
            return None
        matches = [item for item in party_count_transitions(rule) if item.matches(count)]
        if len(matches) != 1:
            return None
        target = matches[0].target_form_id
        rules = state.tables.get("government_form_rules")
        destinations = [] if rules is None else [r for r in rules.iter_rows(named=True) if str(r.get("government_form_id") or "").casefold() == target]
        if len(destinations) != 1:
            return None
        destination = destinations[0]
        low, high = _count_limits(destination)
        if type(low) is not int or type(high) is not int or not _within_limits(count, low, high):
            return None
        return target, str(destination.get("display_name") or target)

    def prepare(self, state, context):
        if not self.pending:
            return [], ""
        government, rule = party_policy_context(state, self.country)
        form = self._forms.get(self.country, "")
        if not context.is_own_country or context.net_client is None or str(context.target_tag or "").upper() != self.country:
            return [], "This country's party policy is outside your control."
        if not government or not rule or str(government.get("government_form_id") or "") != form or not rule.get("party_policy_editable"):
            return [], "The government form or its party-policy authority changed."
        table = state.tables.get("political_parties")
        rows = {str(row.get("party_id") or ""): row for row in _country_parties(table, self.country)}
        for party, (original, target) in self.pending.items():
            row = rows.get(party)
            if row is None or row.get("eligible") != original or (not target and (row.get("is_ruling") or party == government.get("ruling_party_id"))):
                return [], "The parties changed while editing. Discard the draft and choose again."
        count = _eligible_count(rows.values(), self.pending)
        minimum, maximum = _count_limits(rule)
        if type(minimum) is not int or type(maximum) is not int or minimum < 1 or maximum < 0 or (maximum and maximum < minimum):
            return [], "The configured party-count limits are invalid."
        confirmed_form = ""
        if not _within_limits(count, minimum, maximum):
            destination = self.transition_target(state)
            if destination is None:
                return [], "This party count requires a configured constitutional transition; the government form has not changed."
            confirmed_form = destination[0]
            if self._confirmed.get(self.country) != (self.fingerprint(), confirmed_form):
                return [], "Confirm the constitutional transition before applying this party policy."
        return [ActionSetPartyEligibility(context.net_client.player_id, self.country, form,
                                         {key: target for key, (_, target) in self.pending.items()},
                                         confirmed_government_form=confirmed_form)], ""
