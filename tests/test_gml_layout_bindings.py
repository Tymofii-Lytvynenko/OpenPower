"""Regression coverage for data-dependent relocation of live panel text."""
from unittest.mock import MagicMock, patch
from types import SimpleNamespace
import pytest

from src.client.ui.layouts.gml_layout import GMLLayoutSession, all_gml_layouts, get_gml_layout
from src.client.ui.core.primitives import UIPrimitives


def test_nonclosable_window_uses_no_native_open_pointer():
    from src.client.ui.core.containers import WindowManager
    native = MagicMock()
    native.get_io.return_value = SimpleNamespace(display_size=SimpleNamespace(x=800,y=600))
    native.WindowFlags_.no_collapse = 1
    native.begin.return_value = (True,None)
    with patch("src.client.ui.core.containers.imgui",native), \
         patch("src.client.ui.core.containers.resolve_gml_layout",return_value=None), \
         patch("src.client.ui.core.containers.active_telemetry",return_value=None):
        with WindowManager.window("Unclosable",closable=False) as opened:
            assert opened is True
    assert native.begin.call_args.args[1] is None


def test_begin_only_padding_does_not_pop_the_scoped_gml_spacing():
    from contextlib import contextmanager
    from src.client.ui.core.containers import WindowManager

    native, stack = MagicMock(), []
    native.get_io.return_value = SimpleNamespace(display_size=SimpleNamespace(x=1280, y=1080))
    native.get_window_pos.return_value = SimpleNamespace(x=0, y=0)
    native.get_window_size.return_value = SimpleNamespace(x=1024, y=768)
    native.WindowFlags_.no_collapse = 1
    native.begin.return_value = (True, None)
    native.push_style_var.side_effect = lambda *args: stack.append("padding")
    native.pop_style_var.side_effect = lambda count=1: [stack.pop() for _ in range(count)]

    @contextmanager
    def styles():
        stack.extend(("frame", "spacing"))
        yield
        assert stack == ["frame", "spacing"]
        stack.clear()

    with patch("src.client.ui.core.containers.imgui", native), \
         patch("src.client.ui.core.containers.resolve_gml_layout", return_value=get_gml_layout("Battle_Window")), \
         patch("src.client.ui.core.containers.active_telemetry", return_value=None), \
         patch("src.client.ui.core.containers.gml_style", styles):
        with WindowManager.window("Canvas", closable=False, padding=(0, 0)):
            assert stack == ["frame", "spacing"]
    assert not stack


@pytest.mark.parametrize("failure", ["begin", "placement"])
def test_window_unwinds_styles_when_initialization_fails(failure):
    from contextlib import contextmanager
    from src.client.ui.core.containers import WindowManager

    native = MagicMock()
    native.get_io.return_value = SimpleNamespace(display_size=SimpleNamespace(x=1280, y=1080))
    native.WindowFlags_.no_collapse = 1
    native.begin.return_value = (True, True)
    if failure == "begin":
        native.begin.side_effect = RuntimeError("begin failed")
    exits = []

    @contextmanager
    def styles():
        try:
            yield
        finally:
            exits.append(True)

    placement_error = RuntimeError("placement failed") if failure == "placement" else None
    with patch("src.client.ui.core.containers.imgui", native), \
         patch("src.client.ui.core.containers.resolve_gml_layout", return_value=get_gml_layout("Battle_Window")), \
         patch("src.client.ui.core.containers.active_telemetry", return_value=None), \
         patch("src.client.ui.core.containers.gml_style", styles), \
         patch.object(WindowManager, "_update_placement", side_effect=placement_error):
        with pytest.raises(RuntimeError):
            with WindowManager.window("Canvas", padding=(0, 0)):
                pass

    native.pop_style_var.assert_called_once()
    assert exits == [True]
    assert native.end.call_count == (1 if failure == "placement" else 0)


def test_custom_title_hides_native_imgui_id_suffix():
    from src.client.ui.layouts.gml_layout import render_gml_title
    native = MagicMock()
    native.get_window_pos.return_value = SimpleNamespace(x=100, y=100)
    layout = get_gml_layout("Country_Information_Window")
    with patch("src.client.ui.core.instrumented_imgui.imgui", native):
        render_gml_title(layout, "UKRAINE##COUNTRY_MORE_INFO")
    assert native.text_colored.call_args.args[1] == "UKRAINE"


