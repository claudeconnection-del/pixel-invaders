"""Voxel Studio — the cabinet's music workstation.

Tweak every property the composer exposes, preview sections live against a
voxel equalizer, arrange baked sections into a sequence, and export it as
the cabinet's custom in-game soundtrack (see Settings -> Game music).
"""
import math
import os
import tempfile

import pygame

from arcade.game_api import GameInfo, GameRun
from game import theme
from game.theme import TEXT, DIM, GOLD, EMBER, PANEL, PANEL_DIM, HAIR
from game.composer import (
    BASS_NAMES, DRUM_NAMES, LEAD_NAMES, PROGRESSION_NAMES,
    SectionSpec, build_section, rms_profile, write_wav,
)
from render.renderer import Batcher
from render.voxel import quat_axis_angle

INFO = GameInfo(
    "studio", "VOXEL STUDIO",
    "Compose the cabinet's soundtrack yourself.",
    showcase_sprite="powerup_rapid",
    modes=[("studio", "STUDIO")],
    has_scores=False,
    attract=False,
    game_music=False,
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
USERMUSIC_DIR = os.path.join(BASE_DIR, "usermusic")
MAX_SLOTS = 8

# Voxel Studio's signature: creative Bloom (accent) + Petal (accent2).
_T = theme.for_game("studio")
ACCENT, ACCENT2 = _T.accent, _T.accent2

DENSITY_LABELS = {0.32: "SPARSE", 0.2: "MID", 0.08: "BUSY"}

PARAM_ROWS = [
    ("Tempo", "tempo", [90, 110, 130, 150, 170, 190]),
    ("Progression", "progression", PROGRESSION_NAMES),
    ("Bass", "bass_style", BASS_NAMES),
    ("Drums", "drum_style", DRUM_NAMES),
    ("Drum fills", "fills", [True, False]),
    ("Lead voice", "lead_voice", LEAD_NAMES),
    ("Shimmer", "shimmer", [False, True]),
    ("Bars", "bars", [4, 8]),
    ("Note density", "rest_density", [0.32, 0.2, 0.08]),
    ("Melody seed", "seed", "int"),
]

EQ_COLUMNS = 14


def value_label(key, value):
    if key == "rest_density":
        return DENSITY_LABELS.get(value, str(value))
    if isinstance(value, bool):
        return "ON" if value else "OFF"
    return str(value).upper()


class StudioRun(GameRun):
    def __init__(self, mode, rng):
        self.mode = mode
        self.rng = rng
        self.spec = SectionSpec(seed=rng.randrange(1000))
        self.row = 0
        self.sequence = []          # list of SectionSpec
        self.events = []
        self.time = 0.0
        self.status = "Space: preview   Enter: add to sequence"

        # playback state
        self.preview_sound = None
        self.channel = None
        self.profile_levels = []    # rms per eighth for the playing audio
        self.play_started = 0.0
        self.playing_spec = None
        self.eq = [0.0] * EQ_COLUMNS
        self.dirty = True           # spec changed since last bake
        self.baked_samples = None
        # sequence playback: worker thread pre-renders sections, channel
        # queueing chains them with no gap
        self.seq_items = None       # list of (Sound, profile, spec) | None
        self.seq_index = 0
        self.queued_index = None

        # profile hooks (attach_profile fills these)
        self.section = None
        self.settings = None
        self.save_cb = lambda: None
        self._tmpdir = tempfile.mkdtemp(prefix="voxelstudio_")

    # -------------------------------------------------------------- cabinet
    @property
    def score(self):
        return 0

    @property
    def run_over(self):
        return False

    def attach_profile(self, section, settings, save_cb):
        self.section = section
        self.settings = settings
        self.save_cb = save_cb
        saved = section.get("sequence", [])
        self.sequence = [SectionSpec.from_dict(d) for d in saved][:MAX_SLOTS]

    def emit(self, etype, **data):
        self.events.append((etype, data))

    def drain_events(self):
        out = self.events
        self.events = []
        return out

    def run_stats(self):
        return {"slots": len(self.sequence)}

    def run_summary(self):
        return {"win": False, "score": 0}

    def on_event(self, etype, data, renderer, audio, banner):
        if etype == "studio_bake":
            audio.play("menu_select")
        elif etype == "studio_slot_added":
            banner(f"SLOT {data['count']}/{MAX_SLOTS} SAVED", 1.6)
            audio.play("powerup")
        elif etype == "studio_export":
            banner(f"SOUNDTRACK EXPORTED ({data['count']} SECTIONS)", 2.5)
            audio.play("toast")
            renderer.add_aberration(0.5)

    # ------------------------------------------------------------- playback
    def _stop_playback(self):
        if self.channel is not None:
            self.channel.stop()
        self.channel = None
        self.playing_spec = None
        self.seq_items = None
        self.queued_index = None

    def _bake(self):
        if self.dirty or self.baked_samples is None:
            self.baked_samples = build_section(self.spec)
            self.dirty = False
            self.emit("studio_bake")
        return self.baked_samples

    def _make_sound(self, spec, tag, samples=None):
        """Render a spec to a mixer Sound (+ its EQ profile)."""
        samples = samples if samples is not None else build_section(spec)
        path = os.path.join(self._tmpdir, f"{tag}.wav")
        write_wav(path, samples)
        try:
            sound = pygame.mixer.Sound(path)
            sound.set_volume(0.55)
        except pygame.error:
            sound = None
        return sound, rms_profile(samples, spec)

    def toggle_preview(self):
        if self.playing_spec is not None:
            self._stop_playback()
            self.status = "Stopped"
            return
        self.status = "Baking..."
        sound, profile = self._make_sound(self.spec, "preview",
                                          samples=self._bake())
        self.preview_sound = sound
        self.profile_levels = profile
        # seamless: the mixer loops the buffer itself, no restart gap
        self.channel = sound.play(loops=-1) if sound else None
        self.playing_spec = self.spec
        self.play_started = self.time
        self.status = "Previewing (loops) — Space: stop"

    def play_sequence(self):
        if not self.sequence:
            self.status = "Sequence is empty — Enter adds the current section"
            return
        self._stop_playback()
        specs = list(self.sequence)
        self.seq_items = [None] * len(specs)
        sound, profile = self._make_sound(specs[0], "seq_0")
        self.seq_items[0] = (sound, profile, specs[0])
        self.seq_index = 0
        self.queued_index = None
        self.profile_levels = profile
        self.playing_spec = specs[0]
        self.play_started = self.time
        self.channel = sound.play() if sound else None

        def prerender():  # remaining sections bake while the first plays
            for i, spec in enumerate(specs[1:], start=1):
                s, p = self._make_sound(spec, f"seq_{i}")
                self.seq_items[i] = (s, p, spec)

        import threading
        threading.Thread(target=prerender, daemon=True).start()
        self.status = f"Playing sequence ({len(specs)} sections)"

    # -------------------------------------------------------------- actions
    def add_slot(self):
        if len(self.sequence) >= MAX_SLOTS:
            self.status = f"Sequence full ({MAX_SLOTS} slots) — X removes last"
            return
        self.sequence.append(SectionSpec.from_dict(self.spec.to_dict()))
        self._persist_sequence()
        self.emit("studio_slot_added", count=len(self.sequence))

    def remove_slot(self):
        if self.sequence:
            self.sequence.pop()
            self._persist_sequence()
            self.status = f"Removed slot {len(self.sequence) + 1}"

    def _persist_sequence(self):
        if self.section is not None:
            self.section["sequence"] = [s.to_dict() for s in self.sequence]
            self.save_cb()

    def export(self):
        if not self.sequence:
            self.status = "Nothing to export — add sections with Enter"
            return
        os.makedirs(USERMUSIC_DIR, exist_ok=True)
        for old in os.listdir(USERMUSIC_DIR):
            if old.startswith("custom_") and old.endswith(".wav"):
                os.remove(os.path.join(USERMUSIC_DIR, old))
        for i, spec in enumerate(self.sequence):
            write_wav(os.path.join(USERMUSIC_DIR, f"custom_{i:02d}.wav"),
                      build_section(spec))
        if self.settings is not None:
            self.settings["game_music"] = "custom"
            self.save_cb()
        self.emit("studio_export", count=len(self.sequence))
        self.status = "Exported! Game music setting switched to CUSTOM"

    # ---------------------------------------------------------------- input
    def handle_key(self, key):
        if key in (pygame.K_UP, pygame.K_w):
            self.row = (self.row - 1) % len(PARAM_ROWS)
        elif key in (pygame.K_DOWN, pygame.K_s):
            self.row = (self.row + 1) % len(PARAM_ROWS)
        elif key in (pygame.K_LEFT, pygame.K_a, pygame.K_RIGHT, pygame.K_d):
            self._adjust(1 if key in (pygame.K_RIGHT, pygame.K_d) else -1)
        elif key == pygame.K_SPACE:
            self.toggle_preview()
        elif key == pygame.K_RETURN:
            self.add_slot()
        elif key == pygame.K_x:
            self.remove_slot()
        elif key == pygame.K_p:
            self.play_sequence()
        elif key == pygame.K_e:
            self.export()
        elif key == pygame.K_r:
            self.spec.seed = self.rng.randrange(1000)
            self.dirty = True
            if self.playing_spec is not None:
                self.toggle_preview()  # stop; next Space previews new seed
        else:
            return False
        return True

    def _adjust(self, direction):
        label, key, choices = PARAM_ROWS[self.row]
        if choices == "int":
            self.spec.seed = (self.spec.seed + direction) % 1000
        else:
            current = getattr(self.spec, key)
            try:
                i = choices.index(current)
            except ValueError:
                i = 0
            setattr(self.spec, key, choices[(i + direction) % len(choices)])
        self.dirty = True

    # --------------------------------------------------------------- update
    def _update_sequence_playback(self):
        """Advance the pre-rendered chain; keep the next section queued on
        the channel so transitions are gapless."""
        if self.seq_items is None or self.channel is None:
            return
        current = self.channel.get_sound()
        item = self.seq_items[self.seq_index]
        if current is not None and item is not None and current is not item[0]:
            # the queued sound took over: sync index + EQ profile
            for i, entry in enumerate(self.seq_items):
                if entry is not None and entry[0] is current:
                    self.seq_index = i
                    self.profile_levels = entry[1]
                    self.playing_spec = entry[2]
                    self.play_started = self.time
                    break
        nxt = self.seq_index + 1
        if nxt < len(self.seq_items) and self.queued_index != nxt:
            entry = self.seq_items[nxt]  # may still be baking on the thread
            if entry is not None and entry[0] is not None:
                self.channel.queue(entry[0])
                self.queued_index = nxt
        if not self.channel.get_busy():
            self._stop_playback()
            self.status = "Sequence finished"

    def update(self, dt, inp):
        self.time += dt

        if self.seq_items is not None:
            self._update_sequence_playback()
        elif self.playing_spec is not None and self.channel is not None \
                and not self.channel.get_busy():
            self.playing_spec = None  # preview stopped externally

        # drive the EQ from the precomputed rms profile
        if self.playing_spec is not None and self.profile_levels:
            eighth = 60 / self.playing_spec.tempo / 2
            elapsed = self.time - self.play_started
            if self.seq_items is None:  # looping preview wraps around
                elapsed %= max(self.playing_spec.duration, 1e-6)
            bucket = int(elapsed / eighth)
            if bucket < len(self.profile_levels):
                self.eq.append(self.profile_levels[bucket])
                self.eq = self.eq[-EQ_COLUMNS:]
        else:
            self.eq = [max(0.0, v - dt * 1.6) for v in self.eq]

    # --------------------------------------------------------------- visual
    def draw(self, renderer, section):
        b = Batcher()
        t = self.time
        # voxel equalizer across the lower field (curve adds contrast,
        # since per-eighth RMS is fairly uniform when drums run hot)
        for i, level in enumerate(self.eq):
            fx = 90 + i * (460 / (EQ_COLUMNS - 1))
            stack = int((level ** 2.2) * 9)
            for row in range(stack + 1):
                fy = 640 - row * 26
                heat = row / 9
                # bloom pink at the base rising into hot ember at the peak
                tint = (0.9 + heat * 1.2, 0.42 + heat * 0.62, 0.72 - heat * 0.34,
                        1.0)
                b.add("cube", fx, fy, 0.34, tint=tint)
        # beat-pulsing centerpiece while playing
        if self.playing_spec is not None:
            eighth = 60 / self.playing_spec.tempo / 2
            beat = ((self.time - self.play_started) / (eighth * 2)) % 1.0
            pulse = 0.5 + 0.35 * max(0.0, 1.0 - beat * 3)
            spin = quat_axis_angle(0.3, 1, 0.2, t * 1.2)
            b.add("powerup_rapid", 320, 200, pulse, quat=spin,
                  tint=(1.8, 1.6, 0.8, 1.0))
        renderer.draw_scene(b, walls=False)

    def draw_hud(self, o, width, height, section):
        o.text("VOXEL STUDIO", width / 2, 26, size=30, color=ACCENT, center=True)

        panel_x = width - 480
        for i, (label, key, choices) in enumerate(PARAM_ROWS):
            y = 90 + i * 44
            selected = i == self.row
            color = TEXT if selected else DIM
            prefix = "> " if selected else "  "
            o.text(prefix + label, panel_x, y, size=19, color=color)
            value = value_label(key, getattr(self.spec, key))
            o.text(f"< {value} >" if selected else value,
                   panel_x + 250, y, size=19, color=GOLD if selected else DIM)

        # sequence strip
        o.text("SEQUENCE", 60, height - 190, size=16, color=ACCENT)
        for i in range(MAX_SLOTS):
            x = 60 + i * 64
            filled = i < len(self.sequence)
            o.rect(x, height - 165, 54, 40, PANEL if filled else PANEL_DIM)
            o.rect(x, height - 165, 54, 3, GOLD if filled else HAIR)
            if filled:
                o.text(f"{self.sequence[i].tempo}", x + 27, height - 156,
                       size=13, color=TEXT, center=True)
                o.text(self.sequence[i].bass_style[:4].upper(), x + 27,
                       height - 140, size=10, color=ACCENT2, center=True)

        o.text(self.status, width / 2, height - 96, size=15, color=EMBER,
               center=True)
        o.text("Space: preview  R: reroll seed  Enter: add  X: remove  "
               "P: play sequence  E: export as game music",
               width / 2, height - 66, size=13, color=DIM, center=True)
        o.text("Esc: pause/exit", width / 2, height - 44, size=13, color=DIM,
               center=True)


def create_run(mode, rng):
    return StudioRun(mode, rng)
