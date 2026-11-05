"""Shared application of an already validated constitutional transition."""


def apply_government_transition(government, target_rule, target_form, ruling_party, next_election, now,
                                country_id, parties, law_transitions, elections):
    government.update(government_form_id=target_form,
                      government_type=str(target_rule.get("display_name") or target_form),
                      ruling_party_id=ruling_party, succession_party_id=ruling_party,
                      election_eligible=bool(target_rule.get("election_eligible", False)),
                      next_election_at_minute=next_election, updated_at_minute=now)
    changed = {"country_governments"}
    for party in parties:
        if str(party.get("country_id") or "").strip().upper() != country_id:
            continue
        is_ruling = str(party.get("party_id") or "").strip().lower() == ruling_party
        if bool(party.get("is_ruling")) != is_ruling:
            party.update(is_ruling=is_ruling, updated_at_minute=now)
            changed.add("political_parties")
    for transition in law_transitions:
        if (str(transition.get("country_id") or "").strip().upper() == country_id
                and transition.get("status") == "scheduled"
                and transition.get("carry_over_rule") == "cancel_on_regime_change"):
            transition.update(status="cancelled", reason="The regime change cancelled this pending law transition.")
            changed.add("law_transitions")
    for election in elections:
        if str(election.get("country_id") or "").strip().upper() == country_id and election.get("status") == "scheduled":
            election.update(status="cancelled", resolved_at_minute=now,
                            reason="The regime change replaced the existing election schedule.")
            changed.add("political_elections")
    return changed
