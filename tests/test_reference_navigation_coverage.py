"""Keep source callback coverage separate from destination-only smoke tests."""
from pathlib import Path
import csv
import json

from utils import reference_ui_audit as audit
from utils.reference_paths import resolve_reference_file


def _interaction_gap_rows(gaps, component_path: str, binding: dict[str, str]) -> list[dict[str, str]]:
    expected = f"{binding['openpower_surface']}: {binding['openpower_effect']}"
    return [
        row for row in gaps
        if row["gml_node_or_behavior"] == component_path
        and row["openpower_current_implementation"] == expected
    ]


def test_country_information_audit_records_openpower_bindings_and_missing_source_data():
    assert audit.PANEL_ALIASES["Country_Information_Window"] == ("COUNTRY_MORE_INFO", "partial")
    assert "CountryMoreInfoPanel" in audit.PARTIALLY_IMPLEMENTED_WINDOW_GAPS[
        "Country_Information_Window"
    ]["current_implementation"]

    bindings = audit.DISPLAY_BINDINGS_BY_WINDOW["Country_Information_Window"]
    assert bindings["frmInner/frmHumanDevelopment/txtInfrastructure"].state_binding == "countries.infrastructure_index"
    assert bindings["frmInner/frmHumanDevelopment/txtTelecom"].state_binding == "countries.telecom_index"
    assert bindings["frmInner/frmPopulation/txt1565"].state_binding.startswith("sum(regions.pop_15_64)")
    assert bindings["frmInner/frmTerrain/txtLandArea"].state_binding.startswith("sum(regions.area_km2)")
    for path in (
        "frmInner/frmLand/txtArableLand",
        "frmInner/frmPopulation/txtBirthRate",
        "frmInner/frmTerrain/txtWaterArea",
        "frmInner/frmClimate/frmInner/lblClimate",
    ):
        assert bindings[path].status == "verified_unavailable"
        assert "Em dash" in bindings[path].fallback

    interactions = audit.COUNTRY_INFO_INTERACTION_BINDINGS
    assert interactions["Country_Information_Window/frmTitle/btnExit"]["game_action"] == "none (local window close)"
    assert "hides btnApply" in interactions["Country_Information_Window/frmTitle/btnApply"]["openpower_effect"]
    assert "visual meter component" in interactions[
        "Country_Information_Window/frmInner/frmLand/frmForests/btnFill"
    ]["game_action"]

    with (Path(__file__).resolve().parents[1] / "docs/ui/reference/data_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        country_data = [
            row for row in csv.DictReader(source)
            if row["window_id"] == "Country_Information_Window"
        ]
    assert len(country_data) == 43
    assert not any(row["status"] == "assumption/unknown" for row in country_data)
    assert audit.COUNTRY_INFO_BINDINGS["frmInner/frmPopulation/lbl15"].status == "partial"
    assert audit.COUNTRY_INFO_BINDINGS["frmTitle/lblTitle"].status == "partial"
    assert "country name as the title" in audit.COUNTRY_INFO_BINDINGS[
        "frmTitle/lblTitle"
    ].meaning


