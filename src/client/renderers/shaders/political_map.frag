#version 330
in vec2 v_uv;
out vec4 f_color;

uniform sampler2D u_map_texture;    
uniform sampler2D u_lookup_texture; 
uniform vec2      u_texture_size;   
uniform float     u_opacity;        
uniform int       u_overlay_mode;
uniform float     u_lut_dim;        
uniform int       u_selected_id;    

int get_id(vec2 uv) {
    vec4 c = texture(u_map_texture, uv);
    int r = int(round(c.r * 255.0));
    int g = int(round(c.g * 255.0));
    int b = int(round(c.b * 255.0));
    return b + (g * 256) + (r * 65536);
}

vec4 get_country_color(int id) {
    int width = int(u_lut_dim);
    int x = id % width;
    int y = id / width;
    return texelFetch(u_lookup_texture, ivec2(x, y), 0);
}

bool is_id_selected(int id) {
    if (id == u_selected_id && u_selected_id != -1) return true;
    // Check if Alpha is 255 (Selected in Multiselect)
    if (get_country_color(id).a >= 0.99) return true; 
    return false;
}

void main() {
    int region_id = get_id(v_uv);

    // 1. Always discard the "sea" or background ID immediately
    if (region_id == 0) discard;

    vec4 lut_data = get_country_color(region_id);
    
    // 2. Optimization: If unowned and not selected, discard immediately
    //    (Unless you want to highlight borders of unowned regions later)
    if (lut_data.a == 0.0 && region_id != u_selected_id) discard;

    bool is_selected = is_id_selected(region_id);

    // Neighbor logic...
    vec2 step = 1.0 / u_texture_size;
    // Note: You might want to clamp these lookups to texture bounds
    int id_r = get_id(v_uv + vec2(step.x, 0.0));
    int id_u = get_id(v_uv + vec2(0.0, step.y));

    bool is_region_border = (region_id != id_r || region_id != id_u);
    bool is_selection_border = false;

    if (is_selected) {
        if (region_id != id_r && !is_id_selected(id_r)) is_selection_border = true;
        if (region_id != id_u && !is_id_selected(id_u)) is_selection_border = true;
    }
    
    vec3 final_rgb = lut_data.rgb;

    // --- MODE 1: POLITICAL ---
    if (u_overlay_mode == 1) {
        if (is_region_border) final_rgb *= 0.6; 

        if (is_selection_border) {
            final_rgb = vec3(1.0, 1.0, 0.0);
        } else if (is_selected) {
            final_rgb += 0.15;
        }
        
        f_color = vec4(final_rgb, u_opacity * lut_data.a);
    }
    // --- MODE 0: TERRAIN (Default) ---
    else {
        if (is_selection_border) {
            f_color = vec4(1.0, 1.0, 1.0, 1.0);
        } else if (is_selected) {
            f_color = vec4(1.0, 1.0, 1.0, 0.15);
        } else {
            // FIX: Discard instead of writing vec4(0.0). 
            // This ensures the terrain sprite behind this quad is visible.
            discard;
        }
    }
}