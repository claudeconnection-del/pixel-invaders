"""Generic voxel scene engine: camera, starfield, instanced sprite batches,
particles, post-processing, effect state (shake/aberration).

Game content lives in games/<id>/; a game builds a Batcher each frame and
the renderer flushes it. Nothing here knows about any specific game.
"""
import math
import random

import numpy as np
from OpenGL.GL import (
    GL_BLEND, GL_DEPTH_TEST, GL_ONE_MINUS_SRC_ALPHA, GL_SRC_ALPHA,
    glBlendFunc, glDisable, glEnable,
)

from game.sprites import ALL_SPRITES, PALETTE
from render.particles import ParticleSystem
from render.post import PostPipeline
from render.text import OverlayRenderer
from render.voxel import (
    IDENTITY_QUAT, VoxelMesh, VoxelShader, look_at, perspective,
    quat_axis_angle, quat_mul, world_from_field,
)


class Batcher:
    """Per-frame collection of sprite instances in field coordinates."""

    def __init__(self):
        self.batches = {}   # sprite name -> instance rows
        self.late_cubes = []  # emissive cubes drawn last (with particles)

    def add(self, sprite, fx, fy, scale, quat=IDENTITY_QUAT,
            tint=(1, 1, 1, 1), z=0.0):
        x, y, wz = world_from_field(fx, fy, z)
        self.batches.setdefault(sprite, []).append((x, y, wz, scale, *quat, *tint))

    def add_cube_late(self, fx, fy, scale, quat=IDENTITY_QUAT,
                      tint=(1, 1, 1, 1), z=0.0):
        x, y, wz = world_from_field(fx, fy, z)
        self.late_cubes.append((x, y, wz, scale, *quat, *tint))


