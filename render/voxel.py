"""Voxel meshes: pixel grids extruded into cube meshes, drawn instanced.

Coordinates: world x right, y up, z toward camera. The 2D playfield
(640x720, y down) maps to the z=0 plane via world_from_field().
"""
import math

import numpy as np
from OpenGL.GL import (
    GL_ARRAY_BUFFER, GL_DYNAMIC_DRAW, GL_TRIANGLES,
    glBindBuffer, glBindVertexArray, glBufferData, glDrawArraysInstanced,
    glGenBuffers, glGenVertexArrays, glGetUniformLocation, glUniform3f,
    glUniformMatrix4fv, glUseProgram,
)

from render.gl import compile_program, make_static_vbo, setup_attrib

FIELD_SCALE = 32.0  # logical pixels per world unit


def world_from_field(x, y, z=0.0):
    return ((x - 320.0) / FIELD_SCALE, (360.0 - y) / FIELD_SCALE, z)


VOXEL_VS = """
#version 330 core
layout(location = 0) in vec3 a_pos;
layout(location = 1) in vec3 a_normal;
layout(location = 2) in vec3 a_color;
layout(location = 3) in vec4 i_posscale;   // xyz world pos, w uniform scale
layout(location = 4) in vec4 i_quat;       // rotation quaternion (xyzw)
layout(location = 5) in vec4 i_color;      // tint rgb (may exceed 1 = emissive), a alpha

uniform mat4 u_viewproj;

out vec3 v_normal;
out vec3 v_color;
out float v_alpha;

vec3 rot(vec4 q, vec3 v) {
    return v + 2.0 * cross(q.xyz, cross(q.xyz, v) + q.w * v);
}

void main() {
    vec3 world = i_posscale.xyz + rot(i_quat, a_pos * i_posscale.w);
    v_normal = rot(i_quat, a_normal);
    v_color = a_color * i_color.rgb;
    v_alpha = i_color.a;
    gl_Position = u_viewproj * vec4(world, 1.0);
}
"""

VOXEL_FS = """
#version 330 core
in vec3 v_normal;
in vec3 v_color;
in float v_alpha;
out vec4 frag;

uniform vec3 u_lightdir;

void main() {
    vec3 n = normalize(v_normal);
    float diff = max(dot(n, u_lightdir), 0.0);
    float rim = pow(1.0 - abs(n.z), 2.0) * 0.25;
    vec3 lit = v_color * (0.45 + 0.6 * diff) + v_color * rim;
    frag = vec4(lit, v_alpha);
}
"""

CUBE_FACES = [
    # normal, 4 corners (CCW from outside)
    ((0, 0, 1), [(-0.5, -0.5, 0.5), (0.5, -0.5, 0.5), (0.5, 0.5, 0.5), (-0.5, 0.5, 0.5)]),
    ((0, 0, -1), [(0.5, -0.5, -0.5), (-0.5, -0.5, -0.5), (-0.5, 0.5, -0.5), (0.5, 0.5, -0.5)]),
    ((-1, 0, 0), [(-0.5, -0.5, -0.5), (-0.5, -0.5, 0.5), (-0.5, 0.5, 0.5), (-0.5, 0.5, -0.5)]),
    ((1, 0, 0), [(0.5, -0.5, 0.5), (0.5, -0.5, -0.5), (0.5, 0.5, -0.5), (0.5, 0.5, 0.5)]),
    ((0, 1, 0), [(-0.5, 0.5, 0.5), (0.5, 0.5, 0.5), (0.5, 0.5, -0.5), (-0.5, 0.5, -0.5)]),
    ((0, -1, 0), [(-0.5, -0.5, -0.5), (0.5, -0.5, -0.5), (0.5, -0.5, 0.5), (-0.5, -0.5, 0.5)]),
]

NEIGHBOR = {
    (0, 0, 1): None, (0, 0, -1): None,  # depth is 1 voxel: front/back always visible
    (-1, 0, 0): (-1, 0), (1, 0, 0): (1, 0),
    (0, 1, 0): (0, -1), (0, -1, 0): (0, 1),  # +y up = -row direction
}

INSTANCE_FLOATS = 12  # posscale(4) + quat(4) + color(4)
IDENTITY_QUAT = (0.0, 0.0, 0.0, 1.0)


def quat_axis_angle(ax, ay, az, angle):
    s = math.sin(angle / 2)
    norm = math.sqrt(ax * ax + ay * ay + az * az) or 1.0
    return (ax / norm * s, ay / norm * s, az / norm * s, math.cos(angle / 2))


