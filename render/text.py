"""HUD text and solid rectangles: pygame font surfaces as GL textures drawn
in an orthographic overlay pass. Screen coords: origin top-left, y down."""
import numpy as np
import pygame
from OpenGL.GL import (
    GL_ARRAY_BUFFER, GL_CLAMP_TO_EDGE, GL_DYNAMIC_DRAW, GL_NEAREST, GL_RGBA,
    GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_TEXTURE_MIN_FILTER, GL_TEXTURE_WRAP_S,
    GL_TEXTURE_WRAP_T, GL_TRIANGLES, GL_UNSIGNED_BYTE,
    glBindBuffer, glBindTexture, glBindVertexArray, glBufferData, glDeleteTextures,
    glDrawArrays, glGenBuffers, glGenTextures, glGenVertexArrays,
    glGetUniformLocation, glTexImage2D, glTexParameteri, glUniform1i, glUniform2f,
    glUniform4f, glUseProgram,
)

from render.gl import compile_program, setup_attrib

QUAD_VS = """
#version 330 core
layout(location = 0) in vec2 a_pos;   // screen px
layout(location = 1) in vec2 a_uv;
uniform vec2 u_screen;
out vec2 v_uv;
void main() {
    vec2 ndc = vec2(a_pos.x / u_screen.x * 2.0 - 1.0,
                    1.0 - a_pos.y / u_screen.y * 2.0);
    v_uv = a_uv;
    gl_Position = vec4(ndc, 0.0, 1.0);
}
"""

QUAD_FS = """
#version 330 core
in vec2 v_uv;
uniform sampler2D u_tex;
uniform vec4 u_tint;
uniform int u_use_tex;
out vec4 frag;
void main() {
    vec4 base = (u_use_tex == 1) ? texture(u_tex, v_uv) : vec4(1.0);
    frag = base * u_tint;
}
"""


class OverlayRenderer:
    """Draws text strings and solid rects in screen space. Textures cached
    per (text, size); call begin() once per frame before drawing."""

    MAX_CACHE = 384

    def __init__(self, screen_w, screen_h):
        self.screen = (screen_w, screen_h)
        self.program = compile_program(QUAD_VS, QUAD_FS)
        self.u_screen = glGetUniformLocation(self.program, "u_screen")
        self.u_tint = glGetUniformLocation(self.program, "u_tint")
        self.u_use_tex = glGetUniformLocation(self.program, "u_use_tex")
        self.u_tex = glGetUniformLocation(self.program, "u_tex")

        self.vao = glGenVertexArrays(1)
        glBindVertexArray(self.vao)
        self.vbo = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo)
        setup_attrib(0, 2, 16, 0)
        setup_attrib(1, 2, 16, 8)
        glBindVertexArray(0)

        self.fonts = {}
        self.cache = {}  # (text, size) -> (tex, w, h)

    def _font(self, size):
        if size not in self.fonts:
            self.fonts[size] = pygame.font.SysFont("couriernew", size, bold=True)
        return self.fonts[size]

    def _texture_for(self, text, size):
        key = (text, size)
        if key in self.cache:
            return self.cache[key]
        if len(self.cache) >= self.MAX_CACHE:
            for tex, _, _ in self.cache.values():
                glDeleteTextures([tex])
            self.cache.clear()
        surf = self._font(size).render(text, True, (255, 255, 255))
        w, h = surf.get_size()
        data = pygame.image.tobytes(surf, "RGBA", False)
        tex = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, tex)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, w, h, 0, GL_RGBA,
                     GL_UNSIGNED_BYTE, data)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
        self.cache[key] = (tex, w, h)
        return self.cache[key]

    def begin(self):
        glUseProgram(self.program)
        glUniform2f(self.u_screen, *self.screen)
        glUniform1i(self.u_tex, 0)

    def _draw_quad(self, x, y, w, h):
        verts = np.asarray([
            x, y, 0, 0,
            x + w, y, 1, 0,
            x + w, y + h, 1, 1,
            x, y, 0, 0,
            x + w, y + h, 1, 1,
            x, y + h, 0, 1,
        ], dtype=np.float32)
        glBindVertexArray(self.vao)
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo)
        glBufferData(GL_ARRAY_BUFFER, verts.nbytes, verts, GL_DYNAMIC_DRAW)
        glDrawArrays(GL_TRIANGLES, 0, 6)
        glBindVertexArray(0)

    def text(self, s, x, y, size=18, color=(255, 255, 255, 255), center=False):
        if not s:
            return 0
        tex, w, h = self._texture_for(s, size)
        if center:
            x -= w / 2
        glBindTexture(GL_TEXTURE_2D, tex)
        glUniform1i(self.u_use_tex, 1)
        glUniform4f(self.u_tint, color[0] / 255, color[1] / 255, color[2] / 255,
                    (color[3] if len(color) > 3 else 255) / 255)
        self._draw_quad(x, y, w, h)
        return w

    def text_width(self, s, size=18):
        _, w, _ = self._texture_for(s, size)
        return w

    def rect(self, x, y, w, h, color):
        glUniform1i(self.u_use_tex, 0)
        glUniform4f(self.u_tint, color[0] / 255, color[1] / 255, color[2] / 255,
                    (color[3] if len(color) > 3 else 255) / 255)
        self._draw_quad(x, y, w, h)
