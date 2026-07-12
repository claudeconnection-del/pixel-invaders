"""Audio: sfx bank + a shuffling music sequencer.

Music is a bank of short composed sections per pool (menu_XX / game_XX /
boss_XX under assets/music). The sequencer chains sections gaplessly via
pygame's music queue, shuffling with a no-recent-repeat rule so the
soundtrack keeps evolving instead of looping one file.

The main loop must forward pygame events of type MUSIC_END_EVENT to
AudioBank.on_music_end() so the next section gets queued.
"""
import glob
import os
import random

import pygame

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SFX_DIR = os.path.join(BASE_DIR, "assets", "sfx")
MUSIC_DIR = os.path.join(BASE_DIR, "assets", "music")

MUSIC_END_EVENT = pygame.USEREVENT + 7

# name -> volume
SFX = {
    "shoot": 0.16,
    "explosion_enemy": 0.42,
    "explosion_player": 0.6,
    "explosion_big": 0.75,
    "graze": 0.25,
    "powerup": 0.5,
    "shield_break": 0.55,
    "boss_roar": 0.7,
    "phase_sting": 0.6,
    "toast": 0.55,
    "menu_move": 0.35,
    "menu_select": 0.45,
    "game_over": 0.6,
    "win": 0.6,
    "step_0": 0.4,
    "step_1": 0.4,
    "step_2": 0.4,
    "step_3": 0.4,
}


class AudioBank:
    def __init__(self):
        self.sfx = {}
        self.enabled = pygame.mixer.get_init() is not None
        self.music_on = True
        self.sfx_vol = 1.0
        self.music_vol = 0.45
        self.current_pool = None
        self.recent = []          # last section paths, to avoid quick repeats
        self.rng = random.Random()

        # discover section pools by filename prefix: <pool>_<nn>.wav
        self.pools = {}
        for path in sorted(glob.glob(os.path.join(MUSIC_DIR, "*.wav"))):
            pool = os.path.basename(path).rsplit("_", 1)[0]
            self.pools.setdefault(pool, []).append(path)

        if self.enabled:
            pygame.mixer.set_num_channels(24)
            pygame.mixer.music.set_endevent(MUSIC_END_EVENT)
            for name, volume in SFX.items():
                path = os.path.join(SFX_DIR, f"{name}.wav")
                try:
                    sound = pygame.mixer.Sound(path)
                    sound.set_volume(volume)
                    self.sfx[name] = sound
                except (pygame.error, FileNotFoundError):
                    pass

    def play(self, name):
        sound = self.sfx.get(name)
        if sound is not None:
            sound.play()

    def set_volumes(self, sfx_vol, music_vol):
        self.sfx_vol = sfx_vol
        self.music_vol = music_vol
        for name, sound in self.sfx.items():
            sound.set_volume(SFX[name] * sfx_vol)
        if self.enabled:
            pygame.mixer.music.set_volume(music_vol)

    def set_music_enabled(self, on):
        self.music_on = on
        if not self.enabled:
            return
        if on and self.current_pool:
            pool = self.current_pool
            self.current_pool = None
            self.music(pool)
        elif not on:
            pygame.mixer.music.stop()

    # ---------------------------------------------------------- sequencer
    def _pick(self, pool):
        """A section from the pool, avoiding the most recent picks."""
        sections = self.pools.get(pool, [])
        if not sections:
            return None
        avoid = set(self.recent[-max(1, len(sections) // 2):])
        candidates = [s for s in sections if s not in avoid] or sections
        choice = self.rng.choice(candidates)
        self.recent.append(choice)
        self.recent = self.recent[-4:]
        return choice

    def music(self, pool):
        """Switch the active music pool ('menu' | 'game' | 'boss' | None)."""
        if pool == self.current_pool:
            return
        self.current_pool = pool
        if not self.enabled:
            return
        pygame.mixer.music.stop()
        if pool is None or not self.music_on:
            return
        first = self._pick(pool)
        if first is None:
            return
        try:
            pygame.mixer.music.load(first)
            pygame.mixer.music.set_volume(self.music_vol)
            pygame.mixer.music.play()
            nxt = self._pick(pool)
            if nxt:
                pygame.mixer.music.queue(nxt)
        except (pygame.error, FileNotFoundError):
            pass

    def on_music_end(self):
        """A section finished (the queued one is now playing): queue the
        next so playback never gaps."""
        if not self.enabled or not self.music_on or self.current_pool is None:
            return
        nxt = self._pick(self.current_pool)
        if nxt:
            try:
                pygame.mixer.music.queue(nxt)
            except (pygame.error, FileNotFoundError):
                pass
