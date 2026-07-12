"""Voxel Hell's cabinet integration: run wrapper, drawing, HUD, effects."""
import colorsys
import math

from arcade.game_api import GameInfo, GameRun
from game import events as ev
from render.renderer import Batcher
from render.voxel import quat_axis_angle

from games.voxelhell.skins import SKINS
from games.voxelhell.world import World, INTERMISSION, INTRO

INFO = GameInfo(
    "voxelhell", "VOXEL HELL",
    "Bullet-hell invaders. Graze to glory.",
    showcase_sprite="boss",
    modes=[("campaign", "CAMPAIGN"), ("endless", "ENDLESS")],
    has_skins=True,
)

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

GREEN = (140, 255, 170, 255)
DIM = (150, 150, 165, 255)
WHITE = (235, 235, 240, 255)
GOLD = (250, 220, 90, 255)
RED = (255, 110, 100, 255)
CYAN = (140, 235, 255, 255)


class VoxelHellRun(GameRun):
    def __init__(self, mode, rng):
        self.mode = mode
        self.world = World(rng=rng, mode=mode)
        self.time = 0.0
        self.show_hitbox = False
        self.graze_sfx_gate = 0.0

    # ------------------------------------------------------------- core
    @property
    def score(self):
        return self.world.score

    @property
    def run_over(self):
        return self.world.run_over

    def update(self, dt, inp):
        self.time += dt
        self.show_hitbox = inp.focus
        self.world.update(dt, inp)

    def drain_events(self):
        return self.world.drain_events()

    def run_stats(self):
        return self.world.stats

    def run_summary(self):
        return self.world.run_summary(self.world.won)

    # ---------------------------------------------------------- effects
    def on_event(self, etype, data, renderer, audio, banner):
        self.graze_sfx_gate = max(0.0, self.graze_sfx_gate - 1 / 60)
        if etype == ev.ENEMY_KILLED:
            renderer.explosion(EXPLOSION_COLORS.get(data["kind"],
                                                    EXPLOSION_COLORS["octo"]),
                               data["x"], data["y"])
            renderer.add_shake(0.05)
            audio.play("explosion_enemy")
        elif etype == ev.SHOT_FIRED:
            audio.play("shoot")
        elif etype == ev.GRAZE:
            renderer.particles.spark(data["x"], data["y"])
            if self.graze_sfx_gate <= 0:
                audio.play("graze")
                self.graze_sfx_gate = 0.05
        elif etype == ev.PLAYER_HIT:
            renderer.explosion(EXPLOSION_COLORS["player"], data["x"], data["y"])
            renderer.add_shake(0.45)
            renderer.add_aberration(0.8)
            audio.play("explosion_player")
        elif etype == ev.SHIELD_BREAK:
            renderer.particles.burst(data["x"], data["y"],
                                     [(140, 180, 255), (240, 240, 240)], count=30)
            renderer.add_shake(0.2)
            audio.play("shield_break")
        elif etype == ev.WAVE_START:
            banner(f"WAVE {data['index'] + 1}: {data['name']}", 2.6)
            audio.play(f"step_{data['index'] % 4}")
        elif etype == ev.WAVE_CLEAR:
            extra = "  [UNTOUCHED]" if data["untouched"] else ""
            banner(f"WAVE CLEAR  +{data['bonus']}{extra}", 2.2)
            audio.play("menu_select")
        elif etype == ev.POWERUP_PICKUP:
            renderer.particles.burst(data["x"], data["y"],
                                     [(180, 255, 190), (250, 220, 90)], count=24,
                                     gravity=0.2)
            audio.play("powerup")
        elif etype == ev.BOSS_SPAWN:
            banner("!!! DREADNOUGHT APPROACHES !!!", 3.0)
            renderer.add_shake(0.5)
            audio.play("boss_roar")
        elif etype == ev.BOSS_PHASE:
            banner(f"PHASE {data['phase']}", 1.6)
            renderer.add_shake(0.4)
            renderer.add_aberration(0.8)
            audio.play("phase_sting")
        elif etype == ev.BOSS_KILLED:
            renderer.explosion(EXPLOSION_COLORS["boss"], data["x"], data["y"],
                               big=True)
            renderer.add_shake(0.6)
            renderer.add_aberration(1.0)
            audio.play("explosion_big")
        elif etype == ev.LOOP_CLEAR:
            banner(f"LOOP {data['loop']} CLEAR  +{data['bonus']}", 3.0)
            audio.play("win")
        elif etype == ev.RUN_END:
            audio.play("win" if data["win"] else "game_over")

    # ------------------------------------------------------------ visuals
    def per_frame_particles(self, renderer, rng):
        world = self.world
        p = world.player
        if p.alive and not world.run_over:
            renderer.particles.exhaust(p.x, p.y + 16)
        for pu in world.powerups:
            if rng.random() < 0.35:
                renderer.particles.glitter(pu.x, pu.y)

    def draw(self, renderer, section):
        world = self.world
        t = self.time
        b = Batcher()

        for e in world.enemies:
            frame = "a" if int(e.time_alive * 2.5) % 2 == 0 else "b"
            wobble = quat_axis_angle(0, 0, 1, math.sin(t * 1.7 + e.bob_phase) * 0.07)
            b.add(f"enemy_{e.kind}_{frame}", e.x, e.y, SCALES["enemy"],
                  quat=wobble, tint=ENEMY_TINTS[e.kind])

        boss = world.boss
        if boss is not None and boss.alive:
            pulse = 1.0 + 0.12 * max(0.0, math.sin(t * (2.0 + boss.phase)))
            flash = 1.0 + (boss.phase - 1) * 0.12
            b.add("boss", boss.x, boss.y, SCALES["boss"],
                  quat=quat_axis_angle(0, 0, 1, math.sin(t * 0.8) * 0.08),
                  tint=(flash * pulse, flash, flash * pulse, 1.0))

        for blt in world.player_bullets:
            b.add("bullet_player", blt.x, blt.y, SCALES["bullet_player"],
                  tint=(1.7, 1.7, 1.9, 1.0))

        for blt in world.enemy_bullets:
            spin = quat_axis_angle(0, 0, 1, t * 4.0 + (id(blt) % 100) * 0.06)
            b.add(blt.sprite, blt.x, blt.y, SCALES.get(blt.sprite, 0.17),
                  quat=spin, tint=(1.75, 1.75, 1.75, 1.0))

        for pu in world.powerups:
            spin = quat_axis_angle(0, 1, 0, t * 2.4 + pu.time_alive)
            b.add(POWERUP_SPRITES[pu.kind], pu.x, pu.y, SCALES["powerup"],
                  quat=spin, tint=(1.5, 1.5, 1.5, 1.0))

        p = world.player
        if p.alive:
            skin = SKINS[section["selected_skin"]]
            tint = [1.0, 1.0, 1.0, 1.0]
            if skin["special"] == "translucent":
                tint[3] = 0.55
            elif skin["special"] == "hue_cycle":
                r, g, bl = colorsys.hsv_to_rgb((t * 0.18) % 1.0, 0.6, 1.0)
                tint[0], tint[1], tint[2] = r * 1.35, g * 1.35, bl * 1.35
            if p.invuln > 0:
                tint[3] *= 0.45 + 0.4 * math.sin(t * 24)
            bank = quat_axis_angle(0, 1, 0, math.sin(t * 3.1) * 0.12)
            b.add(skin["sprite"], p.x, p.y, SCALES["ship"], quat=bank,
                  tint=tuple(tint))
            if p.shield:
                aura = quat_axis_angle(0.4, 1, 0.2, t * 1.5)
                b.add("powerup_shield", p.x, p.y, 0.34, quat=aura,
                      tint=(0.5, 0.8, 1.6, 0.22))
            if self.show_hitbox:
                b.add_cube_late(p.x, p.y, 0.11,
                                quat=quat_axis_angle(0, 0, 1, t * 3),
                                tint=(2.6, 2.4, 2.6, 1.0), z=0.6)

        renderer.draw_scene(b)

    def draw_hud(self, o, width, height, section):
        world = self.world
        life = section["lifetime"]
        o.text(f"SCORE {world.score:07d}", 26, 16, size=22, color=GREEN)
        o.text(f"BEST  {max(life['best_score'], world.score):07d}", 26, 46,
               size=16, color=DIM)

        frac = (world.multiplier - 1.0) / 4.0
        o.text(f"x{world.multiplier:.1f}", 26, 76, size=18, color=GOLD)
        o.rect(80, 80, 130, 10, (45, 45, 65, 220))
        o.rect(80, 80, 130 * frac, 10, GOLD)
        o.text(f"GRAZE {world.stats['grazes']}", 26, 100, size=14, color=CYAN)

        if self.mode == "campaign" and world.loop > 1:
            o.text(f"LOOP {world.loop}", 26, 124, size=14, color=RED)
        elif self.mode == "endless":
            o.text(f"WAVE {world.wave_index + 1}", 26, 124, size=14, color=DIM)

        o.text("LIVES", width - 210, 16, size=16, color=DIM)
        for i in range(max(0, world.player.lives)):
            o.rect(width - 130 + i * 26, 16, 18, 18, RED)

        p = world.player
        y = 46
        if p.shield:
            o.text("[SHIELD]", width - 210, y, size=14, color=CYAN)
            y += 20
        if p.spread_timer > 0:
            o.text(f"[SPREAD {p.spread_timer:.0f}]", width - 210, y, size=14,
                   color=GREEN)
            y += 20
        if p.rapid_timer > 0:
            o.text(f"[RAPID {p.rapid_timer:.0f}]", width - 210, y, size=14,
                   color=GOLD)

        boss = world.boss
        if boss is not None and boss.alive:
            o.rect(width / 2 - 260, 22, 520, 18, (45, 45, 65, 230))
            o.rect(width / 2 - 257, 25, 514 * boss.hp_frac, 12, (235, 70, 70, 255))
            o.text("DREADNOUGHT", width / 2, 44, size=14, color=RED, center=True)

        if world.state in (INTRO, INTERMISSION):
            o.text("GET READY", width / 2, height * 0.5, size=22,
                   color=WHITE, center=True)


def create_run(mode, rng):
    return VoxelHellRun(mode, rng)
