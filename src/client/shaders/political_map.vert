#version 330
in vec2 in_vert;
in vec2 in_uv;

out vec2 v_uv;

uniform mat4 u_view;
uniform mat4 u_projection;

void main() {
    v_uv = in_uv;
    gl_Position = u_projection * u_view * vec4(in_vert, 0.0, 1.0);
}