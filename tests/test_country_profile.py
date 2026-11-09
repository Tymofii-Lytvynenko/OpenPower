from src.client.services.country_profile import PROFILE_METRICS, suggest_country_profiles


def test_missing_profile_metrics_use_openpower_model_defaults() -> None:
    countries = [
        {"id": "UKR"},
        {"id": "POL", "gdp": 10_000_000.0, "gvt_approval": 50.0, "military_count": 0},
        {"id": "MEX", "gdp": 2_000_000.0, "gvt_approval": 25.0, "military_count": 0},
        {"id": "DEU", "gdp": 100_000_000.0, "gvt_approval": 100.0, "military_count": 100},
    ]

    candidates = suggest_country_profiles(
        countries,
        desired_values={metric: 0.5 for metric in PROFILE_METRICS},
        enabled_metrics={metric: True for metric in PROFILE_METRICS},
    )
    by_country = {candidate.country_id: candidate for candidate in candidates}

    assert by_country["UKR"].economic_rank == 3
    assert by_country["UKR"].political_rank == 3
    assert by_country["UKR"].military_rank == 4
    assert by_country["DEU"].economic_rank == 1
    assert by_country["MEX"].political_rank == 4


def test_empty_or_invalid_country_rows_return_no_profile_candidates() -> None:
    assert suggest_country_profiles(
        [{}, {"id": "  "}],
        desired_values={},
        enabled_metrics={},
    ) == []
