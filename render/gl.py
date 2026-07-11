"""Low-level GL helpers: shader compilation, FBOs, fullscreen triangle."""
import ctypes

import numpy as np
from OpenGL.GL import (
    GL_ARRAY_BUFFER, GL_CLAMP_TO_EDGE, GL_COLOR_ATTACHMENT0, GL_COMPILE_STATUS,
    GL_DEPTH24_STENCIL8, GL_DEPTH_STENCIL_ATTACHMENT, GL_FLOAT, GL_FRAGMENT_SHADER,
    GL_FRAMEBUFFER, GL_FRAMEBUFFER_COMPLETE, GL_LINEAR, GL_LINK_STATUS, GL_RENDERBUFFER,
    GL_RGBA, GL_RGBA16F, GL_STATIC_DRAW, GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER,
    GL_TEXTURE_MIN_FILTER, GL_TEXTURE_WRAP_S, GL_TEXTURE_WRAP_T, GL_TRIANGLES,
    GL_VERTEX_SHADER,
    glAttachShader, glBindBuffer, glBindFramebuffer, glBindRenderbuffer, glBindTexture,
    glBindVertexArray, glBufferData, glCheckFramebufferStatus, glCompileShader,
    glCreateProgram, glCreateShader, glDeleteShader, glDrawArrays,
    glEnableVertexAttribArray, glFramebufferRenderbuffer, glFramebufferTexture2D,
    glGenBuffers, glGenFramebuffers, glGenRenderbuffers, glGenTextures,
    glGenVertexArrays, glGetProgramInfoLog, glGetProgramiv, glGetShaderInfoLog,
    glGetShaderiv, glLinkProgram, glRenderbufferStorage, glShaderSource, glTexImage2D,
    glTexParameteri, glVertexAttribPointer,
)


def compile_program(vs_src, fs_src):
    def compile_one(kind, src, label):
        shader = glCreateShader(kind)
        glShaderSource(shader, src)
        glCompileShader(shader)
        if not glGetShaderiv(shader, GL_COMPILE_STATUS):
            log = glGetShaderInfoLog(shader).decode()
            raise RuntimeError(f"{label} shader compile failed:\n{log}")
        return shader

    vs = compile_one(GL_VERTEX_SHADER, vs_src, "vertex")
    fs = compile_one(GL_FRAGMENT_SHADER, fs_src, "fragment")
    program = glCreateProgram()
    glAttachShader(program, vs)
    glAttachShader(program, fs)
    glLinkProgram(program)
    glDeleteShader(vs)
    glDeleteShader(fs)
    if not glGetProgramiv(program, GL_LINK_STATUS):
        log = glGetProgramInfoLog(program).decode()
        raise RuntimeError(f"program link failed:\n{log}")
    return program


class FBO:
    """Float-color framebuffer with optional depth."""

    def __init__(self, width, height, depth=False):
        self.width = width
        self.height = height
        self.tex = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, self.tex)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA16F, width, height, 0,
                     GL_RGBA, GL_FLOAT, None)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)

        self.fbo = glGenFramebuffers(1)
        glBindFramebuffer(GL_FRAMEBUFFER, self.fbo)
        glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0,
                               GL_TEXTURE_2D, self.tex, 0)
        if depth:
            rb = glGenRenderbuffers(1)
            glBindRenderbuffer(GL_RENDERBUFFER, rb)
            glRenderbufferStorage(GL_RENDERBUFFER, GL_DEPTH24_STENCIL8, width, height)
            glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_DEPTH_STENCIL_ATTACHMENT,
                                      GL_RENDERBUFFER, rb)
        status = glCheckFramebufferStatus(GL_FRAMEBUFFER)
        if status != GL_FRAMEBUFFER_COMPLETE:
            raise RuntimeError(f"FBO incomplete: {status}")
        glBindFramebuffer(GL_FRAMEBUFFER, 0)

    def bind(self):
        glBindFramebuffer(GL_FRAMEBUFFER, self.fbo)


class FullscreenTriangle:
    """Single triangle covering the screen; UVs derived in the shader."""

    VS = """
    #version 330 core
    out vec2 v_uv;
    void main() {
        vec2 pos = vec2((gl_VertexID << 1) & 2, gl_VertexID & 2);
        v_uv = pos;
        gl_Position = vec4(pos * 2.0 - 1.0, 0.0, 1.0);
    }
    """

    def __init__(self):
        self.vao = glGenVertexArrays(1)

    def draw(self):
        glBindVertexArray(self.vao)
        glDrawArrays(GL_TRIANGLES, 0, 3)
        glBindVertexArray(0)


def make_static_vbo(data):
    vbo = glGenBuffers(1)
    glBindBuffer(GL_ARRAY_BUFFER, vbo)
    arr = np.asarray(data, dtype=np.float32)
    glBufferData(GL_ARRAY_BUFFER, arr.nbytes, arr, GL_STATIC_DRAW)
    glBindBuffer(GL_ARRAY_BUFFER, 0)
    return vbo


def setup_attrib(index, size, stride, offset, divisor=0):
    glEnableVertexAttribArray(index)
    glVertexAttribPointer(index, size, GL_FLOAT, False, stride,
                          ctypes.c_void_p(offset))
    if divisor:
        from OpenGL.GL import glVertexAttribDivisor
        glVertexAttribDivisor(index, divisor)
