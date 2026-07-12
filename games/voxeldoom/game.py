"""Voxel Doom's cabinet integration: first-person rendering, viewmodel, HUD."""
import math

from arcade.game_api import GameInfo, GameRun
from game import events as ev
from game import theme
from game.theme import TEXT, DIM, GOLD, EMBER, DANGER, PANEL, BAR_BG
from game.sprites import GUN_VIEW, surface_from_grid
from render.renderer import Batcher
from render.voxel import quat_axis_angle

from games.voxeldoom.world import DoomWorld, CELL, MAPS

INFO = GameInfo(
    "voxeldoom", "VOXEL DOOM",
    "Three floors down. Everything bites.",
    showcase_sprite="imp_a",
    modes=[("campaign", "CAMPAIGN")],
    music_pool="metal",
)
INFO.mouse_look = True  # mouse turns; A/D strafe; crosshair centered

# Voxel Doom's signature: hell-red Garnet (accent) + Rust (accent2).
_T = theme.for_game("voxeldoom")
ACCENT, ACCENT2 = _T.accent, _T.accent2

# warmed dungeon: sooty warm stone, no cool blue in the shadows
WALL_TINTS = [(0.44, 0.35, 0.30, 1.0), (0.37, 0.29, 0.25, 1.0)]
FLOOR_TINT = (0.17, 0.14, 0.13, 1.0)
CEIL_TINT = (0.11, 0.08, 0.08, 1.0)

ENEMY_SPRITES = {"imp": ("imp_a", "imp_b"), "gunner": ("gunner_a", "gunner_b")}
EXPLOSION_COLORS = {
    "imp": [(230, 60, 60), (250, 150, 60), (250, 220, 90)],
    "gunner": [(120, 120, 130), (70, 110, 230), (240, 240, 240)],
}


