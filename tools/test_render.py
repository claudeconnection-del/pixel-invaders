"""Offscreen render test: simulate a battle, draw frames, save screenshots.

Run with: python tools/test_render.py
Creates a hidden GL window, drives the world with the test bot, renders,
and writes PNGs to tools/_render_*.png for visual inspection.
"""
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pygame  # noqa: E402
from OpenGL.GL import (  # noqa: E402
    GL_RGBA, GL_UNSIGNED_BYTE, glReadPixels,
)

from game import events as ev  # noqa: E402
from game.world import World  # noqa: E402
from tools.test_world import dodge_bot_input, DT  # noqa: E402

W, H = 1280, 860


def screenshot(path):
    data = glReadPixels(0, 0, W, H, GL_RGBA, GL_UNSIGNED_BYTE)
    surf = pygame.image.frombytes(data, (W, H), "RGBA", True)
    pygame.image.save(surf, path)
    print("saved", path)


def main():
    pygame.init()
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 3)
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 3)
    pygame.display.gl_set_attribute(
        pygame.GL_CONTEXT_PROFILE_MASK, pygame.GL_CONTEXT_PROFILE_CORE)
    pygame.display.set_mode((W, H), pygame.OPENGL | pygame.DOUBLEBUF | pygame.HIDDEN)

    from render.renderer import Renderer  # GL context must exist first

    renderer = Renderer(W, H, rng=random.Random(7))
    world = World(rng=random.Random(1234))
    world.player.lives = 99

    here = os.path.dirname(__file__)
    # frame 1: early wave 1; frame 2: deep in a later wave; frame 3: boss
    checkpoints = {"wave1": False, "wave4": False, "boss": False}
    frame = 0
    wave_seen = -1
    while frame < 60 * 60 * 12 and not world.run_over:
        world.update(DT, dodge_bot_input(world))
        for etype, data in world.drain_events():
            if etype == ev.WAVE_START:
                wave_seen = data["index"]
            elif etype == ev.ENEMY_KILLED:
                renderer.explosion(data["kind"], data["x"], data["y"])
                renderer.add_shake(0.04)
            elif etype == ev.GRAZE:
                renderer.particles.spark(data["x"], data["y"])
            elif etype == ev.BOSS_PHASE:
                renderer.add_shake(0.3)
                renderer.add_aberration(0.7)

        renderer.show_hitbox = True
        renderer.begin(DT)
        renderer.draw_world(world, "vanguard")
        renderer.begin_overlay()
        renderer.overlay.text("SCORE 012345", 24, 16, size=20, color=(140, 255, 170))
        renderer.overlay.text(f"x{world.multiplier:.1f}", 24, 44, size=20,
                              color=(250, 220, 90))
        renderer.overlay.rect(W / 2 - 200, 20, 400, 14, (40, 40, 60, 220))
        if world.boss:
            renderer.overlay.rect(W / 2 - 198, 22, 396 * world.boss.hp_frac, 10,
                                  (230, 60, 60, 255))
        renderer.finish(crt=True)
        pygame.display.flip()

        if not checkpoints["wave1"] and wave_seen == 0 and world.time > 8:
            screenshot(os.path.join(here, "_render_wave1.png"))
            checkpoints["wave1"] = True
        elif not checkpoints["wave4"] and wave_seen == 3 and len(world.enemy_bullets) > 40:
            screenshot(os.path.join(here, "_render_wave4.png"))
            checkpoints["wave4"] = True
        elif not checkpoints["boss"] and world.boss is not None and world.boss.alive \
                and world.boss.phase >= 2 and len(world.enemy_bullets) > 60:
            screenshot(os.path.join(here, "_render_boss.png"))
            checkpoints["boss"] = True
            break
        frame += 1

    pygame.quit()
    missing = [k for k, v in checkpoints.items() if not v]
    if missing:
        print("WARNING: missed checkpoints:", missing)
    print("render test done at frame", frame)


if __name__ == "__main__":
    main()