class Renderer:
    def __init__(self, width, height, out_width=None, out_height=None, rng=None):
        # width/height: internal render resolution (fixed HUD space);
        # out_*: window size, letterboxed by the post pass.
        self.width = width
        self.height = height
        self.rng = rng or random.Random()

        self.shader = VoxelShader()
        self.post = PostPipeline(width, height, out_width, out_height)
        self.overlay = OverlayRenderer(width, height)
        self.particles = ParticleSystem(self.rng)

        self.meshes = {name: VoxelMesh(grid, PALETTE)
                       for name, grid in ALL_SPRITES.items()}
        self.cube = VoxelMesh(["W"], PALETTE)  # single voxel for particles/stars
        self.meshes["cube"] = self.cube       # games may batch plain cubes

        self.proj = perspective(52.0, width / height, 0.1, 100.0)

        # effects state
        self.shake = 0.0
        self.aberration = 0.0
        self.time = 0.0

        # starfield
        n = 520
        self.star_pos = np.empty((n, 3), dtype=np.float32)
        self.star_pos[:, 0] = np.random.uniform(-16, 16, n)
        self.star_pos[:, 1] = np.random.uniform(-14, 14, n)
        self.star_pos[:, 2] = np.random.uniform(-30, -6, n)
        self.star_speed = np.random.uniform(0.4, 1.8, n).astype(np.float32)
        shade = np.random.uniform(0.25, 0.8, n).astype(np.float32)
        self.star_color = np.empty((n, 4), dtype=np.float32)
        self.star_color[:, 0] = shade * 0.8
        self.star_color[:, 1] = shade * 0.85
        self.star_color[:, 2] = shade
        self.star_color[:, 3] = 1.0
        self.star_scale = np.random.uniform(0.02, 0.06, n).astype(np.float32)

        # arena boundary: dim emissive studs marking the field edges
        studs = []
        for fy in range(0, 721, 36):
            for fx in (-6, 646):
                x, y, z = world_from_field(fx, fy)
                studs.append((x, y, z, 0.055, 0, 0, 0, 1, 0.25, 0.75, 0.85, 0.5))
        self.wall_instances = np.asarray(studs, dtype=np.float32)

    # ----------------------------------------------------------- settings
    def apply_quality(self, bloom="full", particles="high"):
        self.post.bloom_iterations = {"off": 0, "low": 1, "full": 2}[bloom]
        self.particles.density = {"low": 0.35, "medium": 0.7, "high": 1.0}[particles]

    # ------------------------------------------------------------ effects
    def add_shake(self, amount):
        self.shake = min(0.6, self.shake + amount)

    def add_aberration(self, amount):
        self.aberration = min(1.0, self.aberration + amount)

    def explosion(self, colors, x, y, big=False):
        """colors: list of (r, g, b) 0-255 tuples for the burst."""
        if big:
            self.particles.burst(x, y, colors, count=220, speed=(2.5, 11.0),
                                 life=(0.6, 1.6), scale=(0.06, 0.22), emissive=1.9)
        else:
            self.particles.burst(x, y, colors, count=42)

    # ------------------------------------------------------------- frame
    def begin(self, dt):
        self.time += dt
        self.shake = max(0.0, self.shake - dt * 1.8)
        self.aberration = max(0.0, self.aberration - dt * 2.2)
        self.particles.update(dt)

        # starfield drift (wrap at bottom)
        self.star_pos[:, 1] -= self.star_speed * dt
        wrapped = self.star_pos[:, 1] < -14
        self.star_pos[wrapped, 1] = 14

        self.post.begin_scene()
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

    def _viewproj(self):
        t = self.time
        sx = (self.rng.uniform(-1, 1) * self.shake)
        sy = (self.rng.uniform(-1, 1) * self.shake)
        # pulled back far enough to frame the whole 640x720 field, from
        # slightly below center so the player's end feels closer
        eye = (math.sin(t * 0.13) * 0.3 + sx, -5.5 + sy, 25.5)
        center = (sx * 0.5, sy * 0.5, 0.0)
        return self.proj @ look_at(eye, center)

    def _star_instances(self):
        n = len(self.star_pos)
        out = np.empty((n, 12), dtype=np.float32)
        out[:, 0:3] = self.star_pos
        out[:, 3] = self.star_scale
        out[:, 4:7] = 0.0
        out[:, 7] = 1.0
        out[:, 8:12] = self.star_color
        return out

    # ------------------------------------------------------- scene drawing
    def draw_scene(self, batcher, walls=True):
        """Draw backdrop + a game's Batcher + particles in one pass."""
        vp = self._viewproj()
        self.shader.use(vp)

        self.cube.draw(self._star_instances())
        if walls:
            self.cube.draw(self.wall_instances)

        for sprite, rows in batcher.batches.items():
            self.meshes[sprite].draw(np.asarray(rows, dtype=np.float32))

        parts = self.particles.instances()
        if batcher.late_cubes:
            late_arr = np.asarray(batcher.late_cubes, dtype=np.float32)
            parts = np.vstack([parts, late_arr]) if len(parts) else late_arr
        if len(parts):
            self.cube.draw(parts)

    def draw_menu_model(self, sprite, fx, fy, scale, spin_speed=1.0, tint=(1, 1, 1, 1)):
        """Rotating showcase model for menu screens (field coords)."""
        vp = self._viewproj()
        self.shader.use(vp)
        self.cube.draw(self._star_instances())
        # rock +/-60 deg instead of full revolutions (a 1-voxel-thick model
        # vanishes edge-on at 90) and lean back for depth
        tilt = quat_axis_angle(1, 0, 0, -0.45)
        spin = quat_axis_angle(0, 1, 0, math.sin(self.time * spin_speed) * 0.65)
        q = quat_mul(tilt, spin)
        x, y, z = world_from_field(fx, fy, 1.5)
        row = np.asarray([(x, y, z, scale, *q, *tint)], dtype=np.float32)
        self.meshes[sprite].draw(row)

    def draw_starfield_only(self):
        vp = self._viewproj()
        self.shader.use(vp)
        self.cube.draw(self._star_instances())

    # ------------------------------------------------------------ overlay
    def begin_overlay(self):
        glDisable(GL_DEPTH_TEST)
        self.overlay.begin()

    def finish(self, crt=True):
        self.post.finish(self.time, aberration=self.aberration, crt=crt)
