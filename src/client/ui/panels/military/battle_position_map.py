"""Draw actual battle-force coordinates inside a source map frame."""
import math

from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.panels.shared.panel_widgets import draw_empty_state


def render_battle_positions(groups, own_side="A", *, selected_force=None, on_select=None):
    points = [
        (group["country_id"], group["side"], group["unit_type"], index, float(lat), float(lon))
        for group in groups
        for index, (lat, lon) in enumerate(group["relative_positions"])
        if math.isfinite(float(lat)) and math.isfinite(float(lon))
    ]
    if not points:
        draw_empty_state("No observed force coordinates are available.")
        return
    # A battle spanning the antimeridian is still local. Unwrap longitudes
    # around the first observation rather than drawing a nearly global spread.
    anchor_lon = points[0][5]
    points = [
        (country, side, unit_type, index, lat, anchor_lon + (lon - anchor_lon + 180) % 360 - 180)
        for country, side, unit_type, index, lat, lon in points
    ]
    start = imgui.get_cursor_screen_pos()
    size = imgui.get_content_region_avail()
    width, height = max(1.0, size.x), max(1.0, size.y)
    lat_min, lat_max = min(p[4] for p in points), max(p[4] for p in points)
    lon_min, lon_max = min(p[5] for p in points), max(p[5] for p in points)
    draw = imgui.get_window_draw_list()
    for country, side, unit_type, index, lat, lon in points:
        x = start.x + 12 + (width - 24) * ((lon - lon_min) / (lon_max - lon_min) if lon_max != lon_min else 0.5)
        y = start.y + 12 + (height - 24) * (1 - (lat - lat_min) / (lat_max - lat_min) if lat_max != lat_min else 0.5)
        color = (0.3, 0.75, 1.0, 1.0) if side.removeprefix("SIDE_") == own_side else (1.0, 0.5, 0.3, 1.0)
        imgui.set_cursor_screen_pos((x - 5, y - 5))
        marker = f"{country}.{unit_type}.{index}"
        if imgui.invisible_button(
            "##battle_map_" + marker, (10.0, 10.0), test_id=f"battle.inspection.map.{marker}",
        ) and on_select is not None:
            on_select((country, unit_type))
        if imgui.is_item_hovered():
            imgui.set_tooltip(f"{country} · {unit_type}")
        draw.add_circle_filled((x, y), 4.0, imgui.get_color_u32(color))
        if selected_force == (country, unit_type):
            draw.add_circle((x, y), 7.0, imgui.get_color_u32((1.0, 0.95, 0.4, 1.0)))
        if len(points) < 12:
            draw.add_text((min(x + 6, start.x + width - 30), y - 6), imgui.get_color_u32(color), country)
    imgui.set_cursor_screen_pos(start)
    imgui.dummy((width, height))
