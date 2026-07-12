"""Voxel Aim's cabinet integration: first-person range, crosshair, HUD."""
import math

from arcade.game_api import GameInfo, GameRun
from game import events as ev
from game import theme
from game.theme import TEXT, DIM, GOLD, EMBER, DANGER
from render.renderer import Batcher
from render.voxel import quat_axis_angle

from games.aimtrainer.world import AimWorld, RUN_SECONDS, TARGET_RADIUS, WALL_Z

INFO = GameInfo(
    "aimtrainer", "VOXEL AIM",
    "Sixty seconds. Pop everything.",
    showcase_sprite="bullet_orb",
    modes=[("gridshot", "GRIDSHOT")],
    attract=True,
)
INFO.mouse_aim = True

# Voxel Aim's signature: cool Frost (accent) + Cobalt (accent2) — the calm,
# precise range. Warm ember targets pop against it.
_T = theme.for_game("aimtrainer")
ACCENT, ACCENT2 = _T.accent, _T.accent2

CAMERA = ((0.0, 3.0, 7.5), (0.0, 3.0, 0.0), 56.0)


class AimRun(GameRun):
    def __init__(self, mode, rng):
        self.mode = mode
        self.world = AimWorld(rng=rng)
        self.time = 0.0
        self.aim = (640.0, 430.0)
        self.flash = 0.0

    @property
    def score(self):
        return self.world.score

    @property
    def run_over(self):
        return self.world.run_over

    def update(self, dt, inp):
        self.time += dt
        self.aim = (inp.aim_x, inp.aim_y)
        self.flash = max(0.0, self.flash - dt * 6)
        self.world.update(dt, inp)

    def drain_events(self):
        return self.world.drain_events()

    def run_stats(self):
        return self.world.stats

    def run_summary(self):
        return self.world.run_summary(self.world.won)

    def on_event(self, etype, data, renderer, audio, banner):
        if etype == ev.SHOT_FIRED:
            audio.play("shoot")
            self.flash = 1.0
        elif etype == ev.ENEMY_KILLED:
            audio.play("explosion_enemy")
            renderer.add_shake(0.04)
        elif etype == "aim_miss":
            audio.play("menu_move")
        elif etype == ev.RUN_END:
            audio.play("win")

    # ------------------------------------------------------------ visuals
    def draw(self, renderer, section):
        renderer.camera_override = CAMERA
        b = Batcher()
        t = self.time

        # range walls: dim stud grid behind the targets + floor strip
        for gx in range(-6, 7, 2):
            for gy in range(0, 7, 2):
                b.add_world("cube", gx, gy, WALL_Z - 0.9, 0.12,
                            tint=(0.20, 0.28, 0.44, 1.0))
        for gx in range(-7, 8):
            b.add_world("cube", gx, -0.4, WALL_Z + 3.0, 0.5,
                        tint=(0.11, 0.15, 0.24, 1.0))

        # targets (projected for hit-testing after the draw)
        for target in self.world.targets:
            grow = min(1.0, max(0.15, (self.world.time - target.born) / 0.15))
            pulse = 1.5 + 0.3 * math.sin(t * 6 + target.x)
            spin = quat_axis_angle(0.4, 1, 0.3, t * 2 + target.y)
            b.add_world("bullet_orb", target.x, target.y, target.z,
                        0.28 * grow, quat=spin,
                        tint=(pulse, pulse * 0.55, pulse * 0.45, 1.0))

        renderer.draw_scene(b, walls=False, stars=False)

        # cache screen positions + radii for the world's hit tests
        for target in self.world.targets:
            projected = renderer.project_to_screen(target.x, target.y, target.z)
            edge = renderer.project_to_screen(
                target.x + TARGET_RADIUS, target.y, target.z)
            if projected is None or edge is None:
                target.screen_x = None
                continue
            target.screen_x, target.screen_y = projected[0], projected[1]
            target.screen_r = max(18.0, abs(edge[0] - projected[0]))

    def draw_hud(self, o, width, height, section):
        w = self.world
        life = section["lifetime"]
        o.text(f"SCORE {w.score:07d}", 26, 16, size=22, color=EMBER)
        o.text(f"BEST  {max(life['best_score'], w.score):07d}", 26, 46,
               size=16, color=DIM)
        acc = (w.stats["hits"] / w.stats["shots"]) if w.stats["shots"] else 0
        o.text(f"ACC {acc:.0%}", 26, 76, size=16, color=ACCENT)
        o.text(f"x{w.multiplier:.2f}", 26, 100, size=16, color=GOLD)

        # big timer
        color = DANGER if w.time_left < 10 else TEXT
        o.text(f"{w.time_left:04.1f}", width / 2, 20, size=34, color=color,
               center=True)

        # crosshair (+ muzzle flash ring)
        ax, ay = self.aim
        ch = GOLD if self.flash > 0.5 else ACCENT2  # cobalt rest, gold on fire
        o.rect(ax - 11, ay - 1, 8, 2, ch)
        o.rect(ax + 3, ay - 1, 8, 2, ch)
        o.rect(ax - 1, ay - 11, 2, 8, ch)
        o.rect(ax - 1, ay + 3, 2, 8, ch)


def create_run(mode, rng):
    return AimRun(mode, rng)
