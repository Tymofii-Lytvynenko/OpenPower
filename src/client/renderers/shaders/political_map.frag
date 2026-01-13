#version 330
in vec2 v_uv;
out vec4 f_color;

uniform sampler2D u_map_texture;    
uniform sampler2D u_lookup_texture; 
uniform vec2      u_texture_size;   
uniform float     u_opacity;        
uniform int       u_overlay_mode;
uniform float     u_lut_dim;        // Now 256.0
uniform int       u_selected_id;    // Contains Dense ID

// Decodes RGB texture back to Integer Index
// R=High Byte, B=Low Byte
int get_id(vec2 uv) {
    vec4 c = texture(u_map_texture, uv);
    int r = int(round(c.r * 255.0));
    int g = int(round(c.g * 255.0));
    int b = int(round(c.b * 255.0));
    // Must match Python packing: (r << 16) | (g << 8) | b
    return b + (g * 256) + (r * 65536);
}

vec4 get_country_color(int id) {
    int width = int(u_lut_dim);
    int x = id % width;
    int y = id / width;
    return texelFetch(u_lookup_texture, ivec2(x, y), 0);
}

bool is_id_selected(int id) {
    if (id == u_selected_id) return true;
    if (get_country_color(id).a > 0.9) return true;
    return false;
}

void main() {
    int region_id = get_id(v_uv);
    // Note: ID 0 is usually valid in Dense Map, so we assume your re-indexing 
    // keeps 'Void' or 'Water' as a specific ID or handles it via alpha.
    // If your dense map starts at 0, check your logic for 'empty' space.
    // For now, if index is 0, we can assume it's valid region #0 unless you reserved it.
    
    // Safety check for lookup
    if (region_id < 0) discard;

    bool is_selected = is_id_selected(region_id);

    vec2 step = 1.0 / u_texture_size;
    int id_r = get_id(v_uv + vec2(step.x, 0.0));
    int id_u = get_id(v_uv + vec2(0.0, step.y));

    bool is_region_border = false;
    bool is_selection_border = false;

    if (region_id != id_r || region_id != id_u) {
        is_region_border = true;
    }

    if (is_selected) {
        if (region_id != id_r) {
            if (!is_id_selected(id_r)) is_selection_border = true;
        }
        if (region_id != id_u) {
            if (!is_id_selected(id_u)) is_selection_border = true;
        }
    }
    
    vec4 lut_data = get_country_color(region_id);
    vec3 final_rgb = lut_data.rgb;

    if (u_overlay_mode == 1) {
        if (is_region_border) final_rgb *= 0.6; 

        if (is_selection_border) {
            final_rgb = vec3(1.0, 1.0, 0.0);
        } else if (is_selected) {
            final_rgb += 0.15;
        }
        f_color = vec4(final_rgb, u_opacity);
    }
    else {
        if (is_selection_border) {
            f_color = vec4(1.0, 1.0, 1.0, 1.0);
        } else if (is_selected) {
            f_color = vec4(1.0, 1.0, 1.0, 0.15);
        } else {
            f_color = vec4(0.0);
        }
    }
}