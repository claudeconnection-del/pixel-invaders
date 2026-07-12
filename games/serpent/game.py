"""Voxel Serpent's cabinet integration: drawing, HUD, effects."""
import math

from arcade.game_api import GameInfo, GameRun
from game import events as ev
from game import theme
from game.theme import DIM, GOLD, EMBER
from render.renderer import Batcher
from render.voxel import quat_axis_angle

from games.serpent.world import SerpentWorld, field_pos, CELL

INFO = GameInfo(
    "serpent", "VOXEL SERPENT",
    "Eat. Grow. Don't bite yourself.",
    showcase_sprite="powerup_spread",
    modes=[("arcade", "ARCADE")],
)

# Voxel Serpent's signature: garden Fern (accent) + Sage (accent2), Pine edge.
_T = theme.for_game("serpent")
ACCENT, ACCENT2 = _T.accent, _T.accent2


class SerpentRun(GameRun):
    def __init__(self, mode, rng):
        self.mode = mode
        self.world = SerpentWorld(rng=rng)
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
        return self.world.run_summary(False)

    # ---------------------------------------------------------- effects
    def on_event(self, etype, data, renderer, audio, banner):
        if etype == ev.FRUIT_EATEN:
            if data["kind"] == "gold":
                renderer.explosion([(250, 220, 90), (255, 245, 180)],
                                   data["x"], data["y"])
                renderer.add_shake(0.1)
                audio.play("toast")
            else:
                renderer.particles.burst(data["x"], data["y"],
                                         [(230, 90, 90), (140, 255, 170)],
                                         count=16, gravity=0.4)
                audio.play("powerup")
        elif etype == ev.PLAYER_HIT:
            renderer.explosion([(140, 255, 170), (240, 240, 240)],
                               data["x"], data["y"], big=True)
            renderer.add_shake(0.5)
            renderer.add_aberration(0.8)
            audio.play("explosion_player")
        elif etype == ev.RUN_END:
            audio.play("game_over")

    # ------------------------------------------------------------ visuals
    def draw(self, renderer, section):
        w = self.world
        t = self.time
        b = Batcher()

        for cell in w.obstacles:
            fx, fy = field_pos(cell)
            b.add("cube", fx, fy, CELL / 32 * 0.5, tint=(0.5, 0.44, 0.36, 1.0))

        n = len(w.body)
        for i, cell in enumerate(w.body):
            fx, fy = field_pos(cell)
            k = 1.0 - (i / max(1, n)) * 0.6  # fade toward the tail
            if i == 0:
                wobble = quat_axis_angle(0, 0, 1, math.sin(t * 6) * 0.1)
                b.add("cube", fx, fy, CELL / 32 * 0.62, quat=wobble,
                      tint=(0.8, 1.9, 1.0, 1.0))
            else:
                b.add("cube", fx, fy, CELL / 32 * 0.5,
                      tint=(0.25 * k, 1.15 * k, 0.45 * k, 1.0))

        if w.fruit is not None:
            fx, fy = field_pos(w.fruit)
            spin = quat_axis_angle(0.3, 1, 0.4, t * 3)
            if w.fruit_kind == "gold":
                pulse = 1.6 + 0.5 * abs(math.sin(t * 5))
                b.add("bullet_orb", fx, fy, 0.2, quat=spin,
                      tint=(pulse, pulse * 0.85, pulse * 0.3, 1.0))
            else:
                b.add("bullet_orb", fx, fy, 0.17, quat=spin,
                      tint=(1.7, 0.6, 0.5, 1.0))

        renderer.stud_color = _T.scene_studs()  # pine arena edge
        renderer.draw_scene(b)

    def per_frame_particles(self, renderer, rng):
        if not self.world.run_over and rng.random() < 0.3:
            fx, fy = field_pos(self.world.body[-1])
            renderer.particles.glitter(fx, fy, color=ACCENT2[:3])  # sage trail

    def draw_hud(self, o, width, height, section):
        w = self.world
        life = section["lifetime"]
        o.text(f"SCORE {w.score:07d}", 26, 16, size=22, color=EMBER)
        o.text(f"BEST  {max(life['best_score'], w.score):07d}", 26, 46,
               size=16, color=DIM)
        o.text(f"LENGTH {w.length}", 26, 76, size=18, color=ACCENT)
        o.text(f"GOLD {w.golds_eaten}", 26, 100, size=14, color=GOLD)
        o.text(f"{w.time:.0f}s", width - 120, 16, size=18, color=DIM)


def create_run(mode, rng):
    return SerpentRun(mode, rng)
