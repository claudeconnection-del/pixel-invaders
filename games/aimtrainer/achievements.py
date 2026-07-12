"""Voxel Aim's achievements."""
from game import events as ev
from meta.achievements import Achievement


def _summary(etype, data):
    return data["summary"] if etype == ev.RUN_END else None


ACHIEVEMENTS = [
    Achievement(
        "first_pop", "First Pop", "Hit your first target",
        lambda e, d, life, run: e == ev.ENEMY_KILLED,
    ),
    Achievement(
        "half_century", "Half Century", "Hit 50 targets in one run",
        lambda e, d, life, run: run["hits"] >= 50,
        progress=lambda life, run: (run.get("hits", 0), 50),
    ),
    Achievement(
        "laser_focus", "Laser Focus", "Finish with 90%+ accuracy (min 40 shots)",
        lambda e, d, life, run: (s := _summary(e, d)) is not None
        and s["shots"] >= 40 and s["accuracy"] >= 0.9,
    ),
    Achievement(
        "quick_draw", "Quick Draw", "Pop a target within 0.35s of it spawning",
        lambda e, d, life, run: e == ev.ENEMY_KILLED
        and d.get("reaction", 99) <= 0.35,
    ),
    Achievement(
        "combo_lock", "Combo Lock", "Hold the x3.0 multiplier",
        lambda e, d, life, run: run["max_multiplier"] >= 3.0,
    ),
    Achievement(
        "ten_thousand", "Ten Thousand Club", "Pop 1,000 targets lifetime",
        lambda e, d, life, run: e == ev.ENEMY_KILLED and life["kills"] >= 1000,
        progress=lambda life, run: (life["kills"], 1000),
    ),
]
