"""Voxel Hell's achievements (evaluated by meta.achievements.AchievementEngine)."""
from game import events as ev
from meta.achievements import Achievement


def _summary(etype, data):
    return data["summary"] if etype == ev.RUN_END else None


ACHIEVEMENTS = [
    Achievement(
        "first_blood", "First Blood", "Destroy your first enemy",
        lambda e, d, life, run: e == ev.ENEMY_KILLED,
    ),
    Achievement(
        "warmed_up", "Warmed Up", "Clear Wave 1",
        lambda e, d, life, run: e == ev.WAVE_CLEAR and d["index"] == 0,
    ),
    Achievement(
        "halfway_there", "Halfway There", "Clear Wave 3",
        lambda e, d, life, run: e == ev.WAVE_CLEAR and d["index"] == 2,
    ),
    Achievement(
        "boss_slayer", "Boss Slayer", "Defeat the Dreadnought",
        lambda e, d, life, run: e == ev.BOSS_KILLED,
    ),
    Achievement(
        "one_credit_clear", "One Credit Clear", "Clear the campaign without losing a life",
        lambda e, d, life, run: e == ev.LOOP_CLEAR and d["loop"] == 1
        and run["deaths"] == 0,
    ),
    Achievement(
        "second_verse", "Second Verse", "Clear campaign loop 2",
        lambda e, d, life, run: e == ev.LOOP_CLEAR and d["loop"] >= 2,
    ),
    Achievement(
        "deep_space", "Deep Space", "Reach wave 10 in endless mode",
        lambda e, d, life, run: e == ev.WAVE_START and d.get("mode") == "endless"
        and d["index"] + 1 >= 10,
    ),
    Achievement(
        "untouchable", "Untouchable", "Clear any wave without getting hit",
        lambda e, d, life, run: e == ev.WAVE_CLEAR and d["untouched"],
    ),
    Achievement(
        "graze_addict", "Graze Addict", "Graze 100 bullets in one run",
        lambda e, d, life, run: e == ev.GRAZE and run["grazes"] >= 100,
        progress=lambda life, run: (run["grazes"], 100),
    ),
    Achievement(
        "edge_lord", "Edge Lord", "Graze 1,000 bullets lifetime",
        lambda e, d, life, run: e == ev.GRAZE and life["grazes"] >= 1000,
        progress=lambda life, run: (life["grazes"], 1000),
    ),
    Achievement(
        "sharpshooter", "Sharpshooter", "Finish a run with 75%+ accuracy (min 50 shots)",
        lambda e, d, life, run: (s := _summary(e, d)) is not None
        and s["shots"] >= 50 and s["accuracy"] >= 0.75,
    ),
    Achievement(
        "hoarder", "Hoarder", "Collect 5 power-ups in one run",
        lambda e, d, life, run: e == ev.POWERUP_PICKUP and run["powerups"] >= 5,
        progress=lambda life, run: (run["powerups"], 5),
    ),
    Achievement(
        "exterminator", "Exterminator", "Destroy 1,000 enemies lifetime",
        lambda e, d, life, run: e in (ev.ENEMY_KILLED, ev.BOSS_KILLED)
        and life["kills"] >= 1000,
        progress=lambda life, run: (life["kills"], 1000),
    ),
    Achievement(
        "marathoner", "Marathoner", "Play for 1 hour total",
        lambda e, d, life, run: life["playtime"] >= 3600,
        progress=lambda life, run: (int(life["playtime"]), 3600),
    ),
]
