from utils.reference_gml_validation import _validate_gml, _walk


def test_catalog_validation_reports_unknown_types_and_inheritance_cycles(tmp_path):
    source = tmp_path / "layout_catalog.gml"
    source.write_text(
        "<ROOT><OBJECT><NAME>A</NAME><BASE>B</BASE>"
        "<OBJECT><NAME>child</NAME><TYPE>unknown_widget</TYPE></OBJECT></OBJECT>"
        "<OBJECT><NAME>B</NAME><BASE>A</BASE></OBJECT></ROOT>",
        encoding="utf-8",
    )
    catalog = {"templates": {
        "A": {"name": "A", "children": [{"name": "child"}]},
        "B": {"name": "B"},
    }}
    report = _validate_gml(source, catalog)
    assert report["definition_count"] == 2
    assert report["resolved_catalog_node_count"] == 3
    assert report["unknown_root_names"] == []
    assert report["unknown_gml_types"] == ["unknown_widget"]
    assert report["inheritance_cycles"] == [["A", "B", "A"]]
    assert [item["path"] for item in _walk("A", catalog["templates"]["A"])] == ["A", "A/child"]
