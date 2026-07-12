"""Entity data types for the bullet-hell simulation.

Pure logic: no pygame, no GL. Positions are floats on a 640x720 logical
playfield (origin top-left, y down). Collision is circle-based.
"""
import math
from dataclasses import dataclass, field

FIELD_WIDTH = 640
FIELD_HEIGHT = 720


@dataclass
class InputState:
    left: bool = False
    right: bool = False
    up: bool = False
    down: bool = False
    focus: bool = False
    fire: bool = False
    # pointer aim in logical screen coords (1280x860 render space); used by
    # the FPS games, ignored by the classics
    aim_x: float = 640.0
    aim_y: float = 430.0


@dataclass
class Player:
    x: float = FIELD_WIDTH / 2
    y: float = FIELD_HEIGHT - 70
    speed: float = 300.0
    focus_speed: float = 150.0
    hitbox_r: float = 4.0
    graze_r: float = 18.0
    lives: int = 3
    fire_cooldown: float = 0.0
    base_fire_delay: float = 0.14
    invuln: float = 0.0
    shield: bool = False
    spread_timer: float = 0.0
    rapid_timer: float = 0.0
    alive: bool = True

    @property
    def fire_delay(self):
        return self.base_fire_delay * (0.5 if self.rapid_timer > 0 else 1.0)

    def update(self, dt, inp):
        speed = self.focus_speed if inp.focus else self.speed
        dx = (1 if inp.right else 0) - (1 if inp.left else 0)
        dy = (1 if inp.down else 0) - (1 if inp.up else 0)
        if dx and dy:
            norm = 1 / math.sqrt(2)
            dx *= norm
            dy *= norm
        self.x = max(20, min(FIELD_WIDTH - 20, self.x + dx * speed * dt))
        self.y = max(FIELD_HEIGHT * 0.45, min(FIELD_HEIGHT - 30, self.y + dy * speed * dt))
        if self.fire_cooldown > 0:
            self.fire_cooldown -= dt
        if self.invuln > 0:
            self.invuln -= dt
        if self.spread_timer > 0:
            self.spread_timer -= dt
        if self.rapid_timer > 0:
            self.rapid_timer -= dt


@dataclass
class Bullet:
    x: float
    y: float
    vx: float
    vy: float
    r: float = 5.0
    sprite: str = "bullet_enemy"
    from_player: bool = False
    grazed: bool = False
    curve: float = 0.0  # radians/sec applied to velocity direction
    alive: bool = True

    def update(self, dt):
        if self.curve:
            angle = math.atan2(self.vy, self.vx) + self.curve * dt
            speed = math.hypot(self.vx, self.vy)
            self.vx = math.cos(angle) * speed
            self.vy = math.sin(angle) * speed
        self.x += self.vx * dt
        self.y += self.vy * dt
        if not (-40 <= self.x <= FIELD_WIDTH + 40 and -40 <= self.y <= FIELD_HEIGHT + 40):
            self.alive = False


@dataclass
class Enemy:
    kind: str            # squid | crab | octo | elite
    slot_x: float        # formation home position
    slot_y: float
    hp: int
    points: int
    radius: float = 22.0
    entry_delay: float = 0.0
    entry_t: float = 0.0  # 0..1 fly-in progress
    spawn_x: float = 0.0
    spawn_y: float = -60.0
    bob_phase: float = 0.0
    patterns: list = field(default_factory=list)
    x: float = 0.0
    y: float = -60.0
    time_alive: float = 0.0
    alive: bool = True

    ENTRY_DURATION = 1.2

    def update(self, dt, formation_offset_x):
        self.time_alive += dt
        if self.time_alive < self.entry_delay:
            self.x, self.y = self.spawn_x, self.spawn_y
            return False  # not yet active (can't fire)
        if self.entry_t < 1.0:
            self.entry_t = min(1.0, self.entry_t + dt / self.ENTRY_DURATION)
            # ease-out fly-in from spawn point to formation slot
            k = 1 - (1 - self.entry_t) ** 3
            self.x = self.spawn_x + (self.slot_x - self.spawn_x) * k
            self.y = self.spawn_y + (self.slot_y - self.spawn_y) * k
            return False
        t = self.time_alive
        self.x = self.slot_x + formation_offset_x + math.sin(t * 1.7 + self.bob_phase) * 6
        self.y = self.slot_y + math.sin(t * 2.3 + self.bob_phase * 2) * 4
        return True  # in formation, may fire


@dataclass
class Boss:
    hp: int
    max_hp: int
    x: float = FIELD_WIDTH / 2
    y: float = 150.0
    radius: float = 58.0
    time_alive: float = 0.0
    phase: int = 1  # 1..3
    alive: bool = True

    def update(self, dt):
        self.time_alive += dt
        t = self.time_alive
        self.x = FIELD_WIDTH / 2 + math.sin(t * 0.55) * 170
        self.y = 150 + math.sin(t * 1.1) * 24

    @property
    def hp_frac(self):
        return max(0.0, self.hp / self.max_hp)


@dataclass
class PowerUp:
    kind: str  # spread | rapid | shield
    x: float
    y: float
    vy: float = 95.0
    radius: float = 24.0
    time_alive: float = 0.0
    alive: bool = True

    def update(self, dt):
        self.time_alive += dt
        self.y += self.vy * dt
        self.x += math.sin(self.time_alive * 2.2) * 20 * dt
        if self.y > FIELD_HEIGHT + 40:
            self.alive = False


def dist_sq(ax, ay, bx, by):
    dx, dy = ax - bx, ay - by
    return dx * dx + dy * dy


def circles_hit(ax, ay, ar, bx, by, br):
    r = ar + br
    return dist_sq(ax, ay, bx, by) <= r * r
