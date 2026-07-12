"""Pixel Invaders: Voxel Hell — 8-bit voxel bullet-hell built with
pygame-ce + PyOpenGL. All art and audio generated from code.

Controls:
    Left/Right/Up/Down or WASD - move        Space - shoot (hold)
    Shift - focus (slow + show hitbox)       Enter - confirm
    Esc - pause / back                       C - CRT filter, M - music
"""
import math
import random
import sys

import pygame

from game import events as ev
from game.assets import AudioBank
from game.entities import InputState
from game.skins import SKINS, SKIN_ORDER
from game.world import World, INTERMISSION, INTRO
from meta import profile as profile_mod
from meta.achievements import ACHIEVEMENTS, AchievementEngine
from meta.stats import StatsTracker

WIDTH, HEIGHT = 1280, 860
FPS = 60

# app states
MENU = "menu"
SKINS_SCREEN = "skins"
ACHIEVEMENTS_SCREEN = "achievements"
STATS_SCREEN = "stats"
SETTINGS_SCREEN = "settings"
PLAYING = "playing"
PAUSED = "paused"
RUN_END = "run_end"

GREEN = (140, 255, 170, 255)
DIM = (150, 150, 165, 255)
WHITE = (235, 235, 240, 255)
GOLD = (250, 220, 90, 255)
RED = (255, 110, 100, 255)
CYAN = (140, 235, 255, 255)

MENU_ITEMS = ["PLAY", "SKINS", "ACHIEVEMENTS", "STATS", "SETTINGS", "QUIT"]

SHOWCASE_SPRITES = ["boss", "enemy_octo_a", "enemy_crab_a", "enemy_squid_a",
                    "enemy_elite_a"]

# (label, settings key, choices) — Left/Right cycles; floats step by 0.1
SETTINGS_ROWS = [
    ("FPS cap", "fps_cap", [60, 120, 144, 240, 0]),
    ("VSync", "vsync", [True, False]),
    ("Fullscreen", "fullscreen", [False, True]),
    ("Bloom", "bloom", ["off", "low", "full"]),
    ("Particles", "particles", ["low", "medium", "high"]),
    ("CRT filter", "crt", [True, False]),
    ("Music volume", "music_vol", "float"),
    ("SFX volume", "sfx_vol", "float"),
    ("Show FPS", "show_fps", [False, True]),
]
DISPLAY_KEYS = {"vsync", "fullscreen"}  # need a window/context rebuild


def settings_value_label(key, value):
    if key == "fps_cap":
        return "UNLIMITED" if value == 0 else str(value)
    if isinstance(value, bool):
        return "ON" if value else "OFF"
    if isinstance(value, float):
        return f"{int(round(value * 100))}%"
    return str(value).upper()


