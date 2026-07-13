"""Replay tests: deterministic reconstruction, plus a real GIF/MP4 export.

Run with: python tools/test_replay.py
The reconstruction test needs no GL; the export test creates a hidden GL
context and writes a short clip to a temp file.
"""
import os
import random
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from games.voxelhell.game import create_run  # noqa: E402
from games.voxelhell.bot import demo_bot  # noqa: E402
from meta import replay as replay_mod  # noqa: E402

DT = 1 / 60


def _record(seed, frames):
    """Drive a run with the bot, recording the exact inputs; return the
    replay dict and the final score."""
    run = create_run("campaign", random.Random(seed))
    run.world.player.lives = 99
    rec = replay_mod.ReplayRecorder("voxelhell", "campaign", seed, analog=False)
    for _ in range(frames):
        inp = demo_bot(run.world)
        run.update(DT, inp)
        run.drain_events()
        rec.on_frame(DT, inp)
        if run.run_over:
            break
    return rec.build(run.score), run.score


def _resim(data):
    """Reconstruct the run purely from the replay's seed + input stream."""
    rep = replay_mod.Replay(data)
    run = create_run("campaign", random.Random(rep.seed))
    run.world.player.lives = 99
    for dt, inp in rep.frames():
        run.update(dt, inp)
        run.drain_events()
    return run.score, (run.world.player.x, run.world.player.y)


def test_deterministic_reconstruction():
    data, original_score = _record(4242, 60 * 25)
    resim_score, resim_pos = _resim(data)
    assert resim_score == original_score, \
        f"replay diverged: {original_score} vs {resim_score}"
    # a second reconstruction is identical too
    again_score, again_pos = _resim(data)
    assert again_pos == resim_pos
    print(f"reconstruction OK: score={original_score} exactly reproduced "
          f"from {data['schema']}-schema replay ({len(data['dts'])} frames, "
          f"{len(str(data)) / 1024:.1f}KB raw)")


def test_persistence_roundtrip():
    data, _ = _record(7, 60 * 5)
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "r.json")
        replay_mod._atomic_write(path, data)
        loaded = replay_mod.load(path)
        assert loaded["seed"] == data["seed"]
        assert loaded["masks"] == data["masks"]
    print("persistence round-trip OK")


def test_export_gif():
    data, score = _record(99, 60 * 8)
    rep = replay_mod.Replay(data)
    from render import export as export_mod
    with tempfile.TemporaryDirectory() as tmp:
        gif = os.path.join(tmp, "clip.gif")
        export_mod.export(rep, gif, fmt="gif", fps=15, full=True)
        assert os.path.exists(gif) and os.path.getsize(gif) > 2000, \
            "GIF missing or too small"
        print(f"GIF export OK ({os.path.getsize(gif) / 1024:.0f} KB)")
        if export_mod.mp4_available():
            import pygame
            pygame.quit()  # export() quit the display; reinit for a 2nd export
            mp4 = os.path.join(tmp, "clip.mp4")
            export_mod.export(rep, mp4, fmt="mp4", fps=15, full=True)
            assert os.path.exists(mp4) and os.path.getsize(mp4) > 2000
            print(f"MP4 export OK ({os.path.getsize(mp4) / 1024:.0f} KB)")
        else:
            print("MP4 skipped (imageio-ffmpeg not installed)")


if __name__ == "__main__":
    test_deterministic_reconstruction()
    test_persistence_roundtrip()
    test_export_gif()
    print("ALL REPLAY TESTS PASSED")
