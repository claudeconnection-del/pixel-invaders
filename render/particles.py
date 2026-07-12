"""CPU-simulated (numpy), GPU-instanced voxel-cube particle system."""
import math
import random

import numpy as np

from render.voxel import world_from_field

CAPACITY = 4096
GRAVITY = 7.0  # world units / s^2, pulls -y


class ParticleSystem:
    def __init__(self, rng=None):
        self.rng = rng or random.Random()
        self.density = 1.0  # graphics setting: scales spawn counts
        self.pos = np.zeros((CAPACITY, 3), dtype=np.float32)
        self.vel = np.zeros((CAPACITY, 3), dtype=np.float32)
        self.color = np.zeros((CAPACITY, 4), dtype=np.float32)
        self.scale = np.zeros(CAPACITY, dtype=np.float32)
        self.life = np.zeros(CAPACITY, dtype=np.float32)
        self.max_life = np.ones(CAPACITY, dtype=np.float32)
        self.quat = np.zeros((CAPACITY, 4), dtype=np.float32)
        self.quat[:, 3] = 1.0
        self.gravity = np.zeros(CAPACITY, dtype=np.float32)
        self.cursor = 0

    def _alloc(self, n):
        idx = (np.arange(self.cursor, self.cursor + n)) % CAPACITY
        self.cursor = (self.cursor + n) % CAPACITY
        return idx

    def _rand_quats(self, n):
        out = np.empty((n, 4), dtype=np.float32)
        for i in range(n):
            angle = self.rng.uniform(0, math.tau)
            ax, ay, az = (self.rng.uniform(-1, 1) for _ in range(3))
            norm = math.sqrt(ax * ax + ay * ay + az * az) or 1.0
            s = math.sin(angle / 2)
            out[i] = (ax / norm * s, ay / norm * s, az / norm * s, math.cos(angle / 2))
        return out

    def burst(self, fx, fy, colors, count=40, speed=(2.0, 7.0), life=(0.4, 1.0),
              scale=(0.05, 0.16), emissive=1.6, gravity=1.0):
        """Explosion at field coords: cubes fly outward in 3D."""
        x, y, z = world_from_field(fx, fy)
        self.burst_world(x, y, z, colors, count=count, speed=speed, life=life,
                         scale=scale, emissive=emissive, gravity=gravity)

    def burst_world(self, x, y, z, colors, count=40, speed=(2.0, 7.0),
                    life=(0.4, 1.0), scale=(0.05, 0.16), emissive=1.6,
                    gravity=1.0):
        """Explosion at raw world coords (first-person games)."""
        count = max(1, int(count * self.density))
        idx = self._alloc(count)
        self.pos[idx] = (x, y, z)
        for k, i in enumerate(idx):
            theta = self.rng.uniform(0, math.tau)
            phi = math.acos(self.rng.uniform(-1, 1))
            spd = self.rng.uniform(*speed)
            self.vel[i] = (
                spd * math.sin(phi) * math.cos(theta),
                spd * math.sin(phi) * math.sin(theta),
                spd * math.cos(phi) * 0.6,
            )
            r, g, b = self.rng.choice(colors)
            self.color[i] = (r / 255 * emissive, g / 255 * emissive, b / 255 * emissive, 1.0)
            self.scale[i] = self.rng.uniform(*scale)
            lifespan = self.rng.uniform(*life)
            self.life[i] = lifespan
            self.max_life[i] = lifespan
            self.gravity[i] = gravity
        self.quat[idx] = self._rand_quats(count)

    def spark(self, fx, fy, color=(255, 226, 150), count=6):
        """Small bright graze spark (candle-gold by default)."""
        self.burst(fx, fy, [color], count=count, speed=(1.5, 4.0),
                   life=(0.15, 0.35), scale=(0.03, 0.07), emissive=2.4, gravity=0.2)

    def exhaust(self, fx, fy, color=(255, 158, 70)):
        """Engine trail puff below the ship (ember by default)."""
        if self.rng.random() > self.density:
            return
        idx = self._alloc(2)
        x, y, z = world_from_field(fx, fy)
        for i in idx:
            self.pos[i] = (x + self.rng.uniform(-0.08, 0.08), y - 0.8, z)
            self.vel[i] = (self.rng.uniform(-0.4, 0.4), self.rng.uniform(-2.5, -1.2), 0)
            self.color[i] = (color[0] / 255 * 1.4, color[1] / 255 * 1.4,
                             color[2] / 255 * 1.4, 0.8)
            self.scale[i] = self.rng.uniform(0.04, 0.09)
            self.life[i] = self.max_life[i] = self.rng.uniform(0.2, 0.4)
            self.gravity[i] = 0.0
        self.quat[idx] = self._rand_quats(len(idx))

    def glitter(self, fx, fy, color=(255, 214, 120)):
        """Sparkle trail for falling power-ups (candle-gold by default)."""
        if self.rng.random() > self.density:
            return
        idx = self._alloc(1)
        x, y, z = world_from_field(fx, fy)
        i = idx[0]
        self.pos[i] = (x + self.rng.uniform(-0.3, 0.3), y + self.rng.uniform(-0.3, 0.3), z)
        self.vel[i] = (0, self.rng.uniform(-0.5, 0.5), 0)
        self.color[i] = (color[0] / 255 * 2.0, color[1] / 255 * 2.0, color[2] / 255 * 2.0, 0.9)
        self.scale[i] = self.rng.uniform(0.02, 0.05)
        self.life[i] = self.max_life[i] = self.rng.uniform(0.3, 0.6)
        self.gravity[i] = 0.0
        self.quat[idx] = self._rand_quats(1)

    def update(self, dt):
        alive = self.life > 0
        self.life[alive] -= dt
        self.vel[alive, 1] -= self.gravity[alive] * GRAVITY * dt
        self.pos[alive] += self.vel[alive] * dt

    def instances(self):
        """Build the (n, 12) instance array for the voxel cube mesh."""
        alive = self.life > 0
        n = int(alive.sum())
        if n == 0:
            return np.empty((0, 12), dtype=np.float32)
        frac = np.clip(self.life[alive] / self.max_life[alive], 0.0, 1.0)
        out = np.empty((n, 12), dtype=np.float32)
        out[:, 0:3] = self.pos[alive]
        out[:, 3] = self.scale[alive] * (0.4 + 0.6 * frac)  # shrink as they die
        out[:, 4:8] = self.quat[alive]
        out[:, 8:11] = self.color[alive, 0:3]
        out[:, 11] = self.color[alive, 3] * frac  # fade out
        return out
