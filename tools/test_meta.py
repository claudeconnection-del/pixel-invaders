"""Headless meta-layer tests: stats accumulation, achievement unlocks,
skin unlocks, and profile save/load round-trip.

Run with: python tools/test_meta.py
"""
import os
import random
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from game.world import World, WON  # noqa: E402
from meta import profile as profile_mod  # noqa: E402
from meta.achievements import AchievementEngine  # noqa: E402
from meta.stats import StatsTracker  # noqa: E402
from tools.test_world import dodge_bot_input, DT  # noqa: E402


def run_full_campaign_with_meta():
    profile = profile_mod.load(path="/nonexistent/so/defaults/load")
    stats = StatsTracker(profile)
    engine = AchievementEngine(profile)

    world = World(rng=random.Random(1234))
    world.player.lives = 99
    unlocked = []
    frames = 0
    while not world.run_over and frames < 60 * 60 * 12:
        world.update(DT, dodge_bot_input(world))
        frame_events = world.drain_events()
        stats.on_frame(DT, frame_events)
        unlocked += engine.on_frame(frame_events, world.stats)
        frames += 1

    assert world.state == WON
    ids = {a.id for a in unlocked}
    for expected in ("first_blood", "warmed_up", "halfway_there", "boss_slayer"):
        assert expected in ids, f"expected achievement {expected}, got {ids}"
    # each unlocked exactly once
    assert len(ids) == len(unlocked), "duplicate achievement unlocks"

    life = profile["lifetime"]
    assert life["runs"] == 1 and life["wins"] == 1
    assert life["kills"] > 0 and life["bosses"] == 1
    assert life["best_score"] == world.score
    assert life["best_wave"] == len(world.waves) + 1
    assert life["playtime"] > 0

    # skin unlocks tied to achievements
    assert "raider" in profile["unlocked_skins"]      # warmed_up
    assert "gold_ace" in profile["unlocked_skins"]    # boss_slayer
    assert "vanguard" in profile["unlocked_skins"]

    print(f"meta campaign OK: achievements={sorted(ids)}")
    print(f"  skins unlocked={profile['unlocked_skins']}")
    return profile


def round_trip(profile):
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "profile.json")
        profile_mod.save(profile, path=path)
        loaded = profile_mod.load(path=path)
        assert loaded["lifetime"] == profile["lifetime"]
        assert loaded["achievements"].keys() == profile["achievements"].keys()
        assert loaded["unlocked_skins"] == profile["unlocked_skins"]
        assert loaded["selected_skin"] == profile["selected_skin"]

        # corrupt file falls back to defaults instead of crashing
        with open(path, "w") as f:
            f.write("{not json")
        recovered = profile_mod.load(path=path)
        assert recovered["lifetime"]["runs"] == 0
    print("profile round-trip + corruption recovery OK")


if __name__ == "__main__":
    p = run_full_campaign_with_meta()
    round_trip(p)
    print("ALL META TESTS PASSED")
