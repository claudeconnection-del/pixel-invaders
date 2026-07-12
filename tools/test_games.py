"""Headless simulation tests for the cabinet's other games.

Run with: python tools/test_games.py
"""
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from game import events as ev  # noqa: E402
from game.entities import InputState  # noqa: E402
from games.breaker.world import BreakerWorld, PLAYING_STATE  # noqa: E402
from games.serpent.world import (  # noqa: E402
    SerpentWorld, DIRS, OPPOSITE, COLS, ROWS,
)

DT = 1 / 60


# ------------------------------------------------------------------ breaker
def breaker_bot(world):
    """Follow the most-dangerous descending ball; hold fire for lasers."""
    inp = InputState(fire=True)
    falling = [b for b in world.balls if b.vy > 0]
    target = None
    if falling:
        target = min(falling, key=lambda b: (world.paddle_y - b.y))
    elif world.balls:
        target = world.balls[0]
    tx = target.x if target else 320
    if tx < world.paddle_x - 8:
        inp.left = True
    elif tx > world.paddle_x + 8:
        inp.right = True
    return inp


def run_breaker():
    world = BreakerWorld(rng=random.Random(42))
    world.lives = 99
    seen = set()
    frames = 0
    levels_cleared = 0
    while frames < 60 * 60 * 8:
        world.update(DT, breaker_bot(world))
        for etype, data in world.drain_events():
            seen.add(etype)
            if etype == ev.LEVEL_CLEAR:
                levels_cleared += 1
        frames += 1
        if levels_cleared >= 2:
            break
    assert levels_cleared >= 2, f"bot only cleared {levels_cleared} levels"
    for expected in (ev.WAVE_START, ev.ENEMY_KILLED, ev.LEVEL_CLEAR):
        assert expected in seen, f"never saw {expected}"
    print(f"breaker OK: cleared {levels_cleared} levels in {frames} frames, "
          f"score={world.score} bricks={world.stats['kills']} "
          f"deaths={world.stats['deaths']}")

    # loss path
    world2 = BreakerWorld(rng=random.Random(7))
    world2.lives = 1
    got_end = False
    for _ in range(60 * 120):
        world2.update(DT, InputState())  # frozen paddle
        for etype, data in world2.drain_events():
            if etype == ev.RUN_END:
                got_end = True
                assert data["win"] is False
        if world2.run_over:
            break
    assert got_end and world2.run_over
    print("breaker loss path OK")


# ------------------------------------------------------------------ serpent
def serpent_bot(world):
    """Greedy chase with 1-step survival lookahead."""
    head = world.body[0]
    fruit = world.fruit
    deadly = set(world.body[:-1]) | world.obstacles

    def safe(direction):
        dx, dy = DIRS[direction]
        nxt = (head[0] + dx, head[1] + dy)
        return (0 <= nxt[0] < COLS and 0 <= nxt[1] < ROWS
                and nxt not in deadly)

    prefs = []
    if fruit:
        if fruit[0] > head[0]:
            prefs.append("right")
        elif fruit[0] < head[0]:
            prefs.append("left")
        if fruit[1] > head[1]:
            prefs.append("down")
        elif fruit[1] < head[1]:
            prefs.append("up")
    prefs += ["up", "left", "down", "right"]
    for d in prefs:
        if d != OPPOSITE[world.direction] and safe(d):
            return InputState(**{d: True})
    return InputState()


def run_serpent():
    world = SerpentWorld(rng=random.Random(1))
    frames = 0
    fruit_events = 0
    while frames < 60 * 60 * 6 and not world.run_over:
        world.update(DT, serpent_bot(world))
        for etype, data in world.drain_events():
            if etype == ev.FRUIT_EATEN:
                fruit_events += 1
        frames += 1
        if world.length >= 12:
            break
    assert world.length >= 12, f"bot stalled at length {world.length}"
    assert fruit_events >= 3  # gold fruit grows +3, so 12 length >= 3 fruit
    print(f"serpent OK: length={world.length} fruit={fruit_events} "
          f"score={world.score} in {frames} frames")

    # death path: drive straight into the wall
    world2 = SerpentWorld(rng=random.Random(2))
    got_end = False
    for _ in range(60 * 30):
        world2.update(DT, InputState(right=True))
        for etype, data in world2.drain_events():
            if etype == ev.RUN_END:
                got_end = True
        if world2.run_over:
            break
    assert got_end and world2.run_over
    print("serpent death path OK")


def run_determinism():
    def breaker_n(seed, n):
        w = BreakerWorld(rng=random.Random(seed))
        for _ in range(n):
            w.update(DT, breaker_bot(w))
            w.drain_events()
        return (w.score, len(w.bricks), w.paddle_x)

    a, b = breaker_n(9, 3000), breaker_n(9, 3000)
    assert a == b, f"breaker diverged: {a} vs {b}"

    def serpent_n(seed, n):
        w = SerpentWorld(rng=random.Random(seed))
        for _ in range(n):
            if w.run_over:
                break
            w.update(DT, serpent_bot(w))
            w.drain_events()
        return (w.score, w.length, tuple(w.body[:3]))

    a, b = serpent_n(9, 3000), serpent_n(9, 3000)
    assert a == b, f"serpent diverged: {a} vs {b}"
    print("determinism OK (breaker + serpent)")


if __name__ == "__main__":
    run_determinism()
    run_breaker()
    run_serpent()
    print("ALL GAME TESTS PASSED")
