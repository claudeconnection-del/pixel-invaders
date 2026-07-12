"""Composable bullet pattern generators.

Each pattern is a small stateful object; world calls update(dt, ctx) every
frame while the owner is alive, and the pattern spawns bullets through
ctx.spawn(x, y, angle_rad, speed, sprite, r, curve). Angles: 0 = +x (right),
pi/2 = +y (down, toward the player).
"""
import math


class PatternContext:
    """What a pattern is allowed to see/do. Provided by the world."""

    def __init__(self, spawn, player_x, player_y, bullet_budget):
        self.spawn = spawn
        self.player_x = player_x
        self.player_y = player_y
        self.bullet_budget = bullet_budget  # how many more bullets may spawn this frame


class AimedBurst:
    """Fires n-shot fans aimed at the player every `interval` seconds."""

    def __init__(self, interval=1.4, count=1, spread_deg=10.0, speed=170.0,
                 sprite="bullet_enemy", start_delay=0.0):
        self.interval = interval
        self.count = count
        self.spread = math.radians(spread_deg)
        self.speed = speed
        self.sprite = sprite
        self.timer = -start_delay

    def scale(self, d):
        self.interval /= d
        self.speed *= 1 + 0.3 * (d - 1)

    def update(self, dt, ctx, x, y):
        self.timer += dt
        if self.timer < self.interval:
            return
        self.timer = 0.0
        aim = math.atan2(ctx.player_y - y, ctx.player_x - x)
        n = min(self.count, ctx.bullet_budget)
        for i in range(n):
            off = (i - (n - 1) / 2) * self.spread
            ctx.spawn(x, y, aim + off, self.speed, self.sprite, 5.0)


class RadialBurst:
    """Rings of bullets in all directions; each volley rotates slightly."""

    def __init__(self, interval=2.2, count=16, speed=140.0, rotate_deg=9.0,
                 sprite="bullet_orb", start_delay=0.0):
        self.interval = interval
        self.count = count
        self.speed = speed
        self.rotate = math.radians(rotate_deg)
        self.sprite = sprite
        self.timer = -start_delay
        self.volley = 0

    def scale(self, d):
        self.interval /= d
        self.speed *= 1 + 0.3 * (d - 1)
        self.count = int(self.count * (1 + 0.2 * (d - 1)))

    def update(self, dt, ctx, x, y):
        self.timer += dt
        if self.timer < self.interval:
            return
        self.timer = 0.0
        base = self.volley * self.rotate
        n = min(self.count, ctx.bullet_budget)
        for i in range(n):
            angle = base + i * (2 * math.pi / self.count)
            ctx.spawn(x, y, angle, self.speed, self.sprite, 6.0)
        self.volley += 1


class Spiral:
    """Continuous rotating spiral arms."""

    def __init__(self, arms=2, rate=9.0, speed=130.0, omega_deg=95.0,
                 sprite="bullet_orb", curve_deg=0.0, start_delay=0.0):
        self.arms = arms
        self.rate = rate          # bullets per arm per second
        self.speed = speed
        self.omega = math.radians(omega_deg)
        self.sprite = sprite
        self.curve = math.radians(curve_deg)
        self.angle = 0.0
        self.emit_acc = -start_delay * rate

    def scale(self, d):
        self.rate *= d
        self.speed *= 1 + 0.3 * (d - 1)
        self.omega *= 1 + 0.2 * (d - 1)

    def update(self, dt, ctx, x, y):
        self.angle += self.omega * dt
        self.emit_acc += self.rate * dt
        while self.emit_acc >= 1.0:
            self.emit_acc -= 1.0
            if ctx.bullet_budget < self.arms:
                continue
            for a in range(self.arms):
                angle = self.angle + a * (2 * math.pi / self.arms)
                ctx.spawn(x, y, angle, self.speed, self.sprite, 6.0, self.curve)


class WallVolley:
    """Horizontal curtain of bullets falling from the owner's row, with a
    randomly placed gap the player must slip through."""

    def __init__(self, interval=3.2, columns=14, speed=120.0, gap_cols=3,
                 sprite="bullet_wall", start_delay=0.0, rng=None):
        self.interval = interval
        self.columns = columns
        self.speed = speed
        self.gap_cols = gap_cols
        self.sprite = sprite
        self.timer = -start_delay
        self.rng = rng

    def scale(self, d):
        self.interval /= d
        self.speed *= 1 + 0.3 * (d - 1)

    def update(self, dt, ctx, x, y):
        self.timer += dt
        if self.timer < self.interval:
            return
        self.timer = 0.0
        from game.entities import FIELD_WIDTH
        gap_start = (self.rng.randrange(self.columns - self.gap_cols)
                     if self.rng else (self.columns - self.gap_cols) // 2)
        spacing = FIELD_WIDTH / self.columns
        n_spawned = 0
        for col in range(self.columns):
            if gap_start <= col < gap_start + self.gap_cols:
                continue
            if n_spawned >= ctx.bullet_budget:
                break
            bx = spacing * (col + 0.5)
            ctx.spawn(bx, y, math.pi / 2, self.speed, self.sprite, 6.0)
            n_spawned += 1