def test_options_window_audit_classifies_source_only_controls_explicitly():
    assert audit.PANEL_ALIASES["Options_Window"] == ("SETTINGS", "partial")
    assert "462x329" in audit.PARTIALLY_IMPLEMENTED_WINDOW_GAPS["Options_Window"]["reason"]

    bindings = audit.OPTIONS_INTERACTION_BINDINGS
    assert bindings["Options_Window/frmTitle/btnApply"]["status"] == "verified_cpp"
    assert bindings["Options_Window/frmInner/btnCancel"]["status"] == "verified_openpower"
    clear_ban = bindings["Options_Window/frmInner/tabOptions/Tab1/btnClearBan"]
    assert clear_ban["status"] == "verified_unavailable"
    assert "admin player ID" in clear_ban["validation_condition"]
    assert bindings["Options_Window/frmInner/tabOptions/Tab2/cboZoomLevel"]["status"] == "verified_unavailable"
    assert bindings["Options_Window/frmInner/tabOptions/Tab2/cboResolution"]["status"] == "verified_cpp"

    autosave_paths = (
        "Options_Window/frmInner/tabOptions/Tab1/togAutosave",
        "Options_Window/frmInner/tabOptions/Tab1/frmAutosave/edtAutosaveEach",
        "Options_Window/frmInner/tabOptions/Tab1/frmAutosave/edtAutosaveName",
        "Options_Window/frmInner/tabOptions/Tab1/frmAutosave/togIncremental",
    )
    for path in autosave_paths:
        binding = bindings[path]
        assert binding["status"] == "verified_openpower"
        assert "AutosaveScheduler" in binding["openpower_effect"]
        assert binding["game_action"].startswith("ActionSaveGame")
        assert "validate_save_name" in binding["validation_condition"]

    assert "autosave" not in audit.PARTIALLY_IMPLEMENTED_WINDOW_GAPS["Options_Window"]["missing_action"].lower()
    root = Path(__file__).resolve().parents[1]
    with (root / "docs/ui/reference/interaction_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        contracts = {row["component_path"]: row for row in csv.DictReader(source)}
    for path in autosave_paths:
        assert contracts[path]["status"] == "verified_openpower"
        assert contracts[path]["game_action"].startswith("ActionSaveGame")
        assert "AutosaveScheduler" in contracts[path]["openpower_effect"]

    display = audit.DISPLAY_BINDINGS_BY_WINDOW["Options_Window"]
    assert display["frmInner/tabOptions/Tab1/frmAIAggressivenessMtr"].status == "verified_unavailable"
    assert "camera magnification" in display["frmInner/tabOptions/Tab2/cboZoomLevel"].meaning
    assert display["frmInner/tabOptions/Tab2/cboResolution"].status == "partial"
    assert display["frmInner/tabOptions/Tab2/cboColorDepth"].status == "verified_unavailable"
    assert display["frmTitle/lblTitle"].status == "partial"


def test_credits_window_audit_preserves_unavailable_source_slots_in_the_rendered_roster():
    credits = audit.PARTIALLY_IMPLEMENTED_WINDOW_GAPS["Credits_Window"]
    assert "57-entry public Steam Edition roster" in credits["reason"]
    assert "ProjectCreditsContent" in credits["reason"]
    assert "MainMenuContent/Credits" in credits["current_implementation"]
    assert "Art team section uses lblTitle5" in credits["reason"]
    assert "lblTitle35/Text 101405" in credits["reason"]
    assert "inferred (www.multimediarts.net)" in credits["current_implementation"]
    assert "footer mapping is inferred" in credits["reason"]
    assert "\u00a9 GolemLabs 2004" in credits["current_implementation"]
    assert "N/A placeholder" not in credits["current_implementation"]
    assert "101405" in credits["missing_action"]
    assert "102121" in credits["missing_action"]

    root = Path(__file__).resolve().parents[1]
    with (root / "docs/ui/reference/window_registry.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        registry = {row["window_id"]: row for row in csv.DictReader(source)}
    assert "57-entry public Steam Edition roster" in registry["Credits_Window"]["openpower_surface"]

    with (root / "docs/ui/reference/unimplemented_windows.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        inbound = [row for row in csv.DictReader(source) if row["window_id"] == "Credits_Window"]
    assert inbound
    assert all(
        all(token in row["missing_action"] for token in ("101405", "102121"))
        for row in inbound
    )


def test_covert_form_confirmation_buttons_map_to_authoritative_actions():
    bindings = audit.COVERT_FORM_ACTION_INTERACTION_BINDINGS
    expected = {
        "Covert_Actions_Cell_Creation/frmInner/btnConfirm": "ActionCreateCovertCell",
        "Covert_Actions_Cell_Training/frmInner/btnConfirm": "ActionTrainCovertCell",
        "Covert_Actions_New_Mission/frmInner/btnConfirm": "ActionStartCovertMission",
    }
    for path, action in expected.items():
        binding = bindings[path]
        assert binding["game_action"] == action
        assert binding["status"] == "verified_openpower"
        assert binding["action_required"] == ""
    assert "requires_execution_confirmation=True" in bindings[
        "Covert_Actions_New_Mission/frmInner/btnConfirm"
    ]["confirmation_state"]
    root = Path(__file__).resolve().parents[1]
    with (root / "docs/ui/reference/interaction_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        contracts = {row["component_path"]: row for row in csv.DictReader(source)}
    for path, action in expected.items():
        for field, value in bindings[path].items():
            assert contracts[path][field] == value
        assert contracts[path]["game_action"] == action


def test_covert_cell_creation_controls_keep_the_selected_training_and_openpower_rules():
    bindings = audit.COVERT_FORM_ACTION_INTERACTION_BINDINGS
    expected_status = {
        "Covert_Actions_Cell_Creation/frmTitle/btnExit": "verified_openpower",
        "Covert_Actions_Cell_Creation/frmTitle/btnApply": "verified_unavailable",
        "Covert_Actions_Cell_Creation/frmInner/btnCancel": "verified_openpower",
        "Covert_Actions_Cell_Creation/frmInner/frmCell/edtName": "verified_openpower",
        "Covert_Actions_Cell_Creation/frmInner/frmCell/cboCountry": "verified_openpower",
        "Covert_Actions_Cell_Creation/frmInner/frmCell/cboTraining": "verified_openpower",
    }
    for path, status in expected_status.items():
        assert bindings[path]["status"] == status
        assert bindings[path]["action_required"] == ""

    training = bindings["Covert_Actions_Cell_Creation/frmInner/frmCell/cboTraining"]
    assert training["game_action"] == "ActionCreateCovertCell(training_level)"
    assert "flat setup-cost rule" in training["restrictions_confirmation_error"]
    assert "route-based travel time" in training["restrictions_confirmation_error"]

    root = Path(__file__).resolve().parents[1]
    with (root / "docs/ui/reference/interaction_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        contracts = {row["component_path"]: row for row in csv.DictReader(source)}
    for path in expected_status:
        for field, value in bindings[path].items():
            assert contracts[path][field] == value


def test_source_hidden_title_apply_slots_are_not_reported_as_unknown_actions():
    hidden_windows = {
        "Advisor_Window",
        "Covert_Actions_Cell_Training",
        "Covert_Actions_New_Mission",
        "Covert_Actions_Window",
        "Credits_Window",
        "Economic_Window",
        "Game_Over_Window",
        "Join_Multiplayer_Game",
        "Load_Saved_Game",
        "Main_Menu",
        "Objectives_Window",
        "Party_Selection_Window",
        "Relations_Window",
        "Save_Game_Window",
        "Strategic_Missile_List_Window",
        "Submenu_Multi",
        "Submenu_Single",
        "Unit_List_Window_New",
        "frmBaseWindow",
    }
    root = Path(__file__).resolve().parents[1]
    with (root / "docs/ui/reference/interaction_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        contracts = {
            row["window_id"]: row
            for row in csv.DictReader(source)
            if row["window_id"] in hidden_windows
            and row["component_path"].endswith("/frmTitle/btnApply")
        }

    assert contracts.keys() == hidden_windows
    for window_id, contract in contracts.items():
        assert contract["status"] == "verified_unavailable"
        assert contract["cpp_member_binding"] == "m_pObjApplyBtn"
        assert "OnCreate hides" in contract["reference_side_effect"]
        assert "m_pObjApplyBtn->Hide()" in contract["verified_cpp_transition"]
        assert contract["game_action"] == "none (source-hidden title control)"
        assert contract["action_required"] == ""


def test_standard_title_exit_controls_trace_direct_and_inherited_source_callbacks():
    root = Path(__file__).resolve().parents[1]
    with (root / "docs/ui/reference/interaction_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        contracts = {
            row["window_id"]: row
            for row in csv.DictReader(source)
            if row["window_id"] in {
                "Battle_Info_Window",
                "Covert_Actions_Cell_Training",
                "Credits_Window",
                "Relations_Window",
            }
            and row["component_path"].endswith("/frmTitle/btnExit")
        }

    assert contracts.keys() == {
        "Battle_Info_Window",
        "Covert_Actions_Cell_Training",
        "Credits_Window",
        "Relations_Window",
    }
    for window_id, contract in contracts.items():
        assert contract["status"] in {"verified_cpp", "verified_openpower"}
        assert contract["cpp_member_binding"] == "m_pObjExitBtn"
        assert "OnMouseClick" in contract["reference_callback"]
        assert contract["reference_side_effect"] != "unknown"
        assert contract["verified_cpp_transition"]
    assert "SaveConfirmationWindow" in contracts["Battle_Info_Window"]["reference_side_effect"]


def test_advisor_plan_buttons_keep_accept_and_dismiss_semantics_distinct():
    root = Path(__file__).resolve().parents[1]
    source = resolve_reference_file(root, ".codex/Client/Source/reference_advisor_window.cpp").read_text(encoding="utf-8")
    server = (
        resolve_reference_file(
            root,
            ".codex/reference-hdm-full-reference/Server/Source/reference_advisor_event_handler.cpp",
        )
    ).read_text(encoding="utf-8")
    assert "if(in_pCaller == m_pObjExecuteBtn)" in source
    assert "l_pUpdate->m_bAccept = true" in source
    assert "l_pUpdate->m_bAccept = false" in source
    assert "AcceptPendingPlan(l_iObjective)" in server
    assert "RemovePlan(l_iObjective)" in server
    assert "HandleTooManyMilitaryUnits(l_pEvent)" in server

    bindings = audit.ADVISOR_PLAN_INTERACTION_BINDINGS
    execute_path = "Advisor_Window/frmInner/btnExecute"
    exit_path = "Advisor_Window/frmTitle/btnExit"
    execute = bindings[execute_path]
    dismiss = bindings[exit_path]
    assert "accept=True" in execute["game_action"]
    assert "accept=False" in dismiss["game_action"]
    assert "no direct field-level translation" in execute["openpower_effect"]
    assert "not a wire-compatible mapping" in execute["restrictions_confirmation_error"]
    assert execute["status"] == dismiss["status"] == "partial"

    with (root / "docs/ui/reference/interaction_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as file:
        rows = {
            row["component_path"]: row
            for row in csv.DictReader(file)
            if row["component_path"] in {execute_path, exit_path}
        }
    assert rows.keys() == {execute_path, exit_path}
    for path, binding in bindings.items():
        for field, value in binding.items():
            assert rows[path][field] == value
        assert rows[path]["reference_game_event"].endswith("Event::GSendPlan")
        assert not rows[path]["game_action"].startswith("unknown;")

    with (root / "docs/ui/reference/gap_table.csv").open(
        encoding="utf-8-sig", newline=""
    ) as file:
        gaps = list(csv.DictReader(file))
    for path, binding in bindings.items():
        matching_gaps = _interaction_gap_rows(gaps, path, binding)
        assert matching_gaps and all(gap["status"] == "partial" for gap in matching_gaps)


def test_battle_info_apply_and_country_lists_match_the_read_only_source_window():
    root = Path(__file__).resolve().parents[1]
    source = resolve_reference_file(root, ".codex/Client/Source/reference_battle_info_window.cpp").read_text(encoding="utf-8")
    base_header = resolve_reference_file(root, ".codex/Client/Include/reference_base_window.h").read_text(encoding="utf-8")
    panel = (root / "src/client/ui/panels/military/battle_inspection_windows.py").read_text(encoding="utf-8")
    journey = (root / "tests/ui/journeys/reference-battle-inspection-observed.json").read_text(encoding="utf-8")

    assert "m_pObjCountryListA =" in source and "m_pObjCountryListB =" in source
    assert "OnListItemSelected" not in source and "OnListItemDoubleClicked" not in source
    assert "virtual void Save(){return;};" in base_header
    assert "title_ui.button(" in panel and '"btnApply"' in panel
    assert '("A", "defender_side", "DEFENDERS"), ("B", "attacker_side", "ATTACKERS")' in panel
    assert '"target": "battle.info.apply"' in journey
    assert '"type": "ActionSetBattleStrategy",\n      "count": 0' in journey

    bindings = audit.BATTLE_INFO_INTERACTION_BINDINGS
    paths = {
        "Battle_Info_Window/frmTitle/btnApply",
        "Battle_Info_Window/frmInner/frmInner/frmBattleInfo/lstCountriesA",
        "Battle_Info_Window/frmInner/frmInner/frmBattleInfo/lstCountriesB",
    }
    assert set(bindings) == paths
    assert all(binding["status"] == "verified_openpower" for binding in bindings.values())
    assert bindings["Battle_Info_Window/frmTitle/btnApply"]["game_action"] == "none (inherited Save is a no-op)"
    assert "defenders" in bindings[next(path for path in paths if path.endswith("lstCountriesA"))]["reference_side_effect"]
    assert "attackers" in bindings[next(path for path in paths if path.endswith("lstCountriesB"))]["reference_side_effect"]

    with (root / "docs/ui/reference/interaction_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as file:
        rows = {row["component_path"]: row for row in csv.DictReader(file) if row["component_path"] in paths}
    assert rows.keys() == paths
    for path, binding in bindings.items():
        for field, value in binding.items():
            assert rows[path][field] == value

    with (root / "docs/ui/reference/gap_table.csv").open(
        encoding="utf-8-sig", newline=""
    ) as file:
        gaps = list(csv.DictReader(file))
    for path, binding in bindings.items():
        matching_gaps = _interaction_gap_rows(gaps, path, binding)
        assert matching_gaps and all(gap["status"] == "verified_openpower" for gap in matching_gaps)


def test_unit_design_confirm_maps_to_authoritative_validation_and_feedback():
    path = "Unit_New_Design/frmAction/btnConfirm"
    binding = audit.UNIT_DESIGN_INTERACTION_BINDINGS[path]
    assert binding["game_action"] == "ActionCreateUnitDesign"
    assert binding["status"] == "verified_openpower"
    assert "source-mapped required capabilities" in binding["openpower_effect"]
    assert "fraction" in binding["restrictions_confirmation_error"]

    root = Path(__file__).resolve().parents[1]
    with (root / "docs/ui/reference/interaction_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        contracts = [
            row for row in csv.DictReader(source)
            if row["component_path"] == path
        ]
    assert len(contracts) == 1
    for field, value in binding.items():
        assert contracts[0][field] == value


def test_politics_window_audit_classifies_all_source_meter_and_title_controls():
    bindings = audit.POLITICS_INTERACTION_BINDINGS
    assert len(bindings) == 12
    assert bindings["Politic_Window/frmTitle/btnExit"]["status"] == "verified_openpower"
    assert bindings["Politic_Window/frmTitle/btnApply"]["status"] == "verified_openpower"

    approval_fill = bindings[
        "Politic_Window/frmInner/frmApproval/frmGradient/btnFill"
    ]
    assert approval_fill["status"] == "verified_unavailable"
    assert "no OnCustomEvent receiver" in approval_fill["reference_side_effect"]
    assert bindings[
        "Politic_Window/frmInner/frmApproval/frmGradient/btnUnfilled"
    ]["status"] == "verified_openpower"
    assert bindings[
        "Politic_Window/frmInner/frmIdeology/frmIdeologyCursor/btnFill"
    ]["status"] == "verified_openpower"

    pressure = audit.DISPLAY_BINDINGS_BY_WINDOW["Politic_Window"]
    assert pressure["frmInner/frmPressure/txtValue"].status == "verified_unavailable"
    assert pressure["frmInner/frmPressure/frmGradient"].status == "partial"
    assert pressure["frmInner/frmConstitutionalForm/txtValue"].status == "partial"
    assert all(pressure[path].status == "partial" for path in (
        "frmTitle/lblTitle",
        "frmInner/frmIdeology/lblLeft",
        "frmInner/frmIdeology/lblRight",
        "frmInner/frmApproval/lblTitle",
    ))

    root = Path(__file__).resolve().parents[1]
    with (root / "docs/ui/reference/interaction_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        political_interactions = [
            row for row in csv.DictReader(source)
            if row["window_id"] == "Politic_Window"
        ]
    with (root / "docs/ui/reference/data_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        political_data = [
            row for row in csv.DictReader(source)
            if row["window_id"] == "Politic_Window"
        ]
    assert not any(row["status"] == "assumption/unknown" for row in political_interactions)
    assert not any(row["status"] == "assumption/unknown" for row in political_data)


def test_country_profile_audit_traces_filters_selection_and_read_only_rank_bars():
    bindings = audit.COUNTRY_PROFILE_INTERACTION_BINDINGS
    assert len(bindings) == 20
    assert bindings["Country_Profile_Window/frmTitle/btnExit"]["status"] == "verified_openpower"
    assert bindings["Country_Profile_Window/frmTitle/btnApply"]["status"] == "verified_openpower"
    assert bindings["Country_Profile_Window/frmInner/btnConfirm"]["status"] == "partial"
    assert bindings["Country_Profile_Window/frmInner/frmDesired/frmEconomic/btnFill"]["status"] == "partial"
    assert bindings["Country_Profile_Window/frmInner/frmDesired/togEconomic"]["status"] == "partial"
    assert bindings["Country_Profile_Window/frmInner/frmSuggested/frmEconomic/btnFill"]["status"] == "verified_openpower"
    assert "rank arrays" in bindings[
        "Country_Profile_Window/frmInner/frmSuggested/lstCountries"
    ]["restrictions_confirmation_error"]

    display = audit.DISPLAY_BINDINGS_BY_WINDOW["Country_Profile_Window"]
    assert display["frmInner/frmSuggested/frmEconomic"].status == "partial"
    assert display["frmInner/frmSuggested/picPolitic"].status == "partial"
    assert display["frmInner/frmSuggested/picSep"].status == "partial"
    assert display["frmInner/frmSuggested/lblGoals2"].status == "partial"

    root = Path(__file__).resolve().parents[1]
    with (root / "docs/ui/reference/interaction_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        rows = [row for row in csv.DictReader(source) if row["window_id"] == "Country_Profile_Window"]
    assert not any(row["status"] == "assumption/unknown" for row in rows)


def test_treaty_details_audit_maps_source_controls_and_marks_real_parity_limits():
    bindings = audit.TREATY_DETAILS_INTERACTION_BINDINGS
    assert bindings[
        "Treaty_Details_Window/frmInner/frmMain/frmModify/btnRefuse"
    ]["game_action"].startswith("ActionRespondTreaty")
    assert bindings[
        "Treaty_Details_Window/frmInner/frmPressure/btnSponsor"
    ]["status"] == "verified_unavailable"
    assert "pressure side" in bindings[
        "Treaty_Details_Window/frmInner/frmPressure/btnSponsor"
    ]["restrictions_confirmation_error"]
    assert bindings[
        "Treaty_Details_Window/frmInner/frmConditions/cboGeographicProximity"
    ]["status"] == "partial"
    assert "not one-to-one" in bindings[
        "Treaty_Details_Window/frmInner/frmConditions/cboGeographicProximity"
    ]["restrictions_confirmation_error"]

    display = audit.DISPLAY_BINDINGS_BY_WINDOW["Treaty_Details_Window"]
    assert display["frmInner/frmPressure/txtValue"].status == "verified_unavailable"
    assert display["frmInner/frmPressure/lstPressure"].status == "verified_unavailable"
    assert display["frmInner/frmMain/lstCountriesA"].status == "partial"
    assert display["frmInner/frmConditions/cboRelations"].status == "partial"

    root = Path(__file__).resolve().parents[1]
    for filename in ("interaction_contracts.csv", "data_contracts.csv"):
        with (root / "docs/ui/reference" / filename).open(
            encoding="utf-8-sig", newline=""
        ) as source:
            rows = [row for row in csv.DictReader(source) if row["window_id"] == "Treaty_Details_Window"]
        assert rows
        assert not any(row["status"] == "assumption/unknown" for row in rows)


def coverage_row(tmp_path, monkeypatch, *, verification_kind=None, bound=True,
                 operation="key", control="b", step_control=None,
                 suite_passed: bool | None = True):
    monkeypatch.setattr(audit, "REPO_ROOT", tmp_path)
    directory = tmp_path / "docs/ui/reference"
    directory.mkdir(parents=True)
    route = {"source_file": "source.cpp", "source_line": 42, "target_window": "Target",
             "status": "blocked_missing_ui", "reason": "The source dialog is missing."}
    if bound:
        route.update(journey_file="route.json", operation=operation, control_id=control,
                     expected_region="target.panel", expected_visible=True)
    if verification_kind:
        route["verification_kind"] = verification_kind
    (directory / "navigation_route_bindings.json").write_text(json.dumps([route]))
    journey_dir = tmp_path / "journeys"
    journey_dir.mkdir()
    (journey_dir / "route.json").write_text(json.dumps({"steps": [
        {"op": operation, "key" if operation in {"key", "key_down", "key_up"} else "fixture":
         control if step_control is None else step_control},
        {"op": "assert_region", "target": "target.panel", "visible": True},
    ]}))
    suite = tmp_path / "suite.json"
    suite_results = [] if suite_passed is None else [
        {"journey": "route.json", "passed": suite_passed}
    ]
    suite.write_text(json.dumps({"results": suite_results}))
    edge = {"source_widget_path": "handler:test", "source_file": "source.cpp", "source_line": 42,
            "source_window": "Source", "target_window": "Target", "mode": "show",
            "event": "OnKeyDown", "context": "", "control_path_status": "verified_cpp"}
    return audit._navigation_journey_coverage_rows([edge], [], [], journey_dir, suite)[0]


def test_keyboard_binding_requires_the_actual_key_operation(tmp_path, monkeypatch):
    assert coverage_row(tmp_path, monkeypatch)["coverage_status"] == "tested"


def test_navigation_journey_that_has_not_run_is_not_reported_as_failed(tmp_path, monkeypatch):
    row = coverage_row(tmp_path, monkeypatch, suite_passed=None)

    assert row["journey_suite_status"] == "not_run"
    assert row["coverage_status"] == "journey_not_run"


def test_failed_navigation_journey_has_a_distinct_coverage_status(tmp_path, monkeypatch):
    row = coverage_row(tmp_path, monkeypatch, suite_passed=False)

    assert row["journey_suite_status"] == "failed"
    assert row["coverage_status"] == "journey_failed"


def test_unrun_seed_transition_journey_is_reported_as_not_run(tmp_path, monkeypatch):
    monkeypatch.setattr(audit, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(audit, "SEED_JOURNEY_MAP", {
        "source.button": ("route.json", "source.button", "target.panel"),
    })
    monkeypatch.setattr(audit, "LATEST_JOURNEY_REPORTS", {})
    journey_dir = tmp_path / "journeys"
    journey_dir.mkdir()
    (journey_dir / "route.json").write_text(json.dumps({"steps": [
        {"op": "click", "target": "source.button"},
        {"op": "assert_region", "target": "target.panel", "visible": True},
    ]}))
    suite_path = tmp_path / "suite.json"
    suite_path.write_text(json.dumps({"results": []}))

    row = audit._seed_transition_journey_rows(
        {"transitions": [{"source": "source.button", "destination": "Target"}]},
        journey_dir,
        suite_path,
    )[0]

    assert row["journey_suite_status"] == "not_run"
    assert row["coverage_status"] == "journey_not_run"


def test_handler_only_routes_keep_cpp_evidence_without_claiming_a_gml_widget():
    assert audit._source_control_path_status("", "BACKGROUND_EARTH", {}) == "verified_cpp"
    assert audit._source_control_path_status(
        "frmInner/btnPolicy", "Politic_Window", {"Politic_Window": {"frmInner/btnPolicy"}}
    ) == "verified_gml"
    assert audit._source_control_path_status(
        "m_pInheritedExit", "Military_Window", {"Military_Window": set()}
    ) == "verified_cpp"


def test_global_shortcuts_keep_cpp_handler_evidence_and_passed_journeys():
    root = Path(__file__).resolve().parents[1]
    with (root / "docs/ui/reference/navigation_journey_coverage.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        rows = list(csv.DictReader(source))

    expected = {
        "reference-shortcut-d.json": ("Unit_Ground_Deployment_Window", "d"),
        "reference-shortcut-u.json": ("Unit_Production_Window", "u"),
        "reference-shortcut-c.json": ("Covert_Actions_Window", "c"),
        "reference-shortcut-w.json": ("War_List_Window", "w"),
        "reference-shortcut-b.json": ("Budget_Window", "b"),
        "reference-shortcut-r.json": ("Resources_Window", "r"),
        "reference-shortcut-t.json": ("Treaties_Window", "t"),
    }
    actual = {
        Path(row["journey_file"]).name: row
        for row in rows
        if row["source_widget_path"] == "handler:GBackgroundEarth::OnKeyDown"
        and Path(row["journey_file"]).name in expected
    }
    assert set(actual) == set(expected)
    for journey, (target, key) in expected.items():
        row = actual[journey]
        assert row["target_window"] == target
        assert row["journey_operation"] == "key"
        assert row["journey_control_id"] == key
        assert row["control_path_status"] == "verified_cpp"
        assert row["coverage_status"] == "tested"
        assert row["journey_suite_status"] == "passed"


def test_tested_navigation_routes_are_not_left_unknown_in_gap_table():
    root = Path(__file__).resolve().parents[1] / "docs/ui/reference"
    with (root / "navigation_journey_coverage.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        routes = list(csv.DictReader(source))
    with (root / "gap_table.csv").open(encoding="utf-8-sig", newline="") as source:
        gaps = list(csv.DictReader(source))

    gap_by_site = {}
    for gap in gaps:
        evidence = gap["evidence"]
        if "#L" in evidence:
            gap_by_site.setdefault((evidence, gap["gml_node_or_behavior"]), []).append(gap)

    guided_tutorial_routes = 0
    for route in routes:
        if not route["coverage_status"].startswith("tested"):
            continue
        site = (
            f"{route['source_file']}#L{route['source_line']}",
            route["source_widget_path"],
        )
        matching_gaps = gap_by_site[site]
        assert all(gap["status"] != "assumption/unknown" for gap in matching_gaps)

        if route["coverage_status"] == "tested_equivalent_guided_tutorial":
            guided_tutorial_routes += 1
            assert all(gap["status"] == "partial" for gap in matching_gaps)
            assert all("unsupported" in gap["action_required"].lower() for gap in matching_gaps)

    assert guided_tutorial_routes == 7


def test_held_keyboard_binding_requires_the_exact_held_key(tmp_path, monkeypatch):
    assert coverage_row(tmp_path, monkeypatch, operation="key_down", control="tab")["coverage_status"] == "tested"
    assert coverage_row(tmp_path / "wrong-key", monkeypatch, operation="key_down", control="tab",
                        step_control="space")["coverage_status"] == "source_operation_missing"


def test_snapshot_binding_requires_the_exact_delivered_fixture(tmp_path, monkeypatch):
    assert coverage_row(tmp_path, monkeypatch, operation="server_snapshot",
                        control="activation.json")["coverage_status"] == "tested"


def test_other_snapshot_does_not_establish_the_source_callback(tmp_path, monkeypatch):
    assert coverage_row(tmp_path, monkeypatch, operation="server_snapshot",
                        control="activation.json", step_control="other.json")["coverage_status"] == "source_operation_missing"


def test_alternative_validation_is_not_literal_navigation_parity(tmp_path, monkeypatch):
    row = coverage_row(tmp_path, monkeypatch, verification_kind="equivalent_validation")
    assert row["coverage_status"] == "tested_equivalent_validation"


def test_guided_tutorial_route_preserves_unsupported_source_setup_as_partial(tmp_path, monkeypatch):
    row = coverage_row(tmp_path, monkeypatch, verification_kind="guided_tutorial_equivalent")

    assert row["coverage_status"] == "tested_equivalent_guided_tutorial"
    assert audit._navigation_gap_status(row["coverage_status"]) == "partial"


def test_missing_callback_is_not_verified_by_a_destination_smoke_test(tmp_path, monkeypatch):
    row = coverage_row(tmp_path, monkeypatch, bound=False)
    assert row["coverage_status"] == "blocked_missing_ui"
    assert not row["journey_has_source_operation"]


def test_geometry_crosswalk_does_not_merge_branches_in_one_handler():
    edges, journeys = [], []
    for line in (101, 102):
        edge = {"source_file": "source.cpp", "source_line": line, "source_window": "Source",
                "source_widget_path": "handler:shared", "target_window": "Target",
                "mode": "show", "event": "HandleContextMenu"}
        edges.append(edge)
        journeys.append({**edge, "journey_file": f"route-{line}.json"})
    rows = audit._layout_geometry_crosswalk(edges, journeys, [], [], {})
    assert [row["journey_file"] for row in rows] == ["route-101.json", "route-102.json"]


def test_geometry_uses_the_visible_destination_capture_before_close(tmp_path):
    capture = tmp_path / "checkpoint.png"
    capture.write_bytes(b"capture-existence-marker")
    snapshot = {"regions": [{"id": "target", "visible": True, "present": True,
                              "rect": {"width": 358, "height": 248}}]}
    capture.with_suffix(".json").write_text(json.dumps(snapshot), encoding="utf-8")
    final = {"regions": [{"id": "target", "visible": False, "present": False}]}
    report = {"telemetry": final, "details": {"steps": [
        {"region": "target", "passed": True, "screenshot": str(capture)},
    ]}}
    assert audit._route_evidence_snapshot(report, "target") == (snapshot, str(capture))
    assert audit._route_evidence_snapshot(report, "other") == (final, "")


def test_generic_question_factory_calls_are_accounted_with_their_actual_source_sites():
    import re
    root = Path(__file__).resolve().parents[1]
    source = root / ".codex/Client/Source"
    catalog = json.loads(resolve_reference_file(root, ".codex/reference_ui_catalog.json").read_text(encoding="utf-8"))
    index = audit._source_index(source)
    edges, _ = audit._window_edges(index, catalog)
    questions = [row for row in edges if row["target_window"] == "Generic_Question_Window"]
    represented = {(Path(row.get("action_source_file") or row["source_file"]).name,
                    int(row.get("action_source_line") or row["source_line"])) for row in questions}
    literal = set()
    for path, text in index["texts"].items():
        for match in re.finditer(r"g_ClientDDL\.GenericQuestion\s*\(", text):
            literal.add((path.name, text[:match.start()].count("\n") + 1))
    assert represented == literal
    assert any(name.endswith("internal_laws_window.cpp") and line == 297 for name, line in represented)
    assert any(name.endswith("internal_laws_window.cpp") and line == 326 for name, line in represented)
    assert all(row["status"] == "verified_cpp" for row in questions)


def test_generic_message_callback_map_preserves_all_route_columns():
    root = Path(__file__).resolve().parents[1]
    path = root / "docs/ui/reference/generic_message_callback_map.csv"
    with path.open(encoding="utf-8-sig", newline="") as source:
        rows = list(csv.reader(source))

    header = rows[0]
    assert all(len(row) == len(header) for row in rows[1:])
    routes = [dict(zip(header, row)) for row in rows[1:]]
    display_routes = [route for route in routes if route["route_id"].startswith("SHOW-")]
    assert len(display_routes) == 28
    assert len({route["route_id"] for route in routes}) == len(routes)

    by_id = {route["route_id"]: route for route in routes}
    assert by_id["SHOW-07"]["mapping_status"] == "verified_openpower"
    assert "aggregates each incoming batch by authoritative refusal reason" in by_id["SHOW-07"]["openpower_route"]
    assert by_id["SHOW-25"]["mapping_status"] == "verified_openpower"
    assert "m_bCountryNotEligible" in by_id["SHOW-25"]["source_on_acknowledge"]
    assert "CommandFeedback" in by_id["SHOW-25"]["openpower_route"]


def test_generic_question_controls_and_message_use_caller_supplied_routes():
    root = Path(__file__).resolve().parents[1]
    with (root / "docs/ui/reference/interaction_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        interactions = list(csv.DictReader(source))
    for path, binding in audit.GENERIC_QUESTION_INTERACTION_BINDINGS.items():
        row = next(item for item in interactions if item["component_path"] == path)
        for field, value in binding.items():
            assert row[field] == value

    with (root / "docs/ui/reference/data_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        data = list(csv.DictReader(source))
    message = next(
        row for row in data
        if row["component_path"] == "Generic_Question_Window/lblMessage"
    )
    message_binding = audit.DISPLAY_BINDINGS_BY_WINDOW["Generic_Question_Window"]["lblMessage"]
    assert message["openpower_state_binding"] == message_binding.state_binding
    assert message["openpower_binding_status"] == message_binding.status
    assert "GenericQuestionDialog._question.message" in message["openpower_state_binding"]

    generic_message = next(
        row for row in data
        if row["component_path"] == "Generic_Message_Window/lblMessage"
    )
    assert generic_message["openpower_state_binding"] == "MessageDialogContent.message"
    assert generic_message["openpower_binding_status"] == "verified_openpower"


def test_host_multiplayer_display_contracts_cover_gml_labels_and_local_drafts():
    bindings = audit.DISPLAY_BINDINGS_BY_WINDOW["Host_Multiplayer_Game"]
    assert bindings["frmInner/frmGameSettings/lblPrivate"].status == "verified_openpower"
    assert bindings["frmInner/frmGoals/cboGameSpeed"].status == "partial"
    assert "HostMultiplayerSettingsDraft.game_speed_index" in bindings[
        "frmInner/frmGoals/cboGameSpeed"
    ].state_binding

    root = Path(__file__).resolve().parents[1]
    with (root / "docs/ui/reference/data_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        host_rows = [
            row for row in csv.DictReader(source)
            if row["window_id"] == "Host_Multiplayer_Game"
        ]

    assert host_rows
    assert not any(row["openpower_binding_status"] == "assumption/unknown" for row in host_rows)


def test_covert_outcome_contracts_bind_authoritative_and_audience_scoped_values():
    own = audit.DISPLAY_BINDINGS_BY_WINDOW["Covert_Actions_Mission_Outcome"]
    attacked = audit.DISPLAY_BINDINGS_BY_WINDOW["Covert_Actions_Mission_Outcome_Attacked"]
    assert "audience_country_ids" in own["frmInner/frmMission/txtResult"].state_binding
    assert "presenter-masked" in attacked["txtCountry"].state_binding
    assert "omitted" in attacked["txtOutcome"].fallback

    root = Path(__file__).resolve().parents[1]
    with (root / "docs/ui/reference/data_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        outcome_rows = [
            row for row in csv.DictReader(source)
            if row["window_id"] in {
                "Covert_Actions_Mission_Outcome",
                "Covert_Actions_Mission_Outcome_Attacked",
            }
        ]

    assert outcome_rows
    assert not any(row["openpower_binding_status"] == "assumption/unknown" for row in outcome_rows)


def test_campaign_setup_display_contracts_bind_scenario_and_country_data():
    scenarios = audit.DISPLAY_BINDINGS_BY_WINDOW["Scenarios_Window"]
    setup = audit.DISPLAY_BINDINGS_BY_WINDOW["Start_Single_Player"]

    assert "enabled rows from campaign_scenarios" in scenarios[
        "frmInner/frmCustom/lstCustom"
    ].state_binding
    assert "campaign_scenarios.objectives_json" in scenarios[
        "frmInner/frmScenario/tabInfo/Tab2/frmObjectives/lstGoals"
    ].state_binding
    assert "enabled_rules" in scenarios[
        "frmInner/frmScenario/tabInfo/Tab3/frmInner/txtTips"
    ].state_binding
    assert "scenario-filtered playable countries" in setup[
        "frmInner/frmCountrySelection/cboCountry"
    ].state_binding
    assert "deadline" in setup["frmInner/frmGoals/cboGoal1"].state_binding
    assert "not an editable combo" in setup["frmInner/frmGoals/cboGoal1"].fallback
    assert setup["frmInner/frmGoals/cboGoal1"].status == "partial"

    root = Path(__file__).resolve().parents[1]
    with (root / "docs/ui/reference/data_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        setup_rows = [
            row for row in csv.DictReader(source)
            if row["window_id"] in {"Scenarios_Window", "Start_Single_Player"}
        ]

    assert setup_rows
    assert not any(row["openpower_binding_status"] == "assumption/unknown" for row in setup_rows)


def test_system_bar_callbacks_are_bound_to_verified_routes_or_explicit_gaps():
    bindings = audit.SYSTEM_BAR_INTERACTION_BINDINGS

    assert bindings["System_Bar_Window/btnF2"]["status"] == "verified_unavailable"
    assert bindings["System_Bar_Window/btnF3"]["status"] == "verified_openpower"
    assert bindings["System_Bar_Window/btnF4"]["status"] == "verified_openpower"
    assert bindings["System_Bar_Window/btnF5"]["status"] == "verified_openpower"
    assert bindings["System_Bar_Window/btnF10"]["status"] == "verified_openpower"
    assert "273x223" in bindings["System_Bar_Window/btnF10"]["openpower_effect"]
    assert bindings["System_Bar_Window/togMain"]["status"] == "verified_openpower"
    assert "animates" in bindings["System_Bar_Window/togMain"]["reference_side_effect"]
    assert "0.26 seconds" in bindings["System_Bar_Window/togMain"]["restrictions_confirmation_error"]


def test_legacy_unit_list_sell_has_a_python_group_route_and_keeps_the_source_spawn_gap():
    legacy_path = "Unit_List_Window/frmInner/frmActions/btnSell"
    new_path = "Unit_List_Window_New/frmInner/frmList/btnSell"
    legacy_binding = audit.UNIT_LIST_INTERACTION_BINDINGS[legacy_path]
    new_binding = audit.UNIT_LIST_INTERACTION_BINDINGS[new_path]

    assert legacy_binding["status"] == "partial"
    assert "ActionListUsedUnit" in legacy_binding["game_action"]
    assert "ActionWithdrawUsedUnitListing" in legacy_binding["game_action"]
    assert "UnitReorganizationWindows._legacy_list" in legacy_binding["openpower_surface"]
    assert "no registered C++ spawn call site" in legacy_binding["restrictions_confirmation_error"]
    assert new_binding["game_action"].startswith("ActionListUsedUnit(")

    root = Path(__file__).resolve().parents[1]
    group_window = (root / "src/client/ui/panels/military/unit_reorganization_windows.py").read_text(encoding="utf-8")
    assert 'root = "Unit_List_Window"' in group_window
    assert '"unit.group.sell"' in group_window
    assert '"unit.group.merge"' in group_window
    assert "ActionMergeUnits(" in group_window
    with (root / "docs/ui/reference/interaction_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        contracts = list(csv.DictReader(source))
    assert all(None not in row for row in contracts)
    legacy_contracts = [row for row in contracts if row["component_path"] == legacy_path]
    new_contracts = [row for row in contracts if row["component_path"] == new_path]
    assert legacy_contracts
    for contract in legacy_contracts:
        for field, value in legacy_binding.items():
            assert contract[field] == value
    assert new_contracts
    assert all(row["game_action"] == new_binding["game_action"] for row in new_contracts)

    with (root / "docs/ui/reference/gap_table.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        gaps = [
            row for row in csv.DictReader(source)
            if row["gml_node_or_behavior"] == legacy_path
        ]
    assert gaps
    assert all(row["status"] == "partial" for row in gaps)
    assert all("ActionListUsedUnit" in row["openpower_current_implementation"] for row in gaps)

    with (root / "docs/ui/reference/window_registry.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        windows = {row["window_id"]: row for row in csv.DictReader(source)}
    assert windows["Unit_List_Window"]["status"] == "unknown"
    assert windows["Unit_List_Window"]["window_spawn_call_count"] == "0"
    assert audit.LAYOUT_SURFACES["Unit_List_Window"] == ("GameLayout/UnitReorganizationWindows", "partial")
    assert windows["Unit_List_Window_New"]["status"] == "reachable"

    journey = json.loads(
        (root / "tests/ui/journeys/reference-unit-group-list.json").read_text(encoding="utf-8")
    )
    assert any(
        step.get("op") == "assert_action" and step.get("type") == "ActionListUsedUnit"
        for step in journey["steps"]
    )
    assert any(
        step.get("op") == "assert_action" and step.get("type") == "ActionMergeUnits"
        for step in journey["steps"]
    )


def test_legacy_unit_group_controls_match_the_python_route_and_source_boundary():
    bindings = {
        path: binding for path, binding in audit.UNIT_LIST_INTERACTION_BINDINGS.items()
        if path.startswith("Unit_List_Window/")
    }
    assert len(bindings) == 6
    assert bindings["Unit_List_Window/frmTitle/btnExit"]["status"] == "verified_openpower"
    assert bindings["Unit_List_Window/frmTitle/btnApply"]["status"] == "verified_unavailable"
    assert bindings["Unit_List_Window/frmInner/frmActions/btnMerge"]["status"] == "partial"
    for fragment in ("btnFill", "btnUnfilled"):
        path = f"Unit_List_Window/frmInner/frmInformationAccuracy/frmAccuracy/{fragment}"
        assert bindings[path]["status"] == "partial"
        assert bindings[path]["read_only_or_state_changing"] == "read-only intelligence-confidence presentation"

    root = Path(__file__).resolve().parents[1]
    source = resolve_reference_file(root, ".codex/Client/Source/reference_unit_list_window.cpp").read_text(encoding="utf-8")
    click_start = source.index("GUnitListWindow::OnMouseClick")
    click_end = source.index("GUnitListWindow::OnMouseWheel", click_start)
    assert "m_pObjMergeBtn" not in source[click_start:click_end]
    assert "m_pObjAccuracy->Value(l_fAccuracy" in source
    assert "m_pObjAccuracyOfInformationFrm->Hide()" in source
    assert "GameAction" in bindings[
        "Unit_List_Window/frmInner/frmInformationAccuracy/frmAccuracy/btnFill"
    ]["validation_condition"]

    with (root / "docs/ui/reference/interaction_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source_file:
        contracts = list(csv.DictReader(source_file))
    for path, binding in bindings.items():
        row = next(row for row in contracts if row["component_path"] == path)
        for field, value in binding.items():
            assert row[field] == value

    with (root / "docs/ui/reference/gap_table.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source_file:
        gaps = list(csv.DictReader(source_file))
    for path, binding in bindings.items():
        gap_rows = _interaction_gap_rows(gaps, path, binding)
        assert gap_rows
        assert all(row["status"] == binding["status"] for row in gap_rows)


def test_single_player_start_maps_fixed_scenario_setup_and_keeps_source_goal_gap_explicit():
    path = "Start_Single_Player/frmInner/btnStart"
    binding = audit.START_SINGLE_PLAYER_INTERACTION_BINDINGS[path]

    assert binding["game_action"] == "ActionStartCampaign(player_id, scenario_id, country_tag, player_party_id)"
    assert binding["status"] == "partial"
    assert "fixed objectives" in binding["restrictions_confirmation_error"]
    assert "m_vGameObjectives" in binding["restrictions_confirmation_error"]
    assert "advisor CPU-toggle values" in binding["restrictions_confirmation_error"]

    root = Path(__file__).resolve().parents[1]
    with (root / "docs/ui/reference/interaction_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        contracts = [row for row in csv.DictReader(source) if row["component_path"] == path]
    assert contracts
    for contract in contracts:
        for field, value in binding.items():
            assert contract[field] == value

    with (root / "docs/ui/reference/gap_table.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        gaps = list(csv.DictReader(source))
    interaction_gaps = _interaction_gap_rows(gaps, path, binding)
    assert interaction_gaps
    assert all(row["status"] == binding["status"] for row in interaction_gaps)
    assert all("ActionStartCampaign" in row["openpower_current_implementation"] for row in interaction_gaps)

    new_game_task = (root / "src/client/tasks/new_game_task.py").read_text(encoding="utf-8")
    task_test = (root / "tests/test_new_game_task.py").read_text(encoding="utf-8")
    assert "ActionStartCampaign(" in new_game_task
    assert "test_new_game_start_action_includes_selected_party" in task_test

    with (root / "docs/ui/reference/interaction_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        all_contracts = list(csv.DictReader(source))
    setup_contracts = [row for row in all_contracts if row["window_id"] == "Start_Single_Player"]
    assert all(row["status"] != "assumption/unknown" for row in setup_contracts)
    for component_path, setup_binding in audit.START_SINGLE_PLAYER_INTERACTION_BINDINGS.items():
        rows = [row for row in setup_contracts if row["component_path"] == component_path]
        assert rows
        for row in rows:
            for field, value in setup_binding.items():
                assert row[field] == value

    with (root / "docs/ui/reference/gap_table.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        setup_gaps = [
            row for row in csv.DictReader(source)
            if row["gml_node_or_behavior"].startswith("Start_Single_Player/")
        ]
    for component_path, setup_binding in audit.START_SINGLE_PLAYER_INTERACTION_BINDINGS.items():
        rows = _interaction_gap_rows(setup_gaps, component_path, setup_binding)
        assert rows
        assert all(row["status"] == setup_binding["status"] for row in rows)


def test_unavailable_multiplayer_events_and_strategic_research_buttons_are_not_mapped_to_unrelated_actions():
    multiplayer_paths = {
        "Game_Lobby/frmInner/frmAdministrator/togReady",
        "Game_Lobby/frmInner/frmAdministrator/edtPlayerName",
        "Game_Lobby/frmInner/btnKickPlayer",
        "Game_Lobby/frmInner/btnBanPlayer",
        "Game_Lobby/frmInner/btnStartGame",
    }
    for path in multiplayer_paths:
        binding = audit.MULTIPLAYER_LOBBY_UNAVAILABLE_INTERACTION_BINDINGS[path]
        assert binding["status"] == "verified_unavailable"
        assert binding["game_action"] == "none (unavailable multiplayer lobby workflow)"

    strategic = audit.MILITARY_STRATEGIC_RESEARCH_INTERACTION_BINDINGS
    amds = strategic["Military_Window/frmInner/frmStrategicWeapons/btnResearch"]
    nuclear = strategic["Military_Window/frmInner/frmStrategicWeapons/btnNuclearProgram"]
    assert amds["status"] == "partial"
    assert amds["game_action"].startswith("none on click")
    assert "not a direct event mapping" in amds["restrictions_confirmation_error"]
    assert nuclear["status"] == "verified_unavailable"
    assert nuclear["game_action"].startswith("none (")

    root = Path(__file__).resolve().parents[1]
    with (root / "docs/ui/reference/interaction_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        contracts = list(csv.DictReader(source))
    for path, binding in {
        **audit.MULTIPLAYER_LOBBY_UNAVAILABLE_INTERACTION_BINDINGS,
        **strategic,
    }.items():
        rows = [row for row in contracts if row["component_path"] == path]
        assert rows
        for row in rows:
            for field, value in binding.items():
                assert row[field] == value
    assert not [
        row for row in contracts
        if row["reference_game_event"] and row["game_action"].startswith("unknown;")
    ]

    with (root / "docs/ui/reference/gap_table.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        gaps = list(csv.DictReader(source))
    assert all(None not in row for row in gaps)
    for path, binding in {
        **audit.MULTIPLAYER_LOBBY_UNAVAILABLE_INTERACTION_BINDINGS,
        **strategic,
    }.items():
        rows = _interaction_gap_rows(gaps, path, binding)
        assert rows
        assert all(row["status"] == binding["status"] for row in rows)


def test_host_draft_controls_and_lobby_controls_keep_their_distinct_availability():
    bindings = {
        **audit.MULTIPLAYER_WORKFLOW_UNAVAILABLE_INTERACTION_BINDINGS,
        **audit.MULTIPLAYER_LOBBY_UNAVAILABLE_INTERACTION_BINDINGS,
    }
    root = Path(__file__).resolve().parents[1]
    with (root / "docs/ui/reference/interaction_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        contracts = list(csv.DictReader(source))

    for window_id in ("Host_Multiplayer_Game", "Game_Lobby"):
        window_rows = [row for row in contracts if row["window_id"] == window_id]
        non_lock_paths = {
            row["component_path"] for row in window_rows
            if not row["component_path"].endswith("/togLockWindow")
        }
        mapped_paths = {path for path in bindings if path.startswith(f"{window_id}/")}
        assert non_lock_paths == mapped_paths
        if window_id == "Game_Lobby":
            assert all(row["status"] == "verified_unavailable" for row in window_rows
                       if not row["component_path"].endswith("/togLockWindow"))

    for path, binding in bindings.items():
        rows = [row for row in contracts if row["component_path"] == path]
        assert rows
        for row in rows:
            for field, value in binding.items():
                assert row[field] == value

    host_start = bindings["Host_Multiplayer_Game/frmInner/btnStart"]
    assert "StartHostServerGame" in host_start["reference_side_effect"]
    assert host_start["game_action"] == "none (unavailable multiplayer host workflow)"
    assert host_start["status"] == "verified_unavailable"
    host_draft = bindings["Host_Multiplayer_Game/frmInner/frmGameSettings/edtPort"]
    assert host_draft["status"] == "partial"
    assert "local draft" in host_draft["openpower_effect"]
    host_cancel = bindings["Host_Multiplayer_Game/frmInner/btnCancel"]
    assert host_cancel["status"] == "verified_openpower"
    assert "server browser" in host_cancel["openpower_effect"]
    host_objective = bindings["Host_Multiplayer_Game/frmInner/frmGoals/frmTog1/togGoal"]
    assert "m_vGameObjectives" in host_objective["reference_side_effect"]
    assert host_objective["status"] == "partial"
    lobby_chat = bindings["Game_Lobby/frmInner/btnSend"]
    assert "sends the current chat text" in lobby_chat["reference_side_effect"]

    with (root / "docs/ui/reference/gap_table.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        gaps = list(csv.DictReader(source))
    assert all(None not in row for row in gaps)
    for path, binding in bindings.items():
        rows = _interaction_gap_rows(gaps, path, binding)
        assert rows
        assert all(row["status"] == binding["status"] for row in rows)


def test_host_multiplayer_screen_has_a_scenario_bound_source_sized_return_route():
    root = Path(__file__).resolve().parents[1]
    assert audit.LAYOUT_SURFACES["Host_Multiplayer_Game"] == (
        "MainMenuContent/HostMultiplayerGameWindow settings draft", "partial"
    )
    with (root / "docs/ui/reference/navigation_journey_coverage.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        routes = list(csv.DictReader(source))
    route = next(
        row for row in routes
        if row["source_widget_path"] == "Join_Multiplayer_Game/frmInner/btnHostInJoinMenu"
        and row["target_window"] == "Host_Multiplayer_Game"
    )
    assert route["journey_file"] == "tests/ui/journeys/reference-host-window-navigation.json"
    assert route["journey_control_id"] == "multiplayer.join.host"
    assert route["coverage_status"] == "tested"
    assert route["journey_suite_status"] == "passed"

    with (root / "docs/ui/reference/window_registry.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        registry = list(csv.DictReader(source))
    host_window = next(row for row in registry if row["window_id"] == "Host_Multiplayer_Game")
    assert host_window["status"] == "reachable"
    assert host_window["mapping_status"] == "partial"

    journey = json.loads(
        (root / "tests/ui/journeys/reference-host-window-navigation.json").read_text(encoding="utf-8")
    )
    steps = journey["steps"]
    assert any(step.get("op") == "click" and step.get("target") == "multiplayer.join.host"
               for step in steps)
    assert any(step.get("op") == "click" and step.get("target") == "multiplayer.host.cancel"
               for step in steps)
    assert any(step.get("op") == "assert_region" and step.get("target") == "multiplayer.host.window"
               and step.get("rect") == {"width": 341, "height": 342} for step in steps)
    assert any(step.get("op") == "assert" and step.get("target") == "multiplayer.host.start"
               and step.get("enabled") is False for step in steps)


def test_scenario_selection_controls_distinguish_openpower_setup_from_reference_presets():
    bindings = audit.SCENARIO_SELECTION_INTERACTION_BINDINGS
    root = Path(__file__).resolve().parents[1]
    with (root / "docs/ui/reference/interaction_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        contracts = list(csv.DictReader(source))
    scenario_rows = [row for row in contracts if row["window_id"] == "Scenarios_Window"]
    non_lock_paths = {
        row["component_path"] for row in scenario_rows
        if not row["component_path"].endswith("/togLockWindow")
    }
    assert non_lock_paths == set(bindings)
    for path, binding in bindings.items():
        rows = [row for row in scenario_rows if row["component_path"] == path]
        assert rows
        for row in rows:
            for field, value in binding.items():
                assert row[field] == value

    difficulty_bindings = {
        path: binding for path, binding in bindings.items()
        if "/frmGolem/tog" in path
    }
    assert len(difficulty_bindings) == 9
    assert all(binding["status"] == "verified_unavailable" for binding in difficulty_bindings.values())
    for path, binding in difficulty_bindings.items():
        assert binding["game_action"] == "none (unavailable REFERENCE sphere-difficulty preset)"
        assert "/frmGolem/" in path

    start = bindings["Scenarios_Window/frmInner/btnStart"]
    assert start["status"] == "partial"
    assert "country and party setup" in start["openpower_effect"]
    assert "ActionStartCampaign" in start["openpower_effect"]
    objective_list = bindings[
        "Scenarios_Window/frmInner/frmScenario/tabInfo/Tab2/frmObjectives/lstGoals"
    ]
    assert objective_list["status"] == "partial"
    assert "completion-state toggles" in objective_list["openpower_effect"]

    with (root / "docs/ui/reference/gap_table.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        gaps = list(csv.DictReader(source))
    assert all(None not in row for row in gaps)
    for path, binding in bindings.items():
        rows = _interaction_gap_rows(gaps, path, binding)
        assert rows
        assert all(row["status"] == binding["status"] for row in rows)


def test_battle_inspection_controls_document_partial_openpower_strategy_and_display_matches():
    bindings = audit.BATTLE_INSPECTION_INTERACTION_BINDINGS
    assert len(bindings) == 9
    root = Path(__file__).resolve().parents[1]
    with (root / "docs/ui/reference/interaction_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        contracts = list(csv.DictReader(source))
    for path, binding in bindings.items():
        rows = [row for row in contracts if row["component_path"] == path]
        assert rows
        assert all(row["status"] == "partial" for row in rows)
        for row in rows:
            for field, value in binding.items():
                assert row[field] == value

    for path in (
        "Battle_Window/lstFlagsYou",
        "Battle_Window/lstFlagsEnemy",
        "Battle_Window/frmBattle/cboStrategies",
        "Battle_Window/frmBattle/btnRetreat",
    ):
        if "lstFlags" in path:
            assert bindings[path]["game_action"].startswith("none")
        else:
            assert "ActionSetBattleStrategy" in bindings[path]["game_action"]

    separator = bindings["Battle_Window/frmOverviewMeter/btnSeparator1"]
    assert "draws a marker" in separator["openpower_effect"]
    retreat = bindings["Battle_Window/frmBattle/btnRetreat"]
    assert "valid safe-capital route" in retreat["validation_condition"]

    journey = json.loads(
        (root / "tests/ui/journeys/reference-battle-inspection-own.json").read_text(encoding="utf-8")
    )
    assert any(step.get("op") == "assert_action" and step.get("type") == "ActionSetBattleStrategy"
               for step in journey["steps"])
    source_text = resolve_reference_file(root, ".codex/Client/Source/reference_battle_overview_window.cpp").read_text(encoding="utf-8")
    assert "GBattleOverviewUnitActionUpdate" in source_text
    assert "m_bRetreat" in source_text

    with (root / "docs/ui/reference/gap_table.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        gaps = list(csv.DictReader(source))
    assert all(None not in row for row in gaps)
    for path, binding in bindings.items():
        rows = _interaction_gap_rows(gaps, path, binding)
        assert rows
        assert all(row["status"] == binding["status"] for row in rows)


def test_strategic_target_controls_preserve_openpower_region_and_weapon_semantics():
    bindings = audit.STRATEGIC_TARGET_SELECTION_INTERACTION_BINDINGS
    assert len(bindings) == 9
    root = Path(__file__).resolve().parents[1]
    with (root / "docs/ui/reference/interaction_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        contracts = list(csv.DictReader(source))
    target_rows = [row for row in contracts if row["window_id"] == "Strategic_Target_Country_Window"]
    unknown_paths = {
        row["component_path"] for row in target_rows if row["status"] == "assumption/unknown"
    }
    assert not unknown_paths
    for path, binding in bindings.items():
        rows = [row for row in target_rows if row["component_path"] == path]
        assert rows
        for row in rows:
            for field, value in binding.items():
                assert row[field] == value

    unavailable = {
        path for path, binding in bindings.items()
        if binding["status"] == "verified_unavailable"
    }
    assert unavailable == {
        "Strategic_Target_Country_Window/frmAttackStrength/btnArrowDecrease1",
        "Strategic_Target_Country_Window/frmAttackStrength/btnArrowIncrease1",
        "Strategic_Target_Country_Window/frmAttackStrength/frmAttackStrengthValue/btnFill",
        "Strategic_Target_Country_Window/frmAttackStrength/frmAttackStrengthValue/btnUnfilled",
    }
    assert "no quantity field" in bindings[
        "Strategic_Target_Country_Window/frmAttackStrength/btnArrowIncrease1"
    ]["openpower_effect"]
    assert "ActionLaunchStrategicStrike" in bindings[
        "Strategic_Target_Country_Window/frmAttackType/cboAttackType"
    ]["game_action"]

    source_text = resolve_reference_file(root, ".codex/Client/Source/reference_strategic_target_country_window.cpp").read_text(encoding="utf-8")
    assert "m_iNbMissileUsed++" in source_text
    assert "SelectNuclearTargetsAndAssignMissiles" in source_text
    plan_text = (root / "src/client/ui/panels/military/strategic_plan.py").read_text(encoding="utf-8")
    assert "ActionLaunchStrategicStrike(" in plan_text
    journey = json.loads(
        (root / "tests/ui/journeys/reference-strategic-planner.json").read_text(encoding="utf-8")
    )
    assert any(step.get("op") == "assert_action" and step.get("type") == "ActionLaunchStrategicStrike"
               for step in journey["steps"])

    with (root / "docs/ui/reference/gap_table.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        gaps = list(csv.DictReader(source))
    assert all(None not in row for row in gaps)
    for path, binding in bindings.items():
        rows = _interaction_gap_rows(gaps, path, binding)
        assert rows
        assert all(row["status"] == binding["status"] for row in rows)


def test_strategic_warfare_controls_have_explicit_source_and_openpower_dispositions():
    bindings = audit.STRATEGIC_WARFARE_INTERACTION_BINDINGS
    expected_paths = {
        "Strategic_Warfare/frmTitle/btnExit",
        "Strategic_Warfare/frmTitle/btnApply",
        "Strategic_Warfare/frmInner/frmButton/btnLaunch",
        "Strategic_Warfare/frmInner/frmAttackType/cboAttackType",
        "Strategic_Warfare/frmInner/frmAttackStrength/frmAttackStrengthValue/btnFill",
        "Strategic_Warfare/frmInner/frmAttackStrength/frmAttackStrengthValue/btnUnfilled",
        "Strategic_Warfare/frmInner/frmCountry/cboCountry",
    }
    assert set(bindings) == expected_paths
    root = Path(__file__).resolve().parents[1]
    with (root / "docs/ui/reference/interaction_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        contracts = list(csv.DictReader(source))
    rows = [row for row in contracts if row["window_id"] == "Strategic_Warfare"]
    by_path = {row["component_path"]: row for row in rows}
    assert set(by_path) == expected_paths | {"Strategic_Warfare/frmTitle/togLockWindow"}
    for path, binding in bindings.items():
        for field, value in binding.items():
            assert by_path[path][field] == value
        assert by_path[path]["status"] != "assumption/unknown"

    assert bindings["Strategic_Warfare/frmTitle/btnExit"]["status"] == "verified_openpower"
    assert bindings["Strategic_Warfare/frmTitle/btnApply"]["status"] == "verified_unavailable"
    assert bindings["Strategic_Warfare/frmInner/frmButton/btnLaunch"]["status"] == "partial"
    assert bindings["Strategic_Warfare/frmInner/frmCountry/cboCountry"]["status"] == "partial"
    for path in (
        "Strategic_Warfare/frmInner/frmAttackStrength/frmAttackStrengthValue/btnFill",
        "Strategic_Warfare/frmInner/frmAttackStrength/frmAttackStrengthValue/btnUnfilled",
    ):
        assert bindings[path]["status"] == "verified_unavailable"
        assert "do not conflate" in bindings[path]["action_required"]

    source_text = resolve_reference_file(root, ".codex/Client/Source/reference_strategic_warfare.cpp").read_text(encoding="utf-8")
    base_window_text = resolve_reference_file(root, ".codex/Client/Source/reference_base_window.cpp").read_text(encoding="utf-8")
    strategic_header = resolve_reference_file(root, ".codex/Client/Include/reference_strategic_warfare.h").read_text(encoding="utf-8")
    base_window_header = resolve_reference_file(root, ".codex/Client/Include/reference_base_window.h").read_text(encoding="utf-8")
    assert "StrategicWarfareWindow()->Hide()" in source_text
    launch_event = source_text.index("GStrategicWarfareLaunch")
    assert source_text.rfind("/*", 0, launch_event) > source_text.rfind("*/", 0, launch_event)
    assert "m_bDirty                   = false;" in base_window_text
    assert "Save(" not in strategic_header
    assert "virtual void Save(){return;};" in base_window_header

    close_journey = json.loads((root / "tests/ui/journeys/reference-strategic-close.json").read_text(encoding="utf-8"))
    assert any(step.get("op") == "close_window" and step.get("target") == "strategic_warfare.panel"
               for step in close_journey["steps"])
    launch_journey = json.loads(
        (root / "tests/ui/journeys/reference-strategic-planner.json").read_text(encoding="utf-8")
    )
    assert any(
        step.get("op") == "assert_action"
        and step.get("type") == "ActionLaunchStrategicStrike"
        and step.get("fields", {}).get("payload_level") == 2
        for step in launch_journey["steps"]
    )

    with (root / "docs/ui/reference/gap_table.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        gaps = list(csv.DictReader(source))
    for path, binding in bindings.items():
        gap_rows = _interaction_gap_rows(gaps, path, binding)
        assert gap_rows
        assert all(row["status"] == binding["status"] for row in gap_rows)


def test_military_panel_routes_and_progress_meters_have_explicit_openpower_dispositions():
    bindings = {
        **audit.MILITARY_TITLE_INTERACTION_BINDINGS,
        **audit.MILITARY_NAVIGATION_INTERACTION_BINDINGS,
        **audit.MILITARY_PROGRESS_METER_INTERACTION_BINDINGS,
        **audit.MILITARY_STRATEGIC_RESEARCH_INTERACTION_BINDINGS,
    }
    root = Path(__file__).resolve().parents[1]
    with (root / "docs/ui/reference/interaction_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        contracts = list(csv.DictReader(source))
    military = [row for row in contracts if row["window_id"] == "Military_Window"]
    military_paths = {row["component_path"] for row in military}
    assert military_paths == set(bindings) | {
        "Military_Window/frmTitle/togLockWindow"
    }
    for path, binding in bindings.items():
        rows = [row for row in military if row["component_path"] == path]
        assert rows
        for row in rows:
            for field, value in binding.items():
                assert row[field] == value

    lock_rows = [
        row for row in military
        if row["component_path"] == "Military_Window/frmTitle/togLockWindow"
    ]
    assert all(row["status"] == "verified_openpower" for row in lock_rows)

    with (root / "docs/ui/reference/gap_table.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        gaps = list(csv.DictReader(source))
    for path, binding in bindings.items():
        rows = _interaction_gap_rows(gaps, path, binding)
        assert rows
        assert all(row["status"] == binding["status"] for row in rows)
        assert all(
            row["openpower_current_implementation"]
            == f"{binding['openpower_surface']}: {binding['openpower_effect']}"
            for row in rows
        )

    for binding in audit.MILITARY_NAVIGATION_INTERACTION_BINDINGS.values():
        journey = binding["restrictions_confirmation_error"].split("covered by ", 1)[1].rstrip(".")
        assert (root / journey).is_file()
    assert all(
        binding["status"] == "partial"
        and binding["game_action"] == "none (read-only progress meter component)"
        for binding in audit.MILITARY_PROGRESS_METER_INTERACTION_BINDINGS.values()
    )


def test_military_display_bindings_expose_source_and_openpower_metric_differences():
    bindings = audit.DISPLAY_BINDINGS_BY_WINDOW["Military_Window"]
    root = Path(__file__).resolve().parents[1]
    with (root / "docs/ui/reference/data_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        data_contracts = list(csv.DictReader(source))
    military = [row for row in data_contracts if row["window_id"] == "Military_Window"]
    assert {row["component_path"].removeprefix("Military_Window/") for row in military} == set(bindings)
    for path, binding in bindings.items():
        row = next(row for row in military if row["component_path"] == f"Military_Window/{path}")
        assert row["openpower_state_binding"] == binding.state_binding
        assert row["openpower_binding_status"] == binding.status
        assert row["units"] == binding.units
        assert row["fallback"] == binding.fallback
        assert row["update_rule"] == binding.update_rule
        assert row["action_required"] == binding.action_required
        assert binding.status == "partial"

    assert "cross-country TotalUnitsValue rank" in bindings[
        "frmInner/frmConventionalWarfare/lblLandRank"
    ].meaning
    assert "unit rows" in bindings[
        "frmInner/frmConventionalWarfare/lblLandRank"
    ].meaning
    assert "not the source NuclearReady research percentage" in bindings[
        "frmInner/frmStrategicWeapons/frmNuclearProgress"
    ].meaning
    assert "operational coverage estimate" in bindings[
        "frmInner/frmStrategicWeapons/txtMissileDefenseStatus"
    ].meaning


def test_unit_reserves_display_and_interaction_contracts_match_verified_python_routes():
    root = Path(__file__).resolve().parents[1]
    display_bindings = audit.DISPLAY_BINDINGS_BY_WINDOW["Unit_Ground_Deployment_Window"]
    interaction_bindings = audit.UNIT_RESERVES_INTERACTION_BINDINGS
    with (root / "docs/ui/reference/data_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        data_contracts = list(csv.DictReader(source))
    with (root / "docs/ui/reference/interaction_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        interaction_contracts = list(csv.DictReader(source))
    with (root / "docs/ui/reference/gap_table.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        gaps = list(csv.DictReader(source))

    window_data = [
        row for row in data_contracts
        if row["window_id"] == "Unit_Ground_Deployment_Window"
    ]
    assert {row["component_path"].removeprefix("Unit_Ground_Deployment_Window/") for row in window_data} == set(display_bindings)
    assert len(window_data) == 10
    for suffix, binding in display_bindings.items():
        row = next(
            row for row in window_data
            if row["component_path"] == f"Unit_Ground_Deployment_Window/{suffix}"
        )
        assert row["openpower_state_binding"] == binding.state_binding
        assert row["openpower_binding_status"] == binding.status
        assert row["units"] == binding.units
        assert row["fallback"] == binding.fallback
        assert row["update_rule"] == binding.update_rule
        assert row["action_required"] == binding.action_required
        assert binding.status == "partial"
        matching_gaps = [gap for gap in gaps if gap["gml_node_or_behavior"] == row["component_path"]]
        assert matching_gaps
        assert all(gap["status"] == binding.status for gap in matching_gaps)

    window_interactions = [
        row for row in interaction_contracts
        if row["window_id"] == "Unit_Ground_Deployment_Window"
    ]
    assert {row["component_path"] for row in window_interactions} == (
        set(interaction_bindings)
        | {"Unit_Ground_Deployment_Window/frmTitle/togLockWindow"}
    )
    for path, binding in interaction_bindings.items():
        row = next(row for row in window_interactions if row["component_path"] == path)
        for field, value in binding.items():
            assert row[field] == value
        matching_gaps = _interaction_gap_rows(gaps, path, binding)
        assert matching_gaps
        assert all(gap["status"] == binding["status"] for gap in matching_gaps)

    dynamic_tabs = next(
        row for row in window_interactions
        if row["component_path"].endswith("/@tabButtons")
    )
    assert dynamic_tabs["input"] == "runtime-generated GTabbed category buttons"
    assert dynamic_tabs["cpp_member_binding"] == "m_objTabGroup.m_vTabButtons[0..3]"
    assert "OnMouseClick" in dynamic_tabs["reference_callback"]
    source = resolve_reference_file(root, ".codex/Client/Source/reference_unit_ground_deployment_window.cpp").read_text(encoding="utf-8")
    assert "m_objTabGroup->m_vTabButtons[3]->Enabled(g_ClientDAL.GameOptions().NuclearAllowed())" in source
    assert "no equivalent of the source NuclearAllowed option" in audit.PARTIALLY_IMPLEMENTED_WINDOW_GAPS[
        "Unit_Ground_Deployment_Window"
    ]["missing_action"]


def test_main_bar_country_status_time_and_openpower_speed_contracts_match_python_routes():
    root = Path(__file__).resolve().parents[1]
    display_bindings = audit.DISPLAY_BINDINGS_BY_WINDOW["Main_Bar"]
    interaction_bindings = audit.MAIN_BAR_INTERACTION_BINDINGS
    with (root / "docs/ui/reference/data_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        data_contracts = list(csv.DictReader(source))
    with (root / "docs/ui/reference/interaction_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        interaction_contracts = list(csv.DictReader(source))
    with (root / "docs/ui/reference/gap_table.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        gaps = list(csv.DictReader(source))

    window_data = [row for row in data_contracts if row["window_id"] == "Main_Bar"]
    assert {row["component_path"].removeprefix("Main_Bar/") for row in window_data} == set(display_bindings)
    for suffix, binding in display_bindings.items():
        row = next(row for row in window_data if row["component_path"] == f"Main_Bar/{suffix}")
        assert row["openpower_state_binding"] == binding.state_binding
        assert row["openpower_binding_status"] == binding.status
        assert row["action_required"] == binding.action_required
        assert any(gap["gml_node_or_behavior"] == row["component_path"] for gap in gaps)

    window_interactions = [row for row in interaction_contracts if row["window_id"] == "Main_Bar"]
    interaction_paths = {row["component_path"] for row in window_interactions}
    assert set(interaction_bindings).issubset(interaction_paths)
    assert "Main_Bar/frmTimeSelection/@openpowerSpeed5" in interaction_paths
    for path, binding in interaction_bindings.items():
        row = next(row for row in window_interactions if row["component_path"] == path)
        for field, value in binding.items():
            assert row[field] == value
        matching_gaps = _interaction_gap_rows(gaps, path, binding)
        assert matching_gaps
        assert all(gap["status"] == binding["status"] for gap in matching_gaps)

    extra_speed = next(
        row for row in window_interactions
        if row["component_path"] == "Main_Bar/frmTimeSelection/@openpowerSpeed5"
    )
    assert extra_speed["status"] == "partial"
    assert "no source gml" in extra_speed["reference_side_effect"].casefold()
    assert "unused right-edge gutter" in extra_speed["openpower_effect"]


def test_unit_split_quantity_controls_match_source_callbacks_and_python_routes():
    root = Path(__file__).resolve().parents[1]
    bindings = audit.UNIT_SPLIT_INTERACTION_BINDINGS
    with (root / "docs/ui/reference/interaction_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        contracts = list(csv.DictReader(source))
    with (root / "docs/ui/reference/gap_table.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        gaps = list(csv.DictReader(source))

    window_contracts = [row for row in contracts if row["window_id"] == "Unit_Split_Window"]
    assert {row["component_path"] for row in window_contracts} == set(bindings)
    for path, binding in bindings.items():
        row = next(row for row in window_contracts if row["component_path"] == path)
        for field, value in binding.items():
            assert row[field] == value
        matching_gaps = _interaction_gap_rows(gaps, path, binding)
        assert matching_gaps
        assert all(gap["status"] == binding["status"] for gap in matching_gaps)

    source = resolve_reference_file(root, ".codex/Client/Source/reference_unit_split_window.cpp").read_text(encoding="utf-8")
    assert "m_iQuantityInGroupB + 1" in source
    assert "m_iQuantityInGroupB - 1" in source
    assert "c_OnMeterChangeEvent" in source
    journey = json.loads((root / "tests/ui/journeys/reference-unit-split.json").read_text(encoding="utf-8"))
    ratio_values = {
        step["fraction"] for step in journey["steps"]
        if step.get("op") == "drag" and step.get("target") == "unit.split.quantity.ratio"
    }
    assert {0.3, 1.0}.issubset(ratio_values)
    assert any(step.get("op") == "assert_action" and step.get("fields", {}).get("detached_strength") == 200 for step in journey["steps"])


def test_budget_and_resource_title_actions_are_traced_to_python_routes():
    root = Path(__file__).resolve().parents[1]
    bindings = audit.BUDGET_RESOURCES_TITLE_INTERACTION_BINDINGS
    with (root / "docs/ui/reference/interaction_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        contracts = list(csv.DictReader(source))
    with (root / "docs/ui/reference/gap_table.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        gaps = list(csv.DictReader(source))

    for path, binding in bindings.items():
        window = path.split("/", 1)[0]
        row = next(
            row for row in contracts
            if row["window_id"] == window and row["component_path"] == path
        )
        for field, value in binding.items():
            assert row[field] == value
        matching_gaps = _interaction_gap_rows(gaps, path, binding)
        assert matching_gaps
        assert all(gap["status"] == binding["status"] for gap in matching_gaps)

    budget_source = resolve_reference_file(root, ".codex/Client/Source/reference_budget_window.cpp").read_text(encoding="utf-8")
    resource_source = resolve_reference_file(root, ".codex/Client/Source/reference_resources_window.cpp").read_text(encoding="utf-8")
    base_source = resolve_reference_file(root, ".codex/Client/Source/reference_base_window.cpp").read_text(encoding="utf-8")
    assert "GBudgetUpdate" in budget_source and "GResourcesUpdate" in resource_source
    assert "ExitWindow();" in base_source and "Apply();" in base_source

    route_files = (
        "tests/ui/journeys/budget.json",
        "tests/ui/journeys/reference-budget-close-apply.json",
        "tests/ui/journeys/reference-resources-close-apply.json",
        "tests/ui/journeys/reference-resources-close-discard.json",
    )
    assert all((root / path).is_file() for path in route_files)


def test_increase_production_apply_and_value_rows_are_registered():
    root = Path(__file__).resolve().parents[1]
    template = "Increase_Production_Window"
    assert audit.PANEL_ALIASES[template] == ("RESOURCES", "partial")
    display_bindings = audit.DISPLAY_BINDINGS_BY_WINDOW[template]
    with (root / "docs/ui/reference/data_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        data_rows = [
            row for row in csv.DictReader(source)
            if row["window_id"] == template
        ]

    for suffix, binding in display_bindings.items():
        row = next(item for item in data_rows if item["component_path"] == f"{template}/{suffix}")
        assert row["openpower_panel_spec"] == "RESOURCES"
        assert binding.surface in row["openpower_surface"]
        assert row["openpower_state_binding"] == binding.state_binding
        assert row["openpower_binding_status"] == binding.status

    with (root / "docs/ui/reference/window_registry.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        window = next(row for row in csv.DictReader(source) if row["window_id"] == template)
    assert window["openpower_panel_spec"] == "RESOURCES"

    path = "Increase_Production_Window/frmTitle/btnApply"
    binding = audit.INCREASE_PRODUCTION_INTERACTION_BINDINGS[path]
    with (root / "docs/ui/reference/interaction_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        row = next(
            item for item in csv.DictReader(source)
            if item["window_id"] == template and item["component_path"] == path
        )
    for field, value in binding.items():
        assert row[field] == value

    with (root / "docs/ui/reference/gap_table.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        gaps = list(csv.DictReader(source))
    matching_gaps = _interaction_gap_rows(gaps, path, binding)
    assert matching_gaps and all(item["status"] == "verified_openpower" for item in matching_gaps)

    journey = json.loads(
        (root / "tests/ui/journeys/reference-resource-production-dialog.json").read_text(encoding="utf-8")
    )
    steps = journey["steps"]
    selected_percentages = [
        step["target"] for step in steps
        if step.get("op") == "click"
        and step.get("target") in {
            "resources.increase_production.percent.2",
            "resources.increase_production.percent.25",
        }
    ]
    assert selected_percentages[-2:] == [
        "resources.increase_production.percent.2",
        "resources.increase_production.percent.25",
    ]
    assert any(
        step.get("op") == "assert_action"
        and step.get("type") == "ActionIncreaseResourceProduction"
        and step.get("count") == 1
        and step.get("fields", {}).get("increase_percent") == 25
        for step in steps
    )


def test_unit_production_gml_caption_and_eta_slots_have_explicit_bindings():
    root = Path(__file__).resolve().parents[1]
    window = "Unit_Production_Window"
    expected = {
        "frmTitle/lblTitle",
        "frmRight/frmProduction/lblTitle",
        "frmRight/frmProduction/lblNbType",
        "frmRight/frmProduction/lblNbType1",
        "frmRight/frmProduction/lblNbType2",
        "frmRight/frmProduction/lblPriority",
        "frmRight/frmProduction/lblProgress",
        "frmRight/frmProduction/txtAcceptForeign",
        "frmRight/frmProduction/lblUnitName",
        "frmDesignList/frmInfo/lblSpeed",
        "frmDesignList/frmInfo/lblPriority",
        "frmDesignList/frmUnitName/lblUnitName",
        "frmDesignList/frmCost/lblQty",
        "frmDesignList/frmCost/lblTotalCost",
        "frmDesignList/frmEta/lblEta",
        "frmDesignList/frmDesignList/lblProducer",
        "frmDesignList/frmEta/txtEta",
    }
    bindings = audit.DISPLAY_BINDINGS_BY_WINDOW[window]
    assert len(bindings) == 19
    assert expected.issubset(bindings)

    with (root / "docs/ui/reference/data_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        rows = {
            row["component_path"]: row for row in csv.DictReader(source)
            if row["window_id"] == window
        }
    for suffix in expected:
        binding = bindings[suffix]
        row = rows[f"{window}/{suffix}"]
        assert binding.status == "partial"
        assert row["status"] == binding.status
        assert row["openpower_binding_status"] == binding.status
        assert row["openpower_state_binding"] == binding.state_binding
        assert row["openpower_surface"] == binding.surface
        assert "localization/placeholder meaning is unresolved" not in row["what_is_displayed"]

    panel = (root / "src/client/ui/panels/military/unit_production_panel.py").read_text(encoding="utf-8")
    for caption in (
        "UNIT PRODUCTION", "PRODUCTION QUEUE", "QTY", "FROM", "TO", "PRIORITY",
        "PROGRESS", "ACCEPT FOREIGN", "CAPACITY", "SPEED", "DESIGN", "QUANTITY",
        "TOTAL COST", "ETA", "BUILD IN",
    ):
        assert f'"{caption}"' in panel
    assert "initial_production_eta_days" in panel


def test_economic_window_gml_captions_have_explicit_openpower_bindings():
    root = Path(__file__).resolve().parents[1]
    window = "Economic_Window"
    expected = {
        "frmTitle/lblTitle": ("100002", "ECONOMY"),
        "frmInner/frmResources/lblTitle": ("100047", "RESOURCES"),
        "frmInner/frmEconomicModel/lblTitle": ("100165", "ECONOMIC MODEL"),
        "frmInner/frmEconomicModel/lblStateControlled": ("100039", "State"),
        "frmInner/frmEconomicModel/lblFreeMarket": ("100040", "Market"),
        "frmInner/frmBudget/lblTitle": ("100042", "BUDGET"),
        "frmInner/frmEconomicHealth/lblTitle": ("100166", "ECONOMIC HEALTH"),
    }
    bindings = audit.DISPLAY_BINDINGS_BY_WINDOW[window]
    assert set(expected).issubset(bindings)

    code = (root / "src/client/ui/panels/economy_panel.py").read_text(encoding="utf-8")
    with (root / "docs/ui/reference/data_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        rows = {
            row["component_path"]: row for row in csv.DictReader(source)
            if row["window_id"] == window
        }
    for suffix, (token, caption) in expected.items():
        binding = bindings[suffix]
        assert binding.status == "partial"
        assert f'"{caption}"' in code
        row = rows[f"{window}/{suffix}"]
        assert row["gml_text_token"] == token
        assert row["status"] == binding.status
        assert row["openpower_binding_status"] == binding.status
        assert row["openpower_state_binding"] == binding.state_binding
        assert row["openpower_surface"] == binding.surface == "economy.panel"
        assert "localization/placeholder meaning is unresolved" not in row["what_is_displayed"]


def test_treaties_window_gml_captions_have_explicit_openpower_bindings():
    root = Path(__file__).resolve().parents[1]
    window = "Treaties_Window"
    expected = {
        "frmTitle/lblTitle": ("100023", "Treaties"),
        "frmInner/frmFilters/lblTitle": ("100586", "FILTERS"),
        "frmInner/frmFilters/lblType": ("100585", "TYPE"),
        "frmInner/frmFilters/lblMember": ("100587", "MEMBER"),
        "frmInner/frmPendingTreaties/lblTitle": ("100590", "PENDING PROPOSALS"),
        "frmInner/frmPendingTreaties/lblType": ("100585", "TYPE"),
        "frmInner/frmPendingTreaties/lblName": ("100584", "NAME"),
        "frmInner/frmActiveTreaties/lblTitle": ("100583", "ACTIVE TREATIES"),
        "frmInner/frmActiveTreaties/lblType": ("100585", "TYPE"),
        "frmInner/frmActiveTreaties/lblName": ("100584", "NAME"),
    }
    bindings = audit.DISPLAY_BINDINGS_BY_WINDOW[window]
    assert set(expected).issubset(bindings)

    panel = (root / "src/client/ui/panels/politics/treaties_live.py").read_text(encoding="utf-8")
    with (root / "docs/ui/reference/data_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        rows = {
            row["component_path"]: row for row in csv.DictReader(source)
            if row["window_id"] == window
        }
    for suffix, (token, caption) in expected.items():
        binding = bindings[suffix]
        assert binding.status == "partial"
        assert f'"{caption}"' in panel
        row = rows[f"{window}/{suffix}"]
        assert row["gml_text_token"] == token
        assert row["status"] == binding.status
        assert row["openpower_binding_status"] == binding.status
        assert row["openpower_state_binding"] == binding.state_binding
        assert row["openpower_surface"] == binding.surface == "treaties.panel"
        assert "localization/placeholder meaning is unresolved" not in row["what_is_displayed"]


def test_resources_window_captions_keep_openpower_ledger_differences_explicit():
    root = Path(__file__).resolve().parents[1]
    window = "Resources_Window"
    expected = {
        "frmTitle/lblTitle": ("100047", "RESOURCES MENU"),
        "frmInner/frmResources/lblMarketShare": ("100343", "MKT SHARE"),
        "frmInner/frmResources/lblGlobalTaxMod": ("100341", "GLOBAL TAX"),
        "frmInner/frmResources/lblDesired": ("100345", "DESIRED"),
        "frmInner/frmResources/lblTrade": ("100066", "MARKET FLOW"),
        "frmInner/frmResources/lblProduction": ("100064", "PRODUCTION"),
        "frmInner/frmResources/lblAvailable": ("100045", None),
        "frmInner/frmResources/lblActual": ("100346", "ACTUAL"),
        "frmInner/frmResources/lblSectorTax": ("100078", "RESOURCE TAX"),
        "frmInner/frmResources/lblMeetConsumption": ("100347", "Meet consumption"),
        "frmInner/frmResources/lblStatus": ("100077", "LEGAL STATUS"),
        "frmInner/frmResources/lblManagement": ("100076", "MANAGEMENT"),
        "frmInner/frmResources/lblMarketAvailability": ("100344", "NET BALANCE"),
        "frmInner/frmResources/lblResource": ("100063", None),
        "frmInner/frmResources/lblConsumption": ("100340", "CONSUMPTION"),
        "frmInner/frmResources/lblGdp": ("100342", "SHARE OF GDP"),
        "frmInner/frmResources/lblTrade2": ("100066", "TRADE"),
        "frmInner/frmResources/txtMarketShare": ("0", None),
        "frmInner/frmResources/txtAvailability": ("0", None),
        "frmInner/frmResources/cboTrade": ("", None),
        "frmInner/frmResources/txtGdp": ("0", None),
    }
    bindings = audit.DISPLAY_BINDINGS_BY_WINDOW[window]
    assert set(expected).issubset(bindings)

    panel = (root / "src/client/ui/panels/resources_panel.py").read_text(encoding="utf-8")
    with (root / "docs/ui/reference/data_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        rows = {
            row["component_path"]: row for row in csv.DictReader(source)
            if row["window_id"] == window
        }

    for suffix, (token, caption) in expected.items():
        binding = bindings[suffix]
        assert binding.status == "partial"
        if caption is not None:
            assert f'"{caption}"' in panel
        row = rows[f"{window}/{suffix}"]
        assert row["gml_text_token"] == token
        assert row["status"] == binding.status
        assert row["openpower_binding_status"] == binding.status
        assert row["openpower_state_binding"] == binding.state_binding
        assert row["openpower_surface"] == binding.surface == "resources.panel"
        assert "localization/placeholder meaning is unresolved" not in row["what_is_displayed"]

    available = bindings["frmInner/frmResources/lblAvailable"]
    assert "balance_usd" in available.state_binding
    assert "not stock availability" in available.meaning
    selected_resource = bindings["frmInner/frmResources/lblResource"]
    assert "selected_resource" in selected_resource.state_binding
    assert "Select a Resource" in selected_resource.fallback
    market_share = bindings["frmInner/frmResources/txtMarketShare"]
    assert "production_usd" in market_share.state_binding
    assert "world production_usd" in market_share.state_binding
    availability = bindings["frmInner/frmResources/txtAvailability"]
    assert "balance_usd" in availability.state_binding
    assert "not stock availability" in availability.meaning
    trade = bindings["frmInner/frmResources/cboTrade"]
    assert "Disabled" in trade.state_binding
    assert "no matching per-resource desired-trade command" in trade.meaning
    assert "BALANCE" in panel


def test_system_bar_shortcut_captions_are_bound_to_source_slots():
    root = Path(__file__).resolve().parents[1]
    window = "System_Bar_Window"
    expected = {
        "txtF1": ("102211", "Help"),
        "txtF2": ("102212", "Chat"),
        "txtF3": ("102210", "Save"),
        "txtF4": ("102209", "Load"),
        "txtF5": ("101596", "Objectives"),
        "txtF10": ("102208", "Menu"),
    }
    bindings = audit.DISPLAY_BINDINGS_BY_WINDOW[window]
    assert set(expected).issubset(bindings)

    code = (root / "src/client/ui/components/hud/system_bar.py").read_text(encoding="utf-8")
    with (root / "docs/ui/reference/data_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        rows = {
            row["component_path"]: row for row in csv.DictReader(source)
            if row["window_id"] == window
        }

    for suffix, (token, caption) in expected.items():
        binding = bindings[suffix]
        assert binding.status == "partial"
        assert f'"{caption}"' in code
        row = rows[f"{window}/{suffix}"]
        assert row["gml_text_token"] == token
        assert row["status"] == binding.status
        assert row["openpower_binding_status"] == binding.status
        assert row["openpower_state_binding"] == binding.state_binding
        assert row["openpower_surface"] == binding.surface == "hud.system_bar"
        assert "localization/placeholder meaning is unresolved" not in row["what_is_displayed"]

    chat = bindings["txtF2"]
    assert "no OpenPower route" in chat.action_required
    assert "Chat" in chat.meaning


def test_relations_window_display_slots_keep_openpower_pair_semantics_explicit():
    root = Path(__file__).resolve().parents[1]
    window = "Relations_Window"
    expected = {
        "frmTitle/lblTitle": ("100153", "RELATIONS"),
        "frmInner/frmRelations/lblTitle": ("101032", None),
        "frmInner/frmRelations/lblCountryA": ("101031", "Country A"),
        "frmInner/frmRelations/lblCountryB": ("101030", "Country B"),
    }
    bindings = audit.DISPLAY_BINDINGS_BY_WINDOW[window]
    assert set(expected).issubset(bindings)

    panel = (root / "src/client/ui/panels/politics/relations_panel.py").read_text(encoding="utf-8")
    presenter = (root / "src/client/ui/panels/politics/relations_presenter.py").read_text(encoding="utf-8")
    with (root / "docs/ui/reference/data_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        rows = {
            row["component_path"]: row for row in csv.DictReader(source)
            if row["window_id"] == window
        }

    for suffix, (token, caption) in expected.items():
        binding = bindings[suffix]
        assert binding.status == "partial"
        if caption is not None:
            assert f'"{caption}"' in panel
        row = rows[f"{window}/{suffix}"]
        assert row["gml_text_token"] == token
        assert row["status"] == binding.status
        assert row["openpower_binding_status"] == binding.status
        assert row["openpower_state_binding"] == binding.state_binding
        assert row["openpower_surface"] == binding.surface == "relations.panel"
        assert "localization/placeholder meaning is unresolved" not in row["what_is_displayed"]

    summary = bindings["frmInner/frmRelations/lblTitle"]
    assert "countries_relations" in summary.state_binding
    assert "directed" in summary.meaning
    assert "not proven equivalent" in summary.meaning
    assert "countries_relations" in presenter
    assert "No relation history recorded." in panel


def test_internal_laws_window_display_slots_have_explicit_openpower_bindings():
    root = Path(__file__).resolve().parents[1]
    window = "Internal_Laws"
    expected = {
        "frmTitle/lblTitle": ("100016", "INTERNAL LAWS"),
        "frmInner/frmOrganizations/lblTitle": ("100099", "POLITICAL PARTIES"),
        "frmInner/frmLaws/lblTitle": ("100097", "CIVIL AND FAMILY LAWS"),
        "frmInner/frmDemographicGroups/lblTitle": ("100100", "DEMOGRAPHIC GROUPS"),
        "frmInner/frmHumanMigration/lblTitle": ("100098", "HUMAN MIGRATION"),
        "frmInner/frmHumanMigration/lblImmigration": ("100122", "Immigration"),
        "frmInner/frmHumanMigration/lblEmigration": ("100121", "Emigration"),
        "frmInner/frmDemographicGroups": ("", None),
        "frmInner/frmHumanMigration/txtImmigrationValue": ("0", None),
        "frmInner/frmHumanMigration/txtEmigrationValue": ("0", None),
    }
    bindings = audit.DISPLAY_BINDINGS_BY_WINDOW[window]
    assert set(expected).issubset(bindings)

    code = (root / "src/client/ui/panels/politics/internal_laws_panel.py").read_text(encoding="utf-8")
    with (root / "docs/ui/reference/data_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        rows = {
            row["component_path"]: row for row in csv.DictReader(source)
            if row["window_id"] == window
        }
    for suffix, (token, caption) in expected.items():
        binding = bindings[suffix]
        assert binding.status == "partial"
        if caption is not None:
            assert f'"{caption}"' in code
        row = rows[f"{window}/{suffix}"]
        assert row["gml_text_token"] == token
        assert row["status"] == binding.status
        assert row["openpower_binding_status"] == binding.status
        assert row["openpower_state_binding"] == binding.state_binding
        assert row["openpower_surface"] == binding.surface == "laws.panel"
        assert "localization/placeholder meaning is unresolved" not in row["what_is_displayed"]


def test_internal_laws_migration_values_match_source_one_decimal_percent_format():
    from src.client.ui.panels.politics.internal_laws_panel import InternalLawsPanel

    assert InternalLawsPanel._format_migration_rate(0.056) == "5.6%"
    assert InternalLawsPanel._format_migration_rate(1.0) == "100.0%"
    assert InternalLawsPanel._format_migration_rate(None) == "\u2014"


def test_covert_window_gml_captions_have_explicit_openpower_bindings():
    root = Path(__file__).resolve().parents[1]
    window = "Covert_Actions_Window"
    expected = {
        "frmTitle/lblTitle": "COVERT OPS",
        "frmInner/frmCell/lblTitle": "COVERT CELLS",
        "frmInner/frmCell/lblName": "NAME",
        "frmInner/frmCell/lblCountry": "ASSIGNED COUNTRY",
        "frmInner/frmCell/lblStatus": "STATUS",
        "frmInner/frmCell/lblUpkeep": "UPKEEP / DAY",
        "frmInner/frmUpkeep/lblProtection": "PROTECTION",
        "frmInner/frmUpkeep/lblUpkeep": "ROSTER / DAY",
        "frmInner/frmMission/lblTitle": "MISSION \u00b7 ",
        "frmInner/frmMission/lblType": "TYPE",
        "frmInner/frmMission/lblSector": "SECTOR",
        "frmInner/frmMission/lblComplexity": "COMPLEXITY",
        "frmInner/frmMission/lblResourceUnit": "RESOURCE / UNIT",
        "frmInner/frmMission/lblFramedCountry": "FRAMED COUNTRY",
    }
    bindings = audit.DISPLAY_BINDINGS_BY_WINDOW[window]
    assert set(expected).issubset(bindings)

    code = (root / "src/client/ui/panels/military/covert_ops_panel.py").read_text(encoding="utf-8")
    with (root / "docs/ui/reference/data_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        rows = {
            row["component_path"]: row for row in csv.DictReader(source)
            if row["window_id"] == window
        }
    for suffix, caption in expected.items():
        path = f"{window}/{suffix}"
        binding = bindings[suffix]
        assert caption in code
        assert binding.status == "partial"
        row = rows[path]
        assert binding.surface == row["openpower_surface"]
        assert binding.state_binding == row["openpower_state_binding"]
        assert row["openpower_binding_status"] == "partial"
        assert "localization/placeholder meaning is unresolved" not in row["what_is_displayed"]


def test_covert_new_mission_form_display_slots_bind_python_state_to_source_controls():
    root = Path(__file__).resolve().parents[1]
    window = "Covert_Actions_New_Mission"
    expected = {
        "frmTitle/lblTitle": ("101040", "New Covert Mission"),
        "frmInner/frmMission/lblFramedCountry": ("101047", "Framed country"),
        "frmInner/frmMission/cboResourceUnit": ("", None),
        "frmInner/frmMission/lblMissionType": ("101043", "Mission type"),
        "frmInner/frmMission/txtCountry": ("0", None),
        "frmInner/frmMission/lblTargetSector": ("101053", "Target sector"),
        "frmInner/frmMission/cboCountry": ("", None),
        "frmInner/frmMission/cboComplexity": ("", None),
        "frmInner/frmMission/lblResourceUnit": ("101046", "Resource / unit"),
        "frmInner/frmMission/lblComplexity": ("101045", "Complexity"),
        "frmInner/frmMission/lblTargetCountry": ("101052", "Target country"),
        "frmInner/frmMission/cboSector": ("", None),
        "frmInner/frmMission/cboMissionType": ("", None),
    }
    bindings = audit.DISPLAY_BINDINGS_BY_WINDOW[window]
    assert set(expected) == set(bindings)

    code = (root / "src/client/ui/panels/military/covert_action_windows.py").read_text(encoding="utf-8")
    options = (root / "src/shared/covert_mission_options.py").read_text(encoding="utf-8")
    with (root / "docs/ui/reference/data_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        rows = {
            row["component_path"]: row for row in csv.DictReader(source)
            if row["window_id"] == window
        }

    assert set(expected) == {path.removeprefix(f"{window}/") for path in rows}
    for suffix, (token, caption) in expected.items():
        binding = bindings[suffix]
        path = f"{window}/{suffix}"
        row = rows[path]
        assert row["gml_text_token"] == token
        assert row["status"] == binding.status
        assert row["openpower_binding_status"] == binding.status
        assert row["openpower_state_binding"] == binding.state_binding
        assert row["openpower_surface"] == binding.surface == "PanelSpec/COVERT_OPS/CovertActionWindows mission dialog"
        assert "localization/placeholder meaning is unresolved" not in row["what_is_displayed"]
        if caption is not None:
            assert caption in code

    resource = bindings["frmInner/frmMission/cboResourceUnit"]
    assert resource.status == "partial"
    assert "country_resource_ids(state" in resource.state_binding
    assert "OpenPower's resource tables" in resource.meaning
    assert "country_resource_ids" in options
    sector = bindings["frmInner/frmMission/cboSector"]
    assert sector.status == "verified_openpower"
    assert "cleared for categories without a sector" in sector.fallback
    assert "self._mission_sector = \"\"" in code
    target_country = bindings["frmInner/frmMission/txtCountry"]
    assert target_country.status == "partial"
    assert "Selected covert_cells.target_country_id" in target_country.state_binding


def test_thematic_map_country_list_selection_matches_source_look_at_handler():
    root = Path(__file__).resolve().parents[1]
    path = "Thematic_Map_Legend/lstCountries"
    binding = audit.THEMATIC_MAP_LEGEND_INTERACTION_BINDINGS[path]
    with (root / "docs/ui/reference/interaction_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        row = next(
            row for row in csv.DictReader(source)
            if row["window_id"] == "Thematic_Map_Legend" and row["component_path"] == path
        )
    with (root / "docs/ui/reference/gap_table.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        gaps = list(csv.DictReader(source))

    for field, value in binding.items():
        assert row[field] == value
    matching_gaps = _interaction_gap_rows(gaps, path, binding)
    assert matching_gaps and all(gap["status"] == "verified_openpower" for gap in matching_gaps)

    source = resolve_reference_file(root, ".codex/Client/Source/reference_thematic_map_legend_window.cpp").read_text(encoding="utf-8")
    assert "OnListItemSelected" in source
    assert "SelectedCountrySetLookAt" in source
    for journey_name in ("reference-map-thematic-legend.json", "reference-map-empire-legend.json"):
        journey = json.loads((root / "tests/ui/journeys" / journey_name).read_text(encoding="utf-8"))
        assert any(step.get("op") == "click" and step.get("target") == "map.legend.country.POL" for step in journey["steps"])
        assert any(step.get("op") == "assert_viewport_request" and step.get("type") == "country" for step in journey["steps"])


def test_battle_overview_country_rows_remain_distinct_from_openpower_battle_selection():
    root = Path(__file__).resolve().parents[1]
    path = "Battle_Overview_Small_Unit_Info/lstUnits"
    binding = audit.BATTLE_OVERVIEW_SMALL_UNIT_INFO_INTERACTION_BINDINGS[path]
    with (root / "docs/ui/reference/interaction_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        row = next(
            row for row in csv.DictReader(source)
            if row["window_id"] == "Battle_Overview_Small_Unit_Info" and row["component_path"] == path
        )
    with (root / "docs/ui/reference/gap_table.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        gaps = list(csv.DictReader(source))

    for field, value in binding.items():
        assert row[field] == value
    matching_gaps = _interaction_gap_rows(gaps, path, binding)
    assert matching_gaps and all(gap["status"] == "partial" for gap in matching_gaps)

    source = resolve_reference_file(root, ".codex/Client/Source/reference_battle_overview_small_unit_info_window.cpp").read_text(encoding="utf-8")
    assert "OnListItemSelected" in source
    assert "//((GBattleOverviewWindow*)Owner())->OnSmallUnitInfoSelection" in source
    assert "OnSmallUnitInfoSelection" not in source.replace(
        "//((GBattleOverviewWindow*)Owner())->OnSmallUnitInfoSelection", ""
    )


def test_economic_summary_meter_controls_keep_source_drag_boundary_explicit():
    root = Path(__file__).resolve().parents[1]
    bindings = audit.ECONOMIC_WINDOW_METER_INTERACTION_BINDINGS
    meter_source = resolve_reference_file(root, ".codex/Client/Source/reference_frame_cursor_meter.cpp").read_text(encoding="utf-8")
    window_source = resolve_reference_file(root, ".codex/Client/Source/reference_economic_window.cpp").read_text(encoding="utf-8")
    panel_source = (root / "src/client/ui/panels/economy_panel.py").read_text(encoding="utf-8")

    ideology = meter_source.split("bool GIdeologyMeter::OnCreate()", 1)[1].split("GSplitMeter::", 1)[0]
    generic_meter = meter_source.split("bool GCursorMeter::OnCreate()", 1)[1].split(
        "GUI::EEventStatus::Enum GCursorMeter::OnMouseDown", 1
    )[0]
    assert "CursorDragable()[0] = false;" in ideology
    assert "CursorDragable()[0] = true;" in generic_meter
    assert "Locked()[1] = true;" in generic_meter
    assert "GEconomicWindow::OnCustomEvent" not in window_source
    assert "m_pObjHealth   ->Value(l_fHealth / 100,  0);" in window_source
    assert "m_pObjResources->Value(l_fRessRatio,     0);" in window_source
    assert 'ui.meter("frmEconomicModel/frmModelCursor", market_model_val' in panel_source
    assert '("frmEconomicHealth", eco_health), ("frmResources", resources_health)' in panel_source
    assert ".meter_slider(" not in panel_source

    with (root / "docs/ui/reference/interaction_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        rows = list(csv.DictReader(source))
    with (root / "docs/ui/reference/gap_table.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        gaps = list(csv.DictReader(source))

    assert set(bindings) == {
        "Economic_Window/frmInner/frmEconomicModel/frmModelCursor/btnFill",
        "Economic_Window/frmInner/frmEconomicModel/frmModelCursor/btnUnfilled",
        "Economic_Window/frmInner/frmEconomicHealth/frmGradient/btnFill",
        "Economic_Window/frmInner/frmEconomicHealth/frmGradient/btnUnfilled",
        "Economic_Window/frmInner/frmResources/frmGradient/btnFill",
        "Economic_Window/frmInner/frmResources/frmGradient/btnUnfilled",
    }
    for path, binding in bindings.items():
        row = next(
            row for row in rows
            if row["window_id"] == "Economic_Window" and row["component_path"] == path
        )
        for field, value in binding.items():
            assert row[field] == value
        matching_gaps = _interaction_gap_rows(gaps, path, binding)
        assert matching_gaps and all(gap["status"] == binding["status"] for gap in matching_gaps)


def test_relations_country_selectors_map_to_read_only_pair_history():
    root = Path(__file__).resolve().parents[1]
    expected_sides = {"A", "B"}
    assert {
        path.rsplit("cboCountry", 1)[1]
        for path in audit.RELATIONS_INTERACTION_BINDINGS
    } == expected_sides

    with (root / "docs/ui/reference/interaction_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        contracts = {
            row["component_path"]: row
            for row in csv.DictReader(source)
            if row["window_id"] == "Relations_Window"
        }
    for path, binding in audit.RELATIONS_INTERACTION_BINDINGS.items():
        row = contracts[path]
        assert binding["status"] == row["status"] == "verified_openpower"
        assert row["game_action"] == "none (read-only relation history lookup)"
        assert row["reference_callback"] == "OnCustomEvent@reference_relations_window.cpp:114"
        assert "StartRequestRelationHistory" in row["verified_cpp_transition"]
        assert "different countries" in row["validation_condition"]

    journey = json.loads((root / "tests/ui/journeys/reference-relations-data.json").read_text(encoding="utf-8"))
    assert any(
        step.get("op") == "select" and step.get("target") == "relations.country_a"
        for step in journey["steps"]
    )
    assert any(
        step.get("op") == "assert" and step.get("target") == "relations.summary"
        for step in journey["steps"]
    )


def test_save_and_load_dialog_controls_have_explicit_field_level_contracts():
    root = Path(__file__).resolve().parents[1]
    expected_interactions = {
        "Save_Game_Window/frmInner/frmSave/edtSaveName",
        "Save_Game_Window/frmInner/frmSave/lstSaves",
        "Save_Game_Window/frmInner/btnSaveGame",
        "Load_Saved_Game/frmInner/frmList/lstGames",
        "Load_Saved_Game/frmInner/btnLoadGame",
    }
    assert set(audit.SAVE_LOAD_INTERACTION_BINDINGS) == expected_interactions

    with (root / "docs/ui/reference/interaction_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        interaction_rows = {
            row["component_path"]: row
            for row in csv.DictReader(source)
            if row["window_id"] in {"Save_Game_Window", "Load_Saved_Game"}
        }
    for path, binding in audit.SAVE_LOAD_INTERACTION_BINDINGS.items():
        row = interaction_rows[path]
        assert row["status"] == binding["status"]
        assert row["game_action"] == binding["game_action"]
        assert row["reference_callback"] == binding["reference_callback"]
        assert row["verified_cpp_transition"] == binding["verified_cpp_transition"]
        assert row["action_required"] == binding["action_required"]

    expected_display_paths = {
        (window, path)
        for window, bindings in audit.DISPLAY_BINDINGS_BY_WINDOW.items()
        if window in {"Save_Game_Window", "Load_Saved_Game"}
        for path in bindings
    }
    with (root / "docs/ui/reference/data_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        data_rows = list(csv.DictReader(source))
    matching_data = {
        (row["window_id"], row["component_path"].removeprefix(row["window_id"] + "/")): row
        for row in data_rows
        if row["window_id"] in {"Save_Game_Window", "Load_Saved_Game"}
    }
    assert set(matching_data) == expected_display_paths
    assert all(row["openpower_binding_status"] == "partial" for row in matching_data.values())

    save_journey = json.loads((root / "tests/ui/journeys/reference-save-dialog.json").read_text(encoding="utf-8"))
    assert any(step.get("target") == "save_game.name" for step in save_journey["steps"])
    assert any(
        step.get("op") == "assert_action" and step.get("type") == "ActionSaveGame"
        for step in save_journey["steps"]
    )
    load_journey = json.loads((root / "tests/ui/journeys/reference-load-saved-game-route.json").read_text(encoding="utf-8"))
    assert any(step.get("target") == "load_game.submit" for step in load_journey["steps"])


def test_internal_laws_controls_map_to_supported_drafts_and_separate_migration_editor():
    root = Path(__file__).resolve().parents[1]
    bindings = audit.INTERNAL_LAWS_INTERACTION_BINDINGS
    source = resolve_reference_file(root, ".codex/Client/Source/reference_internal_laws_window.cpp").read_text(encoding="utf-8")
    base_source = resolve_reference_file(root, ".codex/Client/Source/reference_base_window.cpp").read_text(encoding="utf-8")
    panel = (root / "src/client/ui/panels/politics/internal_laws_panel.py").read_text(encoding="utf-8")
    law_draft = (root / "src/client/ui/panels/politics/law_policy_draft.py").read_text(encoding="utf-8")
    party_draft = (root / "src/client/ui/panels/politics/party_policy_draft.py").read_text(encoding="utf-8")
    migration_panel = (root / "src/client/ui/panels/migration_panel.py").read_text(encoding="utf-8")

    assert "OnComboBoxSelectionEvent" in source
    assert "m_pObjEmigrationCbo" in source and "m_pObjImmigrationCbo" in source
    assert "GInternalLawsUpdate" in source
    assert "GBaseWindow::ExitWindow" in base_source and "GBaseWindow::Apply" in base_source
    assert "DirtyCloseConfirmation" in panel and "def _apply_drafts" in panel
    assert "ActionChangePoliticalLaw" in law_draft
    identity_view = (root / "src/client/ui/panels/politics/identity_policy_view.py").read_text(encoding="utf-8")
    assert "ActionSetCountryIdentityPolicy" in identity_view
    assert "ActionSetPartyEligibility" in party_draft
    assert "ActionUpdateMigrationPolicy" in migration_panel
    assert '"laws.open_migration"' in panel and '"laws.open_emigration"' in panel

    journey_expectations = {
        "law-policy-apply.json": ("laws.value.speech", "ActionChangePoliticalLaw"),
        "identity-policy.json": ("ActionSetCountryIdentityPolicy", "laws.open_migration"),
        "party-policy.json": ("ActionSetPartyEligibility", "laws.apply"),
        "internal-laws-layout.json": ("laws.open_migration", "laws.open_politics"),
        "law-close-apply.json": ("laws.close.confirmation", "laws.close.apply"),
    }
    for journey_name, expected_tokens in journey_expectations.items():
        journey = (root / "tests/ui/journeys" / journey_name).read_text(encoding="utf-8")
        assert all(token in journey for token in expected_tokens)

    with (root / "docs/ui/reference/interaction_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as file:
        rows = list(csv.DictReader(file))
    with (root / "docs/ui/reference/gap_table.csv").open(
        encoding="utf-8-sig", newline=""
    ) as file:
        gaps = list(csv.DictReader(file))

    assert len(bindings) == 8
    for path, binding in bindings.items():
        row = next(
            row for row in rows
            if row["window_id"] == "Internal_Laws" and row["component_path"] == path
        )
        for field, value in binding.items():
            assert row[field] == value
        matching_gaps = _interaction_gap_rows(gaps, path, binding)
        assert matching_gaps and all(gap["status"] == "partial" for gap in matching_gaps)


def test_treaty_list_filters_and_selection_map_to_openpower_treaty_browser_routes():
    root = Path(__file__).resolve().parents[1]
    bindings = audit.TREATIES_WINDOW_INTERACTION_BINDINGS
    source = resolve_reference_file(root, ".codex/Client/Source/reference_treaties_window.cpp").read_text(encoding="utf-8")
    base_source = resolve_reference_file(root, ".codex/Client/Source/reference_base_window.cpp").read_text(encoding="utf-8")
    panel = (root / "src/client/ui/panels/politics/treaties_live.py").read_text(encoding="utf-8")
    filters = (root / "src/client/ui/panels/politics/treaty_filters.py").read_text(encoding="utf-8")
    containers = (root / "src/client/ui/core/containers.py").read_text(encoding="utf-8")

    assert "GBaseWindow::ExitWindow" in base_source
    assert "m_pObjApplyBtn->Hide();" in source
    assert "OnListItemSelected" in source and "OnListItemDoubleClicked" in source
    assert "OnComboBoxSelectionEvent" in source
    assert "FillCountries();" in source
    assert "_treaty_filter_options(state, rows)" in panel
    assert "_matches_treaty_filter(row, self._filter_member_tag, self._filter_type_key)" in panel
    assert "TREATY_DEFINITIONS" in filters and "normalize_treaty_type" in filters
    assert '"treaties.filter_member"' in panel and '"treaties.filter_type"' in panel
    assert "treaties.active.{treaty_id}" in panel
    assert "treaties.pending.{proposal_id}" in panel
    assert "apply_base_window_titlebar_rules" in containers
    assert "Treaties_Window/frmTitle/btnApply" in bindings

    journey_expectations = {
        "reference-treaty-filters.json": ("treaties.filter_member", "treaties.filter_type", "assert_absent"),
        "reference-politics-treaty-details.json": ("treaties.active.treaty-ukr-pol", "treaties.view_selected"),
        "reference-treaty-response-accept.json": ("treaties.pending.proposal-long", "ActionRespondTreaty"),
        "reference-treaty-long-rows.json": ("treaties.active.nato-long", "treaties.pending.proposal-long"),
    }
    for journey_name, expected_tokens in journey_expectations.items():
        journey = (root / "tests/ui/journeys" / journey_name).read_text(encoding="utf-8")
        assert all(token in journey for token in expected_tokens)

    suite = json.loads((root / "tests/ui/reference-navigation-suite.json").read_text(encoding="utf-8"))
    assert any(item["journey"].endswith("reference-treaty-filters.json") for item in suite["results"])

    with (root / "docs/ui/reference/interaction_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as file:
        rows = list(csv.DictReader(file))
    with (root / "docs/ui/reference/gap_table.csv").open(
        encoding="utf-8-sig", newline=""
    ) as file:
        gaps = list(csv.DictReader(file))

    assert len(bindings) == 6
    for path, binding in bindings.items():
        row = next(
            row for row in rows
            if row["window_id"] == "Treaties_Window" and row["component_path"] == path
        )
        for field, value in binding.items():
            assert row[field] == value
        matching_gaps = _interaction_gap_rows(gaps, path, binding)
        assert matching_gaps and all(gap["status"] == binding["status"] for gap in matching_gaps)


def test_unused_source_templates_are_explicitly_unavailable_instead_of_inferred():
    expected_counts = {
        "Player_Options_Window": 23,
        "Political_Parties_Window": 6,
        "Strategic_Alert_Window": 2,
        "Strategic_News_Window": 2,
    }
    bindings = audit.UNUSED_SOURCE_TEMPLATE_INTERACTION_BINDINGS
    root = Path(__file__).resolve().parents[1]
    with (root / "docs/ui/reference/window_registry.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        registry = {row["window_id"]: row for row in csv.DictReader(source)}
    with (root / "docs/ui/reference/interaction_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        contracts = list(csv.DictReader(source))
    with (root / "docs/ui/reference/gap_table.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        gaps = list(csv.DictReader(source))

    for window, expected_count in expected_counts.items():
        assert registry[window]["status"] == "unused"
        assert registry[window]["mapping_status"] == "verified_unavailable"
        window_contracts = [row for row in contracts if row["window_id"] == window]
        assert len(window_contracts) == expected_count
        assert all(row["status"] == "verified_unavailable" for row in window_contracts)
        assert all(
            row["game_action"] == "none (unused source template; no runtime callback)"
            for row in window_contracts
        )
        for row in window_contracts:
            binding = bindings[row["component_path"]]
            for field, value in binding.items():
                assert row[field] == value
            matching_gaps = [
                gap for gap in gaps
                if gap["gml_node_or_behavior"] == row["component_path"]
                and gap["openpower_current_implementation"]
                == f"{binding['openpower_surface']}: {binding['openpower_effect']}"
            ]
            assert matching_gaps
            assert all(gap["status"] == "verified_unavailable" for gap in matching_gaps)

    assert len(bindings) == sum(expected_counts.values())

    assert "Strategic_News_Window" not in audit.PANEL_ALIASES
    assert audit.LAYOUT_SURFACES["Strategic_News_Window"] == (
        "UnusedSourceTemplate/NoRuntimeRoute",
        "verified_unavailable",
    )
    assert "Strategic_News_Window" not in audit.PARTIALLY_IMPLEMENTED_WINDOW_GAPS
    assert "Strategic_Alert_Window" not in audit.PANEL_ALIASES
    assert "Strategic_Alert_Window" not in audit.PARTIALLY_IMPLEMENTED_WINDOW_GAPS
    assert audit.LAYOUT_SURFACES["Strategic_Alert_Window"] == (
        "UnusedSourceTemplate/NoRuntimeRoute",
        "verified_unavailable",
    )
    inactive_registry_row = registry["Strategic_News_Window"]
    assert inactive_registry_row["cpp_type"] == ""
    assert inactive_registry_row["registered_gui_object"] == "False"
    assert inactive_registry_row["window_spawn_call_count"] == "0"
    assert "C++ TypeName" not in inactive_registry_row["discovery_evidence"]
    ticker = audit.DISPLAY_BINDINGS_BY_WINDOW["Strategic_News_Window"]["txtNews"]
    assert ticker.status == "verified_unavailable"
    assert "separate from OpenPower's NEWS_LOG Event Feed" in ticker.meaning

    with (root / "docs/ui/reference/data_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        data_contracts = list(csv.DictReader(source))
    ticker_row = next(
        row for row in data_contracts
        if row["window_id"] == "Strategic_News_Window"
        and row["component_path"] == "Strategic_News_Window/txtNews"
    )
    assert ticker_row["openpower_binding_status"] == "verified_unavailable"
    assert "separate from OpenPower's NEWS_LOG Event Feed" in ticker_row["what_is_displayed"]

    alert_bindings = audit.DISPLAY_BINDINGS_BY_WINDOW["Strategic_Alert_Window"]
    assert set(alert_bindings) == {
        "frmMessage/txtCountry",
        "frmMessage/txtMessage",
        "frmFlag/frmTrim/picFlag",
    }
    alert_rows = [
        row for row in data_contracts if row["window_id"] == "Strategic_Alert_Window"
    ]
    assert {row["component_path"].removeprefix("Strategic_Alert_Window/") for row in alert_rows} == set(
        alert_bindings
    )
    assert all(row["openpower_binding_status"] == "verified_unavailable" for row in alert_rows)


def test_trade_offer_window_records_the_swallowed_source_click_handler():
    root = Path(__file__).resolve().parents[1]
    source = resolve_reference_file(root, ".codex/Client/Source/reference_trade_window.cpp").read_text(encoding="utf-8")
    click_handler = next(
        function for function in audit.cpp_functions(source)
        if function["class"] == "GTradeWindow" and function["method"] == "OnMouseClick"
    )
    assert "return GUI::EEventStatus::Handled;" in click_handler["body"]
    assert "in_pCaller" not in click_handler["body"]
    assert "__super::OnMouseClick" not in click_handler["body"]

    source_controls = {
        "Trade_Window/frmTitle/btnExit": "none (local trade view close)",
        "Trade_Window/frmTitle/btnApply": "none (local trade view selection)",
        "Trade_Window/frmInner/frmList/lstTrade": "none (local offer selection)",
        "Trade_Window/frmInner/frmList/btnViewTrade": "none (local trade detail navigation)",
    }
    with (root / "docs/ui/reference/interaction_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source_file:
        rows = {
            row["component_path"]: row
            for row in csv.DictReader(source_file)
            if row["window_id"] == "Trade_Window"
        }

    for path, expected_action in source_controls.items():
        binding = audit.TRADE_INTERACTION_BINDINGS[path]
        row = rows[path]
        assert binding["status"] == row["status"] == "partial"
        assert binding["game_action"] == row["game_action"] == expected_action
        assert row["reference_callback"].endswith("trade_window.cpp:114")
        assert "immediately returns Handled" in row["reference_side_effect"]
        assert "does not call the base close handler" in row["action_required"] or path.endswith(
            ("btnApply", "lstTrade", "btnViewTrade")
        )

    journey = json.loads((root / "tests/ui/journeys/bilateral-trade.json").read_text(encoding="utf-8"))
    operations = {
        step.get("target")
        for step in journey["steps"]
        if step.get("op") in {"click", "select"}
    }
    assert "trade.page.offers" in operations
    assert "trade.deal.view" in operations


def test_trade_detail_data_slots_match_source_controls_and_hide_the_unit_tab():
    root = Path(__file__).resolve().parents[1]
    bindings = audit.TRADE_DETAILED_BINDINGS
    with (root / "docs/ui/reference/data_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source_file:
        rows = [
            row for row in csv.DictReader(source_file)
            if row["window_id"] == "Trade_Detailed_Window"
        ]

    mapped_rows = {
        row["component_path"].removeprefix("Trade_Detailed_Window/"): row
        for row in rows
    }
    assert set(mapped_rows) >= set(bindings)
    for path, binding in bindings.items():
        row = mapped_rows[path]
        assert row["openpower_state_binding"] == binding.state_binding
        assert row["openpower_binding_status"] == binding.status
        assert row["status"] == binding.status
        assert row["action_required"] == binding.action_required
    assert not any(row["status"] == "assumption/unknown" for row in mapped_rows.values())

    cpp = resolve_reference_file(root, ".codex/Client/Source/reference_trade_detailed_window.cpp").read_text(encoding="utf-8")
    panel = (root / "src/client/ui/panels/trade_panel.py").read_text(encoding="utf-8")
    assert "m_vTabButtons[TAB_UNITS_IDX]->Hide();" in cpp
    assert '("unit", "Units")' not in panel
    assert 'elif self.asset_category == "unit"' not in panel

    unit_paths = [path for path in bindings if "/Tab4/" in path]
    assert len(unit_paths) == 8
    assert all(bindings[path].status == "verified_unavailable" for path in unit_paths)
    journey = json.loads((root / "tests/ui/journeys/trade-units-unavailable.json").read_text(encoding="utf-8"))
    assert sum(step.get("op") == "assert_absent" for step in journey["steps"]) == 6


def test_objectives_list_is_read_only_with_a_disabled_completion_indicator():
    root = Path(__file__).resolve().parents[1]
    path = "Objectives_Window/frmInner/frmInner/tabInfo/Tab2/frmObjectives/lstGoals"
    binding = audit.OBJECTIVES_INTERACTION_BINDINGS[path]

    assert binding["status"] == "verified_openpower"
    assert binding["game_action"] == "none (read-only objective display)"
    assert "disabled completion toggles" in binding["reference_side_effect"]
    assert "no source action" in binding["reference_side_effect"]
    assert "read-only rows" in binding["openpower_effect"]

    cpp = resolve_reference_file(root, ".codex/Client/Source/reference_frame_scenario.cpp").read_text(encoding="utf-8")
    window_cpp = resolve_reference_file(root, ".codex/Client/Source/reference_objectives_window.cpp").read_text(encoding="utf-8")
    panel = (root / "src/client/ui/panels/service/objectives_panel.py").read_text(encoding="utf-8")
    content = (root / "src/client/ui/panels/service/objectives_window_content.py").read_text(encoding="utf-8")
    assert "m_pObjObjectiveList->Insert_New_Row()" in cpp
    assert "l_pObjectiveComplete->Enabled(false)" in cpp
    assert "m_pObjExitBtn" in window_cpp
    assert "ObjectivesWindowContent" in panel
    assert "for row in overview.objectives:" in content
    objective_renderer = content.split("    def _render_objective", maxsplit=1)[1]
    assert "imgui.selectable" not in objective_renderer
    assert "_render_completion_indicator" in objective_renderer
    assert "imgui.begin_disabled()" in content

    with (root / "docs/ui/reference/interaction_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        rows = list(csv.DictReader(source))
    row = next(item for item in rows if item["component_path"] == path)
    assert row["status"] == "verified_openpower"
    assert row["game_action"] == binding["game_action"]


def test_objectives_window_gml_content_slots_have_explicit_openpower_bindings():
    root = Path(__file__).resolve().parents[1]
    expected_paths = {
        "frmTitle/lblTitle",
        "frmInner/frmInner/frmInfo/txtTitle",
        "frmInner/frmInner/frmInfo/lblCountry",
        "frmInner/frmInner/frmInfo/lblTitle",
        "frmInner/frmInner/frmInfo/txtCountry",
        "frmInner/frmInner/tabInfo/Tab1/frmInner/txtDescription",
        "frmInner/frmInner/tabInfo/Tab2/frmObjectives/lblTimeLimit",
        "frmInner/frmInner/tabInfo/Tab2/frmObjectives/lblGoals",
        "frmInner/frmInner/tabInfo/Tab3/frmInner/txtTips",
    }
    bindings = audit.DISPLAY_BINDINGS_BY_WINDOW["Objectives_Window"]
    assert set(bindings) == expected_paths

    with (root / "docs/ui/reference/data_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        rows = {
            row["component_path"]: row for row in csv.DictReader(source)
            if row["window_id"] == "Objectives_Window"
        }

    for suffix in expected_paths:
        path = f"Objectives_Window/{suffix}"
        binding = bindings[suffix]
        row = rows[path]
        assert binding.status == "partial"
        assert row["status"] == binding.status
        assert row["openpower_binding_status"] == binding.status
        assert row["openpower_state_binding"] == binding.state_binding
        assert row["openpower_surface"] == binding.surface
        assert "localization/placeholder meaning is unresolved" not in row["what_is_displayed"]

    panel = (root / "src/client/ui/panels/service/objectives_panel.py").read_text(encoding="utf-8")
    content = (root / "src/client/ui/panels/service/objectives_window_content.py").read_text(encoding="utf-8")
    assert '"OBJECTIVES", x=x' in panel
    assert '"frmInner/frmInner/frmInfo/lblTitle", "SCENARIO"' in content
    assert '"frmInner/frmInner/frmInfo/lblCountry", "COUNTRY"' in content
    assert '"frmInner/frmInner/tabInfo/Tab2/frmObjectives/lblGoals"' in content
    assert '"frmInner/frmInner/tabInfo/Tab2/frmObjectives/lblTimeLimit"' in content
    assert '"frmInner/frmInner/tabInfo/Tab3/frmInner"' in content


def test_remaining_source_interactions_have_explicit_contracts_instead_of_unknown_statuses():
    root = Path(__file__).resolve().parents[1]
    with (root / "docs/ui/reference/interaction_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        rows = list(csv.DictReader(source))

    by_path = {row["component_path"]: row for row in rows}
    assert len(audit.REMAINING_INTERACTION_BINDINGS) == 29
    assert (
        audit.REMAINING_INTERACTION_BINDINGS["Unit_Movement_Denial/lstDenialList"]["status"]
        == "verified_openpower"
    )
    for path, binding in audit.REMAINING_INTERACTION_BINDINGS.items():
        assert path in by_path
        row = by_path[path]
        assert row["status"] == binding["status"]
        assert row["status"] != "assumption/unknown"
        for field in (
            "reference_side_effect",
            "openpower_surface",
            "openpower_effect",
            "game_action",
            "action_required",
        ):
            assert row[field] == binding[field]

    assert not any(row["status"] == "assumption/unknown" for row in rows)

    party_journey = json.loads(
        (root / "tests/ui/journeys/reference-new-game-party-selection.json").read_text(encoding="utf-8")
    )
    assert any(
        step.get("target") == "new_game.party_selection.party.ukr-opposition"
        for step in party_journey["steps"]
    )
    assert (root / "tests/ui/journeys/reference-movement-refusal-feedback.json").is_file()
    assert (root / "tests/ui/journeys/reference-multiplayer-input-dialog.json").is_file()


def test_budget_display_contracts_cover_source_fields_and_preserve_semantic_differences():
    root = Path(__file__).resolve().parents[1]
    with (root / "docs/ui/reference/data_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        rows = [
            row for row in csv.DictReader(source)
            if row["window_id"] == "Budget_Window"
        ]

    by_path = {row["component_path"].removeprefix("Budget_Window/"): row for row in rows}
    assert rows
    assert not any(row["openpower_binding_status"] == "assumption/unknown" for row in rows)
    for path, binding in audit.BUDGET_BINDINGS.items():
        assert path in by_path
        row = by_path[path]
        assert row["openpower_state_binding"] == binding.state_binding
        assert row["openpower_binding_status"] == binding.status

    imf_income = audit.BUDGET_BINDINGS["frmInner/frmIncome/txtImf"]
    assert imf_income.status == "partial"
    assert "reuses budget_imf_ratio" in imf_income.meaning
    assert audit.BUDGET_BINDINGS[
        "frmInner/frmExpenses/txtImf"
    ].status == "partial"
    assert audit.BUDGET_BINDINGS[
        "frmInner/frmExpenses/frmMeterHealthCare/picGreenMeter"
    ].units == "visual-only meter segment"


def test_credits_display_contracts_bind_every_roster_slot_and_leave_unmapped_gml_text_explicit():
    root = Path(__file__).resolve().parents[1]
    with (root / "docs/ui/reference/data_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        rows = [
            row for row in csv.DictReader(source)
            if row["window_id"] == "Credits_Window"
        ]

    by_path = {row["component_path"].removeprefix("Credits_Window/"): row for row in rows}
    assert len(audit.CREDITS_BINDINGS) == 98
    assert len(rows) == 98
    for path, binding in audit.CREDITS_BINDINGS.items():
        assert path in by_path
        assert by_path[path]["openpower_state_binding"] == binding.state_binding
        assert by_path[path]["openpower_binding_status"] == binding.status

    assert sum(binding.status == "partial" for binding in audit.CREDITS_BINDINGS.values()) == 98
    assert sum(binding.status == "verified_unavailable" for binding in audit.CREDITS_BINDINGS.values()) == 0
    section_path = "frmInner/frmCredits/frmInner/lblTitle5"
    modeling_path = "frmInner/frmCredits/frmInner/lblTitle23"
    assert "Art team" in audit.CREDITS_BINDINGS[section_path].state_binding
    assert "Modeling" in audit.CREDITS_BINDINGS[modeling_path].meaning
    assert audit.CREDITS_BINDINGS[section_path].status == "partial"
    assert audit.CREDITS_BINDINGS[modeling_path].status == "partial"
    contact_path = "frmInner/frmCredits/frmInner/lblTitle35"
    assert audit.CREDITS_BINDINGS[contact_path].status == "partial"
    assert "www.multimediarts.net" in audit.CREDITS_BINDINGS[contact_path].state_binding
    assert "inference" in audit.CREDITS_BINDINGS[contact_path].meaning
    copyright_path = "frmInner/frmCredits/frmInner/lblTitle91"
    assert audit.CREDITS_BINDINGS[copyright_path].status == "partial"
    assert "\u00a9 GolemLabs 2004" in audit.CREDITS_BINDINGS[copyright_path].state_binding
    assert "inference" in audit.CREDITS_BINDINGS[copyright_path].meaning


def test_research_display_contracts_separate_branch_metrics_from_missing_characteristic_data():
    root = Path(__file__).resolve().parents[1]
    with (root / "docs/ui/reference/data_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        rows = [
            row for row in csv.DictReader(source)
            if row["window_id"] == "Unit_Research_Window"
        ]

    by_path = {row["component_path"].removeprefix("Unit_Research_Window/"): row for row in rows}
    assert len(audit.UNIT_RESEARCH_DISPLAY_BINDINGS) == 94
    assert len(rows) == 94
    assert not any(row["status"] == "assumption/unknown" for row in rows)
    for path, binding in audit.UNIT_RESEARCH_DISPLAY_BINDINGS.items():
        assert path in by_path
        assert by_path[path]["openpower_state_binding"] == binding.state_binding
        assert by_path[path]["status"] == binding.status

    for metric in audit._UNIT_RESEARCH_METRICS[:3]:
        assert audit.UNIT_RESEARCH_DISPLAY_BINDINGS[
            f"frmDetails/tabResearch/Tab1/frmInner/frm{metric}"
        ].status == "partial"
        assert audit.UNIT_RESEARCH_DISPLAY_BINDINGS[
            f"frmDetails/tabResearch/Tab2/frmInner/frm{metric}"
        ].status == "partial"
        assert audit.UNIT_RESEARCH_DISPLAY_BINDINGS[
            f"frmDetails/tabResearch/Tab3/frmInner/frm{metric}"
        ].status == "partial"

    for metric in audit._UNIT_RESEARCH_METRICS[3:]:
        for page in ("Tab1", "Tab2", "Tab3"):
            assert audit.UNIT_RESEARCH_DISPLAY_BINDINGS[
                f"frmDetails/tabResearch/{page}/frmInner/frm{metric}"
            ].status == "verified_unavailable"

    advancement = audit.UNIT_RESEARCH_DISPLAY_BINDINGS[
        "frmMain/frmGroundFinancing/lblNextAdvancement"
    ]
    assert advancement.status == "partial"
    assert "token 100209" in advancement.meaning


def test_unit_design_display_contracts_keep_roles_and_capability_scales_explicit():
    root = Path(__file__).resolve().parents[1]
    with (root / "docs/ui/reference/data_contracts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        rows = list(csv.DictReader(source))

    binding_sets = {
        "Unit_Design_New": audit.UNIT_DESIGN_DISPLAY_BINDINGS,
        "Unit_New_Design": audit.UNIT_DESIGN_BUILDER_DISPLAY_BINDINGS,
    }
    for window, bindings in binding_sets.items():
        window_rows = [row for row in rows if row["window_id"] == window]
        by_path = {row["component_path"].removeprefix(window + "/"): row for row in window_rows}
        assert len(bindings) == len(window_rows)
        assert not any(row["status"] == "assumption/unknown" for row in window_rows)
        for path, binding in bindings.items():
            assert path in by_path
            assert by_path[path]["openpower_state_binding"] == binding.state_binding
            assert by_path[path]["status"] == binding.status
            assert binding.status in {"partial", "verified_unavailable"}
            if "/frm" in path and path.endswith(tuple(f"frm{name}" for name, _ in audit._UNIT_DESIGN_METERS)):
                assert "capability_catalog.py" in binding.openpower_source
                assert "source" in binding.meaning and "scale" in binding.meaning

    assert audit.UNIT_DESIGN_DISPLAY_BINDINGS[
        f"{audit._UNIT_DESIGN_OVERVIEW_METER_ROOT.removeprefix('Unit_Design_New/')}/frmGunRange"
    ].state_binding.startswith("capabilities_for_design")
    assert audit.UNIT_DESIGN_BUILDER_DISPLAY_BINDINGS[
        f"{audit._UNIT_DESIGN_BUILDER_METER_ROOT.removeprefix('Unit_New_Design/')}/frmGunRange"
    ].state_binding.startswith("UnitDesignEditor._capabilities_by_role")
    assert audit.UNIT_DESIGN_BUILDER_DISPLAY_BINDINGS[
        "frmBuild/frmPage/cboType"
    ].status == "verified_unavailable"


def test_source_reachability_ignores_unverified_and_disconnected_transitions():
    from utils.reference_audit_navigation import reachable_windows

    def edge(source, target, status='verified_cpp'):
        return dict(source_window=source, target_window=target, status=status)

    edges = [edge('root', 'a'), edge('a', 'root'), edge('a', 'b'),
             edge('root', 'unverified', 'assumption/unknown'),
             edge('disconnected', 'hidden'), edge('b', 'outside'), edge('outside', 'blocked')]
    assert reachable_windows(edges, ['root', 'a', 'b', 'disconnected'], ['root']) == {
        'root', 'a', 'b', 'outside',
    }

