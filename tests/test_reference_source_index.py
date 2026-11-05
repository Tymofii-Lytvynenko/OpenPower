from utils.reference_source_index import _source_index


def test_indexes_registered_window_inheritance_and_spawn_call(tmp_path):
    source = tmp_path / "Client" / "Source"
    headers = tmp_path / "Client" / "Include"
    source.mkdir(parents=True)
    headers.mkdir()
    (headers / "window.h").write_text("class GChild : public GBaseWindow {};", encoding="utf-8")
    (source / "window.cpp").write_text(
        'const GString GChild::TypeName(L"Child_Window");\n'
        'void GChild::Open() { g_ClientDDL.ChildWindowSpawn(); }\n', encoding="utf-8"
    )
    (source / "data_display_layer.cpp").write_text(
        'REGISTER_GUI_OBJECT(GChild)\n'
        'bool GDataDisplayLayer::ChildWindowSpawn() { return GChild::TypeName; }\n', encoding="utf-8"
    )
    index = _source_index(source)
    assert index["base_classes"]["GChild"] == {"GBaseWindow"}
    assert "GChild" in index["registered_classes"]
    assert index["spawn_templates"]["ChildWindowSpawn"] == "Child_Window"
    assert index["spawn_calls"]["ChildWindowSpawn"][0]["target"] == "Child_Window"


def test_spawn_call_location_keeps_multiline_comment_lines(tmp_path):
    source = tmp_path / "Client" / "Source"
    source.mkdir(parents=True)
    (source / "window.cpp").write_text(
        "/* a comment\nwith a second line\n*/\n"
        "// g_ClientDDL.HiddenWindowSpawn();\n"
        "g_ClientDDL.VisibleWindowSpawn();\n",
        encoding="utf-8",
    )
    calls = _source_index(source)["spawn_calls"]
    assert calls["VisibleWindowSpawn"][0]["line"] == 5
    assert "HiddenWindowSpawn" not in calls


def test_spawn_scanner_ignores_literals_without_losing_following_code(tmp_path):
    source = tmp_path / "Client" / "Source"
    source.mkdir(parents=True)
    (source / "window.cpp").write_text(
        'auto url = "https://example.test"; g_ClientDDL.RealWindowSpawn();\n'
        'auto sample = "g_ClientDDL.FakeWindowSpawn()";\n'
        'auto raw = R"tag(g_ClientDDL.RawWindowSpawn(); // text)tag";\n'
        "auto count = 1'000; g_ClientDDL.AnotherWindowSpawn();\n",
        encoding="utf-8",
    )
    calls = _source_index(source)["spawn_calls"]
    assert set(calls) == {"RealWindowSpawn", "AnotherWindowSpawn"}
    assert calls["RealWindowSpawn"][0]["line"] == 1
    assert calls["AnotherWindowSpawn"][0]["line"] == 4
