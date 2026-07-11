"""Central loader for the pre-baked images and sound effects."""
import os

import pygame

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGES_DIR = os.path.join(BASE_DIR, "assets", "images")
SFX_DIR = os.path.join(BASE_DIR, "assets", "sfx")

IMAGE_FILES = [
    "player",
    "enemy_squid_a",
    "enemy_squid_b",
    "enemy_crab_a",
    "enemy_crab_b",
    "enemy_octo_a",
    "enemy_octo_b",
    "bullet_player",
    "bullet_enemy",
    "explosion",
    "barrier",
]

SFX_FILES = [
    "shoot",
    "explosion_enemy",
    "explosion_player",
    "step_0",
    "step_1",
    "step_2",
    "step_3",
    "game_over",
    "win",
]


class Assets:
    def __init__(self):
        self.images = {}
        self.sfx = {}

    def load(self):
        for name in IMAGE_FILES:
            path = os.path.join(IMAGES_DIR, f"{name}.png")
            self.images[name] = pygame.image.load(path).convert_alpha()

        if pygame.mixer.get_init() is not None:
            for name in SFX_FILES:
                path = os.path.join(SFX_DIR, f"{name}.wav")
                self.sfx[name] = pygame.mixer.Sound(path)

    def play(self, name):
        sound = self.sfx.get(name)
        if sound is not None:
            sound.play()
