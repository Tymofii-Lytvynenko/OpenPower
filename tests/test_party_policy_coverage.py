from src.shared.party_policy import party_count_transitions


def test_party_count_transitions_ignore_invalid_json_and_non_list_data():
    assert party_count_transitions({"party_count_transitions_json": "{"}) == ()
    assert party_count_transitions({"party_count_transitions_json": "{}"}) == ()


def test_party_count_transitions_skip_malformed_records_and_keep_valid_ranges():
    transitions = party_count_transitions(
        {
            "party_count_transitions_json": (
                '[null,{"target_form_id":"","minimum":1,"maximum":0},'
                '{"target_form_id":"single-party", "minimum":1, "maximum":1}]'
            )
        }
    )

    assert len(transitions) == 1
    assert transitions[0].target_form_id == "single-party"
    assert transitions[0].matches(1)
    assert not transitions[0].matches(2)
