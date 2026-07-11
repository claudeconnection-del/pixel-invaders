"""Bakes sprite PNGs (and a contact sheet) from the pixel grids in game/sprites.py.

Run with: python tools/gen_art.py
The grids themselves are the runtime source of truth for the voxel renderer;
the PNGs baked here are for docs and 2D previews.
"""
import os
import sys

import pygame

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from game.sprites import ALL_SPRITES, PALETTE  # noqa: E402

SCALE = 8
BASE_DIR = os.path.join(os.path.dirname(__file__), "..")
OUT_DIR = os.path.join(BASE_DIR, "assets", "images")
SHEET_PATH = os.path.join(BASE_DIR, "docs", "sprites.png")


def validate(name, grid):
    widths = {len(row) for row in grid}
    assert len(widths) == 1, f"{name}: inconsistent row lengths {widths}"
    for row in grid:
        for ch in row:
            assert ch in PALETTE, f"{name}: unknown palette char {ch!r}"


def build_surface(grid):
    w, h = len(grid[0]), len(grid)
    surf = pygame.Surface((w * SCALE, h * SCALE), pygame.SRCALPHA)
    for y, row in enumerate(grid):
        for x, ch in enumerate(row):
            color = PALETTE[ch]
            if color[3] == 0:
                continue
            surf.fill(color, (x * SCALE, y * SCALE, SCALE, SCALE))
    return surf


def bake_contact_sheet(surfaces):
    cols = 6
    cell = 20 * SCALE  # fits the 16-wide boss with margin
    rows = (len(surfaces) + cols - 1) // cols
    sheet = pygame.Surface((cols * cell, rows * (cell + 24)), pygame.SRCALPHA)
    sheet.fill((10, 10, 18, 255))
    font = pygame.font.SysFont("couriernew", 14, bold=True)
    for i, (name, surf) in enumerate(surfaces.items()):
        cx = (i % cols) * cell
        cy = (i // cols) * (cell + 24)
        sheet.blit(
            surf,
            (cx + (cell - surf.get_width()) // 2, cy + (cell - surf.get_height()) // 2),
        )
        label = font.render(name, True, (140, 255, 170))
        sheet.blit(label, (cx + (cell - label.get_width()) // 2, cy + cell))
    pygame.image.save(sheet, SHEET_PATH)
    print(f"wrote {SHEET_PATH}")


def main():
    pygame.init()
    pygame.display.set_mode((1, 1), pygame.HIDDEN)
    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(SHEET_PATH), exist_ok=True)

    surfaces = {}
    for name, grid in ALL_SPRITES.items():
        validate(name, grid)
        surf = build_surface(grid)
        surfaces[name] = surf
        path = os.path.join(OUT_DIR, f"{name}.png")
        pygame.image.save(surf, path)
        print(f"wrote {path} ({surf.get_width()}x{surf.get_height()})")

    bake_contact_sheet(surfaces)
    pygame.quit()


if __name__ == "__main__":
    main()