def test_live_text_does_not_steal_a_source_slot():
    layout = get_gml_layout("Economic_Window")
    slot = "Economic_Window/frmInner/frmBudget/txtIncome"
    component = layout.component(slot)
    assert component is not None
    for country_value in ("INCOME", "$ 17 235 403 775", "Unknown", "more"):
        session = GMLLayoutSession(layout, (100, 200), (244, 337))
        native = MagicMock()
        native.get_scroll_x.return_value = 0
        native.get_scroll_y.return_value = 0
        native.calc_text_size.side_effect = lambda text, **_kwargs: SimpleNamespace(
            x=len(text) * 6.0,
            y=9.0,
        )
        native.get_font_size.return_value = 9.0
        with patch("src.client.ui.core.instrumented_imgui.imgui", native):
            assert session.place_widget("text", (country_value,)) is None
            native.set_cursor_screen_pos.assert_not_called()
            session.place_widget("text", (country_value,), explicit_id=slot)
            rect = session.rect_for(component)
            expected = (
                100.0 + rect.x + rect.width
                - len(country_value) * 6.0 + component.text_offset[0],
                200.0 + rect.y + (rect.height - 9.0) / 2.0,
            )
            native.set_cursor_screen_pos.assert_called_once_with(expected)


def test_credits_text_uses_gml_font_alignment_and_offset_metadata():
    layout = get_gml_layout("Credits_Window")
    component = layout.component(
        "Credits_Window/frmInner/frmCredits/frmInner/lblTitle1"
    )
    assert component is not None
    assert component.font_size == 9.0
    assert component.text_align == "MiddleRight"
    assert component.text_offset == (-3.0, 0.0)

    session = GMLLayoutSession(layout, (100.0, 200.0), (568.0, 580.0))
    native = MagicMock()
    native.get_scroll_x.return_value = native.get_scroll_y.return_value = 0.0
    native.calc_text_size.return_value = SimpleNamespace(x=12.0, y=9.0)
    native.get_font_size.return_value = 9.0
    with patch("src.client.ui.core.instrumented_imgui.imgui", native):
        session.place_widget(
            "text",
            ("CEO",),
            explicit_id="Credits_Window/frmInner/frmCredits/frmInner/lblTitle1",
        )
    rect = session.rect_for(component)
    expected = (
        100.0 + rect.x + rect.width - 12.0 + component.text_offset[0],
        200.0 + rect.y + (rect.height - 9.0) / 2.0,
    )
    native.set_cursor_screen_pos.assert_called_once_with(expected)


def test_gml_widgets_inherit_source_font_when_no_override_is_passed():
    from src.client.ui.core.gml_widgets import GMLWidgets

    layout = get_gml_layout("Credits_Window")
    session = GMLLayoutSession(layout, (0.0, 0.0), (568.0, 580.0))
    native = MagicMock()
    native.get_style.return_value = SimpleNamespace(
        font_scale_main=1.0,
        font_scale_dpi=1.0,
    )
    native.is_item_hovered.return_value = False
    widgets = GMLWidgets("Credits_Window/frmInner/frmCredits/frmInner")
    with patch("src.client.ui.core.gml_widgets.imgui", native), \
         patch("src.client.ui.core.gml_widgets.active_gml_layout", return_value=session), \
         patch("src.client.ui.core.gml_widgets.UIPrimitives.fit_text", side_effect=lambda text, _width: text):
        widgets.text("lblTitle1", "CEO")

    native.push_font.assert_called_once_with(None, 9.0)
    native.pop_font.assert_called_once()


def test_text_after_an_explicit_field_keeps_the_flow_cursor():
    layout = get_gml_layout("Politic_Window")
    session = GMLLayoutSession(layout, (0, 0), (244, 408))
    native = MagicMock()
    native.get_scroll_x.return_value = 0
    native.get_scroll_y.return_value = 0
    with patch("src.client.ui.core.instrumented_imgui.imgui", native):
        session.place_widget("text", ("APPROVAL",),
                             explicit_id="Politic_Window/frmInner/frmApproval/lblTitle")
        native.set_cursor_screen_pos.reset_mock()
        # This used to consume the next sibling, despite being additional live data.
        assert session.place_widget("text", ("Active treaties: 1",)) is None
        native.set_cursor_screen_pos.assert_not_called()


