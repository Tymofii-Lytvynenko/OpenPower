#version 330

uniform sampler2D u_terrain_texture;
uniform sampler2D u_map_texture;
uniform sampler2D u_lookup_texture;

uniform float u_lut_dim;
uniform vec2  u_texture_size; // Needed for border calculation
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

// Helper: Convert encoded color (RGB) back to Integer ID
int decode_id(vec3 rgb) {
    ivec3 c = ivec3(rgb * 255.0 + 0.5);
    return (c.r << 16) | (c.g << 8) | c.b;
}

// Helper: Fetch color from Lookup Texture (LUT)
vec4 lut_lookup(int dense_id) {
    int x = dense_id % int(u_lut_dim);
    int y = dense_id / int(u_lut_dim);
    // Sample center of the pixel
    vec2 uv = (vec2(x, y) + vec2(0.5)) / vec2(u_lut_dim, u_lut_dim);
    return texture(u_lookup_texture, uv);
}

void main() {
    vec2 uv = vec2(fract(v_uv.x), clamp(v_uv.y, 0.0, 1.0));

    // --- Lighting ---
    vec3 n = normalize(v_nrm_ws);
    float ndotl = max(dot(n, normalize(u_light_dir)), 0.0);
    float light = u_ambient + (1.0 - u_ambient) * ndotl;

    // --- Base Terrain ---
    vec4 terrain = texture(u_terrain_texture, uv);
    vec3 base = terrain.rgb * light;

    // --- Map Data Lookup ---
    vec3 map_rgb = texture(u_map_texture, uv).rgb;
    int dense_id = decode_id(map_rgb);
    vec4 overlay = lut_lookup(dense_id);

    float opacity = u_opacity;
    int mode = u_overlay_mode;

    // Start with base rendering
    vec4 final_color;

    // --- BORDER DETECTION ---
    // We check the pixel to the right and above. If the ID is different, we are on an edge.
    bool is_border = false;
    
    // Optimization: Only check borders if we are in overlay mode and not in the ocean (id 0)
    if (mode == 1 && dense_id > 0) {
        vec2 step = 1.0 / u_texture_size;
        
        // Sample neighbor pixels
        int id_r = decode_id(texture(u_map_texture, uv + vec2(step.x, 0.0)).rgb);
        int id_u = decode_id(texture(u_map_texture, uv + vec2(0.0, step.y)).rgb);

        if (dense_id != id_r || dense_id != id_u) {
            is_border = true;
        }
    }

    // --- COLOR BLENDING ---
    if (mode == 1 && overlay.a > 0.0) {
        // Political/Data Mode
        float a = overlay.a * opacity;
        vec3 overlay_rgb = overlay.rgb;

        // Darken the color at the border for separation
        // This is strictly for visualization, not selection style.
        if (is_border) {
            overlay_rgb *= 0.6; 
        }

        vec3 mixed = mix(base, overlay_rgb * light, a);
        final_color = vec4(mixed, 1.0);
    } else {
        // Terrain Mode
        final_color = vec4(base, 1.0);
    }

    // --- ATMOSPHERIC EFFECTS (Visual Polish) ---
    vec3 view_dir = normalize(u_camera_pos - v_world_pos);
    float fresnel = pow(1.0 - max(dot(v_nrm_ws, view_dir), 0.0), 2.0);

    vec3 atmosphere_color = vec3(0.4, 0.6, 1.0);
    float atmosphere_strength = fresnel * 0.15;
    final_color.rgb = mix(final_color.rgb, atmosphere_color, atmosphere_strength);

    float depth_fog = pow(max(dot(v_nrm_ws, -view_dir), 0.0), 1.5) * 0.05;
    vec3 fog_color = vec3(0.7, 0.8, 0.9);
    final_color.rgb = mix(final_color.rgb, fog_color, depth_fog);

    // --- SELECTION HIGHLIGHT (New Style Preserved) ---
    // Single selection via ID or Multi-selection via LUT Alpha
    float single_sel = (u_selected_id >= 0 && dense_id == u_selected_id) ? 1.0 : 0.0;
    float multi_sel  = (overlay.a > 0.95) ? 1.0 : 0.0;
    float sel = max(single_sel, multi_sel);

    if (sel > 0.0) {
        // "New Style": Brightness Boost + White Tint
        vec3 highlight_color = vec3(1.0);
        float highlight_strength = 0.55;

        final_color.rgb = mix(final_color.rgb, highlight_color, highlight_strength);
        final_color.rgb = min(final_color.rgb * 1.15, vec3(1.0));
    }

    out_color = final_color;
}