"""Post-processing: bloom (bright pass + separable blur) composited with a
CRT pass (scanlines, vignette, barrel distortion, chromatic aberration)."""
from OpenGL.GL import (
    GL_CLAMP_TO_EDGE, GL_COLOR_BUFFER_BIT, GL_DEPTH_BUFFER_BIT, GL_FLOAT,
    GL_FRAMEBUFFER, GL_LINEAR, GL_RGBA, GL_RGBA16F, GL_TEXTURE0, GL_TEXTURE1,
    GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_TEXTURE_MIN_FILTER,
    GL_TEXTURE_WRAP_S, GL_TEXTURE_WRAP_T,
    glActiveTexture, glBindFramebuffer, glBindTexture, glClear, glClearColor,
    glDisable, glGenTextures, glGetUniformLocation, glTexImage2D,
    glTexParameteri, glUniform1f, glUniform1i, glUniform2f, glUseProgram,
    glViewport, GL_DEPTH_TEST, GL_BLEND,
)

from render.gl import FBO, FullscreenTriangle, compile_program

BRIGHT_FS = """
#version 330 core
in vec2 v_uv;
uniform sampler2D u_tex;
out vec4 frag;
void main() {
    vec3 c = texture(u_tex, v_uv).rgb;
    float lum = dot(c, vec3(0.299, 0.587, 0.114));
    frag = vec4(c * smoothstep(0.75, 1.15, lum), 1.0);
}
"""

BLUR_FS = """
#version 330 core
in vec2 v_uv;
uniform sampler2D u_tex;
uniform vec2 u_dir;   // (1/w, 0) or (0, 1/h)
out vec4 frag;
void main() {
    float weights[5] = float[](0.227027, 0.194594, 0.121622, 0.054054, 0.016216);
    vec3 sum = texture(u_tex, v_uv).rgb * weights[0];
    for (int i = 1; i < 5; i++) {
        sum += texture(u_tex, v_uv + u_dir * float(i)).rgb * weights[i];
        sum += texture(u_tex, v_uv - u_dir * float(i)).rgb * weights[i];
    }
    frag = vec4(sum, 1.0);
}
"""

COMPOSITE_FS = """
#version 330 core
in vec2 v_uv;
uniform sampler2D u_scene;
uniform sampler2D u_bloom;
uniform vec2 u_resolution;
uniform float u_time;
uniform float u_aberration;   // 0..1 pulse
uniform float u_crt;          // 0 or 1 toggle
out vec4 frag;

vec2 barrel(vec2 uv, float k) {
    vec2 c = uv - 0.5;
    float r2 = dot(c, c);
    return 0.5 + c * (1.0 + k * r2);
}

void main() {
    vec2 uv = v_uv;
    if (u_crt > 0.5) uv = barrel(uv, 0.045);

    float ab = 0.0007 + u_aberration * 0.006;
    vec3 scene;
    scene.r = texture(u_scene, uv + vec2(ab, 0.0)).r;
    scene.g = texture(u_scene, uv).g;
    scene.b = texture(u_scene, uv - vec2(ab, 0.0)).b;
    vec3 bloom = texture(u_bloom, uv).rgb;

    vec3 c = scene + bloom * 0.85;

    if (u_crt > 0.5) {
        float scan = 0.92 + 0.08 * sin(uv.y * u_resolution.y * 3.14159);
        c *= scan;
        vec2 vg = uv - 0.5;
        c *= 1.0 - dot(vg, vg) * 0.55;
        if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0) c = vec3(0.0);
    }

    // subtle tonemap to keep hot emissives from clipping harshly
    c = c / (1.0 + c * 0.15);
    frag = vec4(c, 1.0);
}
"""


class PostPipeline:
    def __init__(self, width, height):
        # scene renders at the window's native resolution/aspect
        self.width = width
        self.height = height
        self.bloom_iterations = 2  # graphics setting: 0=off, 1=low, 2=full
        self.scene = FBO(width, height, depth=True)
        half_w, half_h = max(1, width // 2), max(1, height // 2)
        self.half = (half_w, half_h)
        self.bright = FBO(half_w, half_h)
        self.ping = FBO(half_w, half_h)
        self.tri = FullscreenTriangle()

        # 1x1 black texture stands in for bloom when it's disabled
        self.black_tex = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, self.black_tex)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA16F, 1, 1, 0, GL_RGBA, GL_FLOAT,
                     (0.0, 0.0, 0.0, 1.0))
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)

        self.p_bright = compile_program(FullscreenTriangle.VS, BRIGHT_FS)
        self.p_blur = compile_program(FullscreenTriangle.VS, BLUR_FS)
        self.p_comp = compile_program(FullscreenTriangle.VS, COMPOSITE_FS)

        self.u_blur_dir = glGetUniformLocation(self.p_blur, "u_dir")
        self.u_comp_scene = glGetUniformLocation(self.p_comp, "u_scene")
        self.u_comp_bloom = glGetUniformLocation(self.p_comp, "u_bloom")
        self.u_comp_res = glGetUniformLocation(self.p_comp, "u_resolution")
        self.u_comp_time = glGetUniformLocation(self.p_comp, "u_time")
        self.u_comp_ab = glGetUniformLocation(self.p_comp, "u_aberration")
        self.u_comp_crt = glGetUniformLocation(self.p_comp, "u_crt")

    def begin_scene(self):
        self.scene.bind()
        glViewport(0, 0, self.width, self.height)
        glClearColor(0.028, 0.028, 0.055, 1.0)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

    def finish(self, time_s, aberration=0.0, crt=True):
        glDisable(GL_DEPTH_TEST)
        glDisable(GL_BLEND)
        half_w, half_h = self.half
        bloom_tex = self.black_tex

        if self.bloom_iterations > 0:
            # bright pass at half res
            self.bright.bind()
            glViewport(0, 0, half_w, half_h)
            glUseProgram(self.p_bright)
            glActiveTexture(GL_TEXTURE0)
            glBindTexture(GL_TEXTURE_2D, self.scene.tex)
            self.tri.draw()

            # blur iterations (H then V), bright <-> ping
            glUseProgram(self.p_blur)
            for _ in range(self.bloom_iterations):
                self.ping.bind()
                glUniform2f(self.u_blur_dir, 1.0 / half_w, 0.0)
                glBindTexture(GL_TEXTURE_2D, self.bright.tex)
                self.tri.draw()
                self.bright.bind()
                glUniform2f(self.u_blur_dir, 0.0, 1.0 / half_h)
                glBindTexture(GL_TEXTURE_2D, self.ping.tex)
                self.tri.draw()
            bloom_tex = self.bright.tex

        # composite to the default framebuffer at native size
        glBindFramebuffer(GL_FRAMEBUFFER, 0)
        glViewport(0, 0, self.width, self.height)
        glUseProgram(self.p_comp)
        glUniform1i(self.u_comp_scene, 0)
        glUniform1i(self.u_comp_bloom, 1)
        glUniform2f(self.u_comp_res, self.width, self.height)
        glUniform1f(self.u_comp_time, time_s)
        glUniform1f(self.u_comp_ab, aberration)
        glUniform1f(self.u_comp_crt, 1.0 if crt else 0.0)
        glActiveTexture(GL_TEXTURE0)
        glBindTexture(GL_TEXTURE_2D, self.scene.tex)
        glActiveTexture(GL_TEXTURE1)
        glBindTexture(GL_TEXTURE_2D, bloom_tex)
        self.tri.draw()
        glActiveTexture(GL_TEXTURE0)
