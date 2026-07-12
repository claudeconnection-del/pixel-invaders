"""Voxel Crisis's achievements."""
from game import events as ev
from meta.achievements import Achievement


def _summary(etype, data):
    return data["summary"] if etype == ev.RUN_END else None


ACHIEVEMENTS = [
    Achievement(
        "first_takedown", "First Takedown", "Drop your first trooper",
        lambda e, d, life, run: e == ev.ENEMY_KILLED,
    ),
    Achievement(
        "zone_one", "Zone One", "Clear the first zone",
        lambda e, d, life, run: e == ev.WAVE_CLEAR and d["index"] == 0,
    ),
    Achievement(
        "captain_down", "Captain Down", "Defeat the Dread Captain",
        lambda e, d, life, run: e == ev.BOSS_KILLED,
    ),
    Achievement(
        "quick_hands", "Quick Hands", "Land 5 quick kills in one run",
        lambda e, d, life, run: run.get("quick_kills", 0) >= 5,
        progress=lambda life, run: (run.get("quick_kills", 0), 5),
    ),
    Achievement(
        "iron_nerves", "Iron Nerves", "Finish the stage with full armor",
        lambda e, d, life, run: (s := _summary(e, d)) is not None
        and s["win"] and s.get("final_hp", 0) >= 5,
    ),
    Achievement(
        "trooper_tally", "Trooper Tally", "Drop 150 troopers lifetime",
        lambda e, d, life, run: e == ev.ENEMY_KILLED and life["kills"] >= 150,
        progress=lambda life, run: (life["kills"], 150),
    ),
]
