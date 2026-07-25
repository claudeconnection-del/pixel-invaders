"""Gin Rummy achievements — the same event/grind-counter pattern as Solitaire
(games/solitaire/achievements.py), evaluated by the shared AchievementEngine
against the events the run emits ("rm_win" / "rm_game") plus the grind
counters kept in the rummy profile section's lifetime dict (rm_hands /
rm_hand_wins / rm_gins / rm_undercuts / rm_game_wins / rm_streak /
rm_best_streak). Ids are namespaced so they can never collide with
Solitaire's skin-gate ids (first_win / streak_3 / century / founder /
millennium are taken — a colliding id would wrongly unlock Solitaire-gated
skins via the shared sync step).
"""
from meta.achievements import Achievement


def _progress(key, target):
    return lambda life, run: (min(life.get(key, 0), target), target)


ACHIEVEMENTS = [
    Achievement(
        "first_hand", "First Hand", "Win your first hand of Gin Rummy",
        lambda e, d, life, run: e == "rm_win"),
    Achievement(
        "first_gin", "Gin!", "Win a hand by going gin",
        lambda e, d, life, run: e == "rm_win" and d.get("gin")),
    Achievement(
        "undercut", "Undercut", "Win as the defender after the house knocks",
        lambda e, d, life, run: e == "rm_win" and d.get("undercut")),
    Achievement(
        "game_win", "Game, Set", "Win a full game to 100",
        lambda e, d, life, run: e == "rm_game" and d.get("win")),
    Achievement(
        "hot_streak", "Hot Streak", "Win five hands in a row",
        lambda e, d, life, run: life.get("rm_streak", 0) >= 5,
        progress=_progress("rm_streak", 5)),
    Achievement(
        "hand_century", "Card Sharp", "Play 100 hands of Gin Rummy",
        lambda e, d, life, run: life.get("rm_hands", 0) >= 100,
        progress=_progress("rm_hands", 100)),
    Achievement(
        "shark", "Shark", "Win 250 hands of Gin Rummy",
        lambda e, d, life, run: life.get("rm_hand_wins", 0) >= 250,
        progress=_progress("rm_hand_wins", 250)),
]
