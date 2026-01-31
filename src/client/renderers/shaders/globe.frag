#version 330

uniform sampler2D u_terrain_texture;
uniform sampler2D u_map_texture;
uniform sampler2D u_lookup_texture;

uniform float u_lut_dim;
uniform int   u_selected_id;
uniform int   u_overlay_mode;
uniform float u_opacity;

uniform vec3  u_light_dir;
uniform float u_ambient;
uniform vec3  u_camera_pos;

in vec2 v_uv;
in vec3 v_nrm_ws;
in vec3 v_world_pos;

out vec4 out_color;

int decode_id(vec3 rgb) {
    ivec3 c = ivec3(rgb * 255.0 + 0.5);
    return (c.r << 16) | (c.g << 8) | c.b;
}

vec4 lut_lookup(int dense_id) {
    int x = dense_id % int(u_lut_dim);
    int y = dense_id / int(u_lut_dim);
    vec2 uv = (vec2(x, y) + vec2(0.5)) / vec2(u_lut_dim, u_lut_dim);
    return texture(u_lookup_texture, uv);
}

void main() {
    vec2 uv = vec2(fract(v_uv.x), clamp(v_uv.y, 0.0, 1.0));

    vec3 n = normalize(v_nrm_ws);
    float ndotl = max(dot(n, normalize(u_light_dir)), 0.0);
    float light = u_ambient + (1.0 - u_ambient) * ndotl;

    vec4 terrain = texture(u_terrain_texture, uv);
    vec3 base = terrain.rgb * light;

    // dense id -> overlay
    int dense_id = decode_id(texture(u_map_texture, uv).rgb);
    vec4 overlay = lut_lookup(dense_id);

    // Ensure uniforms are "used" (prevents optimization removing them)
    float opacity = u_opacity;
    int mode = u_overlay_mode;

    // Start with base rendering
    vec4 final_color;

    if (mode == 1 && overlay.a > 0.0) {
        // Overlay mode: show political colors
        float a = overlay.a * opacity;
        vec3 mixed = mix(base, overlay.rgb * light, a);
        final_color = vec4(mixed, 1.0);
    } else {
        // Terrain or other modes: show base terrain
        final_color = vec4(base, 1.0);
    }


    // --- Atmospheric Effects ---
// Calculate fresnel for rim lighting effect
vec3 view_dir = normalize(u_camera_pos - v_world_pos);
float fresnel = pow(1.0 - max(dot(v_nrm_ws, view_dir), 0.0), 2.0);

// Subtle atmospheric glow at the edges
vec3 atmosphere_color = vec3(0.4, 0.6, 1.0); // Soft blue atmosphere
float atmosphere_strength = fresnel * 0.15;
final_color.rgb = mix(final_color.rgb, atmosphere_color, atmosphere_strength);

// Add subtle depth fog for distant areas
float depth_fog = pow(max(dot(v_nrm_ws, -view_dir), 0.0), 1.5) * 0.05;
vec3 fog_color = vec3(0.7, 0.8, 0.9); // Light blue fog
final_color.rgb = mix(final_color.rgb, fog_color, depth_fog);

// --- Selection highlight ---
// Single selection (uses uniform) OR multi-selection (uses LUT alpha = 255)
float single_sel = (u_selected_id >= 0 && dense_id == u_selected_id) ? 1.0 : 0.0;

// LUT alpha is normalized 0..1. Selected regions are written as 255 => ~1.0.
// Use a slightly lower threshold to be robust (255, 254, etc.)
float multi_sel  = (overlay.a > 0.95) ? 1.0 : 0.0;

float sel = max(single_sel, multi_sel);

if (sel > 0.0) {
    vec3 highlight_color = vec3(1.0);
    float highlight_strength = 0.55;          // tweak: 0.4 subtle, 0.8 strong

    final_color.rgb = mix(final_color.rgb, highlight_color, highlight_strength);

    // small brightness boost (keep subtle so terrain stays readable)
    final_color.rgb = min(final_color.rgb * 1.15, vec3(1.0));
}


    out_color = final_color;
}
