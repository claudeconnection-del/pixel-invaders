"""Client-side replay -> GIF/MP4 export. Re-simulates a recorded run and
renders it offscreen, so nothing is captured live and the server never
renders (the home box has no GPU). GIF needs only Pillow; MP4 needs the
optional imageio-ffmpeg (a bundled static ffmpeg) and falls back to GIF.

Runs in its own process/GL context (the cabinet spawns it as a subprocess),
so it never clobbers the live game's renderer.
"""
import os
import random

import numpy as np

# offscreen render size — matches the cabinet's ~1.49 aspect, even dims so
# H.264 (yuv420p) accepts it
EXPORT_W, EXPORT_H = 960, 644
DEFAULT_FPS = 20
MAX_SECONDS = 24.0                  # default: the run's last N seconds
GIF_MAX_W = 480                     # GIFs get downscaled for size


class _NullAudio:
    def play(self, name):
        pass

    def music(self, *a):
        pass


def mp4_available():
    try:
        import imageio_ffmpeg  # noqa: F401
        return True
    except Exception:
        return False


def _grab_rgb(width, height):
    from OpenGL.GL import glReadPixels, GL_RGB, GL_UNSIGNED_BYTE
    data = glReadPixels(0, 0, width, height, GL_RGB, GL_UNSIGNED_BYTE)
    arr = np.frombuffer(data, dtype=np.uint8).reshape(height, width, 3)
    return arr[::-1]  # GL origin is bottom-left; flip to top-left


def render_frames(replay, fps=DEFAULT_FPS, max_seconds=MAX_SECONDS, full=False,
                  crt=True):
    """Re-sim the replay and yield rendered RGB frames (numpy HxWx3) at `fps`.
    A GL context must be current. Captures only the last `max_seconds`
    (unless full) but always simulates from the start for determinism."""
    import importlib
    import pygame
    from render.renderer import Renderer
    from meta import profile as profile_mod

    module = importlib.import_module(f"games.{replay.game}")
    run = module.create_run(replay.mode, random.Random(replay.seed))
    if hasattr(run, "attach_profile"):
        # tools don't record, but be safe: give a throwaway section
        run.attach_profile({}, {}, lambda: None)

    profile = profile_mod.load()
    section = profile_mod.game_section(profile, replay.game)

    renderer = Renderer(EXPORT_W, EXPORT_H, rng=random.Random(replay.seed))
    audio = _NullAudio()
    banner = {"text": None, "timer": 0.0}

    def post_banner(text, seconds):
        banner["text"], banner["timer"] = text, seconds

    total = replay.duration
    start = 0.0 if full else max(0.0, total - max_seconds)
    video_dt = 1.0 / fps
    sim_time = 0.0
    next_emit = start
    pending = []

    frames = replay.frames()
    for dt, inp in frames:
        run.update(dt, inp)
        pending.extend(run.drain_events())
        sim_time += dt
        while sim_time >= next_emit:
            if next_emit >= start:
                renderer.begin(video_dt)
                for etype, data in pending:
                    run.on_event(etype, data, renderer, audio, post_banner)
                if hasattr(run, "per_frame_particles"):
                    run.per_frame_particles(renderer, random)
                run.draw(renderer, section)
                renderer.finish(crt=crt)
                renderer.begin_overlay()
                hud_w = EXPORT_W if renderer.camera_override else min(EXPORT_W, 1460)
                run.draw_hud(renderer.overlay, hud_w, EXPORT_H, section)
                if banner["timer"] > 0:
                    banner["timer"] -= video_dt
                    from game.theme import EMBER
                    renderer.overlay.text(banner["text"], EXPORT_W / 2,
                                          EXPORT_H * 0.36, size=26,
                                          color=EMBER, center=True)
                pending = []
                yield _grab_rgb(EXPORT_W, EXPORT_H)
            next_emit += video_dt
        if run.run_over:
            break


def _hidden_gl():
    import pygame
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 3)
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 3)
    pygame.display.gl_set_attribute(
        pygame.GL_CONTEXT_PROFILE_MASK, pygame.GL_CONTEXT_PROFILE_CORE)
    pygame.display.set_mode((EXPORT_W, EXPORT_H),
                            pygame.OPENGL | pygame.DOUBLEBUF | pygame.HIDDEN)


def export(replay, out_path, fmt="gif", fps=DEFAULT_FPS, full=False, crt=True):
    """Render `replay` (a meta.replay.Replay) to out_path. fmt 'gif' or 'mp4'.
    Creates its own hidden GL context. Returns the written path."""
    import pygame
    pygame.init()
    _hidden_gl()
    try:
        frames = list(render_frames(replay, fps=fps, full=full, crt=crt))
    finally:
        pass
    if not frames:
        raise RuntimeError("replay produced no frames")

    if fmt == "mp4":
        _write_mp4(frames, out_path, fps)
    else:
        _write_gif(frames, out_path, fps)
    pygame.quit()
    return out_path


def _write_gif(frames, out_path, fps):
    from PIL import Image
    scale = min(1.0, GIF_MAX_W / frames[0].shape[1])
    imgs = []
    for f in frames:
        im = Image.fromarray(f, "RGB")
        if scale < 1.0:
            im = im.resize((int(im.width * scale), int(im.height * scale)),
                           Image.BILINEAR)
        imgs.append(im.convert("P", palette=Image.ADAPTIVE, colors=128))
    imgs[0].save(out_path, save_all=True, append_images=imgs[1:],
                 duration=int(1000 / fps), loop=0, optimize=True, disposal=2)


def _write_mp4(frames, out_path, fps):
    import imageio_ffmpeg
    h, w = frames[0].shape[:2]
    writer = imageio_ffmpeg.write_frames(out_path, (w, h), fps=fps,
                                         macro_block_size=1, quality=7)
    writer.send(None)
    for f in frames:
        writer.send(np.ascontiguousarray(f).tobytes())
    writer.close()
