from utils.reference_cpp_parser import cpp_functions, find_matching


def test_matching_ignores_delimiters_in_strings_and_comments():
    text = '{ "}"; /* } */ if (ok) { call(); } // }\n return; }'
    assert find_matching(text, 0, "{", "}") == len(text) - 1
    assert find_matching("{ incomplete", 0, "{", "}") == -1


def test_extracts_complete_methods_and_skips_declarations():
    source = 'void Window::First();\nvoid Window::Second() { const char *s = "}"; if (ok) { run(); } }'
    methods = list(cpp_functions(source))
    assert [(method["class"], method["method"]) for method in methods] == [("Window", "Second")]
    assert 'const char *s = "}"' in methods[0]["body"]
    assert "run();" in methods[0]["body"]