def test_value_rows_do_not_jump_back_to_the_first_table_column():
    native = MagicMock()
    native.get_cursor_pos_x.return_value = 360.0
    native.get_content_region_avail.return_value = SimpleNamespace(x=228.0)
    native.calc_text_size.side_effect = lambda text: SimpleNamespace(x=len(text) * 6.0)
    with patch("src.client.ui.core.primitives.imgui", native):
        UIPrimitives.value_row("Life expectancy", "74.5", label_width=130.0)
    assert native.same_line.call_args.args[0] >= 360.0
    assert native.set_cursor_pos_x.call_args.args[0] >= 360.0


def test_runtime_enable_does_not_change_initial_gml_state():
    layout = get_gml_layout("Unit_List_Window")
    path = "Unit_List_Window/frmInner/frmActions/btnSplit"
    session = GMLLayoutSession(layout,(0,0),(343,492))
    native = MagicMock()
    native.get_scroll_x.return_value = native.get_scroll_y.return_value = 0
    assert layout.component(path).enabled is False
    with patch("src.client.ui.core.instrumented_imgui.imgui",native):
        placed = session.place_widget("button",("Split",),explicit_id=path,enabled_override=True)
    assert placed[1].enabled is True
    assert layout.component(path).enabled is False


def test_source_trade_offer_list_uses_its_own_gml_window_and_slots():
    layout = get_gml_layout("Trade_Window")
    assert (layout.width, layout.height) == (630, 245)
    assert len(all_gml_layouts()) >= 92

    session = GMLLayoutSession(layout, (40, 60), (630, 245))
    list_rect = session.rect_for("Trade_Window/frmInner/frmList/lstTrade")
    view_rect = session.rect_for("Trade_Window/frmInner/frmList/btnViewTrade")
    assert (list_rect.x, list_rect.y, list_rect.width, list_rect.height) == (32, 56, 574, 149)
    assert (view_rect.x, view_rect.y, view_rect.width, view_rect.height) == (507, 209, 100, 18)


def test_base_window_moves_apply_into_the_hidden_lock_slot():
    layout = get_gml_layout("Constitutional_Form")
    session = GMLLayoutSession(layout, (0, 0), (352, 153))
    apply = "Constitutional_Form/frmTitle/btnApply"
    lock = "Constitutional_Form/frmTitle/togLockWindow"
    source_apply_x = layout.component(apply).local_rect.x
    source_lock_x = layout.component(lock).local_rect.x

    session.apply_base_window_titlebar_rules()

    assert source_apply_x != source_lock_x
    assert session.rect_for(apply).x == session.rect_for(lock).x
    assert layout.component(apply).local_rect.x == source_apply_x


def test_derived_base_window_anchors_inherited_title_and_shadow_to_derived_size():
    layout = get_gml_layout("Economic_Health_Window")
    session = GMLLayoutSession(layout, (0, 0), (layout.width, layout.height))

    title = session.rect_for("Economic_Health_Window/frmTitle")
    close = session.rect_for("Economic_Health_Window/frmTitle/btnExit")
    shadow = session.rect_for("Economic_Health_Window/picShadowGradient")

    assert (layout.width, layout.height) == (264, 333)
    assert (title.x, title.width) == (18, 242)
    assert close.x + close.width <= layout.width
    assert shadow.y + shadow.height <= layout.height


def test_wide_derived_base_window_expands_inherited_title_to_outer_frame():
    layout = get_gml_layout("Treaty_Details_Window")
    session = GMLLayoutSession(layout, (0, 0), (layout.width, layout.height))
    title = session.rect_for("Treaty_Details_Window/frmTitle")
    close = session.rect_for("Treaty_Details_Window/frmTitle/btnExit")

    assert title.x + title.width == layout.width - 4
    assert close.x + close.width <= layout.width - 4