class DoomRun(GameRun):
    def __init__(self, mode, rng):
        self.mode = mode
        self.world = DoomWorld(rng=rng)
        self.time = 0.0
        self.gun_kick = 0.0
        self.gun_surface = surface_from_grid(GUN_VIEW, scale=14)
        self._static_rows = None
        self._static_level = -1

    @property
    def score(self):
        return self.world.score

    @property
    def run_over(self):
        return self.world.run_over

    def update(self, dt, inp):
        self.time += dt
        self.gun_kick = max(0.0, self.gun_kick - dt * 5)
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
            self.gun_kick = 1.0
        elif etype == "doom_click":
            audio.play("menu_move")
        elif etype == ev.ENEMY_KILLED:
            renderer.particles.burst_world(
                data["wx"], data["wy"], data["wz"],
                EXPLOSION_COLORS.get(data["kind"], EXPLOSION_COLORS["imp"]),
                count=36)
            renderer.add_shake(0.06)
            audio.play("explosion_enemy")
        elif etype == "doom_enemy_hurt":
            renderer.particles.burst_world(data["wx"], data["wy"], data["wz"],
                                           [(230, 60, 60)], count=8,
                                           speed=(1.0, 3.0))
        elif etype == "doom_enemy_shot":
            audio.play("graze")
        elif etype == ev.PLAYER_HIT:
            renderer.add_shake(0.3)
            renderer.add_aberration(0.7)
            audio.play("explosion_player")
        elif etype == ev.POWERUP_PICKUP:
            audio.play("powerup")
        elif etype == ev.WAVE_START:
            banner(f"FLOOR {data['index'] + 1}: {data['name']}", 2.6)
            audio.play("boss_roar" if data["index"] == 0 else "phase_sting")
        elif etype == ev.LEVEL_CLEAR:
            banner(f"FLOOR CLEAR  +{data['bonus']}", 2.2)
            audio.play("win")
        elif etype == ev.RUN_END:
            audio.play("win" if data["win"] else "game_over")

    # ------------------------------------------------------------- visuals
    def _static_geometry(self):
        """Wall/floor/ceiling instance rows, cached per level."""
        w = self.world
        if self._static_level == w.level_index and self._static_rows:
            return self._static_rows
        rows = []
        for cy in range(w.rows):
            for cx in range(w.cols):
                x, z = cx * CELL, cy * CELL
                if w.is_wall(cx, cy):
                    tint = WALL_TINTS[(cx + cy) % 2]
                    rows.append((x, 1.0, z, CELL, 0, 0, 0, 1, *tint))
                else:
                    rows.append((x, -1.0, z, CELL, 0, 0, 0, 1, *FLOOR_TINT))
                    rows.append((x, 3.0, z, CELL, 0, 0, 0, 1, *CEIL_TINT))
        self._static_rows = rows
        self._static_level = w.level_index
        return rows

    def draw(self, renderer, section):
        w = self.world
        t = self.time
        eye = (w.px, 1.0, w.pz)
        center = (w.px + math.cos(w.angle), 1.0, w.pz + math.sin(w.angle))
        renderer.camera_override = (eye, center, 64.0)

        b = Batcher()
        b.batches["cube"] = list(self._static_geometry())

        for e in w.enemies:
            frame_a, frame_b = ENEMY_SPRITES[e.kind]
            sprite = frame_a if int(t * 2.5) % 2 == 0 else frame_b
            yaw = math.atan2(w.px - e.x, w.pz - e.z)
            hurt = 1.0 + (2.2 if e.hurt_timer > 0 else 0.0)
            b.add_world(sprite, e.x, 1.0, e.z, 0.16,
                        quat=quat_axis_angle(0, 1, 0, yaw),
                        tint=(hurt, hurt if e.hurt_timer > 0 else 1.0,
                              hurt if e.hurt_timer > 0 else 1.0, 1.0))

        for p in w.projectiles:
            b.add_world("bullet_orb", p.x, 1.0, p.z, 0.09,
                        quat=quat_axis_angle(0, 0, 1, t * 6),
                        tint=(1.9, 1.5, 1.0, 1.0))

        for pk in w.pickups:
            sprite = "medkit" if pk.kind == "medkit" else "ammo_box"
            bob = 0.6 + 0.1 * math.sin(t * 3 + pk.x)
            b.add_world(sprite, pk.x, bob, pk.z, 0.08,
                        quat=quat_axis_angle(0, 1, 0, t * 2),
                        tint=(1.4, 1.4, 1.4, 1.0))

        if w.exit_cell is not None:
            ex, ez = w.exit_cell[0] * CELL, w.exit_cell[1] * CELL
            pulse = 1.4 + 0.6 * abs(math.sin(t * 3))
            for level in range(4):
                # a warm doorway of light — the way out, the light left on
                b.add_world("cube", ex, 0.3 + level * 0.55, ez, 0.22,
                            quat=quat_axis_angle(0, 1, 0, t * 2 + level),
                            tint=(pulse, pulse * 0.72, 0.38 * pulse, 1.0))

        renderer.draw_scene(b, walls=False, stars=False)

    def draw_hud(self, o, width, height, section):
        w = self.world
        # health + ammo plates
        o.rect(24, height - 74, 250, 52, PANEL)
        hp_color = EMBER if w.hp > 50 else (GOLD if w.hp > 25 else DANGER)
        o.text(f"HP {max(0, w.hp):3d}", 40, height - 62, size=26, color=hp_color)
        o.rect(150, height - 56, 110, 14, BAR_BG)
        o.rect(150, height - 56, 110 * max(0, w.hp) / 100, 14, hp_color)

        o.rect(width - 220, height - 74, 196, 52, PANEL)
        o.text(f"AMMO {w.ammo:3d}", width - 200, height - 62, size=26,
               color=GOLD if w.ammo > 8 else DANGER)

        o.text(f"SCORE {w.score:06d}", 26, 16, size=20, color=EMBER)
        o.text(f"FLOOR {w.level_index + 1}/{len(MAPS)}", 26, 44, size=14,
               color=DIM)
        o.text(f"KILLS {w.stats['kills']}", 26, 66, size=14, color=ACCENT2)

        # crosshair
        o.rect(width / 2 - 1, height / 2 - 6, 2, 4, TEXT)
        o.rect(width / 2 - 1, height / 2 + 2, 2, 4, TEXT)
        o.rect(width / 2 - 6, height / 2 - 1, 4, 2, TEXT)
        o.rect(width / 2 + 2, height / 2 - 1, 4, 2, TEXT)

        # gun viewmodel with bob + kick, muzzle flash overlay
        bob = math.sin(self.time * 7) * 6
        kick = self.gun_kick * 26
        gx = width / 2 + 90 + math.cos(self.time * 3.5) * 4
        gy = height - 150 + bob + kick
        if self.gun_kick > 0.55:
            o.rect(width / 2 - 26, height / 2 - 26, 52, 52,
                   (255, 230, 140, 90))
        o.image("gun_view", self.gun_surface, gx, gy, scale=1.6)

        # damage vignette
        if w.hurt_flash > 0:
            alpha = int(110 * w.hurt_flash)
            o.rect(0, 0, width, height, (200, 30, 30, alpha))


def create_run(mode, rng):
    return DoomRun(mode, rng)
