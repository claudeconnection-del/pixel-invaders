"""Voxel Breaker's cabinet integration: drawing, HUD, effects."""
import math

from arcade.game_api import GameInfo, GameRun
from game import events as ev
from render.renderer import Batcher
from render.voxel import quat_axis_angle

from games.breaker.world import (
    BreakerWorld, BRICK_TYPES, SERVING, INTERMISSION, BRICK_W, BRICK_H,
)

INFO = GameInfo(
    "breaker", "VOXEL BREAKER",
    "Brick demolition with a combo habit.",
    showcase_sprite="brick",
    modes=[("arcade", "ARCADE")],
)

GREEN = (140, 255, 170, 255)
DIM = (150, 150, 165, 255)
WHITE = (235, 235, 240, 255)
GOLD = (250, 220, 90, 255)
RED = (255, 110, 100, 255)
CYAN = (140, 235, 255, 255)

POWERUP_SPRITES = {"multi": "powerup_spread", "wide": "powerup_shield",
                   "laser": "powerup_rapid"}


class BreakerRun(GameRun):
    def __init__(self, mode, rng):
        self.mode = mode
        self.world = BreakerWorld(rng=rng)
        self.time = 0.0

    @property
    def score(self):
        return self.world.score

    @property
    def run_over(self):
        return self.world.run_over

    def update(self, dt, inp):
        self.time += dt
        self.world.update(dt, inp)

    def drain_events(self):
        return self.world.drain_events()

    def run_stats(self):
        return self.world.stats

    def run_summary(self):
        return self.world.run_summary(self.world.won)

    # ---------------------------------------------------------- effects
    def on_event(self, etype, data, renderer, audio, banner):
        if etype == ev.ENEMY_KILLED:
            base = data["color"]
            colors = [base, (240, 240, 240),
                      tuple(min(255, c + 60) for c in base)]
            renderer.explosion(colors, data["x"], data["y"])
            renderer.add_shake(0.03)
            audio.play("explosion_enemy")
        elif etype == ev.SHOT_FIRED:
            audio.play("shoot")
        elif etype == ev.BALL_LOST:
            renderer.add_shake(0.2)
            audio.play("shield_break")
        elif etype == ev.PLAYER_HIT:
            renderer.add_aberration(0.6)
            audio.play("explosion_player")
        elif etype == ev.WAVE_START:
            banner(f"LEVEL {data['index'] + 1}: {data['name']}", 2.4)
            audio.play(f"step_{data['index'] % 4}")
        elif etype == ev.LEVEL_CLEAR:
            extra = "  [PERFECT]" if data["perfect"] else ""
            banner(f"LEVEL CLEAR  +{data['bonus']}{extra}", 2.2)
            audio.play("win")
        elif etype == ev.POWERUP_PICKUP:
            renderer.particles.burst(data["x"], data["y"],
                                     [(180, 255, 190), (250, 220, 90)],
                                     count=24, gravity=0.2)
            audio.play("powerup")
        elif etype == ev.RUN_END:
            audio.play("win" if data["win"] else "game_over")

    # ------------------------------------------------------------ visuals
    def draw(self, renderer, section):
        w = self.world
        t = self.time
        b = Batcher()

        for brick in w.bricks:
            armor = 1.0 + 0.25 * (brick.hp - 1)
            tint = (brick.color[0] / 255 * armor, brick.color[1] / 255 * armor,
                    brick.color[2] / 255 * armor, 1.0)
            b.add("brick", brick.x, brick.y, BRICK_W / 6 / 32, tint=tint)

        paddle_tint = (1.0, 1.0, 1.0, 1.0)
        if w.laser_timer > 0:
            paddle_tint = (1.5, 1.2, 0.7, 1.0)
        b.add("paddle", w.paddle_x, w.paddle_y,
              (w.paddle_half * 2) / 10 / 32, tint=paddle_tint)

        for ball in w.balls:
            spin = quat_axis_angle(0.3, 0.8, 0.5, t * 6)
            b.add("bullet_orb", ball.x, ball.y, 0.16, quat=spin,
                  tint=(1.9, 1.9, 1.9, 1.0))
        if w.state == SERVING:
            pulse = 1.2 + 0.6 * abs(math.sin(t * 4))
            b.add("bullet_orb", w.paddle_x, w.paddle_y - 18, 0.16,
                  tint=(pulse, pulse, pulse, 1.0))

        for bolt in w.lasers:
            b.add("bullet_player", bolt.x, bolt.y, 0.2,
                  tint=(1.9, 1.4, 0.9, 1.0))

        for pu in w.powerups:
            spin = quat_axis_angle(0, 1, 0, t * 2.4)
            b.add(POWERUP_SPRITES[pu.kind], pu.x, pu.y, 0.2, quat=spin,
                  tint=(1.5, 1.5, 1.5, 1.0))

        renderer.draw_scene(b)

    def per_frame_particles(self, renderer, rng):
        for ball in self.world.balls:
            if rng.random() < 0.5:
                renderer.particles.glitter(ball.x, ball.y,
                                           color=(200, 220, 255))

    def draw_hud(self, o, width, height, section):
        w = self.world
        life = section["lifetime"]
        o.text(f"SCORE {w.score:07d}", 26, 16, size=22, color=GREEN)
        o.text(f"BEST  {max(life['best_score'], w.score):07d}", 26, 46,
               size=16, color=DIM)
        frac = (w.multiplier - 1.0) / 4.0
        o.text(f"x{w.multiplier:.1f}", 26, 76, size=18, color=GOLD)
        o.rect(80, 80, 130, 10, (45, 45, 65, 220))
        o.rect(80, 80, 130 * frac, 10, GOLD)
        o.text(f"LEVEL {w.level_index + 1}", 26, 100, size=14, color=CYAN)

        o.text("BALLS", width - 210, 16, size=16, color=DIM)
        for i in range(max(0, w.lives)):
            o.rect(width - 130 + i * 26, 16, 18, 18, CYAN)

        y = 46
        if w.wide_timer > 0:
            o.text(f"[WIDE {w.wide_timer:.0f}]", width - 210, y, size=14,
                   color=CYAN)
            y += 20
        if w.laser_timer > 0:
            o.text(f"[LASER {w.laser_timer:.0f}]", width - 210, y, size=14,
                   color=GOLD)

        if w.state in (SERVING, INTERMISSION):
            o.text("GET READY", width / 2, height * 0.55, size=22,
                   color=WHITE, center=True)


def create_run(mode, rng):
    return BreakerRun(mode, rng)