def test_invisible_button_can_bind_to_source_toggle_geometry():
    layout = get_gml_layout("Advisor_Settings_Window")
    session = GMLLayoutSession(layout, (500, 100), (268, 132))
    path = "Advisor_Settings_Window/frmInner/frmSettings/togPoliManual"
    native = MagicMock()
    native.get_scroll_x.return_value = native.get_scroll_y.return_value = 0

    with patch("src.client.ui.core.instrumented_imgui.imgui", native):
        placed = session.place_widget(
            "invisible_button",
            ("##advisor_politics_manual", (7.0, 7.0)),
            explicit_id=path,
        )

    assert placed is not None
    assert placed[0][1] == (7.0, 7.0)
    native.set_cursor_screen_pos.assert_called_once_with((679.0, 169.0))


def test_horizontal_subtree_scale_keeps_child_geometry_inside_compact_window():
    layout = get_gml_layout("Unit_Production_Window")
    session = GMLLayoutSession(layout, (0, 0), (800, 462))
    right_path = "Unit_Production_Window/frmRight"
    source_right = session.rect_for(right_path)
    factor = (800.0 - source_right.x) / source_right.width

    session.scale_subtree_x(right_path, factor)

    right = session.rect_for(right_path)
    priority = session.rect_for(
        "Unit_Production_Window/frmRight/frmProduction/lblPriority"
    )
    production_list = session.rect_for(
        "Unit_Production_Window/frmRight/frmProduction/lstProduction"
    )
    assert right.x == source_right.x
    assert right.x + right.width == 800.0
    assert priority.x + priority.width <= 800.0
    assert production_list.x + production_list.width <= 800.0


def test_picture_slot_follows_source_canvas_scroll_and_restores_cursor():
    from src.client.ui.core.gml_widgets import GMLWidgets
    layout = get_gml_layout("Battle_Window")
    session = GMLLayoutSession(layout, (100, 200), (1024, 768))
    ui = GMLWidgets("Battle_Window")
    slot = "frmTrimYou/frmFlagYou/picFlag"
    rect = session.rect_for(layout.component(ui.path(slot)))
    native, draw = MagicMock(), MagicMock()
    native.get_scroll_x.return_value = 13
    native.get_scroll_y.return_value = 27
    native.get_cursor_screen_pos.return_value = (50, 60)
    with patch("src.client.ui.core.gml_widgets.imgui", native), \
         patch("src.client.ui.core.gml_widgets.active_gml_layout", return_value=session):
        ui.picture(slot, draw)
    assert native.set_cursor_screen_pos.call_args_list[0].args[0] == (100 + rect.x - 13, 200 + rect.y - 27)
    assert native.set_cursor_screen_pos.call_args_list[-1].args[0] == (50, 60)
    draw.assert_called_once_with(rect.width, rect.height)


