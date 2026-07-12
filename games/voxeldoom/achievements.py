"""Voxel Doom's achievements."""
from game import events as ev
from meta.achievements import Achievement


def _summary(etype, data):
    return data["summary"] if etype == ev.RUN_END else None


ACHIEVEMENTS = [
    Achievement(
        "first_frag", "First Frag", "Put down your first demon",
        lambda e, d, life, run: e == ev.ENEMY_KILLED,
    ),
    Achievement(
        "going_down", "Going Down", "Clear Floor 1",
        lambda e, d, life, run: e == ev.LEVEL_CLEAR and d["index"] == 0,
    ),
    Achievement(
        "rock_bottom", "Rock Bottom", "Escape all three floors",
        lambda e, d, life, run: (s := _summary(e, d)) is not None and s["win"],
    ),
    Achievement(
        "untouched_floor", "Nothing Personal",
        "Beat the dungeon with 75+ HP remaining",
        lambda e, d, life, run: (s := _summary(e, d)) is not None
        and s["win"] and s.get("final_hp", 0) >= 75,
    ),
    Achievement(
        "pack_rat", "Pack Rat", "Grab 6 pickups in one run",
        lambda e, d, life, run: run["powerups"] >= 6,
        progress=lambda life, run: (run.get("powerups", 0), 6),
    ),
    Achievement(
        "demon_census", "Demon Census", "Kill 200 demons lifetime",
        lambda e, d, life, run: e == ev.ENEMY_KILLED and life["kills"] >= 200,
        progress=lambda life, run: (life["kills"], 200),
    ),
]
