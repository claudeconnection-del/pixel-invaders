"""Pixel Invaders arcade cabinet — a multi-game 8-bit voxel arcade built with
pygame-ce + PyOpenGL. All art and audio generated from code.

Cabinet controls:
    Arrows / WASD - navigate + play      Enter - confirm
    Esc - pause / back                   C - CRT filter, M - music
Game controls are per-game (Voxel Hell: Space fire, Shift focus).
"""
import math
import random
import sys

import pygame

from game import events as ev
from game.assets import AudioBank, MUSIC_END_EVENT
from game.entities import InputState
from game.netclient import ArcadeClient
from games import (CATEGORIES, GAME_IDS, category_of, games_in_category,
                   load_games)
from meta import leaderboard as lb
from meta import profile as profile_mod
from meta.achievements import AchievementEngine
from meta.outbox import Outbox
from meta.stats import StatsTracker

WINDOW_W, WINDOW_H = 1280, 860
ATTRACT_IDLE_SECONDS = 15.0
INITIALS_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 "

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
INITIALS = "initials"
LEADERBOARD = "leaderboard"
ATTRACT = "attract"
MULTIPLAYER = "multiplayer"
MP_CODE = "mp_code"
LOBBY = "lobby"

GREEN = (140, 255, 170, 255)
DIM = (150, 150, 165, 255)
WHITE = (235, 235, 240, 255)
GOLD = (250, 220, 90, 255)
RED = (255, 110, 100, 255)
CYAN = (140, 235, 255, 255)

MENU_ITEMS = ["PLAY", "MULTIPLAYER", "HANGAR", "SCORES", "ACHIEVEMENTS",
              "STATS", "SETTINGS", "QUIT"]

