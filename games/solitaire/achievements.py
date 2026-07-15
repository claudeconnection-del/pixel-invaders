"""Solitaire achievements — including the long-haul grind milestones. Evaluated
by the shared AchievementEngine against the events the run emits ("sol_win")
plus the grind counters the game keeps in its profile section's lifetime dict
(sol_games / sol_wins / sol_streak). Progress-bar achievements are checked every
frame; event ones fire on the win.
"""
from meta.achievements import Achievement


def _progress(key, target):
    return lambda life, run: (min(life.get(key, 0), target), target)


ACHIEVEMENTS = [
    Achievement(
        "first_win", "First Win", "Win your first game of Solitaire",
        lambda e, d, life, run: e == "sol_win"),
    Achievement(
        "speed_run", "Quick Deal", "Win a game in under three minutes",
        lambda e, d, life, run: e == "sol_win" and run.get("time", 1e9) <= 180),
    Achievement(
        "no_undo", "Clean Hands", "Win a game without using undo",
        lambda e, d, life, run: e == "sol_win" and run.get("undos", 1) == 0),
    Achievement(
        "streak_3", "On a Roll", "Win three games in a row",
        lambda e, d, life, run: e == "sol_win" and life.get("sol_streak", 0) >= 3,
        progress=lambda life, run: (min(life.get("sol_streak", 0), 3), 3)),
    Achievement(
        "century", "Century", "Play 100 games of Solitaire",
        lambda e, d, life, run: life.get("sol_games", 0) >= 100,
        progress=_progress("sol_games", 100)),
    Achievement(
        "millennium", "Millennium", "Play 1,000 games of Solitaire",
        lambda e, d, life, run: life.get("sol_games", 0) >= 1000,
        progress=_progress("sol_games", 1000)),
    Achievement(
        "founder", "Foundation Founder", "Win 250 games of Solitaire",
        lambda e, d, life, run: life.get("sol_wins", 0) >= 250,
        progress=_progress("sol_wins", 250)),
]
