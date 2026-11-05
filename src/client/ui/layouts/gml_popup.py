"""Source-sized modal scope shared by composed question dialogs."""
from contextlib import contextmanager
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.testability import semantic_region
from src.client.ui.layouts.gml_layout import (
    create_gml_layout_session,
    get_gml_layout,
    gml_style,
    gml_titlebar_close,
    render_gml_title,
    use_gml_layout,
)
from src.client.ui.layouts.gml_message_geometry import (
    GMLMessageGeometry,
    apply_gml_message_geometry,
)


@contextmanager
def gml_popup_modal(
    popup_id,
    template,
    *,
    title=None,
    test_id=None,
    message_geometry: GMLMessageGeometry | None = None,
    movable=False,
):
    layout = get_gml_layout(template)
    viewport = imgui.get_main_viewport()
    imgui.set_next_window_pos(viewport.get_center(), imgui.Cond_.appearing, imgui.ImVec2(.5, .5))
    window_height = message_geometry.window_height if message_geometry is not None else layout.height
    imgui.set_next_window_size((layout.width, window_height), imgui.Cond_.appearing)
    flags = (imgui.WindowFlags_.no_title_bar | imgui.WindowFlags_.no_resize
             | imgui.WindowFlags_.no_saved_settings)
    if not movable:
        flags |= imgui.WindowFlags_.no_move
    with gml_style():
        imgui.push_style_var(imgui.StyleVar_.window_padding, (0, 0))
        try:
            opened, _ = imgui.begin_popup_modal(popup_id, None, flags)
        finally:
            imgui.pop_style_var()
        popup_begun = bool(opened)
        try:
            if not opened:
                if test_id:
                    with semantic_region(test_id, title or template, visible=False):
                        yield False
                else:
                    yield False
            else:
                position, size = imgui.get_window_pos(), imgui.get_window_size()
                session = create_gml_layout_session(template, (position.x, position.y), (size.x, size.y))
                if message_geometry is not None:
                    apply_gml_message_geometry(session, message_geometry)
                with use_gml_layout(session):
                    if title:
                        render_gml_title(layout, title, session)
                        close_component = gml_titlebar_close(layout)
                        if close_component is None:
                            close_component = next(
                                (
                                    component for component in layout.components
                                    if component.component_id == "btnExit"
                                    and "/frmTitle/" in component.path
                                ),
                                None,
                            )
                        if close_component is not None:
                            close_rect = session.rect_for(close_component)
                            # Some source dialogs retain a shared title-bar slot wider than their content root.
                            # Keep the GML root dimensions exact and bring only that close hitbox into the popup.
                            close_x = min(
                                max(float(close_rect.x), 0.0),
                                max(0.0, float(size.x) - float(close_rect.width)),
                            )
                            close_y = min(
                                max(float(close_rect.y), 0.0),
                                max(0.0, float(size.y) - float(close_rect.height)),
                            )
                            imgui.set_cursor_screen_pos((
                                float(position.x) + close_x,
                                float(position.y) + close_y,
                            ))
                            close_id = f"{test_id}.close" if test_id else f"gml.{template}.close"
                            if imgui.button("×", (close_rect.width, close_rect.height), test_id=close_id):
                                imgui.close_current_popup()
                                opened = False
                            inner_frame = layout.component("frmInner")
                            if inner_frame is not None:
                                inner_rect = session.rect_for(inner_frame)
                                imgui.set_cursor_screen_pos((
                                    float(position.x) + inner_rect.x,
                                    float(position.y) + inner_rect.y,
                                ))
                    if test_id:
                        with semantic_region(test_id, title or template, visible=opened):
                            yield opened
                    else:
                        yield opened
        finally:
            if popup_begun:
                if title:
                    # Absolute GML title coordinates need a submitted item to finalize popup bounds.
                    imgui.dummy((1.0, 1.0))
                imgui.end_popup()