# (label, settings key, choices) — Left/Right cycles; floats step by 0.1
SETTINGS_ROWS = [
    ("FPS cap", "fps_cap", [60, 120, 144, 240, 0]),
    ("VSync", "vsync", [True, False]),
    ("Fullscreen", "fullscreen", [False, True]),
    ("Bloom", "bloom", ["off", "low", "full"]),
    ("Particles", "particles", ["low", "medium", "high"]),
    ("CRT filter", "crt", [True, False]),
    ("Game music", "game_music", ["classic", "custom"]),
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
        self.audio.prefer_custom = \
            self.profile["settings"].get("game_music") == "custom"

        self.games = load_games()
        gid = self.profile.get("selected_game", GAME_IDS[0])
        self.game_id = gid if gid in self.games else GAME_IDS[0]

        pygame.joystick.init()
        self.joysticks = {}
        for i in range(pygame.joystick.get_count()):
            stick = pygame.joystick.Joystick(i)
            self.joysticks[stick.get_instance_id()] = stick
        self.pad_nav_cooldown = 0.0

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
        self.run_mode = None
        self.toasts = []          # [[Achievement, timer], ...]
        self.wave_banner = None   # (text, timer)
        self.showcase_index = 0

        # arcade presentation
        self.idle_timer = 0.0
        self.attract_index = -1
        self.attract_run = None
        self.attract_gid = None

        # global leaderboard (offline-safe)
        self.net = ArcadeClient(self.profile["settings"].get("server_url", ""))
        self.board_scope = "local"        # local | global
        self.global_boards = {}           # (game, mode) -> list | "pending" | None

        # offline score outbox: queued submissions retried on next contact
        self.outbox = Outbox(
            self.profile, self.net,
            on_rank=lambda rank: (self.post_banner(f"GLOBAL RANK #{rank}", 3.0),
                                  self.audio.play("toast")),
            save_cb=self.save_profile)
        self.outbox_timer = 5.0  # first drain shortly after boot

        # multiplayer session state
        self.mp = None            # {code, seed, game, mode, players, name}
        self.mp_menu_index = 0    # 0 host / 1 join
        self.mp_mode_index = 0
        self.mp_status = ""
        self.mp_code_entry = list("AAAA")
        self.mp_code_slot = 0
        self.mp_poll_timer = 0.0
        self.initials = list(self.profile["settings"].get("player_name", "AAA"))
        self.initials_slot = 0
        self.pending_board = None    # (game_id, mode, score, extra) awaiting initials
        self.last_rank = None
        self.board_mode_index = 0
        self.kiosk = "--kiosk" in sys.argv
        if self.kiosk and not self.profile["settings"].get("fullscreen"):
            self.profile["settings"]["fullscreen"] = True
            self.apply_display_settings()

    # ----------------------------------------------------------- accessors
    @property
    def game(self):
        return self.games[self.game_id]

    @property
    def section(self):
        return profile_mod.game_section(self.profile, self.game_id)

    @property
    def W(self):
        """Logical UI width (fixed 860-high space, width follows aspect)."""
        return self.renderer.ui_w

    @property
    def H(self):
        return self.renderer.ui_h

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
        size = (WINDOW_W, WINDOW_H)
        if s.get("fullscreen"):
            flags |= pygame.FULLSCREEN
            size = (0, 0)  # desktop resolution
        else:
            flags |= pygame.RESIZABLE  # any aspect from square to 32:9
        pygame.display.set_mode(size, flags, vsync=1 if s.get("vsync", True) else 0)
        out_w, out_h = pygame.display.get_window_size()

        from render.renderer import Renderer  # needs live GL context
        self.renderer = Renderer(out_w, out_h)
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
        elif key == "game_music":
            self.audio.refresh_pools()
            self.audio.prefer_custom = s["game_music"] == "custom"
            if self.audio.current_pool == "game":  # re-resolve immediately
                self.audio.music(None)
                self.audio.music("game")
        self.save_profile()

    # --------------------------------------------------------------- input
    def handle_keydown(self, key):
        audio = self.audio
        self.idle_timer = 0.0

        if self.state == ATTRACT:
            self.stop_attract()
            return

        if self.state == INITIALS:
            if key in (pygame.K_UP, pygame.K_w):
                self._cycle_initial(-1)
                audio.play("menu_move")
            elif key in (pygame.K_DOWN, pygame.K_s):
                self._cycle_initial(1)
                audio.play("menu_move")
            elif key in (pygame.K_LEFT, pygame.K_a):
                self.initials_slot = max(0, self.initials_slot - 1)
                audio.play("menu_move")
            elif key in (pygame.K_RIGHT, pygame.K_d):
                self.initials_slot = min(2, self.initials_slot + 1)
                audio.play("menu_move")
            elif key == pygame.K_RETURN:
                if self.initials_slot < 2:
                    self.initials_slot += 1
                    audio.play("menu_move")
                else:
                    self._submit_initials()
            elif key == pygame.K_ESCAPE:
                self.pending_board = None
                self.state = MENU
                self.audio.music("menu")
            return

        if self.state == LEADERBOARD:
            modes = self.game.INFO.modes
            if key in (pygame.K_LEFT, pygame.K_a, pygame.K_RIGHT, pygame.K_d) \
                    and len(modes) > 1:
                self.board_mode_index = (self.board_mode_index + 1) % len(modes)
                audio.play("menu_move")
            elif key in (pygame.K_UP, pygame.K_w, pygame.K_DOWN, pygame.K_s) \
                    and self.net.available:
                self.board_scope = "global" if self.board_scope == "local" else "local"
                audio.play("menu_move")
                if self.board_scope == "global":
                    self._request_global_board()
            elif key in (pygame.K_ESCAPE, pygame.K_RETURN):
                self.last_rank = None
                self.state = MENU
                self.audio.music("menu")
            return

        if self.state == MULTIPLAYER:
            modes = self.game.INFO.modes
            if key in (pygame.K_UP, pygame.K_w, pygame.K_DOWN, pygame.K_s):
                self.mp_menu_index = 1 - self.mp_menu_index
                audio.play("menu_move")
            elif key in (pygame.K_LEFT, pygame.K_a, pygame.K_RIGHT, pygame.K_d) \
                    and self.mp_menu_index == 0 and len(modes) > 1:
                self.mp_mode_index = (self.mp_mode_index + 1) % len(modes)
                audio.play("menu_move")
            elif key == pygame.K_RETURN:
                audio.play("menu_select")
                if self.mp_menu_index == 0:  # host
                    mode_id = modes[self.mp_mode_index][0]
                    name = self.profile["settings"].get("player_name", "AAA")
                    self.mp_status = "Creating session..."
                    self.net.create_session(self.game_id, mode_id, name)
                else:  # join
                    self.mp_code_entry = list("AAAA")
                    self.mp_code_slot = 0
                    self.state = MP_CODE
            elif key == pygame.K_ESCAPE:
                self.state = MENU
            return

        if self.state == MP_CODE:
            if key in (pygame.K_UP, pygame.K_w, pygame.K_DOWN, pygame.K_s):
                direction = -1 if key in (pygame.K_UP, pygame.K_w) else 1
                ch = self.mp_code_entry[self.mp_code_slot]
                chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
                idx = chars.find(ch)
                self.mp_code_entry[self.mp_code_slot] = \
                    chars[(idx + direction) % len(chars)]
                audio.play("menu_move")
            elif key in (pygame.K_LEFT, pygame.K_a):
                self.mp_code_slot = max(0, self.mp_code_slot - 1)
                audio.play("menu_move")
            elif key in (pygame.K_RIGHT, pygame.K_d):
                self.mp_code_slot = min(3, self.mp_code_slot + 1)
                audio.play("menu_move")
            elif key == pygame.K_RETURN:
                if self.mp_code_slot < 3:
                    self.mp_code_slot += 1
                    audio.play("menu_move")
                else:
                    code = "".join(self.mp_code_entry)
                    name = self.profile["settings"].get("player_name", "AAA")
                    self.mp_status = f"Joining {code}..."
                    self.net.join_session(code, name)
                    audio.play("menu_select")
                    self.state = MULTIPLAYER
            elif key == pygame.K_ESCAPE:
                self.state = MULTIPLAYER
            return

        if self.state == LOBBY:
            if key == pygame.K_RETURN:
                audio.play("menu_select")
                self.start_run(self.mp["mode"], seed=self.mp["seed"])
            elif key == pygame.K_ESCAPE:
                self.mp = None
                self.state = MENU
            return

        if self.state == MENU:
            rows = self.menu_rows()
            self.menu_index = min(self.menu_index, len(rows) - 1)
            if key in (pygame.K_UP, pygame.K_w):
                self.menu_index = (self.menu_index - 1) % len(rows)
                audio.play("menu_move")
            elif key in (pygame.K_DOWN, pygame.K_s):
                self.menu_index = (self.menu_index + 1) % len(rows)
                audio.play("menu_move")
            elif key in (pygame.K_LEFT, pygame.K_a, pygame.K_RIGHT, pygame.K_d):
                direction = 1 if key in (pygame.K_RIGHT, pygame.K_d) else -1
                row = rows[self.menu_index]
                if row == "CATEGORY":
                    self.cycle_category(direction)
                elif row == "GAME":
                    self.cycle_game(direction)
            elif key == pygame.K_RETURN:
                row = rows[self.menu_index]
                audio.play("menu_select")
                if row in ("CATEGORY", "GAME"):
                    self.menu_index = 2  # jump to PLAY
                else:
                    self.menu_choose(row)
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
            elif hasattr(self.run, "handle_key"):
                self.run.handle_key(key)

        elif self.state == PAUSED:
            if key == pygame.K_ESCAPE:
                self.state = PLAYING
                if self.game.INFO.game_music:
                    boss = getattr(self.run.world, "boss", None)
                    fighting_boss = (boss is not None and boss.alive
                                     and not self.run.run_over)
                    self.audio.music("boss" if fighting_boss
                                     else self.gameplay_music_pool())
            elif key == pygame.K_q:
                self.abandon_run()

        elif self.state == RUN_END:
            if key == pygame.K_RETURN:
                if self.mp is not None:
                    self.state = LOBBY
                    self.mp_poll_timer = 0.0
                    self.audio.music("menu")
                elif self.pending_board is not None:
                    self.initials = list(
                        (self.profile["settings"].get("player_name", "AAA") + "AAA")[:3])
                    self.initials_slot = 0
                    self.state = INITIALS
                else:
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

    def menu_rows(self):
        """Navigable main-menu rows: carousels + this game's action items."""
        info = self.game.INFO
        actions = [m for m in MENU_ITEMS
                   if (m != "HANGAR" or info.has_skins)
                   and (m != "SCORES" or info.has_scores)
                   and (m != "MULTIPLAYER"
                        or (info.has_scores and self.net.available))]
        return ["CATEGORY", "GAME"] + actions

    def cycle_category(self, direction):
        names = [name for name, _ in CATEGORIES]
        idx = names.index(category_of(self.game_id))
        new_category = names[(idx + direction) % len(names)]
        self._select_game(games_in_category(new_category)[0])

    def cycle_game(self, direction):
        ids = games_in_category(category_of(self.game_id))
        idx = ids.index(self.game_id)
        self._select_game(ids[(idx + direction) % len(ids)])

    def _select_game(self, gid):
        self.game_id = gid
        self.profile["selected_game"] = gid
        self.skin_index = 0
        self.menu_index = min(self.menu_index, len(self.menu_rows()) - 1)
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
        elif choice == "MULTIPLAYER":
            self.mp_menu_index = 0
            self.mp_mode_index = 0
            self.mp_status = ""
            self.state = MULTIPLAYER
        elif choice == "SCORES":
            if self.game.INFO.has_scores:
                self.board_mode_index = 0
                self.state = LEADERBOARD
        elif choice == "ACHIEVEMENTS":
            self.state = ACHIEVEMENTS_SCREEN
        elif choice == "STATS":
            self.state = STATS_SCREEN
        elif choice == "SETTINGS":
            self.state = SETTINGS_SCREEN
        elif choice == "QUIT":
            self.quit()

    # ---------------------------------------------------------------- runs
    def start_run(self, mode, seed=None):
        self.run = self.game.create_run(mode, random.Random(seed))
        if hasattr(self.run, "attach_profile"):
            self.run.attach_profile(self.section, self.profile["settings"],
                                    self.save_profile)
        self.run_mode = mode
        self.run_stats_tracker = StatsTracker(self.section)
        self.run_engine = self.engine_for_current_game()
        self.run_summary = None
        self.pending_board = None
        self.toasts.clear()
        self.wave_banner = None
        self.state = PLAYING
        if self.game.INFO.mouse_look:
            pygame.mouse.get_rel()  # flush menu motion so the camera doesn't snap
        # tool modules (studio) manage their own audio; games get their pool
        self.audio.music(self.gameplay_music_pool())

    def gameplay_music_pool(self):
        """The section pool for the running game ('game', 'metal', ... or
        None for tool modules that manage their own audio)."""
        info = self.game.INFO
        return info.music_pool if info.game_music else None

    # ------------------------------------------------------------- initials
    def _cycle_initial(self, direction):
        ch = self.initials[self.initials_slot]
        idx = INITIALS_CHARS.find(ch)
        self.initials[self.initials_slot] = \
            INITIALS_CHARS[(idx + direction) % len(INITIALS_CHARS)]

    def _submit_initials(self):
        game_id, mode, score, extra = self.pending_board
        name = "".join(self.initials).strip() or "AAA"
        self.profile["settings"]["player_name"] = "".join(self.initials)
        self.last_rank = lb.submit(self.profile, game_id, mode, name, score, extra)
        # global submission goes through the outbox: survives being offline
        self.outbox.queue_score(game_id, mode, name, score, extra.get("wave"))
        self.pending_board = None
        self.board_scope = "local"
        self.board_mode_index = next(
            (i for i, (m, _) in enumerate(self.game.INFO.modes) if m == mode), 0)
        self.save_profile()
        self.audio.play("toast")
        self.state = LEADERBOARD

    def _request_global_board(self):
        modes = self.game.INFO.modes
        mode_id = modes[self.board_mode_index % len(modes)][0]
        key = (self.game_id, mode_id)
        if self.global_boards.get(key) in (None, "error") or key not in self.global_boards:
            self.global_boards[key] = "pending"
            self.net.fetch_scores(self.game_id, mode_id)

    def poll_network(self):
        for tag, payload in self.net.poll():
            if isinstance(tag, tuple) and tag[0] == "outbox":
                self.outbox.handle_result(tag, payload)
            elif isinstance(tag, tuple) and tag[0] == "scores":
                key = (tag[1], tag[2])
                if payload is None:
                    self.global_boards[key] = "error"
                else:
                    self.global_boards[key] = payload.get("scores", [])
            elif tag == "submit" and payload is not None:
                self.post_banner(f"GLOBAL RANK #{payload['rank']}", 3.0)
                self.audio.play("toast")
            elif tag == "session_create":
                if payload is None:
                    self.mp_status = "OFFLINE — couldn't reach the server"
                else:
                    self._enter_lobby(payload, host=True)
            elif tag == "session_join":
                if payload is None:
                    self.mp_status = "Join failed — bad code, taken name, or offline"
                else:
                    self._enter_lobby(payload, host=False)
            elif tag in ("session_state", "session_score"):
                if payload is not None and self.mp is not None \
                        and payload.get("code") == self.mp["code"]:
                    self.mp["players"] = payload.get("players", [])

    def _enter_lobby(self, payload, host):
        name = self.profile["settings"].get("player_name", "AAA").upper().strip()
        gid = payload.get("game", self.game_id)
        if gid in self.games:
            self.game_id = gid
        self.mp = {
            "code": payload["code"],
            "seed": payload["seed"],
            "game": gid,
            "mode": payload.get("mode", self.game.INFO.modes[0][0]),
            "players": payload.get("players", []),
            "name": name,
        }
        self.mp_status = ""
        self.mp_poll_timer = 0.0
        self.state = LOBBY
        self.audio.play("toast")

    # -------------------------------------------------------------- attract
    def start_attract(self):
        eligible = [g for g in GAME_IDS if self.games[g].INFO.attract]
        if not eligible:
            return
        self.attract_index = (self.attract_index + 1) % len(eligible)
        gid = eligible[self.attract_index]
        self.attract_gid = gid
        self.attract_run = self.games[gid].create_run(
            self.games[gid].INFO.modes[0][0], random.Random())
        self.state = ATTRACT
        self.wave_banner = None
        self.audio.music(None)

    def stop_attract(self):
        self.attract_run = None
        self.idle_timer = 0.0
        self.state = MENU
        self.audio.music("menu")
        self.audio.play("menu_select")

    def update_attract(self, dt):
        run = self.attract_run
        module = self.games[self.attract_gid]
        run.update(dt, module.demo_bot(run.world))
        # effects only — attract demos never touch stats or achievements
        for etype, data in run.drain_events():
            run.on_event(etype, data, self.renderer, self.audio, self.post_banner)
        if hasattr(run, "per_frame_particles"):
            run.per_frame_particles(self.renderer, random)
        if run.run_over:
            self.start_attract()

    def abandon_run(self):
        """Quit to menu mid-run: counts stats so far as an unfinished run."""
        if self.run is not None and not self.run.run_over:
            life = self.section["lifetime"]
            life["runs"] += 1
        self.run = None
        self.save_profile()
        self.state = LOBBY if self.mp is not None else MENU
        self.audio.music("menu")

    def quit(self):
        self.save_profile()
        pygame.quit()
        sys.exit(0)

    # ------------------------------------------------------------- gamepad
    def _pad(self):
        return next(iter(self.joysticks.values()), None)

    def pad_state(self):
        """(dx, dy, fire, focus, right_x) from the first connected controller.
        Assumes the common SDL/Xbox layout: left stick axes 0/1, right stick
        X axis 2, hat 0 d-pad, A(0)=fire, LB/RB(4/5) or triggers=focus."""
        pad = self._pad()
        if pad is None:
            return 0.0, 0.0, False, False, 0.0
        try:
            n = pad.get_numaxes()
            dx = pad.get_axis(0) if n > 0 else 0.0
            dy = pad.get_axis(1) if n > 1 else 0.0
            rx = pad.get_axis(2) if n > 2 else 0.0
            if abs(rx) < 0.2:  # deadzone for the look stick
                rx = 0.0
            if pad.get_numhats() > 0:
                hx, hy = pad.get_hat(0)
                dx = hx or dx
                dy = -hy or dy
            nbuttons = pad.get_numbuttons()
            fire = nbuttons > 0 and pad.get_button(0)
            focus = ((nbuttons > 4 and pad.get_button(4))
                     or (nbuttons > 5 and pad.get_button(5)))
            if not focus and n > 5:
                focus = pad.get_axis(4) > 0.0 or pad.get_axis(5) > 0.0
            return dx, dy, bool(fire), bool(focus), rx
        except pygame.error:
            return 0.0, 0.0, False, False, 0.0

    def handle_pad_button(self, button):
        """Map controller buttons to the keyboard actions per state."""
        self.idle_timer = 0.0
        if self.state == ATTRACT:
            self.stop_attract()
            return
        in_game = self.state in (PLAYING, PAUSED)
        if button == 0:      # A: confirm (fire is polled separately in-game)
            if not in_game:
                self.handle_keydown(pygame.K_RETURN)
        elif button == 1:    # B: back / resume
            if self.state != PLAYING:
                self.handle_keydown(pygame.K_ESCAPE)
        elif button == 6:    # back/select: quit to menu while paused
            if self.state == PAUSED:
                self.handle_keydown(pygame.K_q)
        elif button == 7:    # start: pause / confirm
            self.handle_keydown(
                pygame.K_ESCAPE if in_game else pygame.K_RETURN)

    def poll_pad_navigation(self, dt):
        """Stick/d-pad moves menus like arrow keys, with repeat gating."""
        if self.state in (PLAYING,):
            return
        self.pad_nav_cooldown = max(0.0, self.pad_nav_cooldown - dt)
        dx, dy, _, _, _ = self.pad_state()
        if self.pad_nav_cooldown > 0:
            return
        key = None
        if dy < -0.5:
            key = pygame.K_UP
        elif dy > 0.5:
            key = pygame.K_DOWN
        elif dx < -0.5:
            key = pygame.K_LEFT
        elif dx > 0.5:
            key = pygame.K_RIGHT
        if key is not None:
            self.handle_keydown(key)
            self.pad_nav_cooldown = 0.22

    # ------------------------------------------------------------ gameplay
    def mouse_logical(self):
        """Window mouse position in logical UI coordinates (window pixels
        divided by the device scale — no letterboxing anymore)."""
        mx, my = pygame.mouse.get_pos()
        s = self.renderer.ui_scale
        return mx / s, my / s

    def gameplay_input(self):
        keys = pygame.key.get_pressed()
        pdx, pdy, pfire, pfocus, prx = self.pad_state()
        aim_x, aim_y = self.mouse_logical()
        mouse_fire = pygame.mouse.get_pressed()[0]
        # relative mouse motion, consumed every frame; only applied by
        # mouse-look games (grab is on for those)
        rel_dx = pygame.mouse.get_rel()[0]
        look_dx = rel_dx if self.game.INFO.mouse_look else 0.0

        strafe = ((1 if keys[pygame.K_d] else 0)
                  - (1 if keys[pygame.K_a] else 0))
        if abs(pdx) > 0.35:
            strafe = pdx
        turn = ((1 if keys[pygame.K_RIGHT] else 0)
                - (1 if keys[pygame.K_LEFT] else 0)) + prx
        return InputState(
            left=keys[pygame.K_LEFT] or keys[pygame.K_a] or pdx < -0.35,
            right=keys[pygame.K_RIGHT] or keys[pygame.K_d] or pdx > 0.35,
            up=keys[pygame.K_UP] or keys[pygame.K_w] or pdy < -0.35,
            down=keys[pygame.K_DOWN] or keys[pygame.K_s] or pdy > 0.35,
            focus=keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT] or pfocus,
            fire=keys[pygame.K_SPACE] or pfire or mouse_fire,
            aim_x=aim_x, aim_y=aim_y,
            strafe=strafe, turn=max(-1.0, min(1.0, turn)), look_dx=look_dx,
        )

    def post_banner(self, text, seconds):
        self.wave_banner = (text, seconds)

    def update_playing(self, dt):
        run = self.run
        run.update(dt, self.gameplay_input())
        frame_events = run.drain_events()

        for etype, data in frame_events:
            run.on_event(etype, data, self.renderer, self.audio, self.post_banner)
            if etype == ev.BOSS_SPAWN:
                self.audio.music("boss")
            elif etype == ev.BOSS_KILLED:
                self.audio.music(self.gameplay_music_pool())
            elif etype == "studio_export":
                self.audio.refresh_pools()
                self.audio.prefer_custom = \
                    self.profile["settings"].get("game_music") == "custom"
            elif etype == ev.RUN_END:
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
            score = self.run_summary["score"]
            if self.mp is not None:
                # session runs report to the lobby, not the initials flow;
                # queued so a dropped connection still lands the score
                self.outbox.queue_session_score(
                    self.mp["code"], self.mp["name"], score,
                    self.run_summary.get("wave_reached"))
            elif lb.qualifies(self.profile, self.game_id, self.run_mode, score):
                extra = {}
                if "wave_reached" in self.run_summary:
                    extra["wave"] = self.run_summary["wave_reached"]
                self.pending_board = (self.game_id, self.run_mode, score, extra)
            self.save_profile()

    # ------------------------------------------------------------ overlays
    def draw_banner_and_toasts(self):
        o = self.renderer.overlay
        if self.wave_banner is not None:
            text, timer = self.wave_banner
            alpha = int(255 * min(1.0, timer / 0.6))
            o.text(text, self.W / 2, self.H * 0.36, size=34,
                   color=(GREEN[0], GREEN[1], GREEN[2], alpha), center=True)
        y = 120
        for achievement, timer in self.toasts:
            slide = min(1.0, (3.5 - timer) * 5)
            x = self.W - 20 - 360 * slide
            o.rect(x, y, 360, 58, (25, 30, 45, 235))
            o.rect(x, y, 4, 58, GOLD)
            o.text("ACHIEVEMENT UNLOCKED", x + 16, y + 8, size=13, color=GOLD)
            o.text(achievement.name, x + 16, y + 28, size=18, color=WHITE)
            y += 70

    def draw_menu(self):
        o = self.renderer.overlay
        info = self.game.INFO
        o.text("PIXEL INVADERS ARCADE", self.W / 2, 64, size=44, color=GREEN,
               center=True)

        rows = self.menu_rows()
        self.menu_index = min(self.menu_index, len(rows) - 1)

        # menu panel: everything textual lives inside; on wide screens the
        # showcase model gets the right third to itself, on narrow/square
        # screens the panel centers and the model is skipped
        panel_w = 560
        aspect = self.renderer.width / self.renderer.height
        if aspect >= 1.25:
            panel_x = max(40, int(self.W * 0.5 - 480))
        else:
            panel_x = int((self.W - panel_w) / 2)
        label_x, value_x = panel_x + 46, panel_x + 230
        row_h = 48
        panel_h = 40 + row_h * (len(rows) + 1) + 26  # rows + tagline + footer
        panel_y = max(130, (self.H - panel_h) // 2 - 30)
        o.rect(panel_x, panel_y, panel_w, panel_h, (14, 17, 28, 215))
        o.rect(panel_x, panel_y, 4, panel_h, GREEN)

        y = panel_y + 28
        for i, row in enumerate(rows):
            selected = i == self.menu_index
            if selected:
                o.rect(panel_x + 10, y - 8, panel_w - 20, 38, (40, 48, 70, 160))
            if row == "CATEGORY":
                label = category_of(self.game_id)
                o.text("CATEGORY", label_x, y, size=20,
                       color=WHITE if selected else DIM)
                o.text(f"< {label} >" if selected else label,
                       value_x, y, size=20, color=GOLD if selected else DIM)
                y += row_h
            elif row == "GAME":
                o.text("GAME", label_x, y, size=20,
                       color=WHITE if selected else DIM)
                o.text(f"< {info.name} >" if selected else info.name,
                       value_x, y, size=20, color=RED if selected else WHITE)
                y += 34
                o.text(info.tagline, label_x, y, size=14, color=DIM)
                y += row_h
            else:
                prefix = "> " if selected else "  "
                o.text(prefix + row, label_x, y, size=23,
                       color=WHITE if selected else DIM)
                y += row_h

        life = self.section["lifetime"]
        summary = f"BEST {life['best_score']:07d}"
        if self.game.ACHIEVEMENTS:
            unlocked = len(self.section["achievements"])
            summary += f"    {unlocked}/{len(self.game.ACHIEVEMENTS)} achievements"
        o.text(summary, panel_x + panel_w / 2, y + 8, size=15, color=GOLD,
               center=True)

        o.text("Left/Right: change   C: CRT   M: music   Esc: quit",
               self.W / 2, self.H - 36, size=15, color=DIM, center=True)
        self.draw_banner_and_toasts()

    def draw_mode_select(self):
        o = self.renderer.overlay
        o.text(self.game.INFO.name, self.W / 2, 160, size=40, color=GREEN,
               center=True)
        o.text("SELECT MODE", self.W / 2, 260, size=22, color=DIM, center=True)
        for i, (mode_id, label) in enumerate(self.game.INFO.modes):
            selected = i == self.mode_index
            color = WHITE if selected else DIM
            prefix = "> " if selected else "  "
            o.text(prefix + label, self.W / 2 - 80, 340 + i * 52, size=30,
                   color=color)
        o.text("Esc: back", self.W / 2, self.H - 40, size=14, color=DIM, center=True)

    def draw_hangar(self):
        o = self.renderer.overlay
        module = self.game
        skin_id = module.SKIN_ORDER[self.skin_index]
        skin = module.SKINS[skin_id]
        unlocked = skin_id in self.section["unlocked_skins"]
        selected = skin_id == self.section["selected_skin"]

        o.text("HANGAR", self.W / 2, 90, size=44, color=GREEN, center=True)
        o.text(f"< {skin['name']} >", self.W / 2, 560, size=32,
               color=WHITE if unlocked else DIM, center=True)
        o.text(skin["desc"], self.W / 2, 610, size=16, color=DIM, center=True)
        if not unlocked:
            req = next(a for a in module.ACHIEVEMENTS if a.id == skin["unlock"])
            o.text(f"LOCKED — {req.name}: {req.desc}", self.W / 2, 650, size=16,
                   color=RED, center=True)
        elif selected:
            o.text("[ EQUIPPED ]", self.W / 2, 650, size=18, color=GOLD, center=True)
        else:
            o.text("Enter to equip", self.W / 2, 650, size=16, color=GREEN,
                   center=True)
        o.text(f"{self.skin_index + 1}/{len(module.SKIN_ORDER)}   Esc: back",
               self.W / 2, self.H - 40, size=14, color=DIM, center=True)

    def draw_achievements(self):
        o = self.renderer.overlay
        module = self.game
        engine = self.run_engine or self.engine_for_current_game()
        o.text(f"{module.INFO.name} — ACHIEVEMENTS", self.W / 2, 55, size=32,
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
        o.text("Esc: back", self.W / 2, self.H - 26, size=14, color=DIM, center=True)

    def draw_stats(self):
        o = self.renderer.overlay
        life = self.section["lifetime"]
        o.text(f"{self.game.INFO.name} — SERVICE RECORD", self.W / 2, 70,
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
            o.text(label, self.W / 2 - 280, y, size=20, color=DIM)
            o.text(value, self.W / 2 + 120, y, size=20, color=WHITE)
        o.text("Esc: back", self.W / 2, self.H - 30, size=14, color=DIM, center=True)

    def draw_settings(self):
        o = self.renderer.overlay
        s = self.profile["settings"]
        o.text("SETTINGS", self.W / 2, 80, size=44, color=GREEN, center=True)
        for i, (label, key, choices) in enumerate(SETTINGS_ROWS):
            y = 190 + i * 52
            selected = i == self.settings_index
            color = WHITE if selected else DIM
            prefix = "> " if selected else "  "
            o.text(prefix + label, self.W / 2 - 330, y, size=24, color=color)
            value = settings_value_label(key, s[key])
            o.text(f"< {value} >" if selected else value,
                   self.W / 2 + 160, y, size=24,
                   color=GOLD if selected else DIM)
        o.text("Left/Right: change   Esc: back",
               self.W / 2, self.H - 40, size=14, color=DIM, center=True)

    def draw_run_end(self):
        o = self.renderer.overlay
        s = self.run_summary
        title = "VICTORY" if self.run_won else "GAME OVER"
        color = GOLD if self.run_won else RED
        o.text(title, self.W / 2, 150, size=64, color=color, center=True)
        shown = [(label, fmt.format(s[key])) for key, label, fmt in SUMMARY_ROWS
                 if key in s and not (key == "loop" and s.get("loop", 1) <= 1)]
        for i, (label, value) in enumerate(shown):
            y = 280 + i * 42
            o.text(label, self.W / 2 - 220, y, size=20, color=DIM)
            o.text(value, self.W / 2 + 120, y, size=20, color=WHITE)
        if self.section["lifetime"]["best_score"] <= s["score"] and s["score"] > 0:
            o.text("NEW BEST!", self.W / 2, 240, size=22, color=GREEN, center=True)
        footer = "Enter: back to lobby" if self.mp is not None else "Enter: menu"
        o.text(footer, self.W / 2, self.H - 60, size=18, color=GREEN,
               center=True)
        self.draw_banner_and_toasts()

    def draw_paused(self):
        o = self.renderer.overlay
        o.rect(0, 0, self.W, self.H, (5, 5, 12, 160))
        o.text("PAUSED", self.W / 2, self.H / 2 - 60, size=48, color=WHITE,
               center=True)
        o.text("Esc: resume    Q: quit to menu", self.W / 2, self.H / 2 + 20,
               size=20, color=DIM, center=True)

    def draw_multiplayer(self):
        o = self.renderer.overlay
        modes = self.game.INFO.modes
        o.text(f"{self.game.INFO.name} — MULTIPLAYER", self.W / 2, 120,
               size=32, color=GREEN, center=True)
        o.text("Everyone plays the same seeded run. Highest score takes it.",
               self.W / 2, 175, size=14, color=DIM, center=True)

        host_sel = self.mp_menu_index == 0
        mode_label = modes[self.mp_mode_index % len(modes)][1]
        host_text = f"HOST SESSION   < {mode_label} >" if len(modes) > 1 \
            else "HOST SESSION"
        o.text(("> " if host_sel else "  ") + host_text, self.W / 2 - 220, 300,
               size=26, color=WHITE if host_sel else DIM)
        o.text(("> " if not host_sel else "  ") + "JOIN WITH CODE",
               self.W / 2 - 220, 360, size=26,
               color=WHITE if not host_sel else DIM)

        name = self.profile["settings"].get("player_name", "AAA")
        o.text(f"Playing as {name}  (set initials via any high score)",
               self.W / 2, 460, size=14, color=DIM, center=True)
        if self.mp_status:
            o.text(self.mp_status, self.W / 2, 520, size=16, color=GOLD,
                   center=True)
        o.text("Enter: select   Esc: back", self.W / 2, self.H - 40, size=14,
               color=DIM, center=True)

    def draw_mp_code(self):
        o = self.renderer.overlay
        o.text("ENTER SESSION CODE", self.W / 2, 200, size=30, color=GREEN,
               center=True)
        for i, ch in enumerate(self.mp_code_entry):
            x = self.W / 2 - 135 + i * 90
            selected = i == self.mp_code_slot
            o.rect(x - 32, 300, 64, 84, (25, 30, 45, 230))
            if selected:
                o.rect(x - 32, 384, 64, 5, GOLD)
                pulse = int(150 + 100 * abs(math.sin(self.renderer.time * 4)))
                color = (255, 235, 140, pulse)
            else:
                color = WHITE
            o.text(ch, x, 310, size=52, color=color, center=True)
        o.text("Up/Down: letter   Left/Right: slot   Enter: join   Esc: back",
               self.W / 2, 440, size=14, color=DIM, center=True)

    def draw_lobby(self):
        o = self.renderer.overlay
        mp = self.mp
        module = self.games.get(mp["game"], self.game)
        mode_label = next((label for m, label in module.INFO.modes
                           if m == mp["mode"]), mp["mode"].upper())
        o.text("SESSION LOBBY", self.W / 2, 80, size=32, color=GREEN,
               center=True)
        o.text(f"{module.INFO.name} — {mode_label}", self.W / 2, 130, size=18,
               color=DIM, center=True)
        o.text(mp["code"], self.W / 2, 175, size=56, color=GOLD, center=True)
        o.text("share this code", self.W / 2, 240, size=13, color=DIM,
               center=True)

        players = mp.get("players", [])
        if not players:
            o.text("waiting for players...", self.W / 2, 330, size=16,
                   color=DIM, center=True)
        for i, p in enumerate(players):
            y = 300 + i * 46
            me = p["name"] == mp["name"]
            color = GOLD if i == 0 and p["score"] is not None else \
                (WHITE if me else DIM)
            o.text(f"{i + 1:2d}", self.W / 2 - 280, y, size=22, color=color)
            o.text(p["name"] + (" (you)" if me else ""), self.W / 2 - 210, y,
                   size=22, color=color)
            score = f"{p['score']:,}" if p["score"] is not None else "playing..."
            o.text(score, self.W / 2 + 120, y, size=22, color=color)
        o.text("Enter: play your run   Esc: leave lobby",
               self.W / 2, self.H - 44, size=15, color=GREEN, center=True)

    def draw_initials(self):
        o = self.renderer.overlay
        _, _, score, _ = self.pending_board
        o.text("HIGH SCORE!", self.W / 2, 180, size=52, color=GOLD, center=True)
        o.text(f"{score:,}", self.W / 2, 260, size=30, color=WHITE, center=True)
        o.text("ENTER YOUR INITIALS", self.W / 2, 340, size=20, color=DIM,
               center=True)
        for i, ch in enumerate(self.initials):
            x = self.W / 2 - 90 + i * 90
            selected = i == self.initials_slot
            o.rect(x - 32, 400, 64, 84, (25, 30, 45, 230))
            if selected:
                o.rect(x - 32, 484, 64, 5, GOLD)
                pulse = int(150 + 100 * abs(math.sin(self.renderer.time * 4)))
                color = (255, 235, 140, pulse)
            else:
                color = WHITE
            o.text(ch, x, 410, size=52, color=color, center=True)
        o.text("Up/Down: letter   Left/Right: slot   Enter: confirm",
               self.W / 2, 540, size=14, color=DIM, center=True)

    def draw_leaderboard(self):
        o = self.renderer.overlay
        modes = self.game.INFO.modes
        mode_id, mode_label = modes[self.board_mode_index % len(modes)]
        o.text(f"{self.game.INFO.name} — HIGH SCORES", self.W / 2, 70, size=32,
               color=GREEN, center=True)
        tab = f"< {mode_label} >" if len(modes) > 1 else mode_label
        o.text(tab, self.W / 2, 122, size=20, color=GOLD, center=True)

        if self.net.available:
            scope_label = "LOCAL" if self.board_scope == "local" else "GLOBAL"
            o.text(f"[{scope_label}]  Up/Down: switch", self.W / 2, 152,
                   size=14, color=CYAN, center=True)

        highlight_rank = self.last_rank if self.board_scope == "local" else None
        if self.board_scope == "local":
            board = [dict(e, rank=i + 1) for i, e in
                     enumerate(lb.entries(self.profile, self.game_id, mode_id))]
        else:
            data = self.global_boards.get((self.game_id, mode_id))
            if data == "pending":
                o.text("FETCHING...", self.W / 2, self.H / 2, size=22,
                       color=DIM, center=True)
                board = []
            elif data == "error" or data is None:
                o.text("OFFLINE — couldn't reach the arcade server",
                       self.W / 2, self.H / 2, size=18, color=RED, center=True)
                board = []
            else:
                board = data

        if self.board_scope == "local" and not board:
            o.text("NO SCORES YET — GO SET ONE", self.W / 2, self.H / 2,
                   size=22, color=DIM, center=True)
        for entry in board:
            rank = entry["rank"]
            y = 190 + (rank - 1) * 48
            highlight = highlight_rank == rank
            color = GOLD if highlight else (WHITE if rank <= 3 else DIM)
            if highlight:
                o.rect(self.W / 2 - 330, y - 6, 660, 40, (45, 40, 20, 180))
            o.text(f"{rank:2d}", self.W / 2 - 300, y, size=24, color=color)
            o.text(entry["name"], self.W / 2 - 220, y, size=24, color=color)
            o.text(f"{entry['score']:,}", self.W / 2 + 40, y, size=24, color=color)
            o.text(entry.get("date", ""), self.W / 2 + 220, y, size=16, color=DIM)
        o.text("Esc: back", self.W / 2, self.H - 30, size=14, color=DIM,
               center=True)
        self.draw_banner_and_toasts()

    def draw_attract_overlay(self):
        o = self.renderer.overlay
        module = self.games[self.attract_gid]
        if self.renderer.camera_override is None:
            hud_w = min(self.W, 1460)
            o.offset_x = (self.W - hud_w) / 2
        else:
            hud_w = self.W
        self.attract_run.draw_hud(o, hud_w, self.H, profile_mod.game_section(
            self.profile, self.attract_gid))
        o.offset_x = 0.0
        if math.sin(self.renderer.time * 3) > -0.2:
            o.text("PRESS ANY KEY", self.W / 2, self.H * 0.62, size=36,
                   color=WHITE, center=True)
        o.text(f"DEMO — {module.INFO.name}", self.W / 2, self.H - 44, size=16,
               color=DIM, center=True)

    def draw_fps(self):
        o = self.renderer.overlay
        o.text(f"{self.clock.get_fps():5.0f} FPS", self.W - 120, self.H - 30,
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
        if self.state == ATTRACT and self.attract_run is not None:
            self.attract_run.draw(self.renderer, profile_mod.game_section(
                self.profile, self.attract_gid))
        elif self.state in (PLAYING, PAUSED, RUN_END, INITIALS) \
                and self.run is not None:
            self.run.draw(self.renderer, self.section)
        elif self.state == MENU:
            aspect = self.renderer.width / self.renderer.height
            if aspect >= 1.25:  # narrow/square screens: menu panel only
                # place the model right of the panel, capped so it never
                # sits far enough off-axis to shear on ultrawides
                half_w = 12.44 * aspect
                fx = 320 + 32 * min(half_w * 0.44, 8.5)
                sprite = self.game.INFO.showcase_sprite
                self.renderer.draw_menu_model(
                    sprite, fx, 360,
                    0.26 if sprite == "boss" else 0.4,
                    spin_speed=0.9)
            else:
                self.renderer.draw_starfield_only()
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
            o = self.renderer.overlay
            # field-camera games get a centered HUD band near the arena
            # (the arena is a constant ~700 UI px wide); first-person games
            # use the full screen so crosshairs stay at true center
            if self.renderer.camera_override is None:
                hud_w = min(self.W, 1460)
                o.offset_x = (self.W - hud_w) / 2
            else:
                hud_w = self.W
            self.run.draw_hud(o, hud_w, self.H, self.section)
            o.offset_x = 0.0
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
        elif self.state == INITIALS:
            self.draw_initials()
        elif self.state == LEADERBOARD:
            self.draw_leaderboard()
        elif self.state == MULTIPLAYER:
            self.draw_multiplayer()
        elif self.state == MP_CODE:
            self.draw_mp_code()
        elif self.state == LOBBY:
            self.draw_lobby()
        elif self.state == ATTRACT:
            self.draw_attract_overlay()
        if self.profile["settings"].get("show_fps"):
            self.draw_fps()

    def run_forever(self):
        self.audio.music("menu")
        showcase_timer = 0.0
        self.attract_run = None
        if self.kiosk:
            self.start_attract()
        while True:
            cap = self.profile["settings"].get("fps_cap", 120)
            dt = min(self.clock.tick(cap) / 1000.0, 0.05)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.quit()
                elif event.type == pygame.KEYDOWN:
                    self.handle_keydown(event.key)
                elif event.type == pygame.JOYBUTTONDOWN:
                    self.handle_pad_button(event.button)
                elif event.type == pygame.JOYDEVICEADDED:
                    stick = pygame.joystick.Joystick(event.device_index)
                    self.joysticks[stick.get_instance_id()] = stick
                elif event.type == pygame.JOYDEVICEREMOVED:
                    self.joysticks.pop(event.instance_id, None)
                elif event.type == MUSIC_END_EVENT:
                    self.audio.on_music_end()
                elif event.type == pygame.VIDEORESIZE:
                    self.renderer.resize(event.w, event.h)

            self.poll_pad_navigation(dt)
            self.poll_network()
            self.outbox_timer -= dt
            if self.outbox_timer <= 0:
                self.outbox_timer = 60.0
                self.outbox.drain()
            if self.state == LOBBY and self.mp is not None:
                self.mp_poll_timer -= dt
                if self.mp_poll_timer <= 0:
                    self.mp_poll_timer = 2.5
                    self.net.get_session(self.mp["code"])
            self.update_timers(dt)
            if self.state == PLAYING:
                self.update_playing(dt)
            elif self.state == ATTRACT:
                self.update_attract(dt)
            elif self.state == MENU:
                self.idle_timer += dt
                if self.idle_timer >= ATTRACT_IDLE_SECONDS:
                    self.start_attract()

            # cursor + mouse grab: FPS games hide the pointer while playing;
            # mouse-look games (Doom) also grab so relative motion keeps
            # coming and the cursor can't wander off the window
            info = self.game.INFO
            playing_fps = self.state == PLAYING and (info.mouse_aim
                                                     or info.mouse_look)
            pygame.mouse.set_visible(not playing_fps)
            pygame.event.set_grab(self.state == PLAYING and info.mouse_look)

            self.renderer.begin(dt if self.state != PAUSED else 0.0)
            self.draw_3d_layer(dt, showcase_timer)
            # composite the 3D scene (CRT and all) first; the overlay then
            # draws post-filter so text stays crisp
            self.renderer.finish(crt=self.profile["settings"].get("crt", True))
            self.draw_overlay_layer()
            pygame.display.flip()


def main():
    App().run_forever()


if __name__ == "__main__":
    main()
