"""Headless meta-layer tests: per-game stats, achievements, skin unlocks,
profile v1->v2 migration, and save/load round-trip.

Run with: python tools/test_meta.py
"""
import json
import os
import random
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from games.voxelhell import ACHIEVEMENTS, skin_for_achievement  # noqa: E402
from games.voxelhell.world import World  # noqa: E402
from meta import profile as profile_mod  # noqa: E402
from meta.achievements import AchievementEngine  # noqa: E402
from meta.stats import StatsTracker  # noqa: E402
from tools.test_world import dodge_bot_input, DT  # noqa: E402


def run_campaign_with_meta():
    profile = profile_mod.load(path="/nonexistent/so/defaults/load")
    section = profile_mod.game_section(profile, "voxelhell")
    stats = StatsTracker(section)
    engine = AchievementEngine(section, ACHIEVEMENTS, skin_for_achievement)

    world = World(rng=random.Random(1234), mode="campaign")
    world.player.lives = 99
    unlocked = []
    frames = 0
    while world.loop == 1 and not world.run_over and frames < 60 * 60 * 12:
        world.update(DT, dodge_bot_input(world))
        frame_events = world.drain_events()
        stats.on_frame(DT, frame_events)
        unlocked += engine.on_frame(frame_events, world.stats)
        frames += 1

    # die to finish the run (win, since loop 1 cleared)
    world.player.lives = 1
    from game.entities import InputState
    while not world.run_over and frames < 60 * 60 * 14:
        world.update(DT, InputState())
        frame_events = world.drain_events()
        stats.on_frame(DT, frame_events)
        unlocked += engine.on_frame(frame_events, world.stats)
        frames += 1

    ids = {a.id for a in unlocked}
    for expected in ("first_blood", "warmed_up", "halfway_there", "boss_slayer"):
        assert expected in ids, f"expected achievement {expected}, got {ids}"
    # bot takes hits during the campaign, so the no-death clear must NOT unlock
    assert "one_credit_clear" not in ids
    assert len(ids) == len(unlocked), "duplicate achievement unlocks"

    life = section["lifetime"]
    assert life["runs"] == 1 and life["wins"] == 1
    assert life["kills"] > 0 and life["bosses"] == 1
    assert life["best_score"] == world.score
    assert life["playtime"] > 0

    assert "raider" in section["unlocked_skins"]      # warmed_up
    assert "gold_ace" in section["unlocked_skins"]    # boss_slayer

    print(f"meta campaign OK: achievements={sorted(ids)}")
    print(f"  skins unlocked={section['unlocked_skins']}")
    return profile


def round_trip(profile):
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "profile.json")
        profile_mod.save(profile, path=path)
        loaded = profile_mod.load(path=path)
        assert loaded["games"]["voxelhell"]["lifetime"] == \
            profile["games"]["voxelhell"]["lifetime"]
        assert loaded["games"]["voxelhell"]["achievements"].keys() == \
            profile["games"]["voxelhell"]["achievements"].keys()

        # corrupt file falls back to defaults instead of crashing
        with open(path, "w") as f:
            f.write("{not json")
        recovered = profile_mod.load(path=path)
        assert profile_mod.game_section(recovered, "voxelhell")["lifetime"]["runs"] == 0
    print("profile round-trip + corruption recovery OK")


def migration_v1():
    """A v1 (single-game) save file must migrate into games.voxelhell."""
    v1 = {
        "version": 1,
        "selected_skin": "gold_ace",
        "unlocked_skins": ["vanguard", "gold_ace"],
        "achievements": {"boss_slayer": {"unlocked_at": "2026-07-11T00:00:00+00:00"}},
        "lifetime": {"runs": 7, "kills": 321, "best_score": 12345},
        "settings": {"crt": False, "fps_cap": 144},
        "leaderboard": {},
    }
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "profile.json")
        with open(path, "w") as f:
            json.dump(v1, f)
        migrated = profile_mod.load(path=path)
        section = profile_mod.game_section(migrated, "voxelhell")
        assert section["selected_skin"] == "gold_ace"
        assert "gold_ace" in section["unlocked_skins"]
        assert "boss_slayer" in section["achievements"]
        assert section["lifetime"]["runs"] == 7
        assert section["lifetime"]["kills"] == 321
        assert migrated["settings"]["crt"] is False
        assert migrated["settings"]["fps_cap"] == 144
        assert migrated["settings"]["vsync"] is True  # new default merged in
    print("v1 -> v2 migration OK")


if __name__ == "__main__":
    migration_v1()
    p = run_campaign_with_meta()
    round_trip(p)
    print("ALL META TESTS PASSED")
