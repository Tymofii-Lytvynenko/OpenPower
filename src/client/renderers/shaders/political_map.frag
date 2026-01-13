#version 330
in vec2 v_uv;
out vec4 f_color;

uniform sampler2D u_map_texture;    
uniform sampler2D u_lookup_texture; 
uniform vec2      u_texture_size;   
uniform float     u_opacity;        
uniform int       u_overlay_mode;   
// Removed u_selected_id (Selection is now handled via Alpha channel in u_lookup_texture)

int get_id(vec2 uv) {
    vec4 c = texture(u_map_texture, uv);
    int r = int(round(c.r * 255.0));
    int g = int(round(c.g * 255.0));
    int b = int(round(c.b * 255.0));
    return b + (g * 256) + (r * 65536);
}

vec4 get_country_color(int id) {
    int width = 4096;
    int x = id % width;
    int y = id / width;
    return texelFetch(u_lookup_texture, ivec2(x, y), 0);
}

void main() {
    int region_id = get_id(v_uv);
    if (region_id == 0) discard; 

    // 1. Fetch Data
    vec4 lut_data = get_country_color(region_id);
    
    // 2. Selection Logic (Alpha > 0.9 means "Selected")
    // This allows multiple regions (a whole country) to be "selected" at once.
    bool is_selected = (lut_data.a > 0.9);

    // 3. Neighbor Sampling (Same logic as your snippet: Right and Up)
    vec2 step = 1.0 / u_texture_size;
    int id_r = get_id(v_uv + vec2(step.x, 0.0));
    int id_u = get_id(v_uv + vec2(0.0, step.y));

    // 4. Border Logic
    bool is_region_border = false;      // Internal dark lines between regions
    bool is_selection_border = false;   // External yellow line around the selection

    // A. Detect Region Borders (Always visible in Political Mode)
    if (region_id != id_r || region_id != id_u) {
        is_region_border = true;
    }

    // B. Detect Selection Outline (Only if selected)
    if (is_selected) {
        // If neighbor is different ID...
        if (region_id != id_r) {
            // ...check if neighbor is NOT part of the selection.
            if (get_country_color(id_r).a < 0.9) is_selection_border = true;
        }
        if (region_id != id_u) {
            if (get_country_color(id_u).a < 0.9) is_selection_border = true;
        }
    }
    
    // 5. Coloring (Political Mode)
    if (u_overlay_mode == 1) {
        vec3 final_rgb = lut_data.rgb;

        // Apply dark border to ALL regions (Your "beautiful borders")
        if (is_region_border) {
             final_rgb *= 0.6; 
        }

        // Apply Selection Highlights
        if (is_selection_border) {
            final_rgb = vec3(1.0, 1.0, 0.0); // Yellow Outline
        } else if (is_selected) {
            final_rgb += 0.15; // Brightness boost for selected interior
        }

        f_color = vec4(final_rgb, u_opacity);
        return;
    }

    // 6. Coloring (Terrain Mode - Overlay Only)
    if (u_overlay_mode == 0) {
        if (is_selection_border) {
            f_color = vec4(1.0, 1.0, 1.0, 1.0); // Yellow Outline
        } else if (is_selected) {
            f_color = vec4(1.0, 1.0, 1.0, 0.15); // Faint fill
        } else {
            f_color = vec4(0.0); // Transparent
        }
    }
}