class App:
    def __init__(self):
        pygame.init()
        try:
            pygame.mixer.init()
        except pygame.error:
            pass
        pygame.display.set_caption("Pixel Invaders: Voxel Hell")
        self.clock = pygame.time.Clock()

        self.profile = profile_mod.load()
        self.renderer = None
        self.apply_display_settings()

        self.audio = AudioBank()
        self.stats = StatsTracker(self.profile)
        self.engine = AchievementEngine(self.profile)
        self.audio.music_on = self.profile["settings"].get("music", True)
        self.audio.set_volumes(self.profile["settings"]["sfx_vol"],
                               self.profile["settings"]["music_vol"])

        self.state = MENU
        self.menu_index = 0
        self.settings_index = 0
        self.skin_index = SKIN_ORDER.index(self.profile["selected_skin"])
        self.world = None
        self.run_summary = None
        self.run_won = False
        self.toasts = []          # [(Achievement, timer)]
        self.wave_banner = None   # (text, timer)
        self.graze_sfx_gate = 0.0
        self.showcase_index = 0

    # ------------------------------------------------------------- display
    def apply_display_settings(self):
        """(Re)create the window + GL context from current settings. All GL
        objects die with the context, so the Renderer is rebuilt too."""
        s = self.profile["settings"]
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 3)
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 3)
        pygame.display.gl_set_attribute(
            pygame.GL_CONTEXT_PROFILE_MASK, pygame.GL_CONTEXT_PROFILE_CORE)
        if sys.platform == "darwin":
            # macOS only provides 3.2+ core contexts with the forward-compat bit
            pygame.display.gl_set_attribute(
                pygame.GL_CONTEXT_FORWARD_COMPATIBLE_FLAG, 1)
        flags = pygame.OPENGL | pygame.DOUBLEBUF
        size = (WIDTH, HEIGHT)
        if s.get("fullscreen"):
            flags |= pygame.FULLSCREEN
            size = (0, 0)  # desktop resolution
        pygame.display.set_mode(size, flags, vsync=1 if s.get("vsync", True) else 0)
        out_w, out_h = pygame.display.get_window_size()

        from render.renderer import Renderer  # needs live GL context
        self.renderer = Renderer(WIDTH, HEIGHT, out_w, out_h)
        self.renderer.apply_quality(bloom=s["bloom"], particles=s["particles"])

    # -------------------------------------------------------------- persistence
    def save_profile(self):
        profile_mod.save(self.profile)

    # -------------------------------------------------------------- settings
    def adjust_setting(self, index, direction):
        label, key, choices = SETTINGS_ROWS[index]
        s = self.profile["settings"]
        if choices == "float":
            s[key] = round(min(1.0, max(0.0, s[key] + 0.1 * direction)), 2)
        else:
            try:
                i = choices.index(s[key])
            except ValueError:
                i = 0
            s[key] = choices[(i + direction) % len(choices)]

        if key in DISPLAY_KEYS:
            self.apply_display_settings()
        elif key in ("bloom", "particles"):
            self.renderer.apply_quality(bloom=s["bloom"], particles=s["particles"])
        elif key in ("music_vol", "sfx_vol"):
            self.audio.set_volumes(s["sfx_vol"], s["music_vol"])
        self.save_profile()

    # ------------------------------------------------------------------ events
    def handle_keydown(self, key):
        audio = self.audio
        if self.state == MENU:
            if key in (pygame.K_UP, pygame.K_w):
                self.menu_index = (self.menu_index - 1) % len(MENU_ITEMS)
                audio.play("menu_move")
            elif key in (pygame.K_DOWN, pygame.K_s):
                self.menu_index = (self.menu_index + 1) % len(MENU_ITEMS)
                audio.play("menu_move")
            elif key == pygame.K_RETURN:
                audio.play("menu_select")
                choice = MENU_ITEMS[self.menu_index]
                if choice == "PLAY":
                    self.start_run()
                elif choice == "SKINS":
                    self.state = SKINS_SCREEN
                elif choice == "ACHIEVEMENTS":
                    self.state = ACHIEVEMENTS_SCREEN
                elif choice == "STATS":
                    self.state = STATS_SCREEN
                elif choice == "SETTINGS":
                    self.state = SETTINGS_SCREEN
                elif choice == "QUIT":
                    self.quit()
            elif key == pygame.K_ESCAPE:
                self.quit()

        elif self.state == SKINS_SCREEN:
            if key in (pygame.K_LEFT, pygame.K_a):
                self.skin_index = (self.skin_index - 1) % len(SKIN_ORDER)
                audio.play("menu_move")
            elif key in (pygame.K_RIGHT, pygame.K_d):
                self.skin_index = (self.skin_index + 1) % len(SKIN_ORDER)
                audio.play("menu_move")
            elif key == pygame.K_RETURN:
                skin_id = SKIN_ORDER[self.skin_index]
                if skin_id in self.profile["unlocked_skins"]:
                    self.profile["selected_skin"] = skin_id
                    self.save_profile()
                    audio.play("menu_select")
            elif key == pygame.K_ESCAPE:
                self.state = MENU

        elif self.state in (ACHIEVEMENTS_SCREEN, STATS_SCREEN):
            if key == pygame.K_ESCAPE:
                self.state = MENU

        elif self.state == SETTINGS_SCREEN:
            if key == pygame.K_ESCAPE:
                self.save_profile()
                self.state = MENU
            elif key in (pygame.K_UP, pygame.K_w):
                self.settings_index = (self.settings_index - 1) % len(SETTINGS_ROWS)
                audio.play("menu_move")
            elif key in (pygame.K_DOWN, pygame.K_s):
                self.settings_index = (self.settings_index + 1) % len(SETTINGS_ROWS)
                audio.play("menu_move")
            elif key in (pygame.K_LEFT, pygame.K_a, pygame.K_RIGHT, pygame.K_d,
                         pygame.K_RETURN):
                direction = -1 if key in (pygame.K_LEFT, pygame.K_a) else 1
                self.adjust_setting(self.settings_index, direction)
                audio.play("menu_select")

        elif self.state == PLAYING:
            if key == pygame.K_ESCAPE:
                self.state = PAUSED
                self.audio.music(None)

        elif self.state == PAUSED:
            if key == pygame.K_ESCAPE:
                self.state = PLAYING
                self.audio.music("game")
            elif key == pygame.K_q:
                self.abandon_run()

        elif self.state == RUN_END:
            if key == pygame.K_RETURN:
                self.state = MENU
                self.audio.music("menu")

        # global toggles
        if key == pygame.K_c:
            self.profile["settings"]["crt"] = not self.profile["settings"]["crt"]
            self.save_profile()
        elif key == pygame.K_m:
            on = not self.profile["settings"].get("music", True)
            self.profile["settings"]["music"] = on
            self.audio.set_music_enabled(on)
            self.save_profile()

    # -------------------------------------------------------------------- runs
    def start_run(self):
        self.world = World(rng=random.Random())
        self.run_summary = None
        self.toasts.clear()
        self.wave_banner = None
        self.state = PLAYING
        self.audio.music("game")

    def abandon_run(self):
        """Quit to menu mid-run: counts stats so far as an unfinished run."""
        if self.world is not None and not self.world.run_over:
            summary = self.world.run_summary(False)
            self.profile["lifetime"]["runs"] += 1
            self.profile["lifetime"]["hits"] += summary["hits"]
        self.world = None
        self.save_profile()
        self.state = MENU
        self.audio.music("menu")

    def quit(self):
        self.save_profile()
        pygame.quit()
        sys.exit(0)

    # -------------------------------------------------------------- game frame
    def gameplay_input(self):
        keys = pygame.key.get_pressed()
        return InputState(
            left=keys[pygame.K_LEFT] or keys[pygame.K_a],
            right=keys[pygame.K_RIGHT] or keys[pygame.K_d],
            up=keys[pygame.K_UP] or keys[pygame.K_w],
            down=keys[pygame.K_DOWN] or keys[pygame.K_s],
            focus=keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT],
            fire=keys[pygame.K_SPACE],
        )

    def process_world_events(self, frame_events, dt):
        r = self.renderer
        audio = self.audio
        self.graze_sfx_gate = max(0.0, self.graze_sfx_gate - dt)

        for etype, data in frame_events:
            if etype == ev.ENEMY_KILLED:
                r.explosion(data["kind"], data["x"], data["y"])
                r.add_shake(0.05)
                audio.play("explosion_enemy")
            elif etype == ev.SHOT_FIRED:
                audio.play("shoot")
            elif etype == ev.GRAZE:
                r.particles.spark(data["x"], data["y"])
                if self.graze_sfx_gate <= 0:
                    audio.play("graze")
                    self.graze_sfx_gate = 0.05
            elif etype == ev.PLAYER_HIT:
                r.explosion("player", data["x"], data["y"])
                r.add_shake(0.45)
                r.add_aberration(0.8)
                audio.play("explosion_player")
            elif etype == ev.SHIELD_BREAK:
                r.particles.burst(data["x"], data["y"],
                                  [(140, 180, 255), (240, 240, 240)], count=30)
                r.add_shake(0.2)
                audio.play("shield_break")
            elif etype == ev.WAVE_START:
                self.wave_banner = (f"WAVE {data['index'] + 1}: {data['name']}", 2.6)
                audio.play(f"step_{data['index'] % 4}")
            elif etype == ev.WAVE_CLEAR:
                extra = "  [UNTOUCHED]" if data["untouched"] else ""
                self.wave_banner = (f"WAVE CLEAR  +{data['bonus']}{extra}", 2.2)
                audio.play("menu_select")
            elif etype == ev.POWERUP_PICKUP:
                r.particles.burst(data["x"], data["y"],
                                  [(180, 255, 190), (250, 220, 90)], count=24,
                                  gravity=0.2)
                audio.play("powerup")
            elif etype == ev.BOSS_SPAWN:
                self.wave_banner = ("!!! DREADNOUGHT APPROACHES !!!", 3.0)
                r.add_shake(0.5)
                audio.play("boss_roar")
            elif etype == ev.BOSS_PHASE:
                self.wave_banner = (f"PHASE {data['phase']}", 1.6)
                r.add_shake(0.4)
                r.add_aberration(0.8)
                audio.play("phase_sting")
            elif etype == ev.BOSS_KILLED:
                r.explosion("boss", data["x"], data["y"], big=True)
                r.add_shake(0.6)
                r.add_aberration(1.0)
                audio.play("explosion_big")
            elif etype == ev.RUN_END:
                self.run_summary = data["summary"]
                self.run_won = data["win"]
                audio.play("win" if data["win"] else "game_over")

        # achievements + stats
        self.stats.on_frame(dt, frame_events)
        if self.world is not None:
            for achievement in self.engine.on_frame(frame_events, self.world.stats):
                self.toasts.append([achievement, 3.5])
                self.audio.play("toast")
                self.save_profile()

        if self.run_summary is not None and self.state == PLAYING:
            self.state = RUN_END
            self.audio.music(None)
            self.save_profile()

    def update_playing(self, dt):
        world = self.world
        inp = self.gameplay_input()
        world.update(dt, inp)
        self.process_world_events(world.drain_events(), dt)
        self.renderer.show_hitbox = inp.focus

        p = world.player
        if p.alive and not world.run_over:
            self.renderer.particles.exhaust(p.x, p.y + 16)
        for pu in world.powerups:
            if random.random() < 0.35:
                self.renderer.particles.glitter(pu.x, pu.y)

    # --------------------------------------------------------------- HUD/menus
    def draw_hud(self):
        o = self.renderer.overlay
        world = self.world
        life = self.profile["lifetime"]
        o.text(f"SCORE {world.score:07d}", 26, 16, size=22, color=GREEN)
        o.text(f"BEST  {max(life['best_score'], world.score):07d}", 26, 46,
               size=16, color=DIM)

        # multiplier bar
        frac = (world.multiplier - 1.0) / 4.0
        o.text(f"x{world.multiplier:.1f}", 26, 76, size=18, color=GOLD)
        o.rect(80, 80, 130, 10, (45, 45, 65, 220))
        o.rect(80, 80, 130 * frac, 10, GOLD)
        o.text(f"GRAZE {world.stats['grazes']}", 26, 100, size=14, color=CYAN)

        o.text("LIVES", WIDTH - 210, 16, size=16, color=DIM)
        for i in range(max(0, world.player.lives)):
            o.rect(WIDTH - 130 + i * 26, 16, 18, 18, RED)

        p = world.player
        y = 46
        if p.shield:
            o.text("[SHIELD]", WIDTH - 150, y, size=14, color=CYAN)
            y += 20
        if p.spread_timer > 0:
            o.text(f"[SPREAD {p.spread_timer:.0f}]", WIDTH - 150, y, size=14, color=GREEN)
            y += 20
        if p.rapid_timer > 0:
            o.text(f"[RAPID {p.rapid_timer:.0f}]", WIDTH - 150, y, size=14, color=GOLD)

        boss = world.boss
        if boss is not None and boss.alive:
            o.rect(WIDTH / 2 - 260, 22, 520, 18, (45, 45, 65, 230))
            o.rect(WIDTH / 2 - 257, 25, 514 * boss.hp_frac, 12, (235, 70, 70, 255))
            o.text("DREADNOUGHT", WIDTH / 2, 44, size=14, color=RED, center=True)

        if self.wave_banner is not None:
            text, timer = self.wave_banner
            alpha = int(255 * min(1.0, timer / 0.6))
            o.text(text, WIDTH / 2, HEIGHT * 0.36, size=34,
                   color=(GREEN[0], GREEN[1], GREEN[2], alpha), center=True)

        if world.state in (INTRO, INTERMISSION):
            o.text("GET READY", WIDTH / 2, HEIGHT * 0.5, size=22,
                   color=WHITE, center=True)

        self.draw_toasts()

    def draw_toasts(self):
        o = self.renderer.overlay
        y = 120
        for achievement, timer in self.toasts:
            slide = min(1.0, (3.5 - timer) * 5)
            x = WIDTH - 20 - 360 * slide
            o.rect(x, y, 360, 58, (25, 30, 45, 235))
            o.rect(x, y, 4, 58, GOLD)
            o.text("ACHIEVEMENT UNLOCKED", x + 16, y + 8, size=13, color=GOLD)
            o.text(achievement.name, x + 16, y + 28, size=18, color=WHITE)
            y += 70

    def draw_menu(self):
        o = self.renderer.overlay
        o.text("PIXEL INVADERS", WIDTH / 2, 130, size=64, color=GREEN, center=True)
        o.text("V O X E L   H E L L", WIDTH / 2, 205, size=26, color=RED, center=True)
        for i, item in enumerate(MENU_ITEMS):
            selected = i == self.menu_index
            color = WHITE if selected else DIM
            prefix = "> " if selected else "  "
            o.text(prefix + item, WIDTH / 2 - 90, 330 + i * 52, size=30, color=color)
        life = self.profile["lifetime"]
        o.text(f"BEST {life['best_score']:07d}", WIDTH / 2, 640, size=18,
               color=GOLD, center=True)
        unlocked = len(self.profile["achievements"])
        o.text(f"{unlocked}/{len(ACHIEVEMENTS)} achievements  |  "
               f"{len(self.profile['unlocked_skins'])}/{len(SKINS)} ships",
               WIDTH / 2, 670, size=14, color=DIM, center=True)
        o.text("C: CRT filter   M: music   Esc: quit",
               WIDTH / 2, HEIGHT - 40, size=14, color=DIM, center=True)
        self.draw_toasts()

    def draw_skins(self):
        o = self.renderer.overlay
        skin_id = SKIN_ORDER[self.skin_index]
        skin = SKINS[skin_id]
        unlocked = skin_id in self.profile["unlocked_skins"]
        selected = skin_id == self.profile["selected_skin"]

        o.text("HANGAR", WIDTH / 2, 90, size=44, color=GREEN, center=True)
        o.text(f"< {skin['name']} >", WIDTH / 2, 560, size=32,
               color=WHITE if unlocked else DIM, center=True)
        o.text(skin["desc"], WIDTH / 2, 610, size=16, color=DIM, center=True)
        if not unlocked:
            from meta.achievements import BY_ID
            req = BY_ID[skin["unlock"]]
            o.text(f"LOCKED — {req.name}: {req.desc}", WIDTH / 2, 650, size=16,
                   color=RED, center=True)
        elif selected:
            o.text("[ EQUIPPED ]", WIDTH / 2, 650, size=18, color=GOLD, center=True)
        else:
            o.text("Enter to equip", WIDTH / 2, 650, size=16, color=GREEN, center=True)
        o.text(f"{self.skin_index + 1}/{len(SKIN_ORDER)}   Esc: back",
               WIDTH / 2, HEIGHT - 40, size=14, color=DIM, center=True)

    def draw_achievements(self):
        o = self.renderer.overlay
        o.text("ACHIEVEMENTS", WIDTH / 2, 60, size=40, color=GREEN, center=True)
        col_w = 590
        for i, a in enumerate(ACHIEVEMENTS):
            col = i % 2
            row = i // 2
            x = 60 + col * col_w
            y = 140 + row * 108
            unlocked = self.engine.is_unlocked(a.id)
            o.rect(x, y, col_w - 40, 92, (25, 30, 45, 200))
            o.rect(x, y, 4, 92, GOLD if unlocked else (70, 70, 85, 255))
            o.text(a.name, x + 18, y + 10, size=19,
                   color=GOLD if unlocked else WHITE)
            o.text(a.desc, x + 18, y + 38, size=14, color=DIM)
            if unlocked:
                o.text("UNLOCKED", x + col_w - 150, y + 10, size=13, color=GREEN)
            elif a.progress is not None:
                cur, target = a.progress(self.profile["lifetime"],
                                         self.world.stats if self.world else
                                         {"grazes": 0, "powerups": 0})
                frac = min(1.0, cur / target)
                o.rect(x + 18, y + 64, col_w - 90, 8, (45, 45, 65, 255))
                o.rect(x + 18, y + 64, (col_w - 90) * frac, 8, CYAN)
                o.text(f"{cur}/{target}", x + col_w - 130, y + 58, size=12, color=DIM)
        o.text("Esc: back", WIDTH / 2, HEIGHT - 30, size=14, color=DIM, center=True)

    def draw_stats(self):
        o = self.renderer.overlay
        life = self.profile["lifetime"]
        o.text("SERVICE RECORD", WIDTH / 2, 70, size=40, color=GREEN, center=True)
        acc = (life["hits"] / life["shots"]) if life["shots"] else 0.0
        hours = life["playtime"] / 3600
        rows = [
            ("Best score", f"{life['best_score']:,}"),
            ("Best wave", f"{life['best_wave']}" if life["best_wave"] else "-"),
            ("Runs / wins", f"{life['runs']} / {life['wins']}"),
            ("Bosses slain", f"{life['bosses']}"),
            ("Enemies destroyed", f"{life['kills']:,}"),
            ("Shots fired", f"{life['shots']:,}"),
            ("Lifetime accuracy", f"{acc:.0%}"),
            ("Bullets grazed", f"{life['grazes']:,}"),
            ("Power-ups collected", f"{life['powerups']:,}"),
            ("Times shot down", f"{life['deaths']}"),
            ("Time in the chair", f"{hours:.1f}h"),
        ]
        for i, (label, value) in enumerate(rows):
            y = 160 + i * 46
            o.text(label, WIDTH / 2 - 280, y, size=20, color=DIM)
            o.text(value, WIDTH / 2 + 120, y, size=20, color=WHITE)
        o.text("Esc: back", WIDTH / 2, HEIGHT - 30, size=14, color=DIM, center=True)

    def draw_run_end(self):
        o = self.renderer.overlay
        s = self.run_summary
        title = "VICTORY" if self.run_won else "SHOT DOWN"
        color = GOLD if self.run_won else RED
        o.text(title, WIDTH / 2, 150, size=64, color=color, center=True)
        rows = [
            ("Score", f"{s['score']:,}"),
            ("Wave reached", f"{s['wave_reached']}"),
            ("Enemies destroyed", f"{s['kills']}"),
            ("Accuracy", f"{s['accuracy']:.0%}"),
            ("Bullets grazed", f"{s['grazes']}"),
            ("Max multiplier", f"x{s['max_multiplier']:.1f}"),
            ("Power-ups", f"{s['powerups']}"),
            ("Deaths", f"{s['deaths']}"),
            ("Duration", f"{s['duration']:.0f}s"),
        ]
        for i, (label, value) in enumerate(rows):
            y = 280 + i * 42
            o.text(label, WIDTH / 2 - 220, y, size=20, color=DIM)
            o.text(value, WIDTH / 2 + 120, y, size=20, color=WHITE)
        if self.profile["lifetime"]["best_score"] <= s["score"] and s["score"] > 0:
            o.text("NEW BEST!", WIDTH / 2, 240, size=22, color=GREEN, center=True)
        o.text("Enter: menu", WIDTH / 2, HEIGHT - 60, size=18, color=GREEN, center=True)
        self.draw_toasts()

    def draw_settings(self):
        o = self.renderer.overlay
        s = self.profile["settings"]
        o.text("SETTINGS", WIDTH / 2, 80, size=44, color=GREEN, center=True)
        for i, (label, key, choices) in enumerate(SETTINGS_ROWS):
            y = 190 + i * 52
            selected = i == self.settings_index
            color = WHITE if selected else DIM
            prefix = "> " if selected else "  "
            o.text(prefix + label, WIDTH / 2 - 330, y, size=24, color=color)
            value = settings_value_label(key, s[key])
            o.text(f"< {value} >" if selected else value,
                   WIDTH / 2 + 160, y, size=24,
                   color=GOLD if selected else DIM)
        o.text("Left/Right: change   Esc: back",
               WIDTH / 2, HEIGHT - 40, size=14, color=DIM, center=True)

    def draw_fps(self):
        o = self.renderer.overlay
        o.text(f"{self.clock.get_fps():5.0f} FPS", WIDTH - 120, HEIGHT - 30,
               size=14, color=DIM)

    def draw_paused(self):
        o = self.renderer.overlay
        o.rect(0, 0, WIDTH, HEIGHT, (5, 5, 12, 160))
        o.text("PAUSED", WIDTH / 2, HEIGHT / 2 - 60, size=48, color=WHITE, center=True)
        o.text("Esc: resume    Q: quit to menu", WIDTH / 2, HEIGHT / 2 + 20,
               size=20, color=DIM, center=True)

    # -------------------------------------------------------------------- loop
    def update_timers(self, dt):
        if self.wave_banner is not None:
            text, timer = self.wave_banner
            timer -= dt
            self.wave_banner = (text, timer) if timer > 0 else None
        for toast in self.toasts:
            toast[1] -= dt
        self.toasts = [t for t in self.toasts if t[1] > 0]

    def run(self):
        self.audio.music("menu")
        showcase_timer = 0.0
        while True:
            cap = self.profile["settings"].get("fps_cap", 120)
            dt = min(self.clock.tick(cap) / 1000.0, 0.05)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.quit()
                elif event.type == pygame.KEYDOWN:
                    self.handle_keydown(event.key)

            self.update_timers(dt)
            crt = self.profile["settings"].get("crt", True)

            if self.state == PLAYING:
                self.update_playing(dt)

            self.renderer.begin(dt if self.state != PAUSED else 0.0)

            if self.state in (PLAYING, PAUSED, RUN_END):
                if self.world is not None:
                    self.renderer.draw_world(
                        self.world, self.profile["selected_skin"])
            elif self.state == MENU:
                showcase_timer += dt
                if showcase_timer > 6.0:
                    showcase_timer = 0.0
                    self.showcase_index = (self.showcase_index + 1) % len(SHOWCASE_SPRITES)
                sprite = SHOWCASE_SPRITES[self.showcase_index]
                scale = 0.34 if sprite == "boss" else 0.5
                self.renderer.draw_menu_model(sprite, 575, 265, scale,
                                              spin_speed=0.9)
            elif self.state == SKINS_SCREEN:
                skin_id = SKIN_ORDER[self.skin_index]
                skin = SKINS[skin_id]
                unlocked = skin_id in self.profile["unlocked_skins"]
                tint = (1.0, 1.0, 1.0, 1.0)
                if not unlocked:
                    tint = (0.16, 0.16, 0.2, 1.0)
                elif skin["special"] == "hue_cycle":
                    import colorsys
                    r, g, b = colorsys.hsv_to_rgb(
                        (self.renderer.time * 0.18) % 1.0, 0.6, 1.0)
                    tint = (r * 1.35, g * 1.35, b * 1.35, 1.0)
                elif skin["special"] == "translucent":
                    tint = (1.0, 1.0, 1.0, 0.55)
                self.renderer.draw_menu_model(skin["sprite"], 320, 330, 0.55,
                                              spin_speed=1.3, tint=tint)
            else:
                self.renderer.draw_starfield_only()

            self.renderer.begin_overlay()
            if self.state in (PLAYING, PAUSED):
                self.draw_hud()
                if self.state == PAUSED:
                    self.draw_paused()
            elif self.state == MENU:
                self.draw_menu()
            elif self.state == SKINS_SCREEN:
                self.draw_skins()
            elif self.state == ACHIEVEMENTS_SCREEN:
                self.draw_achievements()
            elif self.state == STATS_SCREEN:
                self.draw_stats()
            elif self.state == SETTINGS_SCREEN:
                self.draw_settings()
            elif self.state == RUN_END:
                self.draw_run_end()
            if self.profile["settings"].get("show_fps"):
                self.draw_fps()

            self.renderer.finish(crt=crt)
            pygame.display.flip()


def main():
    App().run()


if __name__ == "__main__":
    main()
