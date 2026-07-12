"""The cabinet's contract with its games.

Each game lives in games/<id>/ and exposes:
    INFO           - GameInfo metadata
    create_run(mode, rng) -> a run object matching GameRun's interface
    ACHIEVEMENTS   - list of meta.achievements.Achievement
    skin_for_achievement(aid) -> skin id or None   (optional, games w/ skins)

The cabinet owns: menus, settings, profile/stats/achievements persistence,
leaderboards, attract mode, and the render/audio engines. A game owns: its
simulation, its instance batches, its HUD, and its event->effect mapping.
"""


class GameInfo:
    def __init__(self, gid, name, tagline, showcase_sprite, modes,
                 has_skins=False, has_scores=True, attract=True,
                 game_music=True, hud_score_label="SCORE"):
        self.id = gid
        self.name = name
        self.tagline = tagline
        self.showcase_sprite = showcase_sprite
        self.modes = modes  # list of (mode_id, label)
        self.has_skins = has_skins
        self.has_scores = has_scores  # shows SCORES menu / initials entry
        self.attract = attract        # eligible for attract-mode demos
        self.game_music = game_music  # cabinet plays the game pool while running
        self.mouse_aim = False        # FPS-style: hide cursor, aim with mouse
        self.hud_score_label = hud_score_label


class GameRun:
    """Interface every game run implements (duck-typed; subclassing optional).

    Attributes: score (int), run_over (bool)
    """

    def update(self, dt, inp):
        raise NotImplementedError

    def drain_events(self):
        """Frame's (etype, data) tuples using the shared game.events
        vocabulary — stats/achievements/leaderboards consume these."""
        raise NotImplementedError

    def run_stats(self):
        """Live per-run counters dict for achievement progress."""
        raise NotImplementedError

    def run_summary(self):
        """Rows for the run-end screen: {win, score, ...}."""
        raise NotImplementedError

    def draw(self, renderer, profile_section):
        """Build and submit instance batches for the current frame."""
        raise NotImplementedError

    def draw_hud(self, overlay, width, height, profile_section):
        raise NotImplementedError

    def on_event(self, etype, data, renderer, audio, banner):
        """Game-specific effects for one event (particles/sfx/shake).
        banner(text, seconds) posts a center-screen announcement."""

    # ------------------------------------------------------ optional hooks
    # attach_profile(section, settings, save_cb): called right after
    #     create_run when defined — gives tool-like modules (e.g. the music
    #     studio) their profile section, the cabinet settings dict, and a
    #     callback that persists the profile.
    # handle_key(key) -> bool: raw keydowns forwarded while PLAYING (before
    #     the cabinet's own handling, except Esc). Return True if consumed.
    # per_frame_particles(renderer, rng): ambient per-frame effects.
