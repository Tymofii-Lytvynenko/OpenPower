import importlib.util
import sys
from pathlib import Path

import pytest

from src.shared.actions import ActionSetGameSpeed


_MODULE_NAME = "src.simulation.actions"
if _MODULE_NAME in sys.modules:
    simulation_actions = sys.modules[_MODULE_NAME]
else:
    # Load the focused module without initializing unrelated simulation runtime services.
    _module_path = Path(__file__).resolve().parents[1] / "src" / "simulation" / "actions.py"
    _module_spec = importlib.util.spec_from_file_location(_MODULE_NAME, _module_path)
    simulation_actions = importlib.util.module_from_spec(_module_spec)
    sys.modules[_MODULE_NAME] = simulation_actions
    _module_spec.loader.exec_module(simulation_actions)


def test_action_registry_rejects_non_action_types() -> None:
    with pytest.raises(TypeError, match="not a dataclass GameAction"):
        simulation_actions.build_action_registry([str])


def test_action_schedule_filters_day_tick_and_minute() -> None:
    action = ActionSetGameSpeed("simulation", 3)
    matching_action = ActionSetGameSpeed("simulation", 4)
    script = simulation_actions.ActionScript(
        [
            simulation_actions.ScheduledAction(action, tick=2),
            simulation_actions.ScheduledAction(action, minute=29),
            simulation_actions.ScheduledAction(action),
            simulation_actions.ScheduledAction(matching_action, day=2, tick=4, minute=30),
        ]
    )

    assert script.actions_for(day=2, tick=4, minute=30) == [matching_action]


def test_action_script_reads_empty_and_json_lines_files(tmp_path: Path) -> None:
    path = tmp_path / "actions.jsonl"
    path.write_text("\ufeff  \n", encoding="utf-8")
    assert simulation_actions.ActionScript.from_path(path).actions_for(1, 0, 0) == []

    path.write_text(
        '# generated actions\n\n{"type":"ActionSetGameSpeed","speed_level":3}\n',
        encoding="utf-8",
    )
    actions = simulation_actions.ActionScript.from_path(path).actions_for(day=1, tick=0, minute=0)

    assert actions == [ActionSetGameSpeed("simulation", 3)]


def test_action_script_rejects_non_object_lines_and_invalid_records(tmp_path: Path) -> None:
    path = tmp_path / "actions.jsonl"
    path.write_text("1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="line 1 must contain a JSON object"):
        simulation_actions.ActionScript.from_path(path)

    invalid_records = (
        ("{}", "missing 'type'"),
        ('{"type":"UnknownAction"}', "Unknown action type"),
        (
            '{"type":"ActionSetGameSpeed","speed_level":3,"unexpected":true}',
            "unknown fields",
        ),
    )
    for record, message in invalid_records:
        path.write_text(record, encoding="utf-8")
        with pytest.raises(ValueError, match=message):
            simulation_actions.ActionScript.from_path(path)
