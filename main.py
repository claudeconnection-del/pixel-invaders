"""Pixel Invaders arcade cabinet — a multi-game 8-bit voxel arcade built with
pygame-ce + PyOpenGL. All art and audio generated from code.

Cabinet controls:
    Arrows / WASD - navigate + play      Enter - confirm
    Esc - pause / back                   C - CRT filter, M - music
Game controls are per-game (Voxel Hell: Space fire, Shift focus).
"""
import random
import sys

import pygame

from game import events as ev
from game.assets import AudioBank
from game.entities import InputState
from games import load_games, GAME_IDS
from meta import profile as profile_mod
from meta.achievements import AchievementEngine
from meta.stats import StatsTracker

WIDTH, HEIGHT = 1280, 860

# app states
MENU = "menu"
MODE_SELECT = "mode_select"
HANGAR = "hangar"
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

MENU_ITEMS = ["PLAY", "HANGAR", "ACHIEVEMENTS", "STATS", "SETTINGS", "QUIT"]

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

SUMMARY_ROWS = [
    ("score", "Score", "{:,}"),
    ("wave_reached", "Waves survived", "{}"),
    ("loop", "Loop", "{}"),
    ("level_reached", "Level reached", "{}"),
    ("length", "Final length", "{}"),
    ("kills", "Destroyed", "{}"),
    ("accuracy", "Accuracy", "{:.0%}"),
    ("grazes", "Bullets grazed", "{}"),
    ("max_multiplier", "Max multiplier", "x{:.1f}"),
    ("powerups", "Power-ups", "{}"),
    ("deaths", "Deaths", "{}"),
    ("duration", "Duration", "{:.0f}s"),
]


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
        pygame.display.set_caption("Pixel Invaders Arcade")
        self.clock = pygame.time.Clock()

        self.profile = profile_mod.load()
        self.renderer = None
        self.apply_display_settings()

        self.audio = AudioBank()
        self.audio.music_on = self.profile["settings"].get("music", True)
        self.audio.set_volumes(self.profile["settings"]["sfx_vol"],
                               self.profile["settings"]["music_vol"])

        self.games = load_games()
        gid = self.profile.get("selected_game", GAME_IDS[0])
        self.game_id = gid if gid in self.games else GAME_IDS[0]

        self.state = MENU
        self.menu_index = 0
        self.mode_index = 0
        self.settings_index = 0
        self.skin_index = 0
        self.run = None
        self.run_stats_tracker = None
        self.run_engine = None
        self.run_summary = None
        self.run_won = False
        self.toasts = []          # [[Achievement, timer], ...]
        self.wave_banner = None   # (text, timer)
        self.showcase_index = 0

    # ----------------------------------------------------------- accessors
    @property
    def game(self):
        return self.games[self.game_id]

    @property
    def section(self):
        return profile_mod.game_section(self.profile, self.game_id)

    def engine_for_current_game(self):
        module = self.game
        resolver = getattr(module, "skin_for_achievement", None)
        return AchievementEngine(self.section, module.ACHIEVEMENTS, resolver)

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

    # --------------------------------------------------------- persistence
    def save_profile(self):
        profile_mod.save(self.profile)

    # ------------------------------------------------------------ settings
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

    # --------------------------------------------------------------- input
    def handle_keydown(self, key):
        audio = self.audio
        if self.state == MENU:
            if key in (pygame.K_LEFT, pygame.K_a):
                self.cycle_game(-1)
            elif key in (pygame.K_RIGHT, pygame.K_d):
                self.cycle_game(1)
            elif key in (pygame.K_UP, pygame.K_w):
                self.menu_index = (self.menu_index - 1) % len(MENU_ITEMS)
                audio.play("menu_move")
            elif key in (pygame.K_DOWN, pygame.K_s):
                self.menu_index = (self.menu_index + 1) % len(MENU_ITEMS)
                audio.play("menu_move")
            elif key == pygame.K_RETURN:
                audio.play("menu_select")
                self.menu_choose(MENU_ITEMS[self.menu_index])
            elif key == pygame.K_ESCAPE:
                self.quit()

        elif self.state == MODE_SELECT:
            modes = self.game.INFO.modes
            if key in (pygame.K_UP, pygame.K_w, pygame.K_LEFT, pygame.K_a):
                self.mode_index = (self.mode_index - 1) % len(modes)
                audio.play("menu_move")
            elif key in (pygame.K_DOWN, pygame.K_s, pygame.K_RIGHT, pygame.K_d):
                self.mode_index = (self.mode_index + 1) % len(modes)
                audio.play("menu_move")
            elif key == pygame.K_RETURN:
                audio.play("menu_select")
                self.start_run(modes[self.mode_index][0])
            elif key == pygame.K_ESCAPE:
                self.state = MENU

        elif self.state == HANGAR:
            module = self.game
            order = module.SKIN_ORDER
            if key in (pygame.K_LEFT, pygame.K_a):
                self.skin_index = (self.skin_index - 1) % len(order)
                audio.play("menu_move")
            elif key in (pygame.K_RIGHT, pygame.K_d):
                self.skin_index = (self.skin_index + 1) % len(order)
                audio.play("menu_move")
            elif key == pygame.K_RETURN:
                skin_id = order[self.skin_index]
                if skin_id in self.section["unlocked_skins"]:
                    self.section["selected_skin"] = skin_id
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
        if key == pygame.K_c and self.state != SETTINGS_SCREEN:
            self.profile["settings"]["crt"] = not self.profile["settings"]["crt"]
            self.save_profile()
        elif key == pygame.K_m and self.state != SETTINGS_SCREEN:
            on = not self.profile["settings"].get("music", True)
            self.profile["settings"]["music"] = on
            self.audio.set_music_enabled(on)
            self.save_profile()

    def cycle_game(self, direction):
        idx = GAME_IDS.index(self.game_id)
        self.game_id = GAME_IDS[(idx + direction) % len(GAME_IDS)]
        self.profile["selected_game"] = self.game_id
        self.skin_index = 0
        self.audio.play("menu_move")
        self.save_profile()

    def menu_choose(self, choice):
        if choice == "PLAY":
            modes = self.game.INFO.modes
            if len(modes) > 1:
                self.mode_index = 0
                self.state = MODE_SELECT
            else:
                self.start_run(modes[0][0])
        elif choice == "HANGAR":
            if self.game.INFO.has_skins:
                order = self.game.SKIN_ORDER
                selected = self.section["selected_skin"]
                self.skin_index = order.index(selected) if selected in order else 0
                self.state = HANGAR
        elif choice == "ACHIEVEMENTS":
            self.state = ACHIEVEMENTS_SCREEN
        elif choice == "STATS":
            self.state = STATS_SCREEN
        elif choice == "SETTINGS":
            self.state = SETTINGS_SCREEN
        elif choice == "QUIT":
            self.quit()

    # ---------------------------------------------------------------- runs
    def start_run(self, mode):
        self.run = self.game.create_run(mode, random.Random())
        self.run_stats_tracker = StatsTracker(self.section)
        self.run_engine = self.engine_for_current_game()
        self.run_summary = None
        self.toasts.clear()
        self.wave_banner = None
        self.state = PLAYING
        self.audio.music("game")

    def abandon_run(self):
        """Quit to menu mid-run: counts stats so far as an unfinished run."""
        if self.run is not None and not self.run.run_over:
            life = self.section["lifetime"]
            life["runs"] += 1
        self.run = None
        self.save_profile()
        self.state = MENU
        self.audio.music("menu")

    def quit(self):
        self.save_profile()
        pygame.quit()
        sys.exit(0)

    # ------------------------------------------------------------ gameplay
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

    def post_banner(self, text, seconds):
        self.wave_banner = (text, seconds)

    def update_playing(self, dt):
        run = self.run
        run.update(dt, self.gameplay_input())
        frame_events = run.drain_events()

        for etype, data in frame_events:
            run.on_event(etype, data, self.renderer, self.audio, self.post_banner)
            if etype == ev.RUN_END:
                self.run_summary = data["summary"]
                self.run_won = data["win"]

        self.run_stats_tracker.on_frame(dt, frame_events)
        for achievement in self.run_engine.on_frame(frame_events, run.run_stats()):
            self.toasts.append([achievement, 3.5])
            self.audio.play("toast")
            self.save_profile()

        if hasattr(run, "per_frame_particles"):
            run.per_frame_particles(self.renderer, random)

        if self.run_summary is not None and self.state == PLAYING:
            self.state = RUN_END
            self.audio.music(None)
            self.save_profile()

    # ------------------------------------------------------------ overlays
    def draw_banner_and_toasts(self):
        o = self.renderer.overlay
        if self.wave_banner is not None:
            text, timer = self.wave_banner
            alpha = int(255 * min(1.0, timer / 0.6))
            o.text(text, WIDTH / 2, HEIGHT * 0.36, size=34,
                   color=(GREEN[0], GREEN[1], GREEN[2], alpha), center=True)
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
        info = self.game.INFO
        o.text("PIXEL INVADERS ARCADE", WIDTH / 2, 90, size=48, color=GREEN,
               center=True)
        multi = len(GAME_IDS) > 1
        title = f"< {info.name} >" if multi else info.name
        o.text(title, WIDTH / 2, 190, size=34, color=RED, center=True)
        o.text(info.tagline, WIDTH / 2, 240, size=16, color=DIM, center=True)

        items = [m for m in MENU_ITEMS
                 if m != "HANGAR" or info.has_skins]
        if MENU_ITEMS[self.menu_index] not in items:
            self.menu_index = 0
        for i, item in enumerate(items):
            actual_index = MENU_ITEMS.index(item)
            selected = actual_index == self.menu_index
            color = WHITE if selected else DIM
            prefix = "> " if selected else "  "
            o.text(prefix + item, WIDTH / 2 - 90, 330 + i * 48, size=28, color=color)

        life = self.section["lifetime"]
        o.text(f"BEST {life['best_score']:07d}", WIDTH / 2, 640, size=18,
               color=GOLD, center=True)
        unlocked = len(self.section["achievements"])
        o.text(f"{unlocked}/{len(self.game.ACHIEVEMENTS)} achievements",
               WIDTH / 2, 670, size=14, color=DIM, center=True)
        o.text("Left/Right: game   C: CRT   M: music   Esc: quit",
               WIDTH / 2, HEIGHT - 40, size=14, color=DIM, center=True)
        self.draw_banner_and_toasts()

    def draw_mode_select(self):
        o = self.renderer.overlay
        o.text(self.game.INFO.name, WIDTH / 2, 160, size=40, color=GREEN,
               center=True)
        o.text("SELECT MODE", WIDTH / 2, 260, size=22, color=DIM, center=True)
        for i, (mode_id, label) in enumerate(self.game.INFO.modes):
            selected = i == self.mode_index
            color = WHITE if selected else DIM
            prefix = "> " if selected else "  "
            o.text(prefix + label, WIDTH / 2 - 80, 340 + i * 52, size=30,
                   color=color)
        o.text("Esc: back", WIDTH / 2, HEIGHT - 40, size=14, color=DIM, center=True)

    def draw_hangar(self):
        o = self.renderer.overlay
        module = self.game
        skin_id = module.SKIN_ORDER[self.skin_index]
        skin = module.SKINS[skin_id]
        unlocked = skin_id in self.section["unlocked_skins"]
        selected = skin_id == self.section["selected_skin"]

        o.text("HANGAR", WIDTH / 2, 90, size=44, color=GREEN, center=True)
        o.text(f"< {skin['name']} >", WIDTH / 2, 560, size=32,
               color=WHITE if unlocked else DIM, center=True)
        o.text(skin["desc"], WIDTH / 2, 610, size=16, color=DIM, center=True)
        if not unlocked:
            req = next(a for a in module.ACHIEVEMENTS if a.id == skin["unlock"])
            o.text(f"LOCKED — {req.name}: {req.desc}", WIDTH / 2, 650, size=16,
                   color=RED, center=True)
        elif selected:
            o.text("[ EQUIPPED ]", WIDTH / 2, 650, size=18, color=GOLD, center=True)
        else:
            o.text("Enter to equip", WIDTH / 2, 650, size=16, color=GREEN,
                   center=True)
        o.text(f"{self.skin_index + 1}/{len(module.SKIN_ORDER)}   Esc: back",
               WIDTH / 2, HEIGHT - 40, size=14, color=DIM, center=True)

    def draw_achievements(self):
        o = self.renderer.overlay
        module = self.game
        engine = self.run_engine or self.engine_for_current_game()
        o.text(f"{module.INFO.name} — ACHIEVEMENTS", WIDTH / 2, 55, size=32,
               color=GREEN, center=True)
        col_w = 590
        run_stats = self.run.run_stats() if self.run else {}
        for i, a in enumerate(module.ACHIEVEMENTS):
            col = i % 2
            row = i // 2
            x = 60 + col * col_w
            y = 118 + row * 98
            unlocked = engine.is_unlocked(a.id)
            o.rect(x, y, col_w - 40, 84, (25, 30, 45, 200))
            o.rect(x, y, 4, 84, GOLD if unlocked else (70, 70, 85, 255))
            o.text(a.name, x + 18, y + 8, size=18,
                   color=GOLD if unlocked else WHITE)
            o.text(a.desc, x + 18, y + 34, size=13, color=DIM)
            if unlocked:
                o.text("UNLOCKED", x + col_w - 150, y + 8, size=13, color=GREEN)
            elif a.progress is not None:
                try:
                    cur, target = a.progress(self.section["lifetime"], run_stats)
                except (KeyError, TypeError):
                    cur, target = 0, 1
                frac = min(1.0, cur / target)
                o.rect(x + 18, y + 58, col_w - 90, 8, (45, 45, 65, 255))
                o.rect(x + 18, y + 58, (col_w - 90) * frac, 8, CYAN)
                o.text(f"{cur}/{target}", x + col_w - 130, y + 52, size=12,
                       color=DIM)
        o.text("Esc: back", WIDTH / 2, HEIGHT - 26, size=14, color=DIM, center=True)

    def draw_stats(self):
        o = self.renderer.overlay
        life = self.section["lifetime"]
        o.text(f"{self.game.INFO.name} — SERVICE RECORD", WIDTH / 2, 70,
               size=32, color=GREEN, center=True)
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

    def draw_run_end(self):
        o = self.renderer.overlay
        s = self.run_summary
        title = "VICTORY" if self.run_won else "GAME OVER"
        color = GOLD if self.run_won else RED
        o.text(title, WIDTH / 2, 150, size=64, color=color, center=True)
        shown = [(label, fmt.format(s[key])) for key, label, fmt in SUMMARY_ROWS
                 if key in s and not (key == "loop" and s.get("loop", 1) <= 1)]
        for i, (label, value) in enumerate(shown):
            y = 280 + i * 42
            o.text(label, WIDTH / 2 - 220, y, size=20, color=DIM)
            o.text(value, WIDTH / 2 + 120, y, size=20, color=WHITE)
        if self.section["lifetime"]["best_score"] <= s["score"] and s["score"] > 0:
            o.text("NEW BEST!", WIDTH / 2, 240, size=22, color=GREEN, center=True)
        o.text("Enter: menu", WIDTH / 2, HEIGHT - 60, size=18, color=GREEN,
               center=True)
        self.draw_banner_and_toasts()

    def draw_paused(self):
        o = self.renderer.overlay
        o.rect(0, 0, WIDTH, HEIGHT, (5, 5, 12, 160))
        o.text("PAUSED", WIDTH / 2, HEIGHT / 2 - 60, size=48, color=WHITE,
               center=True)
        o.text("Esc: resume    Q: quit to menu", WIDTH / 2, HEIGHT / 2 + 20,
               size=20, color=DIM, center=True)

    def draw_fps(self):
        o = self.renderer.overlay
        o.text(f"{self.clock.get_fps():5.0f} FPS", WIDTH - 120, HEIGHT - 30,
               size=14, color=DIM)

    # ------------------------------------------------------------ mainloop
    def update_timers(self, dt):
        if self.wave_banner is not None:
            text, timer = self.wave_banner
            timer -= dt
            self.wave_banner = (text, timer) if timer > 0 else None
        for toast in self.toasts:
            toast[1] -= dt
        self.toasts = [t for t in self.toasts if t[1] > 0]

    def draw_3d_layer(self, dt, showcase_timer):
        if self.state in (PLAYING, PAUSED, RUN_END) and self.run is not None:
            self.run.draw(self.renderer, self.section)
        elif self.state == MENU:
            self.renderer.draw_menu_model(
                self.game.INFO.showcase_sprite, 575, 265,
                0.34 if self.game.INFO.showcase_sprite == "boss" else 0.5,
                spin_speed=0.9)
        elif self.state == HANGAR:
            module = self.game
            skin = module.SKINS[module.SKIN_ORDER[self.skin_index]]
            unlocked = module.SKIN_ORDER[self.skin_index] in \
                self.section["unlocked_skins"]
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

    def draw_overlay_layer(self):
        self.renderer.begin_overlay()
        if self.state in (PLAYING, PAUSED):
            self.run.draw_hud(self.renderer.overlay, WIDTH, HEIGHT, self.section)
            self.draw_banner_and_toasts()
            if self.state == PAUSED:
                self.draw_paused()
        elif self.state == MENU:
            self.draw_menu()
        elif self.state == MODE_SELECT:
            self.draw_mode_select()
        elif self.state == HANGAR:
            self.draw_hangar()
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

    def run_forever(self):
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
            if self.state == PLAYING:
                self.update_playing(dt)

            self.renderer.begin(dt if self.state != PAUSED else 0.0)
            self.draw_3d_layer(dt, showcase_timer)
            self.draw_overlay_layer()
            self.renderer.finish(crt=self.profile["settings"].get("crt", True))
            pygame.display.flip()


def main():
    App().run_forever()


if __name__ == "__main__":
    main()
