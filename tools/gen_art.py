"""Bakes all sprite PNGs from small pixel-grid definitions using pygame surfaces.

Run with: python tools/gen_art.py
Regenerates everything under assets/images/. Committed output is checked into
git so the game runs without needing this script at runtime.
"""
import os

import pygame

SCALE = 8  # each "pixel" in the grid becomes an 8x8 block on screen
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "images")

# Retro-ish limited palette
TRANSPARENT = (0, 0, 0, 0)
GREEN = (80, 220, 120, 255)
BRIGHT_GREEN = (140, 255, 170, 255)
MAGENTA = (230, 80, 200, 255)
BRIGHT_MAGENTA = (255, 150, 230, 255)
CYAN = (80, 200, 230, 255)
BRIGHT_CYAN = (160, 240, 255, 255)
WHITE = (240, 240, 240, 255)
YELLOW = (250, 220, 90, 255)
ORANGE = (250, 150, 60, 255)
RED = (230, 60, 60, 255)
GREY = (120, 120, 130, 255)

PALETTES = {
    "G": GREEN,
    "g": BRIGHT_GREEN,
    "M": MAGENTA,
    "m": BRIGHT_MAGENTA,
    "C": CYAN,
    "c": BRIGHT_CYAN,
    "W": WHITE,
    "Y": YELLOW,
    "O": ORANGE,
    "R": RED,
    "#": GREY,
    ".": TRANSPARENT,
}

PLAYER = [
    "...W....",
    "..WWW...",
    "..WWW...",
    ".WWWWW..",
    "WWWWWWW.",
    "WWWWWWW.",
    "W.W.W.W.",
    "W.....W.",
]

# Two animation frames per enemy type (classic alternating-legs look)
ENEMY_SQUID_A = [
    "..C....C",
    "...CCCC.",
    "..CcccC.",
    ".CCcccCC",
    "CCCCCCCC",
    "..C..C..",
    ".C.CC.C.",
    "C.C..C.C",
]
ENEMY_SQUID_B = [
    "..C....C",
    "...CCCC.",
    "..CcccC.",
    ".CCcccCC",
    "CCCCCCCC",
    ".C.CC.C.",
    "C.C..C.C",
    "..C..C..",
]

ENEMY_CRAB_A = [
    ".M.....M",
    "..M...M.",
    ".MMMMMMM",
    "MMmMMmMM",
    "MMMMMMMM",
    "..M.M.M.",
    ".M.M.M.M",
    "M.M...M.",
]
ENEMY_CRAB_B = [
    ".M.....M",
    "M.M...M.",
    "MMMMMMMM",
    "MMmMMmMM",
    ".MMMMMMM",
    "..M.M.M.",
    ".M.M.M.M",
    "..M...M.",
]

ENEMY_OCTO_A = [
    "..GGGG..",
    ".GGGGGG.",
    "GGgGGgGG",
    "GGGGGGGG",
    ".GGGGGG.",
    "..G..G..",
    ".G.GG.G.",
    "G.G..G.G",
]
ENEMY_OCTO_B = [
    "..GGGG..",
    ".GGGGGG.",
    "GGgGGgGG",
    "GGGGGGGG",
    ".GGGGGG.",
    "..GGGG..",
    ".G.GG.G.",
    "..G..G..",
]

BULLET_PLAYER = [
    "W",
    "W",
    "W",
    "W",
]

BULLET_ENEMY = [
    ".Y.",
    "Y.Y",
    ".Y.",
    "Y.Y",
]

EXPLOSION = [
    "O.....O.",
    ".O...O..",
    "..OYO...",
    ".OYYYO..",
    "..OYO...",
    ".O...O..",
    "O.....O.",
    "........",
]

BARRIER = [
    ".GGGGGG.",
    "GGGGGGGG",
    "GGGGGGGG",
    "GGGGGGGG",
    "GG....GG",
    "GG....GG",
    "G......G",
    "G......G",
]


def build_surface(grid):
    w = len(grid[0])
    h = len(grid)
    surf = pygame.Surface((w * SCALE, h * SCALE), pygame.SRCALPHA)
    for y, row in enumerate(grid):
        for x, ch in enumerate(row):
            color = PALETTES[ch]
            if color[3] == 0:
                continue
            surf.fill(color, (x * SCALE, y * SCALE, SCALE, SCALE))
    return surf


def main():
    pygame.init()
    pygame.display.set_mode((1, 1), pygame.HIDDEN)
    os.makedirs(OUT_DIR, exist_ok=True)

    sprites = {
        "player.png": PLAYER,
        "enemy_squid_a.png": ENEMY_SQUID_A,
        "enemy_squid_b.png": ENEMY_SQUID_B,
        "enemy_crab_a.png": ENEMY_CRAB_A,
        "enemy_crab_b.png": ENEMY_CRAB_B,
        "enemy_octo_a.png": ENEMY_OCTO_A,
        "enemy_octo_b.png": ENEMY_OCTO_B,
        "bullet_player.png": BULLET_PLAYER,
        "bullet_enemy.png": BULLET_ENEMY,
        "explosion.png": EXPLOSION,
        "barrier.png": BARRIER,
    }

    for filename, grid in sprites.items():
        surf = build_surface(grid)
        path = os.path.join(OUT_DIR, filename)
        pygame.image.save(surf, path)
        print(f"wrote {path} ({surf.get_width()}x{surf.get_height()})")

    pygame.quit()


if __name__ == "__main__":
    main()
