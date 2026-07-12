"""Audio loading and playback. (All visuals are built from game/sprites.py
grids at runtime; the PNGs under assets/images are docs-only.)"""
import os

import pygame

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SFX_DIR = os.path.join(BASE_DIR, "assets", "sfx")
MUSIC_DIR = os.path.join(BASE_DIR, "assets", "music")

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

MUSIC = {
    "menu": os.path.join(MUSIC_DIR, "menu_loop.wav"),
    "game": os.path.join(MUSIC_DIR, "game_loop.wav"),
}


class AudioBank:
    def __init__(self):
        self.sfx = {}
        self.enabled = pygame.mixer.get_init() is not None
        self.music_on = True
        self.current_track = None
        self.sfx_vol = 1.0
        self.music_vol = 0.45
        if self.enabled:
            pygame.mixer.set_num_channels(24)
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
        if on and self.current_track:
            track = self.current_track
            self.current_track = None
            self.music(track)
        elif not on:
            pygame.mixer.music.stop()

    def music(self, track):
        """Switch the looping background track ('menu' | 'game' | None)."""
        if track == self.current_track:
            return
        self.current_track = track
        if not self.enabled or not self.music_on:
            return
        pygame.mixer.music.stop()
        if track is not None:
            try:
                pygame.mixer.music.load(MUSIC[track])
                pygame.mixer.music.set_volume(self.music_vol)
                pygame.mixer.music.play(-1)
            except (pygame.error, FileNotFoundError):
                pass
