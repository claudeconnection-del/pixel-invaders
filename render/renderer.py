"""Scene orchestration: camera, starfield, entity batching, HUD, effects.

The world simulation knows nothing about any of this; main.py hands the
world to draw_world() each frame and forwards events to the effect hooks
(shake/aberration/particle bursts live here).
"""
import colorsys
import math
import random

import numpy as np
from OpenGL.GL import (
    GL_BLEND, GL_DEPTH_TEST, GL_ONE_MINUS_SRC_ALPHA, GL_SRC_ALPHA,
    glBlendFunc, glDisable, glEnable,
)

from game.skins import SKINS
from game.sprites import ALL_SPRITES, PALETTE
from render.particles import ParticleSystem
from render.post import PostPipeline
from render.text import OverlayRenderer
from render.voxel import (
    IDENTITY_QUAT, VoxelMesh, VoxelShader, look_at, perspective,
    quat_axis_angle, world_from_field,
)

# per-voxel world scale for each sprite family
SCALES = {
    "ship": 0.25,
    "enemy": 0.25,
    "boss": 0.30,
    "bullet_player": 0.22,
    "bullet_enemy": 0.17,
    "bullet_orb": 0.17,
    "bullet_wall": 0.17,
    "powerup": 0.22,
}

ENEMY_TINTS = {
    "squid": (1.0, 1.0, 1.0, 1.0),
    "crab": (1.0, 1.0, 1.0, 1.0),
    "octo": (1.0, 1.0, 1.0, 1.0),
    "elite": (1.15, 1.15, 1.25, 1.0),
}

EXPLOSION_COLORS = {
    "squid": [(80, 200, 230), (160, 240, 255), (250, 220, 90)],
    "crab": [(230, 80, 200), (255, 150, 230), (250, 150, 60)],
    "octo": [(80, 220, 120), (140, 255, 170), (250, 220, 90)],
    "elite": [(70, 110, 230), (140, 180, 255), (240, 240, 240)],
    "boss": [(150, 80, 220), (200, 150, 255), (230, 60, 60), (250, 220, 90)],
    "player": [(240, 240, 240), (250, 150, 60), (230, 60, 60)],
}

POWERUP_SPRITES = {
    "spread": "powerup_spread",
    "rapid": "powerup_rapid",
    "shield": "powerup_shield",
}


class Renderer:
    def __init__(self, width, height, rng=None):
        self.width = width
        self.height = height
        self.rng = rng or random.Random()

        self.shader = VoxelShader()
        self.post = PostPipeline(width, height)
        self.overlay = OverlayRenderer(width, height)
        self.particles = ParticleSystem(self.rng)

        self.meshes = {name: VoxelMesh(grid, PALETTE)
                       for name, grid in ALL_SPRITES.items()}
        self.cube = VoxelMesh(["W"], PALETTE)  # single voxel for particles/stars

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

    # ------------------------------------------------------------ effects
    def add_shake(self, amount):
        self.shake = min(0.6, self.shake + amount)

    def add_aberration(self, amount):
        self.aberration = min(1.0, self.aberration + amount)

    def explosion(self, kind, x, y, big=False):
        colors = EXPLOSION_COLORS.get(kind, EXPLOSION_COLORS["octo"])
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

    # ------------------------------------------------------- world drawing
    def draw_world(self, world, skin_id):
        vp = self._viewproj()
        self.shader.use(vp)

        self.cube.draw(self._star_instances())
        self.cube.draw(self.wall_instances)

        batches = {}  # sprite -> list of instance rows

        def add(sprite, fx, fy, scale, quat=IDENTITY_QUAT, tint=(1, 1, 1, 1), z=0.0):
            x, y, wz = world_from_field(fx, fy, z)
            batches.setdefault(sprite, []).append(
                (x, y, wz, scale, *quat, *tint))

        t = self.time

        for e in world.enemies:
            frame = "a" if int(e.time_alive * 2.5) % 2 == 0 else "b"
            wobble = quat_axis_angle(0, 0, 1, math.sin(t * 1.7 + e.bob_phase) * 0.07)
            add(f"enemy_{e.kind}_{frame}", e.x, e.y, SCALES["enemy"],
                quat=wobble, tint=ENEMY_TINTS[e.kind])

        boss = world.boss
        if boss is not None and boss.alive:
            pulse = 1.0 + 0.12 * max(0.0, math.sin(t * (2.0 + boss.phase)))
            flash = 1.0 + (boss.phase - 1) * 0.12
            add("boss", boss.x, boss.y, SCALES["boss"],
                quat=quat_axis_angle(0, 0, 1, math.sin(t * 0.8) * 0.08),
                tint=(flash * pulse, flash, flash * pulse, 1.0))

        for b in world.player_bullets:
            add("bullet_player", b.x, b.y, SCALES["bullet_player"],
                tint=(1.7, 1.7, 1.9, 1.0))

        for b in world.enemy_bullets:
            spin = quat_axis_angle(0, 0, 1, t * 4.0 + (id(b) % 100) * 0.06)
            add(b.sprite, b.x, b.y, SCALES.get(b.sprite, 0.17),
                quat=spin, tint=(1.75, 1.75, 1.75, 1.0))

        for pu in world.powerups:
            spin = quat_axis_angle(0, 1, 0, t * 2.4 + pu.time_alive)
            add(POWERUP_SPRITES[pu.kind], pu.x, pu.y, SCALES["powerup"],
                quat=spin, tint=(1.5, 1.5, 1.5, 1.0))

        p = world.player
        if p.alive:
            skin = SKINS[skin_id]
            tint = [1.0, 1.0, 1.0, 1.0]
            if skin["special"] == "translucent":
                tint[3] = 0.55
            elif skin["special"] == "hue_cycle":
                r, g, b = colorsys.hsv_to_rgb((t * 0.18) % 1.0, 0.6, 1.0)
                tint[0], tint[1], tint[2] = r * 1.35, g * 1.35, b * 1.35
            if p.invuln > 0:
                tint[3] *= 0.45 + 0.4 * math.sin(t * 24)
            bank = quat_axis_angle(0, 1, 0, math.sin(t * 3.1) * 0.12)
            add(skin["sprite"], p.x, p.y, SCALES["ship"], quat=bank, tint=tuple(tint))

            if p.shield:
                aura = quat_axis_angle(0.4, 1, 0.2, t * 1.5)
                add("powerup_shield", p.x, p.y, 0.34, quat=aura,
                    tint=(0.5, 0.8, 1.6, 0.22))

        for sprite, rows in batches.items():
            self.meshes[sprite].draw(np.asarray(rows, dtype=np.float32))

        # focus hitbox indicator + particles: emissive, drawn last
        late = []
        if p.alive and getattr(self, "show_hitbox", False):
            x, y, z = world_from_field(p.x, p.y, 0.6)
            late.append((x, y, z, 0.11, *quat_axis_angle(0, 0, 1, t * 3),
                         2.6, 2.4, 2.6, 1.0))
        parts = self.particles.instances()
        if late:
            late_arr = np.asarray(late, dtype=np.float32)
            parts = np.vstack([parts, late_arr]) if len(parts) else late_arr
        if len(parts):
            self.cube.draw(parts)

    def draw_menu_model(self, sprite, fx, fy, scale, spin_speed=1.0, tint=(1, 1, 1, 1)):
        """Rotating showcase model for menu screens (field coords)."""
        vp = self._viewproj()
        self.shader.use(vp)
        self.cube.draw(self._star_instances())
        q = quat_axis_angle(0, 1, 0.12, self.time * spin_speed)
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
