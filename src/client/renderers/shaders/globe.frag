#version 330 core

// ==========================================
// INPUTS & UNIFORMS
// ==========================================
in vec2 v_uv;
in vec3 v_nrm_ws;
in vec3 v_world_pos;

out vec4 out_color;

// Textures
uniform sampler2D u_terrain_texture; // Base albedo
uniform sampler2D u_map_texture;     // ID map (RGB encoded IDs)
uniform sampler2D u_lookup_texture;  // Data/Political colors (LUT)

// Configuration
uniform float u_lut_dim;       // Dimension of the LUT (e.g., 256.0)
uniform vec2  u_texture_size;  // Size of map texture (for pixel step calc)
uniform int   u_selected_id;   // Currently selected ID (-1 if none)
uniform int   u_overlay_mode;  // 0=Terrain Only, 1=Political Overlay
uniform float u_opacity;       // Overlay opacity

// Environment
uniform vec3  u_light_dir;
uniform float u_ambient;
uniform vec3  u_camera_pos;

// ==========================================
// UTILITY FUNCTIONS
// ==========================================

// Decodes a 24-bit RGB color into a unique integer ID.
// Why: Standard float-to-int casting can be lossy; adding 0.5 ensures stable rounding.
int decode_id(vec3 rgb) {
    ivec3 c = ivec3(rgb * 255.0 + 0.5);
    return (c.r << 16) | (c.g << 8) | c.b;
}

// Fetches data from the Lookup Texture based on the dense ID.
// Why: Maps a linear ID to 2D UV coordinates for the LUT.
vec4 get_overlay_data(int dense_id) {
    int x = dense_id % int(u_lut_dim);
    int y = dense_id / int(u_lut_dim);
    // Offset by 0.5 to sample the exact center of the texel to avoid bleeding
    vec2 uv = (vec2(x, y) + vec2(0.5)) / vec2(u_lut_dim, u_lut_dim);
    return texture(u_lookup_texture, uv);
}

// standard Blinn-Phong/Lambertian hybrid lighting
vec3 apply_lighting(vec3 albedo, vec3 normal, vec3 light_dir, float ambient) {
    float ndotl = max(dot(normal, normalize(light_dir)), 0.0);
    float light_intensity = ambient + (1.0 - ambient) * ndotl;
    return albedo * light_intensity;
}

// Adds depth fog and rim lighting.
// Why: Pure flat maps look artificial in 3D; this grounds the map in the scene.
vec3 apply_atmosphere(vec3 color, vec3 normal, vec3 world_pos, vec3 cam_pos) {
    vec3 view_dir = normalize(cam_pos - world_pos);

    // Rim Light (Fresnel) - Highlights glancing angles
    float fresnel = pow(1.0 - max(dot(normal, view_dir), 0.0), 2.0);
    vec3 atmosphere_color = vec3(0.4, 0.6, 1.0);
    color = mix(color, atmosphere_color, fresnel * 0.15);

    // Depth Fog - Fades distant geometry
    float depth_fog = pow(max(dot(normal, -view_dir), 0.0), 1.5) * 0.05;
    vec3 fog_color = vec3(0.7, 0.8, 0.9);
    color = mix(color, fog_color, depth_fog);

    return color;
}

// Checks if the current pixel is at the edge of a region.
// Optimization: This function performs 2 extra texture lookups. 
// It should ONLY be called if absolutely necessary (i.e., not on ocean pixels).
bool is_border_pixel(vec2 uv, int center_id) {
    vec2 step = 1.0 / u_texture_size;

    // Sample Right and Up neighbors
    int id_r = decode_id(texture(u_map_texture, uv + vec2(step.x, 0.0)).rgb);
    int id_u = decode_id(texture(u_map_texture, uv + vec2(0.0, step.y)).rgb);

    return (center_id != id_r || center_id != id_u);
}

// ==========================================
// MAIN PIPELINE
// ==========================================

void main() {
    // 1. Setup & Coordinates
    vec2 uv = vec2(fract(v_uv.x), clamp(v_uv.y, 0.0, 1.0));
    vec3 n = normalize(v_nrm_ws);

    // 2. Base Terrain Pass
    // We always calculate this first as the foundation of the image.
    vec4 terrain = texture(u_terrain_texture, uv);
    vec3 final_rgb = apply_lighting(terrain.rgb, n, u_light_dir, u_ambient);

    // 3. Data Fetch (The Optimization Hub)
    // We sample the map data ONCE here. The results are reused for overlay AND selection.
    vec3 map_rgb = texture(u_map_texture, uv).rgb;
    int dense_id = decode_id(map_rgb);
    
    // Fetch overlay data (Color in RGB, Multi-select flag in Alpha)
    vec4 overlay_data = get_overlay_data(dense_id);

    // 4. Political Overlay Pass
    // Only process if mode is active AND the overlay has data (alpha > 0)
    if (u_overlay_mode == 1 && overlay_data.a > 0.0) {
        vec3 overlay_color = overlay_data.rgb;

        // BORDER OPTIMIZATION: 
        // Only check borders if this is NOT the ocean (id 0).
        // Checking borders on the ocean is wasted GPU cycles (70% of the map).
        if (dense_id > 0) {
            if (is_border_pixel(uv, dense_id)) {
                // Darken borders for visual separation
                overlay_color *= 0.6; 
            }
        }

        // Apply lighting to the overlay paint so it respects the terrain shape
        vec3 lit_overlay = apply_lighting(overlay_color, n, u_light_dir, u_ambient);
        
        // Blend overlay onto terrain based on global opacity and texture alpha
        final_rgb = mix(final_rgb, lit_overlay, overlay_data.a * u_opacity);
    }

    // 5. Post-Process Effects (Atmosphere)
    final_rgb = apply_atmosphere(final_rgb, n, v_world_pos, u_camera_pos);

    // 6. Selection Logic
    // Combined Check: Is it the single selected ID? OR is it part of a multi-select group?
    // We reuse 'overlay_data.a' here to avoid a second texture lookup.
    bool is_selected = (u_selected_id >= 0 && dense_id == u_selected_id);
    if (!is_selected) {
        // Assuming Alpha > 0.95 indicates a multi-selected region in the LUT
        is_selected = (overlay_data.a > 0.95); 
    }

    if (is_selected) {
        // "New Style" Highlight
        // 1. Tint towards white (desaturate and brighten)
        final_rgb = mix(final_rgb, vec3(1.0), 0.55);
        // 2. Boost exposure
        final_rgb *= 1.15;
        
        // SAFETY CLAMP:
        // Ensure we don't exceed 1.0, which can cause artifacts on non-HDR monitors.
        // If you are using an HDR pipeline, remove this min().
        final_rgb = min(final_rgb, vec3(1.0));
    }

    out_color = vec4(final_rgb, 1.0);
}