def test_legacy_imgui_positions_do_not_override_gml_window_defaults(tmp_path):
    from imgui_bundle import imgui as native
    from src.client.ui.core.containers import WindowManager
    from src.client.ui.core.instrumented_imgui import imgui
    from src.client.ui.layouts.gml_layout import get_gml_layout

    ini_path = tmp_path / "imgui.ini"
    ini_path.write_text(
        "\n".join(
            (
                "[Window][POLITICS]", "Pos=22,134", "Size=240,520", "Collapsed=0",
                "[Window][MILITARY]", "Pos=710,296", "Size=257,440", "Collapsed=0",
                "[Window][ECONOMY]", "Pos=1261,261", "Size=260,450", "Collapsed=0",
                "[Window][Treaties]", "Pos=900,350", "Size=760,480", "Collapsed=0",
            )
        ),
        encoding="utf-8",
    )
    context = native.create_context()
    try:
        io = native.get_io()
        io.display_size = native.ImVec2(1902.0, 991.0)
        io.display_framebuffer_scale = native.ImVec2(1.0, 1.0)
        io.delta_time = 1.0 / 60.0
        io.backend_flags |= native.BackendFlags_.renderer_has_textures
        io.set_ini_filename(str(ini_path))
        native.load_ini_settings_from_disk(str(ini_path))
        native.new_frame()
        viewport_width = 1902.0
        cases = (
            ("POLITICS", "politics.panel", "Politic_Window", 0.0, 0.0, {}),
            ("MILITARY", "military.panel", "Military_Window", 700.0, 164.0, {}),
            (
                "ECONOMY", "economy.panel", "Economic_Window", 0.0, 130.0,
                {"horizontal_anchor": "right", "horizontal_margin": 19.0},
            ),
            ("Treaties", "treaties.panel", "Treaties_Window", 260.0, 18.0, {}),
        )
        rectangles = {}
        for title, test_id, template, expected_x, expected_y, options in cases:
            layout = get_gml_layout(template)
            if template == "Economic_Window":
                expected_x = viewport_width - layout.width - options["horizontal_margin"]
            with WindowManager.window(
                title,
                x=expected_x,
                y=expected_y,
                w=layout.width,
                h=layout.height,
                test_id=test_id,
                gml_template=template,
                **options,
            ) as opened:
                assert opened
                position = imgui.get_window_pos()
                assert (position.x, position.y) == (expected_x, expected_y)
                rectangles[test_id] = (
                    position.x,
                    position.y,
                    layout.width,
                    layout.height,
                )
        rectangles = list(rectangles.values())
        for index, first in enumerate(rectangles):
            for second in rectangles[index + 1:]:
                assert not (
                    first[0] < second[0] + second[2]
                    and second[0] < first[0] + first[2]
                    and first[1] < second[1] + second[3]
                    and second[1] < first[1] + first[3]
                )
        native.end_frame()
    finally:
        native.destroy_context(context)


def test_generic_question_retains_source_bounds_and_multiline_text_alignment():
    layout = get_gml_layout("Generic_Question_Window")
    assert (layout.width, layout.height) == (267, 130)
    label = layout.component("lblMessage")
    assert (label.rect.x, label.rect.y, label.rect.width, label.rect.height) == (12, 10, 241, 86)
    assert label.text_offset == (2., 0.) and label.text_align == "MiddleLeft"
    assert layout.component("btnOk").rect.x == 24
    assert layout.component("btnCancel").rect.x == 136
    native = MagicMock()
    native.get_scroll_x.return_value = native.get_scroll_y.return_value = 0
    native.calc_text_size.return_value = SimpleNamespace(x=120., y=48.)
    session = GMLLayoutSession(layout, (100, 200), (267, 130))
    with patch("src.client.ui.core.instrumented_imgui.imgui", native):
        session.place_widget("text_wrapped", ("Question\nbody",), explicit_id=label.path)
    native.set_cursor_screen_pos.assert_called_once_with((114., 229.))
    native.calc_text_size.assert_called_once_with("Question\nbody", wrap_width=239.)


def test_unit_reserve_tabs_use_exported_gml_metrics_and_runtime_page_offset():
    layout = get_gml_layout("Unit_Ground_Deployment_Window")
    tab_path = "Unit_Ground_Deployment_Window/frmInner/tabGroups"
    tab_component = layout.component(tab_path)
    assert tab_component is not None and tab_component.tab_layout is not None

    tab = tab_component.tab_layout
    assert (tab.button_width, tab.button_height) == (71.0, 16.0)
    assert (tab.button_distance, tab.button_offset_left, tab.frame_offset_top) == (\
        -1.0, 0.0, -1.0,
    )
    assert tab.tab_names == ("101131", "101129", "101130", "101132")
    assert tab.page_offset_y == 17.0

    session = GMLLayoutSession(layout, (0.0, 0.0), (507.0, 390.0))
    buttons = [session.tab_button_rect(tab_path, index) for index in range(4)]
    assert [(rect.x, rect.y, rect.width, rect.height) for rect in buttons] == [
        (28.0, 70.0, 71.0, 16.0),
        (98.0, 70.0, 71.0, 16.0),
        (168.0, 70.0, 71.0, 16.0),
        (238.0, 70.0, 71.0, 16.0),
    ]

    list_path = f"{tab_path}/Tab4/lstDeploy"
    assert layout.component(list_path).rect.y == 77.0
    assert session.apply_tab_page_runtime_geometry(tab_path) == tab
    assert session.rect_for(list_path).y == 94.0
    assert layout.component(list_path).rect.y == 77.0
