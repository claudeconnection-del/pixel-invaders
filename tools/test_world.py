"""Headless simulation tests: drive the full campaign with a scripted bot.

Run with: python tools/test_world.py
No pygame/GL required — exercises waves, patterns, collisions, graze,
power-ups, boss phases, and both run endings.
"""
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from game import events as ev  # noqa: E402
from game.entities import InputState, FIELD_WIDTH  # noqa: E402
from game.world import World, WON, LOST  # noqa: E402

DT = 1 / 60


def dodge_bot_input(world):
    """Cheap bot: dodge only bullets predicted to hit within ~0.7s,
    otherwise line up under the nearest target. Always firing."""
    inp = InputState(fire=True)
    p = world.player
    danger = None
    for b in world.enemy_bullets:
        if b.vy <= 10:
            continue
        t_impact = (p.y - b.y) / b.vy
        if not (0 <= t_impact <= 0.7):
            continue
        x_at_impact = b.x + b.vx * t_impact
        if abs(x_at_impact - p.x) < 26:
            if danger is None or t_impact < danger[0]:
                danger = (t_impact, x_at_impact)
    if danger is not None:
        if danger[1] >= p.x:
            inp.left = True
        else:
            inp.right = True
        return inp
    targets = world.enemies or ([world.boss] if world.boss and world.boss.alive else [])
    targets = [t for t in targets if t.y > -20]  # ignore not-yet-entered enemies
    if targets:
        tx = min(targets, key=lambda e: abs(e.x - p.x)).x
        if tx < p.x - 8:
            inp.left = True
        elif tx > p.x + 8:
            inp.right = True
    return inp


def run_campaign():
    world = World(rng=random.Random(1234))
    world.player.lives = 99  # traversal test: reach the end regardless of bot skill
    seen = set()
    frames = 0
    max_frames = 60 * 60 * 12  # 12 minute cap
    while not world.run_over and frames < max_frames:
        world.update(DT, dodge_bot_input(world))
        for kind, data in world.drain_events():
            seen.add(kind)
            if kind == ev.RUN_END:
                summary = data["summary"]
        frames += 1

    assert world.state == WON, f"expected WON, got {world.state} after {frames} frames"
    for expected in (ev.WAVE_START, ev.WAVE_CLEAR, ev.ENEMY_KILLED, ev.SHOT_FIRED,
                     ev.BOSS_SPAWN, ev.BOSS_PHASE, ev.BOSS_KILLED, ev.RUN_END):
        assert expected in seen, f"never saw event {expected}"
    assert summary["win"] and summary["score"] > 0 and summary["kills"] > 0
    assert summary["wave_reached"] == len(world.waves) + 1
    print(f"campaign WIN in {frames} frames ({frames/60:.0f}s sim time): "
          f"score={summary['score']} kills={summary['kills']} "
          f"grazes={summary['grazes']} accuracy={summary['accuracy']:.0%} "
          f"deaths={summary['deaths']} powerups={summary['powerups']}")


def run_loss():
    world = World(rng=random.Random(99))
    world.player.lives = 1
    frames = 0
    got_run_end = False
    while not world.run_over and frames < 60 * 60 * 5:
        world.update(DT, InputState(fire=False))  # sitting duck, no dodging
        for kind, data in world.drain_events():
            if kind == ev.RUN_END:
                got_run_end = True
                assert data["win"] is False
        frames += 1
    assert world.state == LOST, f"expected LOST, got {world.state}"
    assert got_run_end
    print(f"loss path OK in {frames} frames ({frames/60:.0f}s sim time)")


def run_determinism():
    def run_n(seed, n):
        w = World(rng=random.Random(seed))
        for _ in range(n):
            w.update(DT, dodge_bot_input(w))
            w.drain_events()
        return (w.score, len(w.enemy_bullets), len(w.enemies), w.player.x)

    a = run_n(42, 3000)
    b = run_n(42, 3000)
    assert a == b, f"same seed diverged: {a} vs {b}"
    print(f"determinism OK: {a}")


if __name__ == "__main__":
    run_determinism()
    run_loss()
    run_campaign()
    print("ALL WORLD TESTS PASSED")
