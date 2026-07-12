"""Voxel Breaker simulation. Pure logic — no pygame, no GL.

Paddle + ball + brick levels on the shared 640x720 field. Clearing a level
loads the next; levels loop with faster balls. Run ends when all lives are
lost. Combo multiplier climbs while the ball chews bricks without touching
the paddle.
"""
import math
import random

from game import events as ev
from game.entities import FIELD_WIDTH, FIELD_HEIGHT

LOST = "lost"
PLAYING_STATE = "playing"
INTERMISSION = "intermission"
SERVING = "serving"

BRICK_W = 48
BRICK_H = 26
BRICK_COLS = 12
GRID_X0 = (FIELD_WIDTH - BRICK_COLS * BRICK_W) // 2
GRID_Y0 = 90

BRICK_TYPES = {
    "G": {"hp": 1, "points": 10, "color": (110, 235, 140)},
    "C": {"hp": 1, "points": 20, "color": (110, 215, 245)},
    "M": {"hp": 2, "points": 30, "color": (240, 110, 215)},
    "B": {"hp": 3, "points": 50, "color": (110, 140, 245)},
}

LEVELS = [
    ("FIRST CRACK", [
        "............",
        "..GGGGGGGG..",
        ".GGGGGGGGGG.",
        ".GGCCCCCCGG.",
        "..GGGGGGGG..",
    ]),
    ("THE VAULT", [
        "BB........BB",
        "BMGGGGGGGGMB",
        ".MGCCCCCCGM.",
        ".MGCCCCCCGM.",
        "BMGGGGGGGGMB",
        "BB........BB",
    ]),
    ("CHECKERS", [
        "M.C.G.G.C.M.",
        ".C.G.M.G.C.",
        "C.G.M.M.G.C.",
        ".G.M.B.M.G.",
        "G.M.B.B.M.G.",
    ]),
    ("FORTRESS", [
        "BBBBBBBBBBBB",
        "B..........B",
        "B.MMMMMMMM.B",
        "B.MCCCCCCM.B",
        "B.MMGGGGMM.B",
        "............",
    ]),
    ("VOXEL HELLO", [
        "G.G.GGG.G...",
        "G.G.G...G...",
        "GGG.GG..G...",
        "G.G.G...G...",
        "G.G.GGG.GGG.",
    ]),
]

POWERUP_KINDS = ["multi", "wide", "laser"]


class Brick:
    def __init__(self, kind, col, row):
        spec = BRICK_TYPES[kind]
        self.kind = kind
        self.hp = spec["hp"]
        self.points = spec["points"]
        self.color = spec["color"]
        self.x = GRID_X0 + col * BRICK_W + BRICK_W / 2
        self.y = GRID_Y0 + row * BRICK_H + BRICK_H / 2
        self.alive = True


class Ball:
    def __init__(self, x, y, vx, vy):
        self.x, self.y = x, y
        self.vx, self.vy = vx, vy
        self.r = 8.0
        self.alive = True

    @property
    def speed(self):
        return math.hypot(self.vx, self.vy)


class Falling:
    """A drifting power-up capsule."""

    def __init__(self, kind, x, y):
        self.kind = kind
        self.x, self.y = x, y
        self.alive = True

    def update(self, dt):
        self.y += 120 * dt
        if self.y > FIELD_HEIGHT + 30:
            self.alive = False


