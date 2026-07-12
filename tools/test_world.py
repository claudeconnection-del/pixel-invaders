"""Headless simulation tests: drive campaigns and endless mode with a bot.

Run with: python tools/test_world.py
No pygame/GL required — exercises waves, patterns, collisions, graze,
power-ups, boss phases, campaign loops, endless sectors, and the loss path.
"""
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from game import events as ev  # noqa: E402
from game.entities import InputState  # noqa: E402
from games.voxelhell.world import World, LOST  # noqa: E402

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


def run_campaign_loops():
    """Clear loop 1, verify loop 2 starts harder, then die and check the
    run ends as a win."""
    world = World(rng=random.Random(1234), mode="campaign")
    world.player.lives = 99
    seen = set()
    frames = 0
    max_frames = 60 * 60 * 12
    while world.loop == 1 and frames < max_frames and not world.run_over:
        world.update(DT, dodge_bot_input(world))
        for kind, data in world.drain_events():
            seen.add(kind)
        frames += 1
    assert ev.LOOP_CLEAR in seen, "never cleared loop 1"
    assert world.won

    # ride into loop 2 and confirm a wave actually starts
    loop2_started = False
    for _ in range(60 * 30):
        world.update(DT, dodge_bot_input(world))
        for kind, data in world.drain_events():
            if kind == ev.WAVE_START:
                loop2_started = True
        if loop2_started:
            break
    assert loop2_started and world.loop == 2, \
        f"loop 2 never started (loop={world.loop})"

    # now die: run must end as a WIN because loop 1 was cleared
    world.player.lives = 1
    got_end = None
    for _ in range(60 * 120):
        world.update(DT, InputState())
        for kind, data in world.drain_events():
            if kind == ev.RUN_END:
                got_end = data
        if world.run_over:
            break
    assert world.state == LOST and got_end is not None
    assert got_end["win"] is True, "run after loop clear should count as win"
    for expected in (ev.WAVE_START, ev.WAVE_CLEAR, ev.ENEMY_KILLED,
                     ev.BOSS_SPAWN, ev.BOSS_PHASE, ev.BOSS_KILLED, ev.LOOP_CLEAR):
        assert expected in seen, f"never saw event {expected}"
    s = got_end["summary"]
    print(f"campaign loops OK: frames={frames} score={s['score']} "
          f"loop={s['loop']} waves={s['wave_reached']} kills={s['kills']}")


def run_endless():
    world = World(rng=random.Random(777), mode="endless")
    world.player.lives = 99
    boss_slots = 0
    max_wave = 0
    frames = 0
    while frames < 60 * 60 * 10 and not world.run_over:
        world.update(DT, dodge_bot_input(world))
        for kind, data in world.drain_events():
            if kind == ev.WAVE_START:
                assert data["mode"] == "endless"
                max_wave = max(max_wave, data["index"] + 1)
            elif kind == ev.BOSS_SPAWN:
                boss_slots += 1
        frames += 1
        if max_wave >= 7:
            break
    assert max_wave >= 7, f"endless stalled at wave {max_wave}"
    assert boss_slots >= 1, "endless never spawned a boss (expected at sector 5)"
    print(f"endless OK: reached sector {max_wave} with {boss_slots} boss(es) "
          f"in {frames} frames")


def run_loss():
    world = World(rng=random.Random(99), mode="campaign")
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
    def run_n(seed, n, mode):
        w = World(rng=random.Random(seed), mode=mode)
        for _ in range(n):
            w.update(DT, dodge_bot_input(w))
            w.drain_events()
        return (w.score, len(w.enemy_bullets), len(w.enemies), w.player.x)

    for mode in ("campaign", "endless"):
        a = run_n(42, 3000, mode)
        b = run_n(42, 3000, mode)
        assert a == b, f"{mode}: same seed diverged: {a} vs {b}"
        print(f"determinism OK ({mode}): {a}")


if __name__ == "__main__":
    run_determinism()
    run_loss()
    run_endless()
    run_campaign_loops()
    print("ALL WORLD TESTS PASSED")
