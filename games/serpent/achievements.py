"""Voxel Serpent's achievements."""
from game import events as ev
from meta.achievements import Achievement

ACHIEVEMENTS = [
    Achievement(
        "first_bite", "First Bite", "Eat your first fruit",
        lambda e, d, life, run: e == ev.FRUIT_EATEN,
    ),
    Achievement(
        "well_fed", "Well Fed", "Reach length 15 in one run",
        lambda e, d, life, run: run["length"] >= 15,
        progress=lambda life, run: (run.get("length", 3), 15),
    ),
    Achievement(
        "anaconda", "Anaconda", "Reach length 30 in one run",
        lambda e, d, life, run: run["length"] >= 30,
        progress=lambda life, run: (run.get("length", 3), 30),
    ),
    Achievement(
        "gold_rush", "Gold Rush", "Eat 3 gold fruit in one run",
        lambda e, d, life, run: run.get("golds", 0) >= 3,
        progress=lambda life, run: (run.get("golds", 0), 3),
    ),
    Achievement(
        "survivor", "Survivor", "Stay alive for 2 minutes in one run",
        lambda e, d, life, run: run["duration"] >= 120,
    ),
    Achievement(
        "orchard", "Orchard Raider", "Eat 250 fruit lifetime",
        lambda e, d, life, run: e == ev.FRUIT_EATEN and life["powerups"] >= 250,
        progress=lambda life, run: (life["powerups"], 250),
    ),
]
