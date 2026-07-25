"""Headless Gin Rummy tests: the meld engine (best_deadwood), scoring, and an
AI-vs-AI game driven to completion. No pygame, no GL.

Run: python tools/test_rummy.py
"""
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from games.cards.deck import Card  # noqa: E402
from games.rummy.model import (  # noqa: E402
    GinRummy, all_melds, best_deadwood, deadwood)
from games.rummy.ai import ai_turn  # noqa: E402


def test_meld_engine():
    # a gin hand: two runs + a set cover all ten -> zero deadwood
    gin = [Card(3, "H"), Card(4, "H"), Card(5, "H"), Card(6, "H"),
           Card(7, "S"), Card(7, "H"), Card(7, "D"),
           Card(9, "C"), Card(10, "C"), Card(11, "C")]
    assert deadwood(gin) == 0

    # a run + a set + four loose cards
    hand = [Card(3, "H"), Card(4, "H"), Card(5, "H"),
            Card(7, "S"), Card(7, "H"), Card(7, "D"),
            Card(13, "C"), Card(12, "S"), Card(2, "C"), Card(9, "D")]
    d, melds = best_deadwood(hand)
    assert d == 10 + 10 + 2 + 9 and len(melds) == 2

    # a shared card can't be in two melds — deadwood is the same either way
    overlap = [Card(6, "H"), Card(7, "H"), Card(8, "H"), Card(7, "S"), Card(7, "D")]
    assert best_deadwood(overlap)[0] == 6 + 8   # keep 3 in a meld, 2 loose
    assert any(len(m) >= 3 for m in all_melds(overlap))
    print("meld engine OK")


def test_scoring():
    m = GinRummy(target=100)
    # knocker has gin (0), opponent holds 18 of deadwood -> 18 + 25 bonus
    m.hands["P1"] = [Card(3, "H"), Card(4, "H"), Card(5, "H"), Card(6, "H"),
                     Card(7, "S"), Card(7, "H"), Card(7, "D"),
                     Card(9, "C"), Card(10, "C"), Card(11, "C")]
    # two 4-runs cover eight cards; the loose King + 8 are 18 of deadwood
    m.hands["P2"] = [Card(2, "C"), Card(3, "C"), Card(4, "C"), Card(5, "C"),
                     Card(6, "S"), Card(7, "S"), Card(8, "S"), Card(9, "S"),
                     Card(13, "S"), Card(8, "H")]
    assert deadwood(m.hands["P2"]) == 10 + 8   # K(10) + 8
    m._end_hand("P1")
    assert m.result["gin"] and m.result["winner"] == "P1"
    assert m.scores["P1"] == 18 + 25
    print("scoring OK (gin + bonus)")


def _play_to_completion(seed, target=25):
    m = GinRummy(random.Random(seed), target=target)
    guard = 0
    while not m.game_over:
        while not m.hand_over:
            ai_turn(m)
            guard += 1
            assert guard < 20000, "game did not progress"
            assert all(len(m.hands[p]) == 10 for p in ("P1", "P2"))
        if not m.game_over:
            m.deal(first="P1")
    return m


def test_ai_game():
    m = _play_to_completion(7)
    assert m.game_over and max(m.scores.values()) >= m.target
    # deterministic
    m2 = _play_to_completion(7)
    assert m.scores == m2.scores
    print(f"AI game OK (final {m.scores}, deterministic)")


def test_rummy_achievements():
    from games.rummy.achievements import ACHIEVEMENTS
    by = {a.id: a for a in ACHIEVEMENTS}
    assert by["first_hand"].check("rm_win", {}, {}, {})
    assert not by["first_hand"].check("rm_lose", {}, {}, {})
    assert by["first_gin"].check("rm_win", {"gin": True}, {}, {})
    assert not by["first_gin"].check("rm_win", {"gin": False}, {}, {})
    assert by["undercut"].check("rm_win", {"undercut": True}, {}, {})
    assert not by["undercut"].check("rm_win", {"undercut": False}, {}, {})
    assert by["game_win"].check("rm_game", {"win": True}, {}, {})
    assert not by["game_win"].check("rm_game", {"win": False}, {}, {})
    # grind milestones fire from counters alone (progress-checked every frame)
    assert by["hot_streak"].check(None, None, {"rm_streak": 5}, {})
    assert not by["hot_streak"].check(None, None, {"rm_streak": 4}, {})
    assert by["hand_century"].check(None, None, {"rm_hands": 100}, {})
    assert not by["hand_century"].check(None, None, {"rm_hands": 99}, {})
    assert by["shark"].check(None, None, {"rm_hand_wins": 250}, {})
    assert not by["shark"].check(None, None, {"rm_hand_wins": 249}, {})
    assert by["hot_streak"].progress({"rm_streak": 2}, {}) == (2, 5)
    assert by["hand_century"].progress({"rm_hands": 40}, {}) == (40, 100)
    assert by["shark"].progress({"rm_hand_wins": 5000}, {}) == (250, 250)
    # ids must not collide with solitaire's skin-gate ids
    from games.solitaire.achievements import ACHIEVEMENTS as SOL
    assert not (set(by) & {a.id for a in SOL})
    print(f"rummy achievements OK ({len(ACHIEVEMENTS)} incl. grind, no id collision)")


def test_rummy_wiring():
    import games.rummy.game as rgame
    from meta.achievements import AchievementEngine

    run = rgame.create_run("gin", random.Random(3))
    section = {"achievements": {}, "lifetime": {}, "unlocked_skins": []}
    settings = {}
    run.attach_profile(section, settings, lambda: None)
    assert section["lifetime"]["rm_hands"] == 1   # the initial deal counts

    # contrive a gin hand for P1 (the human) and end it via the model directly
    gin = [Card(3, "H"), Card(4, "H"), Card(5, "H"), Card(6, "H"),
           Card(7, "S"), Card(7, "H"), Card(7, "D"),
           Card(9, "C"), Card(10, "C"), Card(11, "C")]
    run.model.hands["P1"] = gin
    run.model.hands["P2"] = [Card(2, "C"), Card(3, "C"), Card(4, "C"), Card(5, "C"),
                             Card(6, "S"), Card(7, "S"), Card(8, "S"), Card(9, "S"),
                             Card(13, "S"), Card(8, "H")]
    run.model._end_hand("P1")
    run._announce()

    engine = AchievementEngine(section, rgame.ACHIEVEMENTS)
    unlocked = {a.id for a in engine.on_frame(run.drain_events(), run.run_stats())}
    assert {"first_hand", "first_gin"} <= unlocked
    assert section["lifetime"]["rm_hand_wins"] == 1
    assert section["lifetime"]["rm_gins"] == 1
    assert section["lifetime"]["rm_streak"] == 1

    # the shared sync mirrors the tied premium deck into settings["tabletop"]
    run.update(0.016, None)
    assert "juniper" in settings["tabletop"]["unlocked_decks"]
    print("gin rummy wiring OK (achievements + grind counters + cosmetic sync)")


def main():
    test_meld_engine()
    test_scoring()
    test_ai_game()
    test_rummy_achievements()
    test_rummy_wiring()
    print("ALL RUMMY TESTS PASSED")


if __name__ == "__main__":
    main()
