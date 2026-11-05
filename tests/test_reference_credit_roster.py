from src.client.ui.components.reference_credit_roster import (
    REFERENCE_CREDIT_SUPPLEMENTAL_TEXT,
    REFERENCE_STEAM_CREDIT_GROUPS,
)


def test_steam_edition_credits_match_published_roster_count_and_name():
    credited_entities = [
        person
        for group in REFERENCE_STEAM_CREDIT_GROUPS
        for entry in group.entries
        for person in entry.people
    ]

    assert len(credited_entities) == 57
    assert len(set(credited_entities)) == 54
    assert "Vasso T. Kontoulis" in credited_entities
    assert REFERENCE_CREDIT_SUPPLEMENTAL_TEXT[("golemlabs", "Sound and Music")] == "(www.multimediarts.net)"
    assert REFERENCE_CREDIT_SUPPLEMENTAL_TEXT[("golemlabs", "Copyright")] == "© GolemLabs 2004"
