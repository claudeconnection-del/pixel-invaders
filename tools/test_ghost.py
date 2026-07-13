"""Headless ghost tests: record a real run, replay it, verify the personal-
best storage rules. No GL — drives the run object directly.

Run with: python tools/test_ghost.py
"""
import os
import random
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from games.voxelhell.game import create_run  # noqa: E402
from games.voxelhell.bot import demo_bot  # noqa: E402
from meta import ghost as gh  # noqa: E402

DT = 1 / 60


def record_run(seed, lives=99, frames=60 * 20):
    run = create_run("campaign", random.Random(seed))
    run.world.player.lives = lives
    rec = gh.GhostRecorder()
    for _ in range(frames):
        run.update(DT, demo_bot(run.world))
        run.drain_events()
        rec.on_frame(DT, run)
        if run.run_over:
            break
    return run, rec


def test_record_replay():
    run, rec = record_run(1234)
    ghost = rec.build("voxelhell", "campaign", run.score)
    assert ghost["game"] == "voxelhell" and ghost["mode"] == "campaign"
    assert len(ghost["samples"]) == len(ghost["scores"]) >= 100
    assert ghost["score"] == run.score

    player = gh.GhostPlayer(ghost)
    assert player.valid
    # sample_at clamps and interpolates within bounds
    s0 = player.sample_at(0.0)
    assert len(s0) == 2
    mid = player.sample_at(player.duration / 2)
    assert all(isinstance(v, float) for v in mid)
    past_end = player.sample_at(player.duration + 100)
    assert past_end == tuple(ghost["samples"][-1])
    # score timeline is non-decreasing (score only goes up in voxelhell)
    scores = [player.score_at(t) for t in
              [i * player.dt for i in range(len(ghost["scores"]))]]
    assert all(b >= a for a, b in zip(scores, scores[1:])), "score went down"
    assert player.score_at(player.duration + 5) == ghost["scores"][-1]
    print(f"record/replay OK: {len(ghost['samples'])} samples, "
          f"score={ghost['score']}, dur={player.duration:.1f}s")


def test_determinism():
    _, rec_a = record_run(77, frames=60 * 10)
    _, rec_b = record_run(77, frames=60 * 10)
    ga = rec_a.build("voxelhell", "campaign", 0)
    gb = rec_b.build("voxelhell", "campaign", 0)
    assert ga["samples"] == gb["samples"], "same seed diverged (samples)"
    assert ga["scores"] == gb["scores"], "same seed diverged (scores)"
    print("determinism OK")


def test_personal_best_rules():
    store = {}
    lo = {"game": "voxelhell", "mode": "campaign", "score": 500,
          "dt": 0.05, "samples": [[0, 0], [1, 1]], "scores": [0, 500]}
    hi = dict(lo, score=1500, scores=[0, 1500])
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "ghosts.json")
        assert gh.maybe_store_best(store, lo, path) is True
        assert gh.maybe_store_best(store, dict(lo, score=400), path) is False
        assert gh.maybe_store_best(store, hi, path) is True
        assert gh.get_ghost(store, "voxelhell", "campaign")["score"] == 1500
        # round-trips through disk
        reloaded = gh.load(path)
        assert gh.get_ghost(reloaded, "voxelhell", "campaign")["score"] == 1500
    print("personal-best rules + persistence OK")


def test_downsample():
    rec = gh.GhostRecorder()
    rec.samples = [(float(i), float(i)) for i in range(gh.MAX_SAMPLES * 3)]
    rec.scores = list(range(gh.MAX_SAMPLES * 3))
    ghost = rec.build("g", "m", 999)
    assert len(ghost["samples"]) <= gh.MAX_SAMPLES
    assert ghost["dt"] > rec.dt  # dt widened to preserve wall-clock timing
    print(f"downsample OK: {gh.MAX_SAMPLES * 3} -> {len(ghost['samples'])}")


if __name__ == "__main__":
    test_record_replay()
    test_determinism()
    test_personal_best_rules()
    test_downsample()
    print("ALL GHOST TESTS PASSED")
