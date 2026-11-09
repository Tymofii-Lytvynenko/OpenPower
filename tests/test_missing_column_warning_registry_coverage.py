from modules.base.systems.economy.missing_column_warning_registry import (
    MissingColumnWarningRegistry,
)


def test_registry_replaces_seen_columns_and_suppresses_duplicate_warnings(capsys):
    registry = MissingColumnWarningRegistry("trade", {"old-column"})

    registry.seen_columns = {"known-column"}
    registry.report_missing("known-column", 0.0)
    assert capsys.readouterr().out == ""

    registry.report_missing("new-column", False)

    assert registry.seen_columns == {"known-column", "new-column"}
    assert capsys.readouterr().out == (
        "[trade] Column 'new-column' not found in 'domestic_production'. "
        "Defaulting to False.\n"
    )
