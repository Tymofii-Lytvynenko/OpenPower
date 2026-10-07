#version 330

in vec2 v_uv;
out vec4 out_color;

uniform sampler2D u_map_texture;
uniform sampler2D u_lookup_texture;
uniform sampler2D u_previous_lookup_texture;
uniform sampler2D u_terrain_texture;
uniform float u_lut_dim;
uniform int u_selected_id;
uniform int u_overlay_mode;
uniform float u_opacity;
uniform float u_overlay_transition;
uniform vec2 u_viewport_size;
uniform vec2 u_map_size;
uniform vec2 u_map_center;
uniform vec2 u_pan;
uniform float u_zoom;

int decode_dense_id(vec3 encoded_id) {
    ivec3 channels = ivec3(encoded_id * 255.0 + 0.5);
    return (channels.r << 16) | (channels.g << 8) | channels.b;
}

vec2 lookup_uv(int dense_id) {
    float dimension = u_lut_dim;
    vec2 coordinate = vec2(
        float(dense_id % int(dimension)),
        float(dense_id / int(dimension))
    );
    return (coordinate + vec2(0.5)) / vec2(dimension);
}

void main() {
    float fit_scale = min(
        u_viewport_size.x / u_map_size.x,
        u_viewport_size.y / u_map_size.y
    );
    vec2 screen_offset = gl_FragCoord.xy - u_viewport_size * 0.5 - u_pan;
    vec2 map_uv = u_map_center + screen_offset / (u_map_size * fit_scale * u_zoom);
    if (any(lessThan(map_uv, vec2(0.0))) || any(greaterThanEqual(map_uv, vec2(1.0)))) {
        out_color = vec4(0.015, 0.025, 0.04, 1.0);
        return;
    }

    vec3 terrain_color = texture(u_terrain_texture, map_uv).rgb;
    vec4 map_data = texture(u_map_texture, map_uv);
    int dense_id = decode_dense_id(map_data.rgb);
    vec2 palette_uv = lookup_uv(dense_id);
    vec4 current_color = texture(u_lookup_texture, palette_uv);
    vec4 previous_color = texture(u_previous_lookup_texture, palette_uv);
    float transition = smoothstep(0.0, 1.0, u_overlay_transition);
    vec4 visible_color = mix(previous_color, current_color, transition);
    vec3 final_color = terrain_color;

    if (u_overlay_mode == 1 && visible_color.a > 0.001) {
        vec3 overlay_color = map_data.a > 0.5 ? visible_color.rgb * 0.6 : visible_color.rgb;
        final_color = mix(terrain_color, overlay_color, visible_color.a * u_opacity);
    }

    bool selected = (u_selected_id >= 0 && dense_id == u_selected_id)
        || current_color.a > 0.95;
    if (selected) {
        final_color = mix(final_color, vec3(1.0), 0.55) * 1.15;
    }

    out_color = vec4(final_color, 1.0);
}
