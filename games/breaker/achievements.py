"""Voxel Breaker's achievements."""
from game import events as ev
from meta.achievements import Achievement


def _summary(etype, data):
    return data["summary"] if etype == ev.RUN_END else None


ACHIEVEMENTS = [
    Achievement(
        "first_crack", "First Crack", "Break your first brick",
        lambda e, d, life, run: e == ev.ENEMY_KILLED,
    ),
    Achievement(
        "demolition", "Demolition", "Clear Level 1",
        lambda e, d, life, run: e == ev.LEVEL_CLEAR and d["index"] == 0,
    ),
    Achievement(
        "wrecking_crew", "Wrecking Crew", "Clear Level 5",
        lambda e, d, life, run: e == ev.LEVEL_CLEAR and d["index"] == 4,
    ),
    Achievement(
        "perfect_clear", "Perfect Clear", "Clear a level without losing a ball",
        lambda e, d, life, run: e == ev.LEVEL_CLEAR and d["perfect"],
    ),
    Achievement(
        "combo_artist", "Combo Artist", "Hit a x3.0 combo",
        lambda e, d, life, run: run["max_multiplier"] >= 3.0,
    ),
    Achievement(
        "juggler", "Juggler", "Keep 5 balls in play at once",
        lambda e, d, life, run: run.get("max_balls", 1) >= 5,
    ),
    Achievement(
        "brick_layer", "Brick by Brick", "Break 500 bricks lifetime",
        lambda e, d, life, run: e == ev.ENEMY_KILLED and life["kills"] >= 500,
        progress=lambda life, run: (life["kills"], 500),
    ),
    Achievement(
        "overtime", "Overtime", "Play Breaker for 30 minutes total",
        lambda e, d, life, run: life["playtime"] >= 1800,
        progress=lambda life, run: (int(life["playtime"]), 1800),
    ),
]
