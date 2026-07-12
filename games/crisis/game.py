"""Voxel Crisis's cabinet integration: rail camera, cover scene, crosshair."""
import math

from arcade.game_api import GameInfo, GameRun
from game import events as ev
from game import theme
from game.theme import DIM, GOLD, EMBER, DANGER
from render.renderer import Batcher
from render.voxel import quat_axis_angle

from games.crisis.world import (
    CrisisWorld, STAGE, CLIP_SIZE, PLAYER_HP, AIMING, TRAVELING,
)

INFO = GameInfo(
    "crisis", "VOXEL CRISIS",
    "On rails. Behind cover. Out of time.",
    showcase_sprite="gunner_a",
    modes=[("arcade", "ARCADE")],
)
INFO.mouse_aim = True

# Voxel Crisis's signature: dusk Copper (accent) + Ember (accent2).
_T = theme.for_game("crisis")
ACCENT, ACCENT2 = _T.accent, _T.accent2
PIP_EMPTY = (52, 42, 32, 255)  # spent armor/clip pip

EXPLOSION_COLORS = [(120, 120, 130), (70, 110, 230), (250, 150, 60)]


class CrisisRun(GameRun):
    def __init__(self, mode, rng):
        self.mode = mode
        self.world = CrisisWorld(rng=rng)
        self.time = 0.0
        self.aim = (640.0, 430.0)
        self._env_rows = None

    @property
    def score(self):
        return self.world.score

    @property
    def run_over(self):
        return self.world.run_over

    def update(self, dt, inp):
        self.time += dt
        self.aim = (inp.aim_x, inp.aim_y)
        self.world.update(dt, inp)

    def drain_events(self):
        return self.world.drain_events()

    def run_stats(self):
        return self.world.stats

    def run_summary(self):
        return self.world.run_summary(self.world.won)

    # ------------------------------------------------------------- effects
    def on_event(self, etype, data, renderer, audio, banner):
        if etype == ev.SHOT_FIRED:
            audio.play("shoot")
        elif etype == "crisis_click":
            audio.play("menu_move")
        elif etype == "crisis_reload":
            audio.play("powerup")
        elif etype == ev.ENEMY_KILLED:
            renderer.particles.burst_world(data["wx"], data["wy"], data["wz"],
                                           EXPLOSION_COLORS, count=40)
            renderer.add_shake(0.05)
            audio.play("explosion_enemy")
            if data.get("quick"):
                banner("QUICK KILL +100", 0.9)
        elif etype == "crisis_enemy_hurt":
            renderer.particles.burst_world(data["wx"], data["wy"], data["wz"],
                                           [(230, 60, 60)], count=8,
                                           speed=(1.0, 3.0))
            audio.play("explosion_enemy" if data.get("boss") else "graze")
        elif etype == "crisis_enemy_shot":
            renderer.add_aberration(0.25)
            audio.play("graze")
        elif etype == ev.PLAYER_HIT:
            renderer.add_shake(0.4)
            renderer.add_aberration(0.9)
            audio.play("explosion_player")
        elif etype == ev.WAVE_START:
            banner(data["name"], 2.0)
            audio.play(f"step_{data['index'] % 4}")
        elif etype == ev.WAVE_CLEAR:
            banner(f"ZONE CLEAR  +{data['bonus']}", 1.8)
            audio.play("menu_select")
        elif etype == ev.BOSS_SPAWN:
            banner("!!! DREAD CAPTAIN !!!", 2.6)
            audio.play("boss_roar")
        elif etype == ev.BOSS_KILLED:
            renderer.add_shake(0.6)
            audio.play("explosion_big")
        elif etype == ev.RUN_END:
            audio.play("win" if data["win"] else "game_over")

    # ------------------------------------------------------------- visuals
    def _environment(self):
        """Static ground/crates/back-wall instances, built once."""
        if self._env_rows is not None:
            return self._env_rows
        rows = []
        # ground: broad dark tiles under the whole rail path
        for gx in range(-6, 46, 2):
            for gz in range(-32, 14, 2):
                shade = 0.12 + 0.02 * ((gx + gz) % 4 == 0)
                rows.append((gx, -1.0, gz, 2.0, 0, 0, 0, 1,
                             shade * 1.25, shade * 1.05, shade * 0.82, 1.0))
        # cover crates at every enemy spot
        for stop in STAGE:
            for (x, z) in stop["spots"]:
                rows.append((x, 0.35, z + 0.9, 0.9, 0, 0, 0, 1,
                             0.45, 0.38, 0.3, 1.0))
        self._env_rows = rows
        return rows

    def draw(self, renderer, section):
        w = self.world
        t = self.time
        sway = math.sin(t * 1.7) * 0.05
        eye = (w.cam[0], w.cam[1] + sway, w.cam[2])
        renderer.camera_override = (eye, w.look, 58.0)

        b = Batcher()
        b.batches["cube"] = list(self._environment())

        for e in w.enemies:
            y = -0.6 + e.pop_frac * 2.0
            yaw = math.atan2(eye[0] - e.x, eye[2] - e.z)
            frame = "gunner_a" if int(t * 3) % 2 == 0 else "gunner_b"
            tint = [1.0, 1.0, 1.0, 1.0]
            if e.boss:
                frame = "boss"
                tint = [1.1, 0.9, 1.1, 1.0]
            if e.hurt_timer > 0:
                tint = [2.4, 1.2, 1.2, 1.0]
            elif e.state == AIMING and e.telegraph < 0.6:
                blink = math.sin(t * 24) > 0
                if blink:
                    tint = [2.2, 0.7, 0.7, 1.0]
            scale = 0.22 if e.boss else 0.15
            b.add_world(frame, e.x, y, e.z, scale,
                        quat=quat_axis_angle(0, 1, 0, yaw), tint=tuple(tint))
            if e.boss and e.alive:
                # boss health pips floating above
                frac = e.hp / e.max_hp
                b.add_world("cube", e.x, y + 1.6, e.z, 0.1 + 0.25 * frac,
                            tint=(2.0, 0.5, 0.5, 1.0))

        renderer.draw_scene(b, walls=False, stars=True)

        # cache screen positions for hit tests
        for e in w.enemies:
            y = -0.6 + e.pop_frac * 2.0
            projected = renderer.project_to_screen(e.x, y + 0.5, e.z)
            if projected is None:
                e.screen_x = None
                continue
            edge = renderer.project_to_screen(e.x + (1.4 if e.boss else 0.7),
                                              y + 0.5, e.z)
            e.screen_x, e.screen_y = projected[0], projected[1]
            e.screen_r = max(22.0, abs(edge[0] - projected[0]) if edge else 30)

    def draw_hud(self, o, width, height, section):
        w = self.world
        o.text(f"SCORE {w.score:06d}", 26, 16, size=20, color=EMBER)
        o.text(f"ZONE {max(1, w.stop_index + 1)}/{len(STAGE)}", 26, 44,
               size=14, color=DIM)

        # hp pips
        o.text("ARMOR", width - 240, 16, size=14, color=DIM)
        for i in range(PLAYER_HP):
            color = DANGER if i < w.hp else PIP_EMPTY
            o.rect(width - 170 + i * 26, 14, 18, 18, color)

        # clip
        o.text("CLIP", width - 240, 44, size=14, color=DIM)
        for i in range(CLIP_SIZE):
            color = GOLD if i < w.clip else PIP_EMPTY
            o.rect(width - 170 + i * 16, 46, 10, 16, color)
        if w.clip == 0 and not w.ducking:
            o.text("DUCK TO RELOAD!", width / 2, height * 0.62, size=22,
                   color=DANGER, center=True)

        # crosshair (dim while ducking)
        ax, ay = self.aim
        ch = DIM if w.ducking else ACCENT
        o.rect(ax - 12, ay - 1, 9, 2, ch)
        o.rect(ax + 3, ay - 1, 9, 2, ch)
        o.rect(ax - 1, ay - 12, 2, 9, ch)
        o.rect(ax - 1, ay + 3, 2, 9, ch)

        # duck = cover rises over the bottom of the screen
        if w.ducking:
            o.rect(0, height - 300, width, 300, (28, 24, 20, 235))
            o.text("[ IN COVER — RELOADING ]", width / 2, height - 160,
                   size=20, color=GOLD, center=True)
        if w.state == TRAVELING:
            o.text(">>> MOVING <<<", width / 2, height * 0.7, size=20,
                   color=ACCENT2, center=True)

        if w.hurt_flash > 0:
            o.rect(0, 0, width, height, (200, 30, 30, int(100 * w.hurt_flash)))


def create_run(mode, rng):
    return CrisisRun(mode, rng)