def quat_mul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    )


def build_vertices(grid, palette):
    """Extrude filled grid cells into cubes; interior side faces culled.
    Mesh is centered at origin, one voxel = one unit (scale via instances)."""
    h = len(grid)
    w = len(grid[0])
    filled = {}
    for r, row in enumerate(grid):
        for c, ch in enumerate(row):
            color = palette[ch]
            if color[3] == 0:
                continue
            filled[(c, r)] = (color[0] / 255.0, color[1] / 255.0, color[2] / 255.0)

    verts = []
    for (c, r), rgb in filled.items():
        # voxel center in mesh space (y up: row 0 at top)
        cx = c - w / 2 + 0.5
        cy = (h - 1 - r) - h / 2 + 0.5
        for normal, corners in CUBE_FACES:
            step = NEIGHBOR[normal]
            if step is not None and (c + step[0], r + step[1]) in filled:
                continue  # occluded by neighbor voxel
            quad = [(cx + px, cy + py, pz) for (px, py, pz) in corners]
            for idx in (0, 1, 2, 0, 2, 3):
                x, y, z = quad[idx]
                verts.extend([x, y, z, *normal, *rgb])
    return np.asarray(verts, dtype=np.float32)


class VoxelMesh:
    STRIDE = 9 * 4  # pos3 + normal3 + color3 floats

    def __init__(self, grid, palette):
        data = build_vertices(grid, palette)
        self.vertex_count = len(data) // 9
        self.vao = glGenVertexArrays(1)
        glBindVertexArray(self.vao)

        vbo = make_static_vbo(data)
        glBindBuffer(GL_ARRAY_BUFFER, vbo)
        setup_attrib(0, 3, self.STRIDE, 0)
        setup_attrib(1, 3, self.STRIDE, 12)
        setup_attrib(2, 3, self.STRIDE, 24)

        self.ibo = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, self.ibo)
        istride = INSTANCE_FLOATS * 4
        setup_attrib(3, 4, istride, 0, divisor=1)
        setup_attrib(4, 4, istride, 16, divisor=1)
        setup_attrib(5, 4, istride, 32, divisor=1)

        glBindBuffer(GL_ARRAY_BUFFER, 0)
        glBindVertexArray(0)

    def draw(self, instances):
        """instances: numpy float32 array shape (n, 12)."""
        n = len(instances)
        if n == 0:
            return
        glBindVertexArray(self.vao)
        glBindBuffer(GL_ARRAY_BUFFER, self.ibo)
        glBufferData(GL_ARRAY_BUFFER, instances.nbytes, instances, GL_DYNAMIC_DRAW)
        glDrawArraysInstanced(GL_TRIANGLES, 0, self.vertex_count, n)
        glBindVertexArray(0)


class VoxelShader:
    def __init__(self):
        self.program = compile_program(VOXEL_VS, VOXEL_FS)
        self.u_viewproj = glGetUniformLocation(self.program, "u_viewproj")
        self.u_lightdir = glGetUniformLocation(self.program, "u_lightdir")

    def use(self, viewproj, lightdir=(0.35, 0.75, 0.55)):
        glUseProgram(self.program)
        glUniformMatrix4fv(self.u_viewproj, 1, True, viewproj)  # row-major -> transpose
        norm = math.sqrt(sum(v * v for v in lightdir))
        glUniform3f(self.u_lightdir, *(v / norm for v in lightdir))


# ------------------------------------------------------------- matrices
def perspective(fovy_deg, aspect, near, far):
    f = 1.0 / math.tan(math.radians(fovy_deg) / 2)
    m = np.zeros((4, 4), dtype=np.float32)
    m[0, 0] = f / aspect
    m[1, 1] = f
    m[2, 2] = (far + near) / (near - far)
    m[2, 3] = 2 * far * near / (near - far)
    m[3, 2] = -1.0
    return m


def look_at(eye, center, up=(0, 1, 0)):
    eye = np.asarray(eye, dtype=np.float64)
    center = np.asarray(center, dtype=np.float64)
    f = center - eye
    f /= np.linalg.norm(f)
    u = np.asarray(up, dtype=np.float64)
    s = np.cross(f, u)
    s /= np.linalg.norm(s)
    u = np.cross(s, f)
    m = np.identity(4, dtype=np.float32)
    m[0, :3] = s
    m[1, :3] = u
    m[2, :3] = -f
    m[0, 3] = -np.dot(s, eye)
    m[1, 3] = -np.dot(u, eye)
    m[2, 3] = np.dot(f, eye)
    return m