class BreakerWorld:
    def __init__(self, rng=None):
        self.rng = rng or random.Random()
        self.paddle_x = FIELD_WIDTH / 2
        self.paddle_y = FIELD_HEIGHT - 60
        self.paddle_half = 55.0
        self.balls = []
        self.bricks = []
        self.powerups = []
        self.lasers = []
        self.events = []
        self.score = 0
        self.lives = 3
        self.level_index = -1
        self.loop = 1
        self.multiplier = 1.0
        self.wide_timer = 0.0
        self.laser_timer = 0.0
        self.laser_cooldown = 0.0
        self.time = 0.0
        self.state = INTERMISSION
        self.state_timer = 1.2
        self.balls_lost_this_level = 0
        self.stats = {
            "kills": 0, "shots": 0, "hits": 0, "grazes": 0, "powerups": 0,
            "deaths": 0, "max_multiplier": 1.0, "duration": 0.0,
            "wave_reached": 0, "level_reached": 0, "max_balls": 1,
            "mode": "arcade",
        }
        self.won = False

    # ------------------------------------------------------------- helpers
    def emit(self, etype, **data):
        self.events.append((etype, data))

    def drain_events(self):
        out = self.events
        self.events = []
        return out

    @property
    def run_over(self):
        return self.state == LOST

    def _ball_speed(self):
        return 300 + 25 * self.level_index + 60 * (self.loop - 1)

    # -------------------------------------------------------------- levels
    def _start_level(self, index):
        self.level_index = index
        name, layout = LEVELS[index % len(LEVELS)]
        self.loop = 1 + index // len(LEVELS)
        self.bricks = []
        for row, line in enumerate(layout):
            for col, ch in enumerate(line[:BRICK_COLS]):
                if ch in BRICK_TYPES:
                    brick = Brick(ch, col, row)
                    if self.loop > 1:
                        brick.hp += 1  # loops armor everything up
                    self.bricks.append(brick)
        self.stats["level_reached"] = index + 1
        self.stats["wave_reached"] = index + 1
        self.balls_lost_this_level = 0
        self.emit(ev.WAVE_START, index=index, name=name, mode="arcade")
        self._serve()

    def _serve(self):
        self.balls = []
        self.state = SERVING
        self.state_timer = 1.0

    def _launch(self):
        angle = -math.pi / 2 + self.rng.uniform(-0.35, 0.35)
        speed = self._ball_speed()
        self.balls = [Ball(self.paddle_x, self.paddle_y - 18,
                           math.cos(angle) * speed, math.sin(angle) * speed)]
        self.state = PLAYING_STATE

    # -------------------------------------------------------------- update
    def update(self, dt, inp):
        self.time += dt
        if not self.run_over:
            self.stats["duration"] = self.time

        if self.state == INTERMISSION:
            self.state_timer -= dt
            if self.state_timer <= 0:
                self._start_level(self.level_index + 1)
            return
        if self.state == SERVING:
            self._move_paddle(dt, inp)
            self.state_timer -= dt
            if self.state_timer <= 0:
                self._launch()
            return
        if self.state == LOST:
            return

        self._move_paddle(dt, inp)
        self._update_timers(dt)
        self._update_lasers(dt, inp)

        for ball in self.balls:
            self._update_ball(ball, dt)
        self.balls = [b for b in self.balls if b.alive]

        for pu in self.powerups:
            pu.update(dt)
            if pu.alive and abs(pu.x - self.paddle_x) < self.paddle_half + 16 \
                    and abs(pu.y - self.paddle_y) < 22:
                pu.alive = False
                self._apply_powerup(pu)
        self.powerups = [p for p in self.powerups if p.alive]

        if not self.balls and self.state == PLAYING_STATE:
            self._on_all_balls_lost()

        if not self.bricks and self.state == PLAYING_STATE:
            bonus = int(500 * (self.level_index + 1) * self.multiplier)
            self.score += bonus
            self.won = True
            self.emit(ev.LEVEL_CLEAR, index=self.level_index, bonus=bonus,
                      perfect=self.balls_lost_this_level == 0)
            self.state = INTERMISSION
            self.state_timer = 2.0

        # combo decays slowly
        if self.multiplier > 1.0:
            self.multiplier = max(1.0, self.multiplier - 0.03 * dt)

    def _move_paddle(self, dt, inp):
        speed = 420 * (0.5 if inp.focus else 1.0)
        dx = (1 if inp.right else 0) - (1 if inp.left else 0)
        self.paddle_x += dx * speed * dt
        self.paddle_x = max(self.paddle_half,
                            min(FIELD_WIDTH - self.paddle_half, self.paddle_x))

    def _update_timers(self, dt):
        if self.wide_timer > 0:
            self.wide_timer -= dt
            self.paddle_half = 85.0
        else:
            self.paddle_half = 55.0
        if self.laser_timer > 0:
            self.laser_timer -= dt
        if self.laser_cooldown > 0:
            self.laser_cooldown -= dt

    def _update_lasers(self, dt, inp):
        if self.laser_timer > 0 and inp.fire and self.laser_cooldown <= 0:
            self.laser_cooldown = 0.3
            for off in (-self.paddle_half + 12, self.paddle_half - 12):
                self.lasers.append(Ball(self.paddle_x + off, self.paddle_y - 14,
                                        0, -620))
            self.stats["shots"] += 2
            self.emit(ev.SHOT_FIRED, count=2)
        for bolt in self.lasers:
            bolt.y += bolt.vy * dt
            if bolt.y < -20:
                bolt.alive = False
                continue
            hit = self._brick_at(bolt.x, bolt.y, r=4)
            if hit is not None:
                bolt.alive = False
                self.stats["hits"] += 1
                self._damage_brick(hit)
        self.lasers = [b for b in self.lasers if b.alive]

    def _brick_at(self, x, y, r):
        for brick in self.bricks:
            if abs(x - brick.x) <= BRICK_W / 2 + r and \
                    abs(y - brick.y) <= BRICK_H / 2 + r:
                return brick
        return None

    def _update_ball(self, ball, dt):
        ball.x += ball.vx * dt
        ball.y += ball.vy * dt

        # walls
        if ball.x < ball.r:
            ball.x = ball.r
            ball.vx = abs(ball.vx)
        elif ball.x > FIELD_WIDTH - ball.r:
            ball.x = FIELD_WIDTH - ball.r
            ball.vx = -abs(ball.vx)
        if ball.y < 40 + ball.r:
            ball.y = 40 + ball.r
            ball.vy = abs(ball.vy)
        elif ball.y > FIELD_HEIGHT + 20:
            ball.alive = False
            self.emit(ev.BALL_LOST, x=ball.x, y=FIELD_HEIGHT - 10)
            return

        # paddle
        if ball.vy > 0 and abs(ball.y - self.paddle_y) < ball.r + 10 \
                and abs(ball.x - self.paddle_x) < self.paddle_half + ball.r:
            offset = (ball.x - self.paddle_x) / self.paddle_half
            angle = -math.pi / 2 + offset * 1.05
            speed = min(self._ball_speed() * 1.25, ball.speed * 1.02)
            ball.vx = math.cos(angle) * speed
            ball.vy = math.sin(angle) * speed
            ball.y = self.paddle_y - ball.r - 10
            self.multiplier = 1.0  # combo resets at the paddle

        # bricks
        brick = self._brick_at(ball.x, ball.y, ball.r)
        if brick is not None:
            # reflect on the axis of least penetration
            dx = (ball.x - brick.x) / (BRICK_W / 2)
            dy = (ball.y - brick.y) / (BRICK_H / 2)
            if abs(dx) > abs(dy):
                ball.vx = math.copysign(abs(ball.vx), dx)
            else:
                ball.vy = math.copysign(abs(ball.vy), dy)
            self.stats["hits"] += 1
            self._damage_brick(brick)

    def _damage_brick(self, brick):
        brick.hp -= 1
        if brick.hp > 0:
            return
        brick.alive = False
        self.bricks = [b for b in self.bricks if b.alive]
        pts = int(brick.points * self.multiplier)
        self.score += pts
        self.stats["kills"] += 1
        self.multiplier = min(5.0, self.multiplier + 0.15)
        self.stats["max_multiplier"] = max(self.stats["max_multiplier"],
                                           self.multiplier)
        self.emit(ev.ENEMY_KILLED, kind=brick.kind, x=brick.x, y=brick.y,
                  points_awarded=pts, color=brick.color)
        if self.rng.random() < 0.14:
            kind = self.rng.choice(POWERUP_KINDS)
            self.powerups.append(Falling(kind, brick.x, brick.y))
            self.emit(ev.POWERUP_SPAWN, kind=kind, x=brick.x, y=brick.y)

    def _apply_powerup(self, pu):
        self.stats["powerups"] += 1
        if pu.kind == "multi":
            new_balls = []
            for ball in self.balls[:2]:
                for spread in (-0.5, 0.5):
                    angle = math.atan2(ball.vy, ball.vx) + spread
                    speed = ball.speed
                    new_balls.append(Ball(ball.x, ball.y,
                                          math.cos(angle) * speed,
                                          math.sin(angle) * speed))
            self.balls += new_balls
            self.stats["max_balls"] = max(self.stats["max_balls"],
                                          len(self.balls))
        elif pu.kind == "wide":
            self.wide_timer = 10.0
        elif pu.kind == "laser":
            self.laser_timer = 10.0
        self.emit(ev.POWERUP_PICKUP, kind=pu.kind, x=pu.x, y=pu.y)

    def _on_all_balls_lost(self):
        self.lives -= 1
        self.multiplier = 1.0
        self.balls_lost_this_level += 1
        self.stats["deaths"] += 1
        self.emit(ev.PLAYER_HIT, lives_left=self.lives,
                  x=self.paddle_x, y=self.paddle_y)
        if self.lives <= 0:
            self.state = LOST
            self.emit(ev.PLAYER_DEATH)
            self.emit(ev.RUN_END, win=self.won, summary=self.run_summary(self.won))
        else:
            self._serve()

    # -------------------------------------------------------------- output
    def run_summary(self, win):
        s = dict(self.stats)
        s["win"] = win
        s["score"] = self.score
        s["accuracy"] = (s["hits"] / s["shots"]) if s["shots"] else 0.0
        return s
