#version 330
in vec2 v_uv;
out vec4 f_color;

uniform sampler2D u_map_texture;    
uniform sampler2D u_lookup_texture; 
uniform vec2      u_texture_size;   
uniform float     u_opacity;        
uniform int       u_selected_id;    
uniform int       u_overlay_mode;   

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

    bool is_selected = (region_id == u_selected_id);
    bool is_selected_border = false;
    vec2 step = 1.0 / u_texture_size;
    
    if (is_selected || u_overlay_mode == 1) {
        int id_r = get_id(v_uv + vec2(step.x, 0.0));
        int id_u = get_id(v_uv + vec2(0.0, step.y));

        if (is_selected) {
            if (id_r != region_id || id_u != region_id) is_selected_border = true;
        }
        
        if (u_overlay_mode == 1) {
            vec4 country_color = get_country_color(region_id);
            vec3 final_rgb = country_color.rgb;

            if (region_id != id_r || region_id != id_u) {
                 final_rgb *= 0.6; 
            }

            if (is_selected_border) {
                final_rgb = vec3(1.0, 1.0, 0.0); 
            } else if (is_selected) {
                final_rgb += 0.15; 
            }

            f_color = vec4(final_rgb, u_opacity);
            return;
        }
    }

    if (u_overlay_mode == 0) {
        if (is_selected_border) {
            f_color = vec4(1.0, 1.0, 0.0, 1.0);
        } else if (is_selected) {
            f_color = vec4(1.0, 1.0, 1.0, 0.15);
        } else {
            f_color = vec4(0.0);
        }
    }
}