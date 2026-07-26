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
    GinRummy, all_melds, apply_layoffs, best_deadwood, deadwood, deadwood_value)
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


def test_layoffs_run_extension():
    knocker_run = [Card(6, "H"), Card(7, "H"), Card(8, "H")]
    loose = [Card(9, "H"), Card(2, "C")]
    laid_off, remaining = apply_layoffs(loose, [knocker_run])
    assert laid_off == [Card(9, "H")]
    assert remaining == deadwood_value(2)
    print("layoff run extension OK")


def test_layoffs_set_fourth():
    knocker_set = [Card(7, "S"), Card(7, "H"), Card(7, "D")]
    loose = [Card(7, "C"), Card(5, "S")]
    laid_off, remaining = apply_layoffs(loose, [knocker_set])
    assert laid_off == [Card(7, "C")]
    assert remaining == deadwood_value(5)
    print("layoff set 4th-card OK")


def test_layoffs_chained_extension():
    knocker_run = [Card(6, "H"), Card(7, "H"), Card(8, "H")]
    # neither card alone is adjacent to the run's far end order-independent —
    # the fixpoint loop must chain 9H then 10H (or vice versa) to place both.
    loose = [Card(10, "H"), Card(9, "H")]
    laid_off, remaining = apply_layoffs(loose, [knocker_run])
    assert set(laid_off) == {Card(9, "H"), Card(10, "H")}
    assert remaining == 0
    print("layoff chained extension OK")


def test_no_layoff_on_gin():
    m = GinRummy(target=100)
    m.hands["P1"] = [Card(3, "H"), Card(4, "H"), Card(5, "H"), Card(6, "H"),
                     Card(7, "S"), Card(7, "H"), Card(7, "D"),
                     Card(9, "C"), Card(10, "C"), Card(11, "C")]
    # 7C would complete P1's 7-set if laid off — must NOT happen on a gin knock
    m.hands["P2"] = [Card(7, "C"), Card(2, "D"), Card(9, "D"), Card(13, "D"),
                     Card(4, "S"), Card(11, "S"), Card(1, "H"), Card(8, "H"),
                     Card(12, "H"), Card(6, "D")]
    raw_o_dead = deadwood(m.hands["P2"])
    assert raw_o_dead == 67
    m._end_hand("P1")
    assert m.result["gin"] is True
    assert m.result["layoffs"] == []
    assert m.result["deadwood"]["P2"] == raw_o_dead
    assert m.scores["P1"] == raw_o_dead + 25
    print("no layoff on gin OK")


def test_undercut_from_layoff():
    m = GinRummy(target=100)
    # P1 (knocker): a set + two 3-card runs, one loose king -> deadwood 10
    # (a loose ace would have joined the club run into a gin hand instead).
    m.hands["P1"] = [Card(8, "H"), Card(8, "D"), Card(8, "S"),
                     Card(2, "C"), Card(3, "C"), Card(4, "C"),
                     Card(10, "D"), Card(11, "D"), Card(12, "D"),
                     Card(13, "S")]
    # P2 (defender): a fully-melded 7 cards + exactly the 3 cards that lay
    # off onto P1's melds (5C extends the club run, 13D extends the diamond
    # run, 8C completes the 8s) — raw deadwood is high, post-layoff is 0.
    m.hands["P2"] = [Card(2, "H"), Card(3, "H"), Card(4, "H"), Card(5, "H"),
                     Card(9, "S"), Card(10, "S"), Card(11, "S"),
                     Card(5, "C"), Card(8, "C"), Card(13, "D")]
    raw_o_dead = deadwood(m.hands["P2"])
    assert raw_o_dead == deadwood_value(5) + deadwood_value(8) + deadwood_value(13)
    m._end_hand("P1")
    assert set(m.result["layoffs"]) == {Card(5, "C"), Card(8, "C"), Card(13, "D")}
    assert m.result["deadwood"]["P2"] == 0
    # without the layoff P1 would win (23 > 10); the layoff flips it to an
    # undercut in P2's favor — this is the case the rule exists for.
    assert m.result["winner"] == "P2"
    assert m.result["points"] == 35             # (10 - 0) + UNDERCUT_BONUS(25)
    assert m.scores["P2"] == 35
    print("undercut created only by a layoff OK")


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


def test_rummy_tween_wiring():
    import games.rummy.game as rgame

    run = rgame.create_run("gin", random.Random(4))
    section = {"achievements": {}, "lifetime": {}, "unlocked_skins": []}
    run.attach_profile(section, {}, lambda: None)
    assert run.model.turn == "P1" and run.model.phase == "draw"

    # a human stock draw queues exactly one flight, landing in the hand fan
    sx, sy, sw, sh = run._stock_rect()
    run._click(sx + sw / 2, sy + sh / 2)
    assert run.model.phase == "discard"
    assert len(run.tweens) == 1
    drawn = run.model.hands["P1"][-1]
    key = (drawn.rank, drawn.suit)
    to_xy = run.tweens._live[key][1]
    landing = next((x for c, x, _ in run._human_layout() if c == drawn), None)
    assert landing is not None and to_xy == (landing, run._hand_y())

    # discarding that same card queues a flight into the discard pile
    run.tweens = rgame.table.Tweens()
    run._hand_layout = run._human_layout()      # normally refreshed by draw_hud
    card, x, _ = run._hand_layout[0]
    run._click(x + rgame.CARD_W / 2, run._hand_y() + rgame.CARD_H / 2)
    assert len(run.tweens) == 1
    dx, dy = run._discard_rect()[:2]
    assert run.tweens._live[(card.rank, card.suit)][1] == (dx, dy)

    # low-motion setting is a hard no-op
    run.settings["particles"] = "low"
    run.tweens = rgame.table.Tweens()
    if run.model.turn == "P1" and run.model.phase == "draw":
        sx, sy, sw, sh = run._stock_rect()
        run._click(sx + sw / 2, sy + sh / 2)
        assert len(run.tweens) == 0
    print("rummy tween wiring OK (draw + discard flights, low-motion no-op)")


def test_rummy_stats_rows():
    import games.rummy as rummy
    from arcade.game_api import resolve_stats_rows
    life = {"rm_hands": 40, "rm_hand_wins": 18, "rm_gins": 5,
            "rm_undercuts": 2, "rm_game_wins": 3, "rm_best_streak": 6}
    got = dict(resolve_stats_rows(rummy.STATS_ROWS, life))
    assert got["Hands played"] == "40" and got["Hands won"] == "18"
    assert got["Gins"] == "5" and got["Games won"] == "3"
    # zero-state: fresh lifetime resolves without KeyError
    zero = dict(resolve_stats_rows(rummy.STATS_ROWS, {}))
    assert zero["Hands played"] == "0"
    print("rummy stats rows OK (resolver + zero-state)")


def main():
    test_meld_engine()
    test_scoring()
    test_layoffs_run_extension()
    test_layoffs_set_fourth()
    test_layoffs_chained_extension()
    test_no_layoff_on_gin()
    test_undercut_from_layoff()
    test_ai_game()
    test_rummy_achievements()
    test_rummy_wiring()
    test_rummy_tween_wiring()
    test_rummy_stats_rows()
    print("ALL RUMMY TESTS PASSED")


if __name__ == "__main__":
    main()
