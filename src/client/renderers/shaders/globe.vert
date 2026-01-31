#version 330

in vec3 in_pos;
in vec2 in_uv;
in vec3 in_nrm;

uniform mat4 u_model;
uniform mat4 u_view;
uniform mat4 u_projection;

out vec2 v_uv;
out vec3 v_nrm_ws;
out vec3 v_world_pos;

void main() {
    v_uv = in_uv;

    vec4 world_pos = u_model * vec4(in_pos, 1.0);
    v_nrm_ws = mat3(u_model) * in_nrm;
    v_world_pos = world_pos.xyz;

    gl_Position = u_projection * u_view * world_pos;
}
