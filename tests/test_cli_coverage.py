import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src import cli


def basic_args(root, **values):
    return SimpleNamespace(project_root=Path(root), **values)


def test_build_parser_registers_all_command_families_and_defaults(tmp_path):
    parser = cli.build_parser()

    ui_run = parser.parse_args(["ui-test", "run", "map", "--project-root", str(tmp_path)])
    assert ui_run.handler is cli._handle_ui_run
    assert ui_run.width == 1920
    assert ui_run.height == 1080
    assert ui_run.tolerance == 0.03
    assert not ui_run.matrix

    compare = parser.parse_args(["sim", "compare", "--runs", "3"])
    assert compare.handler is cli._handle_sim_compare
    assert compare.runs == 3
    assert compare.mods == "base"
    assert compare.days == 30
    assert compare.snapshot_interval == 30
    assert compare.diagnostics_interval == 1

    budget = parser.parse_args(["ui-test", "budget"])
    assert budget.handler is cli._handle_budget_ui_test
    assert budget.width == 1280
    assert budget.height == 1000
    assert budget.output == Path("artifacts/ui/budget")

    ui_list = parser.parse_args(["ui-test", "list"])
    assert ui_list.handler is cli._handle_ui_list


def test_main_uses_argv_or_process_arguments_and_reports_handler_errors(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_handle_ui_list", lambda _args: 7)
    assert cli.main(["ui-test", "list"]) == 7

    monkeypatch.setattr(sys, "argv", ["openpower", "ui-test", "list"])
    assert cli.main() == 7

    monkeypatch.setattr(
        cli,
        "_handle_ui_list",
        lambda _args: (_ for _ in ()).throw(ValueError("invalid handler input")),
    )
    assert cli.main(["ui-test", "list"]) == 2
    assert "error: invalid handler input" in capsys.readouterr().err


def test_ui_list_prints_catalog_as_json(monkeypatch, capsys):
    from src.client.ui.testing import catalog

    monkeypatch.setattr(catalog, "list_surfaces", lambda: [{"id": "budget"}])

    assert cli._handle_ui_list(SimpleNamespace()) == 0
    assert json.loads(capsys.readouterr().out) == [{"id": "budget"}]


@pytest.mark.parametrize("absolute", [False, True])
def test_ui_live_smoke_resolves_output_path_from_project_root(monkeypatch, tmp_path, absolute):
    from src.client.ui.testing import live_smoke

    output = tmp_path / "absolute" if absolute else Path("artifacts/smoke")
    expected = output if absolute else (tmp_path / output).resolve()
    args = basic_args(tmp_path, output=output)
    run = Mock(return_value=0)
    monkeypatch.setattr(live_smoke, "run_live_smoke", run)

    assert cli._handle_ui_live_smoke(args) == 0
    run.assert_called_once_with(expected)


def test_ui_run_validates_dimensions_and_visual_tolerance(tmp_path):
    args = basic_args(
        tmp_path,
        width=0,
        height=768,
        tolerance=0.03,
        matrix=False,
    )
    with pytest.raises(ValueError, match="Viewport dimensions must be positive"):
        cli._handle_ui_run(args)

    args.width = 800
    args.tolerance = 1.1
    with pytest.raises(ValueError, match="Visual tolerance must be between 0 and 1"):
        cli._handle_ui_run(args)


def test_ui_run_uses_journey_fixture_and_resolves_relative_artifacts(monkeypatch, tmp_path):
    from src.client.ui.testing import surface

    root = tmp_path / "project"
    root.mkdir()
    journey_path = root / "journey.json"
    fixture_path = root / "fixture.json"
    journey = {"steps": [{"op": "click"}], "fixture": "fixture.json"}
    fixture = {"globals": {"game_minute": 4}}
    journey_path.write_text(json.dumps(journey), encoding="utf-8")
    fixture_path.write_text(json.dumps(fixture), encoding="utf-8")
    run = Mock(return_value=0)
    monkeypatch.setattr(surface, "run_surface", run)
    args = basic_args(
        root,
        surface="map",
        width=800,
        height=600,
        tolerance=0.2,
        matrix=False,
        output=Path("results/map"),
        journey=Path("journey.json"),
        fixture=None,
        baseline=Path("baseline.png"),
    )

    assert cli._handle_ui_run(args) == 0
    run.assert_called_once_with(
        "map",
        (root / "results/map").resolve(),
        root.resolve(),
        (800, 600),
        journey,
        fixture,
        (root / "baseline.png").resolve(),
        0.2,
    )


def test_ui_run_honors_explicit_fixture_and_absolute_output(monkeypatch, tmp_path):
    from src.client.ui.testing import surface

    root = tmp_path / "project"
    root.mkdir()
    journey_path = root / "journey.json"
    explicit_fixture = root / "explicit.json"
    journey_path.write_text(json.dumps({"fixture": "ignored.json"}), encoding="utf-8")
    explicit_fixture.write_text(json.dumps({"tables": {}}), encoding="utf-8")
    output = tmp_path / "absolute-output"
    baseline = tmp_path / "baseline.png"
    run = Mock(return_value=1)
    monkeypatch.setattr(surface, "run_surface", run)
    args = basic_args(
        root,
        surface="history",
        width=1024,
        height=768,
        tolerance=0.03,
        matrix=False,
        output=output,
        journey=journey_path,
        fixture=Path("explicit.json"),
        baseline=baseline,
    )

    assert cli._handle_ui_run(args) == 1
    run.assert_called_once_with(
        "history",
        output,
        root.resolve(),
        (1024, 768),
        {"fixture": "ignored.json"},
        {"tables": {}},
        baseline,
        0.03,
    )


@pytest.mark.parametrize("payload", [[], "not an object"])
def test_ui_run_rejects_non_object_journey_and_fixture_files(monkeypatch, tmp_path, payload):
    from src.client.ui.testing import surface

    root = tmp_path / "project"
    root.mkdir()
    journey_path = root / "journey.json"
    journey_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(surface, "run_surface", Mock())
    args = basic_args(
        root,
        surface="map",
        width=800,
        height=600,
        tolerance=0.03,
        matrix=False,
        output=None,
        journey=journey_path,
        fixture=None,
        baseline=None,
    )

    with pytest.raises(ValueError, match="must contain JSON objects"):
        cli._handle_ui_run(args)


def test_ui_run_rejects_a_non_object_fixture_file(monkeypatch, tmp_path):
    from src.client.ui.testing import surface

    root = tmp_path / "project"
    root.mkdir()
    journey_path = root / "journey.json"
    fixture_path = root / "fixture.json"
    journey_path.write_text(json.dumps({"fixture": "fixture.json"}), encoding="utf-8")
    fixture_path.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")
    monkeypatch.setattr(surface, "run_surface", Mock())
    args = basic_args(
        root,
        surface="map",
        width=800,
        height=600,
        tolerance=0.03,
        matrix=False,
        output=None,
        journey=journey_path,
        fixture=None,
        baseline=None,
    )

    with pytest.raises(ValueError, match="must contain JSON objects"):
        cli._handle_ui_run(args)


def test_ui_run_uses_defaults_without_journey_fixture_or_output(monkeypatch, tmp_path):
    from src.client.ui.testing import surface

    root = tmp_path / "project"
    root.mkdir()
    run = Mock(return_value=0)
    monkeypatch.setattr(surface, "run_surface", run)
    args = basic_args(
        root,
        surface="events",
        width=1920,
        height=1080,
        tolerance=0.03,
        matrix=False,
        output=None,
        journey=None,
        fixture=None,
        baseline=None,
    )

    assert cli._handle_ui_run(args) == 0
    run.assert_called_once_with(
        "events",
        (root / "artifacts/ui/events").resolve(),
        root.resolve(),
        (1920, 1080),
        None,
        None,
        None,
        0.03,
    )


def test_ui_run_matrix_delegates_single_surface_to_batch(monkeypatch, tmp_path):
    batch = Mock(return_value=1)
    monkeypatch.setattr(cli, "_run_ui_batch", batch)
    args = basic_args(tmp_path, surface="map", width=800, height=600, tolerance=0.03, matrix=True)

    assert cli._handle_ui_run(args) == 1
    batch.assert_called_once_with(args, ["map"])


def test_ui_all_uses_catalog_ids_and_batch_runner(monkeypatch):
    from src.client.ui.testing import catalog

    monkeypatch.setattr(catalog, "list_surfaces", lambda: [{"id": "map"}, {"id": "budget"}])
    batch = Mock(return_value=0)
    monkeypatch.setattr(cli, "_run_ui_batch", batch)
    args = SimpleNamespace()

    assert cli._handle_ui_all(args) == 0
    batch.assert_called_once_with(args, ["map", "budget"])


def test_run_ui_batch_writes_subprocess_results_and_pass_summary(monkeypatch, tmp_path):
    run_process = Mock(return_value=SimpleNamespace(returncode=0, stdout="out", stderr="err"))
    monkeypatch.setattr(subprocess, "run", run_process)
    args = basic_args(
        tmp_path,
        output=Path("ui-results"),
        matrix=False,
        width=800,
        height=600,
        rerun_failed=False,
        fixture=Path("fixtures/map.json"),
        journey=Path("journeys/map.json"),
        baseline=Path("baseline.png"),
        tolerance=0.15,
    )

    assert cli._run_ui_batch(args, ["map"]) == 0

    output = (tmp_path / "ui-results").resolve()
    summary = json.loads((output / "suite.json").read_text(encoding="utf-8"))
    assert summary["passed"]
    assert summary["runs"] == [
        {
            "surface": "map",
            "width": 800,
            "height": 600,
            "passed": True,
            "exit_code": 0,
            "report": str(output / "map" / "800x600" / "report.json"),
            "log": "outerr",
        }
    ]
    command = run_process.call_args.args[0]
    assert command[:4] == [sys.executable, str((Path(cli.__file__).resolve().parents[1] / "main.py")), "ui-test", "run"]
    assert command[-8:] == [
        "--fixture", str(Path("fixtures/map.json")),
        "--journey", str(Path("journeys/map.json")),
        "--baseline", str(Path("baseline.png")),
        "--tolerance", "0.15",
    ]
    assert run_process.call_args.kwargs["capture_output"]
    assert run_process.call_args.kwargs["timeout"] == 90
    assert run_process.call_args.kwargs["env"]["PYTHONIOENCODING"] == "utf-8"


def test_run_ui_batch_matrix_runs_every_viewport(monkeypatch, tmp_path):
    run_process = Mock(return_value=SimpleNamespace(returncode=0, stdout="", stderr=""))
    monkeypatch.setattr(subprocess, "run", run_process)
    args = basic_args(
        tmp_path,
        output=tmp_path / "matrix",
        matrix=True,
        width=1,
        height=1,
        rerun_failed=False,
    )

    assert cli._run_ui_batch(args, ["map"]) == 0

    summary = json.loads((tmp_path / "matrix" / "suite.json").read_text(encoding="utf-8"))
    assert {(row["width"], row["height"]) for row in summary["runs"]} == {
        (800, 600),
        (1024, 768),
        (1280, 720),
        (1920, 1080),
    }
    assert run_process.call_count == 4


def test_run_ui_batch_reruns_only_failed_jobs_and_preserves_other_rows(
    monkeypatch, tmp_path
):
    output = tmp_path / "results"
    output.mkdir()
    previous_runs = [
        {"surface": "map", "width": 800, "height": 600, "passed": False, "exit_code": 1},
        {"surface": "map", "width": 1024, "height": 768, "passed": True, "exit_code": 0},
        {"surface": "budget", "width": 800, "height": 600, "passed": False, "exit_code": 1},
    ]
    (output / "suite.json").write_text(json.dumps({"runs": previous_runs}), encoding="utf-8")
    run_process = Mock(return_value=SimpleNamespace(returncode=0, stdout="fixed", stderr=""))
    monkeypatch.setattr(subprocess, "run", run_process)
    args = basic_args(
        tmp_path,
        output=output,
        matrix=True,
        width=1,
        height=1,
        rerun_failed=True,
    )

    assert cli._run_ui_batch(args, ["map", "other"]) == 1

    assert run_process.call_count == 1
    command = run_process.call_args.args[0]
    assert command[command.index("--width") + 1] == "800"
    assert command[command.index("--height") + 1] == "600"
    summary = json.loads((output / "suite.json").read_text(encoding="utf-8"))
    assert len(summary["runs"]) == 3
    assert sum(row["surface"] == "other" for row in summary["runs"]) == 0
    assert {row["surface"]: row["passed"] for row in summary["runs"]} == {
        "map": True,
        "budget": False,
    }


def test_run_ui_batch_with_no_failed_jobs_preserves_prior_suite_without_running(
    monkeypatch, tmp_path
):
    output = tmp_path / "results"
    output.mkdir()
    prior = [{"surface": "map", "width": 800, "height": 600, "passed": True}]
    (output / "suite.json").write_text(json.dumps({"runs": prior}), encoding="utf-8")
    run_process = Mock()
    monkeypatch.setattr(subprocess, "run", run_process)
    args = basic_args(
        tmp_path,
        output=output,
        matrix=False,
        width=800,
        height=600,
        rerun_failed=True,
    )

    assert cli._run_ui_batch(args, ["map"]) == 0

    run_process.assert_not_called()
    assert json.loads((output / "suite.json").read_text(encoding="utf-8"))["runs"] == prior


def test_run_ui_batch_rejects_invalid_dimensions_in_previous_suite(tmp_path):
    output = tmp_path / "results"
    output.mkdir()
    prior = [{"surface": "map", "width": 0, "height": 600, "passed": False}]
    (output / "suite.json").write_text(json.dumps({"runs": prior}), encoding="utf-8")
    args = basic_args(
        tmp_path,
        output=output,
        matrix=False,
        width=800,
        height=600,
        rerun_failed=True,
    )

    with pytest.raises(ValueError, match="Suite viewport dimensions must be positive"):
        cli._run_ui_batch(args, ["map"])


def test_run_ui_batch_records_timeout_as_failed_subprocess(monkeypatch, tmp_path):
    run_process = Mock(side_effect=subprocess.TimeoutExpired("openpower", 90))
    monkeypatch.setattr(subprocess, "run", run_process)
    args = basic_args(
        tmp_path,
        output=None,
        matrix=False,
        width=800,
        height=600,
        rerun_failed=False,
    )

    assert cli._run_ui_batch(args, ["map"]) == 1

    summary = json.loads((tmp_path / "artifacts/ui" / "suite.json").read_text(encoding="utf-8"))
    assert summary["runs"][0]["exit_code"] == 1
    assert summary["runs"][0]["log"] == "UI subprocess exceeded 90 seconds."


def test_handle_mod_create_and_validate_print_runtime_reports(monkeypatch, tmp_path, capsys):
    from src.modding import scaffold, validation

    created = SimpleNamespace(mod_id="custom.demo", path=tmp_path / "custom.demo")
    scaffold_call = Mock(return_value=created)
    monkeypatch.setattr(scaffold, "scaffold_mod", scaffold_call)
    assert cli._handle_mod_create(
        basic_args(tmp_path, mod_id="custom.demo", name="Demo", depends=["base, city", "base"])
    ) == 0
    scaffold_call.assert_called_once_with(
        tmp_path,
        "custom.demo",
        display_name="Demo",
        dependencies=("base", "city"),
    )

    report = SimpleNamespace(
        mod_id="custom.demo",
        load_order=("base", "custom.demo"),
        system_ids=("economy", "military"),
        table_schemas=("countries",),
        state_tables=("world", "events"),
        action_types=("SetBudget",),
    )
    validate = Mock(return_value=report)
    monkeypatch.setattr(validation, "validate_mod", validate)
    assert cli._handle_mod_validate(basic_args(tmp_path, mod_id="custom.demo")) == 0
    validate.assert_called_once_with(tmp_path, "custom.demo")
    output = capsys.readouterr().out
    assert "Created module 'custom.demo'" in output
    assert "Module 'custom.demo' is valid." in output
    assert "Systems: 2" in output
    assert "Actions: 1" in output


@pytest.mark.parametrize("failed,expected", [(True, 1), (False, 0)])
def test_handle_sim_run_reports_success_or_failure(monkeypatch, tmp_path, capsys, failed, expected):
    from src.simulation import runner

    report = SimpleNamespace(
        run_id="run-1",
        state_fingerprint="abc123",
        final_report_path=tmp_path / "report.json",
        failed=failed,
        failure_reasons=("missing table", "invalid action"),
    )
    simulator = Mock()
    simulator.return_value.run.return_value = report
    monkeypatch.setattr(runner, "HeadlessSimulationRunner", simulator)
    args = basic_args(
        tmp_path,
        mods="base",
        years=1,
        days=2,
        seed=3,
        player="USA",
        save=None,
        actions=None,
        output=None,
        run_id="fixed",
        snapshot_interval=10,
        diagnostics_interval=2,
        no_export_tables=False,
        fail_on_diagnostics=True,
    )

    assert cli._handle_sim_run(args) == expected

    output = capsys.readouterr()
    assert "Run: run-1" in output.out
    if failed:
        assert "Failure: missing table" in output.err
        assert "Failure: invalid action" in output.err
    else:
        assert output.err == ""
    simulator.assert_called_once()


@pytest.mark.parametrize("matched,expected", [(True, 0), (False, 1)])
def test_handle_sim_compare_reports_match_result(monkeypatch, tmp_path, capsys, matched, expected):
    from src.simulation import comparison

    report = SimpleNamespace(
        matched=matched,
        fingerprints=("fingerprint-1", "fingerprint-2"),
        report_path=tmp_path / "comparison.json",
    )
    comparison_runner = Mock()
    comparison_runner.return_value.run.return_value = report
    monkeypatch.setattr(comparison, "DeterminismComparisonRunner", comparison_runner)
    args = basic_args(
        tmp_path,
        runs=2,
        mods="base",
        years=0,
        days=30,
        seed=1,
        player=None,
        save=None,
        actions=None,
        output=Path("comparison"),
        run_id=None,
        snapshot_interval=30,
        diagnostics_interval=1,
        no_export_tables=False,
        fail_on_diagnostics=False,
    )

    assert cli._handle_sim_compare(args) == expected
    comparison_runner.assert_called_once()
    assert comparison_runner.call_args.kwargs["output_dir"] == (tmp_path / "comparison").resolve()
    assert "Matched: " in capsys.readouterr().out


def test_budget_ui_test_validates_viewport_and_resolves_output(monkeypatch, tmp_path):
    from src.client.ui.testing import budget

    args = basic_args(tmp_path, width=-1, height=768, output=Path("ui/budget"))
    with pytest.raises(ValueError, match="viewport width and height must be positive"):
        cli._handle_budget_ui_test(args)

    args.width = 1024
    run = Mock(return_value=0)
    monkeypatch.setattr(budget, "run_budget_ui_test", run)
    assert cli._handle_budget_ui_test(args) == 0
    run.assert_called_once_with((tmp_path / "ui/budget").resolve(), (1024, 768))


def test_simulation_config_normalizes_mods_and_optional_paths(monkeypatch, tmp_path):
    args = basic_args(
        tmp_path,
        mods="base,custom,base",
        years=2,
        days=3,
        seed=42,
        player="USA",
        save="save-a",
        actions=Path("actions.json"),
        output=Path("out"),
        run_id="run-custom",
        snapshot_interval=7,
        diagnostics_interval=4,
        no_export_tables=True,
        fail_on_diagnostics=True,
    )
    config_class = SimpleNamespace
    monkeypatch.setattr("src.simulation.runner.SimulationRunConfig", config_class)

    config = cli._simulation_config(args)

    assert config.project_root == tmp_path.resolve()
    assert config.active_mods == ("base", "custom")
    assert config.save_name == "save-a"
    assert config.player_tag == "USA"
    assert config.output_dir == (tmp_path / "out").resolve()
    assert config.run_id == "run-custom"
    assert config.years == 2 and config.days == 3
    assert config.snapshot_interval_days == 7
    assert config.diagnostics_interval_days == 4
    assert config.action_script_path == (tmp_path / "actions.json").resolve()
    assert config.random_seed == 42
    assert not config.export_final_tables
    assert config.fail_on_error_diagnostics


def test_simulation_config_uses_default_id_and_omits_optional_paths(monkeypatch, tmp_path):
    class FixedDateTime:
        @staticmethod
        def now():
            return datetime(2026, 11, 7, 13, 14, 15)

    monkeypatch.setattr(cli, "datetime", FixedDateTime)
    args = basic_args(
        tmp_path,
        mods="base",
        years=0,
        days=30,
        seed=1,
        player=None,
        save=None,
        actions=None,
        output=None,
        run_id=None,
        snapshot_interval=30,
        diagnostics_interval=1,
        no_export_tables=False,
        fail_on_diagnostics=False,
    )
    monkeypatch.setattr("src.simulation.runner.SimulationRunConfig", SimpleNamespace)

    config = cli._simulation_config(args)

    assert config.run_id == "sim-20261107-131415"
    assert config.output_dir is None
    assert config.action_script_path is None
    assert config.export_final_tables
    assert not config.fail_on_error_diagnostics


def test_split_names_and_resolved_path_cover_empty_duplicate_and_absolute_values(tmp_path):
    assert cli._split_names([" base, city ", "city,,trade", " "]) == ("base", "city", "trade")
    absolute = tmp_path / "absolute.json"
    assert cli._resolved_path(tmp_path, absolute) == absolute.resolve()
    assert cli._resolved_path(tmp_path, Path("nested/file.json")) == (tmp_path / "nested/file.json").resolve()
