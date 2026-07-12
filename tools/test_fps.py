"""Headless simulation tests for the FPS category (aim, doom, crisis).

Run with: python tools/test_fps.py
Screen projections are stubbed so the mouse-aim games run without GL.
"""
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from game import events as ev  # noqa: E402
from game.entities import InputState  # noqa: E402
from games.aimtrainer.bot import demo_bot as aim_bot  # noqa: E402
from games.aimtrainer.world import AimWorld  # noqa: E402
from games.crisis.bot import demo_bot as crisis_bot  # noqa: E402
from games.crisis.world import CrisisWorld  # noqa: E402
from games.voxeldoom.bot import demo_bot as doom_bot  # noqa: E402
from games.voxeldoom.world import DoomWorld  # noqa: E402

DT = 1 / 60


def project_aim(world):
    for t in world.targets:
        t.screen_x = 640 + t.x * 60
        t.screen_y = 430 - (t.y - 3) * 60
        t.screen_r = 34.0


def project_crisis(world):
    for e in world.enemies:
        e.screen_x = 300 + (e.x % 13) * 60
        e.screen_y = 300 + (e.z % 7) * 40
        e.screen_r = 40.0


def run_aim():
    w = AimWorld(rng=random.Random(5))
    run_end = None
    frames = 0
    while not w.run_over and frames < 60 * 70:
        project_aim(w)
        w.update(DT, aim_bot(w))
        for etype, data in w.drain_events():
            if etype == ev.RUN_END:
                run_end = data
        frames += 1
    assert w.run_over and run_end is not None and run_end["win"]
    s = run_end["summary"]
    assert s["hits"] > 20 and s["best_reaction"] is not None
    print(f"aim OK: score={s['score']} hits={s['hits']} "
          f"acc={s['accuracy']:.0%}")


def run_doom():
    w = DoomWorld(rng=random.Random(3))
    w.hp = 10 ** 9  # traversal test; the loss path is checked separately
    seen = set()
    frames = 0
    while frames < 60 * 900 and not w.run_over:
        w.update(DT, doom_bot(w))
        for etype, data in w.drain_events():
            seen.add(etype)
        frames += 1
    assert w.state == "won", \
        f"doom bot stalled: level={w.level_index + 1} enemies={len(w.enemies)}"
    for expected in (ev.WAVE_START, ev.LEVEL_CLEAR, ev.ENEMY_KILLED,
                     ev.POWERUP_PICKUP, ev.RUN_END):
        assert expected in seen, f"missing {expected}"
    print(f"doom OK: cleared all floors in {frames / 60:.0f}s sim, "
          f"kills={w.stats['kills']}")

    w2 = DoomWorld(rng=random.Random(4))
    for _ in range(60 * 180):
        w2.update(DT, InputState())
        w2.drain_events()
        if w2.run_over:
            break
    assert w2.run_over and w2.state == "lost"
    print("doom loss path OK")


def run_crisis():
    w = CrisisWorld(rng=random.Random(11))
    seen = set()
    frames = 0
    while frames < 60 * 300 and not w.run_over:
        project_crisis(w)
        w.update(DT, crisis_bot(w))
        for etype, data in w.drain_events():
            seen.add(etype)
        frames += 1
    assert w.state == "won", f"crisis bot stalled at zone {w.stop_index}"
    for expected in (ev.WAVE_START, ev.WAVE_CLEAR, ev.ENEMY_KILLED,
                     ev.BOSS_SPAWN, ev.BOSS_KILLED, ev.RUN_END):
        assert expected in seen, f"missing {expected}"
    print(f"crisis OK: full stage in {frames / 60:.0f}s sim, "
          f"kills={w.stats['kills']} hp={w.hp}")

    w2 = CrisisWorld(rng=random.Random(12))
    for _ in range(60 * 120):
        project_crisis(w2)
        w2.update(DT, InputState())
        w2.drain_events()
        if w2.run_over:
            break
    assert w2.run_over and w2.state == "lost"
    print("crisis loss path OK")


def run_determinism():
    def doom_n(seed, n):
        w = DoomWorld(rng=random.Random(seed))
        for _ in range(n):
            if w.run_over:
                break
            w.update(DT, doom_bot(w))
            w.drain_events()
        return (w.score, w.px, w.pz, len(w.enemies))

    def crisis_n(seed, n):
        w = CrisisWorld(rng=random.Random(seed))
        for _ in range(n):
            if w.run_over:
                break
            project_crisis(w)
            w.update(DT, crisis_bot(w))
            w.drain_events()
        return (w.score, w.hp, w.stop_index)

    assert doom_n(9, 3000) == doom_n(9, 3000)
    assert crisis_n(9, 4000) == crisis_n(9, 4000)
    print("determinism OK (doom + crisis)")


if __name__ == "__main__":
    run_aim()
    run_doom()
    run_crisis()
    run_determinism()
    print("ALL FPS TESTS PASSED")
