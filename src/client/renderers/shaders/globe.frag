#version 330

// ==========================================
// 1. CONFIGURATION & CONSTANTS
// ==========================================

// Visual Style: Atmosphere
const vec3  C_ATMOSPHERE_COLOR = vec3(0.4, 0.6, 1.0);
const float C_RIM_STRENGTH     = 0.15;

// Visual Style: Overlay
const float C_BORDER_DARKEN    = 0.6;  // Multiplier for border pixels
const float C_SELECTION_TINT   = 0.55; // How much white to mix in (0.0 - 1.0)
const float C_SELECTION_BOOST  = 1.15; // Brightness multiplier

// System
const float C_EPSILON          = 0.001; 

// ==========================================
// 2. INPUTS & UNIFORMS
// ==========================================
in vec2 v_uv;
in vec3 v_nrm_ws;
in vec3 v_world_pos;

out vec4 out_color;

// Textures
uniform sampler2D u_terrain_texture;
uniform sampler2D u_map_texture;
uniform sampler2D u_lookup_texture;

// Uniforms
uniform float u_lut_dim;
uniform int   u_selected_id;
uniform int   u_overlay_mode; // 0=Terrain, 1=Political
uniform float u_opacity;

// Environment
uniform vec3  u_light_dir;
uniform float u_ambient;
uniform vec3  u_camera_pos;

// ==========================================
// 3. UTILITY FUNCTIONS
// ==========================================

// Convert encoded RGB to Integer ID
// Why: Standard float-to-int casting can be lossy; adding 0.5 ensures stable rounding.
int decode_id(vec3 rgb) {
    ivec3 c = ivec3(rgb * 255.0 + 0.5);
    return (c.r << 16) | (c.g << 8) | c.b;
}

// Map ID to LUT UV coordinates
// Why: Maps a linear ID to 2D UV coordinates for the data lookup texture.
vec4 get_overlay_data(int dense_id) {
    float dim = u_lut_dim;
    float x = float(dense_id % int(dim));
    float y = float(dense_id / int(dim));
    
    // STRICT COMPATIBILITY: 
    // Uses vec2(0.5) instead of 0.5 to prevent crashes on strict drivers (e.g. MacOS)
    vec2 uv = (vec2(x, y) + vec2(0.5)) / vec2(dim);
    
    return texture(u_lookup_texture, uv);
}

// Atmospheric rim light.
vec3 apply_atmosphere(vec3 color, vec3 normal, vec3 world_pos, vec3 cam_pos) {
    vec3 view_dir = normalize(cam_pos - world_pos);
    float NdotV = max(dot(normal, view_dir), 0.0);

    // Rim Light
    float fresnel_base = 1.0 - NdotV;
    float fresnel = fresnel_base * fresnel_base; // optimization: x*x is faster than pow(x, 2.0)
    
    color = mix(color, C_ATMOSPHERE_COLOR, fresnel * C_RIM_STRENGTH);
    return color;
}

// ==========================================
// 4. MAIN
// ==========================================

void main() {
    // A. Setup
    vec2 uv = vec2(fract(v_uv.x), clamp(v_uv.y, 0.0, 1.0));
    vec3 n = normalize(v_nrm_ws);
    float ndotl = max(dot(n, normalize(u_light_dir)), 0.0);
    float lighting = u_ambient + (1.0 - u_ambient) * ndotl;

    // B. Base Layer (Terrain)
    vec4 terrain = texture(u_terrain_texture, uv);
    vec3 final_rgb = terrain.rgb * lighting;

    // C. Map Data & Overlay Lookup (The Optimization Hub)
    // We fetch this ONCE here. The results are reused for both overlay coloring AND selection logic.
    vec4 map_data = texture(u_map_texture, uv);
    int dense_id = decode_id(map_data.rgb);
    vec4 overlay_data = get_overlay_data(dense_id);

    // D. Political Overlay Logic
    // Only apply if mode is active AND the region has valid data (alpha > 0)
    if (u_overlay_mode == 1 && overlay_data.a > C_EPSILON) {
        vec3 overlay_color = overlay_data.rgb;

        if (map_data.a > 0.5) {
            overlay_color *= C_BORDER_DARKEN;
        }

        // Apply lighting to the overlay so it matches terrain shading
        vec3 lit_overlay = overlay_color * lighting;
        
        // Blend overlay onto terrain
        final_rgb = mix(final_rgb, lit_overlay, overlay_data.a * u_opacity);
    }

    // E. Post-Processing (Atmosphere)
    final_rgb = apply_atmosphere(final_rgb, n, v_world_pos, u_camera_pos);

    // F. Selection Highlight
    // 1. Check if specific ID is selected
    bool is_selected = (u_selected_id >= 0 && dense_id == u_selected_id);
    
    // 2. If not, check if it's part of a multi-select group (stored in overlay alpha)
    if (!is_selected) {
        is_selected = (overlay_data.a > 0.95); 
    }

    // 3. Apply Glow (The "New Style")
    if (is_selected) {
        // Tint white
        final_rgb = mix(final_rgb, vec3(1.0), C_SELECTION_TINT);
        // Boost brightness
        final_rgb *= C_SELECTION_BOOST;
        
        // Note: No clamp() applied here to preserve your "bright" style.
        // If you see white artifacts on your monitor, uncomment the line below:
        // final_rgb = min(final_rgb, vec3(1.0));
    }

    out_color = vec4(final_rgb, 1.0);
}
