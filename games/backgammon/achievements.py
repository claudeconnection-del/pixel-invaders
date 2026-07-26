"""Backgammon achievements — the same event/grind-counter pattern as the
other tabletop games, evaluated by the shared AchievementEngine against the
events the run emits ("bg_win") plus the grind counters kept in the
backgammon profile section's lifetime dict (bg_games / bg_wins / bg_gammons /
bg_backgammons). Ids are namespaced so they can never collide with the other
tabletop games' skin-gate ids. `pip_race` reads a live per-run stat
(`max_pip_deficit`, tracked in games/backgammon/game.py) rather than a
lifetime counter.
"""
from meta.achievements import Achievement


def _progress(key, target):
    return lambda life, run: (min(life.get(key, 0), target), target)


PIP_RACE_DEFICIT = 30

ACHIEVEMENTS = [
    Achievement(
        "bg_first_win", "First Win", "Win your first game of Backgammon",
        lambda e, d, life, run: e == "bg_win"),
    Achievement(
        "gammon", "Gammon!", "Win a gammon",
        lambda e, d, life, run: e == "bg_win" and d.get("grade") == "gammon"),
    Achievement(
        "backgammon_win", "Backgammon!", "Win a backgammon",
        lambda e, d, life, run: e == "bg_win" and d.get("grade") == "backgammon"),
    Achievement(
        "pip_race", "Great Comeback",
        f"Win a game after trailing by {PIP_RACE_DEFICIT}+ pips at some point",
        lambda e, d, life, run: (e == "bg_win"
                                 and run.get("max_pip_deficit", 0) >= PIP_RACE_DEFICIT)),
    Achievement(
        "bg_games_100", "Backgammon Regular", "Play 100 games of Backgammon",
        lambda e, d, life, run: life.get("bg_games", 0) >= 100,
        progress=_progress("bg_games", 100)),
    Achievement(
        "bg_wins_50", "Backgammon Master", "Win 50 games of Backgammon",
        lambda e, d, life, run: life.get("bg_wins", 0) >= 50,
        progress=_progress("bg_wins", 50)),
]
