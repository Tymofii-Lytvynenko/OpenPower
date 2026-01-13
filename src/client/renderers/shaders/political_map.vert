#version 330

// Inputs from Arcade/Python
in vec2 in_vert;
in vec2 in_uv;

// Outputs to Fragment Shader
out vec2 v_uv;

// Matrix Uniforms
uniform mat4 u_projection;
uniform mat4 u_view;

void main() {
    v_uv = in_uv;
    gl_Position = u_projection * u_view * vec4(in_vert, 0.0, 1.0);
}