"""Video Poker achievements — the same event/grind-counter pattern as
Solitaire and Rummy, evaluated by the shared AchievementEngine against the
events the run emits ("vp_win") plus the grind counters kept in the poker
profile section's lifetime dict (vp_hands / vp_paid / vp_full_houses /
vp_best_credits). Ids are namespaced so they can never collide with the
other tabletop games' skin-gate ids.
"""
from meta.achievements import Achievement


def _progress(key, target):
    return lambda life, run: (min(life.get(key, 0), target), target)


ACHIEVEMENTS = [
    Achievement(
        "first_paid", "Paid Out", "Win your first paying hand",
        lambda e, d, life, run: e == "vp_win"),
    Achievement(
        "natural_royal", "Natural Royal", "Hit a royal flush",
        lambda e, d, life, run: e == "vp_win" and d.get("rank_key") == "royal_flush"),
    Achievement(
        "quads", "Quads", "Hit four of a kind",
        lambda e, d, life, run: e == "vp_win" and d.get("rank_key") == "four_kind"),
    Achievement(
        "full_houses_10", "House Rules", "Hit 10 full houses",
        lambda e, d, life, run: life.get("vp_full_houses", 0) >= 10,
        progress=_progress("vp_full_houses", 10)),
    Achievement(
        "vp_hands_500", "Grinder", "Play 500 hands of Video Poker",
        lambda e, d, life, run: life.get("vp_hands", 0) >= 500,
        progress=_progress("vp_hands", 500)),
    Achievement(
        "high_roller", "High Roller", "Reach 1,000 credits",
        lambda e, d, life, run: life.get("vp_best_credits", 0) >= 1000,
        progress=_progress("vp_best_credits", 1000)),
]
