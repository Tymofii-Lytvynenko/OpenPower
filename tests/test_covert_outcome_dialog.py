from types import SimpleNamespace

import polars as pl

from src.client.ui.components.shared.covert_outcome_dialog import CovertOutcomeDialog
from src.client.ui.panels.service.journal_dispatches import journal_dispatches


def test_covert_result_mail_respects_discovery_and_ownership():
    state = SimpleNamespace(journal=SimpleNamespace(domain_events=[]),tables={
        "covert_missions":pl.DataFrame([
            dict(id="mine",owner_country_id="UKR",target_country_id="POL",result="success",discovered_by_target=False),
            dict(id="seen",owner_country_id="POL",target_country_id="UKR",result="failed",discovered_by_target=True),
            dict(id="hidden",owner_country_id="POL",target_country_id="UKR",result="success",discovered_by_target=False),
            dict(id="pending",owner_country_id="UKR",target_country_id="POL",result="",discovered_by_target=False),
            dict(id="framed",owner_country_id="POL",target_country_id="CAN",framed_country_id="DEU",
                 attributed_country_id="DEU",result="success",discovered_by_target=True),
        ])})
    assert {row["reference"] for row in journal_dispatches(state,"UKR")} == {"mine","seen"}
    assert {row["reference"] for row in journal_dispatches(state,"DEU")} == {"framed"}
    assert journal_dispatches(state,"FRA") == []


def test_effect_summary_never_joins_private_incidents_for_another_audience():
    state = SimpleNamespace(tables={"covert_incidents":pl.DataFrame([
        dict(mission_id="seen",audience_country_ids=["UKR"],summary="Public incident."),
        dict(mission_id="seen",audience_country_ids=["POL"],summary="Private identity."),
        dict(mission_id="other",audience_country_ids=["UKR"],summary="Unrelated incident."),
    ])})
    dialog = CovertOutcomeDialog()
    dialog.show("seen","UKR")
    assert dialog._summary(state)=="Public incident."
