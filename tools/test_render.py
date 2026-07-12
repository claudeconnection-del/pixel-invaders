"""Offscreen render test: simulate a battle, draw frames, save screenshots.

Run with: python tools/test_render.py
Creates a hidden GL window, drives Voxel Hell with the test bot through the
cabinet game API, renders, and writes PNGs to tools/_render_*.png.
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
from games.voxelhell.game import create_run  # noqa: E402
from tools.test_world import dodge_bot_input, DT  # noqa: E402

W, H = 1280, 860
SECTION = {"selected_skin": "vanguard",
           "lifetime": {"best_score": 0}}


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
    run = create_run("campaign", random.Random(1234))
    run.world.player.lives = 99

    def banner(text, seconds):
        pass

    here = os.path.dirname(__file__)
    checkpoints = {"wave1": False, "boss": False}
    frame = 0
    wave_seen = -1
    world = run.world
    while frame < 60 * 60 * 12:
        bot = dodge_bot_input(world)
        run.update(DT, bot)
        for etype, data in run.drain_events():
            if etype == ev.WAVE_START:
                wave_seen = data["index"]
            run.on_event(etype, data, renderer, _NullAudio(), banner)

        run.show_hitbox = True
        renderer.begin(DT)
        run.draw(renderer, SECTION)
        renderer.begin_overlay()
        run.draw_hud(renderer.overlay, W, H, SECTION)
        renderer.finish(crt=True)
        pygame.display.flip()

        if not checkpoints["wave1"] and wave_seen == 0 and world.time > 8:
            screenshot(os.path.join(here, "_render_wave1.png"))
            checkpoints["wave1"] = True
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


class _NullAudio:
    def play(self, name):
        pass


if __name__ == "__main__":
    main()
